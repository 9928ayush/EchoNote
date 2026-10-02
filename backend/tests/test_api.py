import uuid
from datetime import timedelta

import pytest

from app import main
from app.models import AudioNote, Status, now
from app.services.errors import ServiceError


def payload(**changes):
    return {"filename": "lecture.wav", "file_size": 4, "upload_key": str(uuid.uuid4()), **changes}


def test_create_is_idempotent_and_sanitizes_filename(client):
    body = payload(filename="../../lecture.wav")
    first = client.post("/api/audio-notes", json=body)
    second = client.post("/api/audio-notes", json=body)
    assert first.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["original_filename"] == "lecture.wav"
    assert first.json()["status"] == "UPLOADING"
    assert "storage_key" not in first.json()
    body["file_size"] = 10
    assert client.post("/api/audio-notes", json=body).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"filename": "payload.exe"},
        {"file_size": 0},
        {"language": "xx-XX"},
        {"upload_key": "bad-id"},
    ],
)
def test_validation(client, changes):
    result = client.post("/api/audio-notes", json=payload(**changes))
    assert result.status_code == 422
    assert "message" in result.json()["error"]


def test_large_upload_rejected_before_record(client):
    result = client.post(
        "/api/audio-notes", json=payload(file_size=main.settings().max_upload_bytes + 1)
    )
    assert result.status_code == 413
    assert client.get("/api/audio-notes").json()["total"] == 0


def test_stream_upload_queues_after_storage(client, monkeypatch):
    uploaded = []
    monkeypatch.setattr(
        main.storage, "upload", lambda path, key, mime: uploaded.append(path.read_bytes())
    )
    note = client.post("/api/audio-notes", json=payload()).json()
    result = client.put(f"/api/audio-notes/{note['id']}/content", content=b"test")
    assert result.status_code == 200
    assert result.json()["status"] == "QUEUED"
    assert result.json()["attempts"] == 1
    assert uploaded == [b"test"]
    assert client.put(f"/api/audio-notes/{note['id']}/content", content=b"test").status_code == 409


@pytest.mark.parametrize("data,code", [(b"too long", 413), (b"a", 400)])
def test_stream_size_is_enforced(client, data, code):
    note = client.post("/api/audio-notes", json=payload()).json()
    assert client.put(f"/api/audio-notes/{note['id']}/content", content=data).status_code == code
    result = client.get(f"/api/audio-notes/{note['id']}").json()
    assert result["status"] == "FAILED"
    assert not result["retryable"]


def test_storage_failure_visible(client, monkeypatch):
    def fail(*args):
        raise ServiceError("secret upstream details", False)

    monkeypatch.setattr(main.storage, "upload", fail)
    note = client.post("/api/audio-notes", json=payload()).json()
    response = client.put(f"/api/audio-notes/{note['id']}/content", content=b"test")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert client.get(f"/api/audio-notes/{note['id']}").json()["status"] == "FAILED"


def test_retry_fences_old_attempt(client, database):
    note = client.post("/api/audio-notes", json=payload()).json()
    with database.begin() as db:
        row = db.get(AudioNote, uuid.UUID(note["id"]))
        row.status, row.retryable, row.attempts = Status.FAILED, True, 1
        row.chunks = ["retained"]
        old = row.run_token
    result = client.post(f"/api/audio-notes/{note['id']}/retry")
    assert result.status_code == 200
    assert result.json()["status"] == "QUEUED"
    assert client.post(f"/api/audio-notes/{note['id']}/retry").status_code == 409
    with database() as db:
        row = db.get(AudioNote, uuid.UUID(note["id"]))
        assert row.run_token != old
        assert row.chunks == ["retained"]


def test_stale_read_recovers_without_beat(client, database):
    note = client.post("/api/audio-notes", json=payload()).json()
    with database.begin() as db:
        row = db.get(AudioNote, uuid.UUID(note["id"]))
        row.updated_at = now() - timedelta(hours=1)
    assert client.get(f"/api/audio-notes/{note['id']}/status").json()["status"] == "FAILED"
    assert client.post(f"/api/audio-notes/{note['id']}/retry").status_code == 409


def test_missing_note_and_pagination_validation(client):
    assert client.get(f"/api/audio-notes/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/audio-notes?page=0").status_code == 422
    assert client.get("/api/audio-notes?page=abc").status_code == 422
