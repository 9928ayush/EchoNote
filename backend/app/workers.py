import logging
import math
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from celery import Celery
from celery.signals import setup_logging
from sqlalchemy import or_, select, text, update

from .config import settings
from .db import Session, engine
from .logging_config import configure_logging
from .models import AudioNote, Status, now
from .services import audio, storage
from .services.errors import LostRun, ServiceError
from .services.providers import GnaniASR, OpenAISummary
from .services.summary import summarize_long

log = logging.getLogger(__name__)
celery = Celery("echonote", broker=settings().redis_url)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 25200},
    task_soft_time_limit=21000,
    task_time_limit=21600,
    beat_schedule={"dispatch-and-recover": {"task": "notes.dispatch", "schedule": 30.0}},
)


@setup_logging.connect
def logging_setup(**kwargs):
    configure_logging()


def checkpoint(note_id, token, **values):
    with Session.begin() as db:
        result = db.execute(
            update(AudioNote)
            .where(
                AudioNote.id == note_id,
                AudioNote.run_token == token,
                AudioNote.status.in_([Status.QUEUED, Status.TRANSCRIBING, Status.SUMMARIZING]),
            )
            .values(updated_at=now(), **values)
        )
        if result.rowcount != 1:
            raise LostRun()


def run_pipeline(note, asr=None, summary_provider=None):
    asr = asr or GnaniASR()
    summary_provider = summary_provider or OpenAISummary()
    token = note.run_token
    checkpoint(
        note.id,
        token,
        status=Status.TRANSCRIBING,
        processing_started_at=note.processing_started_at or now(),
    )
    with tempfile.TemporaryDirectory(prefix="echonote-") as directory:
        source, chunk = Path(directory) / "recording", Path(directory) / "chunk.wav"
        storage.download(note.storage_key, source)
        duration = audio.inspect_audio(source)
        count = math.ceil(duration / audio.CHUNK_SECONDS)
        checkpoint(note.id, token, duration=duration, total_chunks=count)
        chunks = list(note.chunks)
        for index in range(len(chunks), count):
            checkpoint(note.id, token)
            audio.extract_chunk(source, chunk, index)
            transcript = asr.transcribe(chunk, note.language)
            chunks.append(transcript)
            checkpoint(note.id, token, chunks=list(chunks), transcript="\n\n".join(chunks))
        transcript = "\n\n".join(chunks)
    checkpoint(note.id, token, status=Status.SUMMARIZING, transcript=transcript)
    summary = summarize_long(transcript, summary_provider, lambda: checkpoint(note.id, token))
    checkpoint(
        note.id,
        token,
        status=Status.COMPLETED,
        summary=summary,
        completed_at=now(),
        error_message=None,
        retryable=False,
    )


@celery.task(name="notes.process", bind=True)
def process(self, note_id: str, run_token: str):
    note_uuid, token = uuid.UUID(note_id), uuid.UUID(run_token)
    # A session advisory lock spans short DB transactions without holding a row lock
    # during network calls. A hash collision only serializes unrelated notes.
    lock_key = int.from_bytes(note_uuid.bytes[:8], "big", signed=True)
    with engine.connect() as lock:
        acquired = lock.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        ).scalar()
        lock.commit()
        if not acquired:
            return
        try:
            with Session() as db:
                note = db.get(AudioNote, note_uuid)
            if (
                not note
                or note.run_token != token
                or note.status not in (Status.QUEUED, Status.TRANSCRIBING, Status.SUMMARIZING)
            ):
                return
            try:
                run_pipeline(note)
            except LostRun:
                log.info("superseded_worker_stopped", extra={"audio_note_id": note_id})
            except Exception as exc:
                log.exception(
                    "processing_failed",
                    extra={"audio_note_id": note_id, "task_id": self.request.id},
                )
                message = (
                    str(exc)
                    if isinstance(exc, ServiceError)
                    else "Processing was interrupted. You can retry."
                )
                retryable = exc.retryable if isinstance(exc, ServiceError) else True
                try:
                    checkpoint(
                        note_uuid,
                        token,
                        status=Status.FAILED,
                        error_message=message,
                        retryable=retryable,
                    )
                except LostRun:
                    pass
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock.commit()


@celery.task(name="notes.dispatch")
def dispatch():
    timestamp = now()
    with Session.begin() as db:
        # A dead worker/upload is visible as FAILED rather than spinning forever.
        db.execute(
            update(AudioNote)
            .where(
                AudioNote.status.in_(
                    [Status.UPLOADING, Status.QUEUED, Status.TRANSCRIBING, Status.SUMMARIZING]
                ),
                AudioNote.updated_at < timestamp - timedelta(seconds=settings().stale_seconds),
            )
            .values(
                status=Status.FAILED,
                error_message="Work was interrupted or no worker became available. Retry processing, or upload again if the file was not saved.",
                retryable=True,
                updated_at=timestamp,
            )
        )
        notes = db.scalars(
            select(AudioNote)
            .where(
                AudioNote.status == Status.QUEUED,
                or_(
                    AudioNote.dispatched_at.is_(None),
                    AudioNote.dispatched_at < timestamp - timedelta(seconds=60),
                ),
            )
            .order_by(AudioNote.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()
        for note in notes:
            # Publish before commit: a duplicate is safe; a lost publish is repaired
            # by the next scan. PostgreSQL, not Redis, retains the work intent.
            process.apply_async(args=[str(note.id), str(note.run_token)], retry=False)
            note.dispatched_at = timestamp
