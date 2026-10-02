import uuid
from unittest.mock import Mock

import pytest
from sqlalchemy import select

from app import workers
from app.models import AudioNote, Status
from app.services.errors import LostRun, ServiceError


@pytest.fixture
def note(database):
    with database.begin() as db:
        row = AudioNote(
            upload_key=uuid.uuid4(),
            original_filename="test.wav",
            storage_key="audio/test.wav",
            mime_type="audio/wav",
            file_size=1,
            language="en-IN",
            status=Status.QUEUED,
            attempts=1,
        )
        db.add(row)
    return row


def test_pipeline_checkpoints_and_completes(database, note, monkeypatch):
    monkeypatch.setattr(workers.storage, "download", lambda *args: None)
    monkeypatch.setattr(workers.audio, "inspect_audio", lambda *args: 65)
    monkeypatch.setattr(workers.audio, "extract_chunk", lambda *args: None)
    asr = Mock()
    asr.transcribe.side_effect = ["one", "two", "three"]
    summary = Mock()
    summary.summarize.return_value = "A summary."
    workers.run_pipeline(note, asr, summary)
    with database() as db:
        row = db.get(AudioNote, note.id)
        assert row.status == Status.COMPLETED
        assert row.chunks == ["one", "two", "three"]
        assert row.transcript == "one\n\ntwo\n\nthree"
        assert row.summary == "A summary."
        assert row.completed_at is not None


def test_resumes_saved_chunks(database, note, monkeypatch):
    with database.begin() as db:
        row = db.get(AudioNote, note.id)
        row.chunks = ["saved"]
    with database() as db:
        note = db.get(AudioNote, note.id)
    monkeypatch.setattr(workers.storage, "download", lambda *args: None)
    monkeypatch.setattr(workers.audio, "inspect_audio", lambda *args: 35)
    monkeypatch.setattr(workers.audio, "extract_chunk", lambda *args: None)
    asr, summary = Mock(), Mock()
    asr.transcribe.return_value = "new"
    summary.summarize.return_value = "Summary"
    workers.run_pipeline(note, asr, summary)
    assert asr.transcribe.call_count == 1
    with database() as db:
        assert db.get(AudioNote, note.id).chunks == ["saved", "new"]


def test_old_token_cannot_write(database, note):
    with database.begin() as db:
        db.get(AudioNote, note.id).run_token = uuid.uuid4()
    with pytest.raises(LostRun):
        workers.checkpoint(note.id, note.run_token, summary="stale")


def test_completed_note_cannot_be_overwritten(database, note):
    with database.begin() as db:
        db.get(AudioNote, note.id).status = Status.COMPLETED
    with pytest.raises(LostRun):
        workers.checkpoint(note.id, note.run_token, status=Status.FAILED)


def test_worker_failure_is_visible(database, note, monkeypatch):
    def fail(*args):
        raise ServiceError("Transcription timed out. You can retry.")

    monkeypatch.setattr(workers, "run_pipeline", fail)
    workers.process.run(str(note.id), str(note.run_token))
    with database() as db:
        row = db.get(AudioNote, note.id)
        assert row.status == Status.FAILED
        assert row.retryable
        assert "timed out" in row.error_message


def test_dispatch_keeps_intent_if_broker_fails(database, note, monkeypatch):
    monkeypatch.setattr(workers.process, "apply_async", Mock(side_effect=ConnectionError()))
    with pytest.raises(ConnectionError):
        workers.dispatch.run()
    with database() as db:
        row = db.scalar(select(AudioNote))
        assert row.status == Status.QUEUED
        assert row.dispatched_at is None
