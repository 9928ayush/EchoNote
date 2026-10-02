import logging
import tempfile
import time
import uuid
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session as DBSession
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from .config import settings
from .db import Session, engine, get_session
from .logging_config import configure_logging
from .models import AudioNote, Status, now
from .schemas import TYPES, CreateNote, NoteDetail, NoteStatus, NoteSummary, serialize
from .services import storage
from .services.errors import ServiceError

configure_logging()
log = logging.getLogger(__name__)
app = FastAPI(title="EchoNote", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({"error": {"message": str(exc.detail)}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse(
        {"error": {"message": "Check the filename, language, file size and request parameters."}},
        status_code=422,
    )


@app.exception_handler(Exception)
async def internal_error(request, exc):
    log.error("request_failed", exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(
        {"error": {"message": "The service is unavailable. Please try again."}}, status_code=503
    )


def get_note(db, note_id):
    note = db.get(AudioNote, note_id)
    if note is None:
        raise HTTPException(404, "Audio note not found.")
    return note


def recover_stale(db):
    # Read-time recovery also works if the scheduler is unavailable.
    db.execute(
        update(AudioNote)
        .where(
            AudioNote.status.in_(
                [Status.UPLOADING, Status.QUEUED, Status.TRANSCRIBING, Status.SUMMARIZING]
            ),
            AudioNote.updated_at < now() - timedelta(seconds=settings().stale_seconds),
        )
        .values(
            status=Status.FAILED,
            error_message="Work was interrupted. Retry processing, or upload again if the file was not saved.",
            retryable=True,
            updated_at=now(),
        )
    )
    db.commit()


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: DBSession = Depends(get_session)):
    db.execute(select(AudioNote.id).limit(1))
    return {"status": "ok"}


@app.get("/api/config")
def config():
    s = settings()
    return {
        "max_upload_bytes": s.max_upload_bytes,
        "max_duration_seconds": s.max_duration_seconds,
        "max_attempts": s.max_attempts,
        "repository_url": s.repository_url,
    }


@app.post("/api/audio-notes", status_code=201, response_model=NoteDetail)
def create_note(body: CreateNote, db: DBSession = Depends(get_session)):
    if body.file_size > settings().max_upload_bytes:
        raise HTTPException(413, "This recording exceeds the configured upload limit.")
    existing = db.scalar(select(AudioNote).where(AudioNote.upload_key == body.upload_key))
    if existing:
        if (existing.original_filename, existing.file_size, existing.language) != (
            body.filename,
            body.file_size,
            body.language,
        ):
            raise HTTPException(409, "This upload key was already used for a different file.")
        return serialize(existing)
    note_id = uuid.uuid4()
    suffix = Path(body.filename).suffix.lower()
    note = AudioNote(
        id=note_id,
        upload_key=body.upload_key,
        original_filename=body.filename,
        storage_key=f"audio/{note_id}{suffix}",
        mime_type=TYPES[suffix],
        file_size=body.file_size,
        language=body.language,
    )
    db.add(note)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(AudioNote).where(AudioNote.upload_key == body.upload_key))
        if existing is None:
            raise
        if (existing.original_filename, existing.file_size, existing.language) != (
            body.filename,
            body.file_size,
            body.language,
        ):
            raise HTTPException(409, "This upload key was already used for a different file.")
        return serialize(existing)
    return serialize(note)


@app.put("/api/audio-notes/{note_id}/content", response_model=NoteDetail)
async def upload_note(note_id: uuid.UUID, request: Request):
    # Raw-body streaming avoids multipart parsers buffering oversized files.
    # One per-note lock prevents overlapping uploads from replacing stored audio.
    lock_key = int.from_bytes(note_id.bytes[:8], "big", signed=True)
    with engine.connect() as lock:
        acquired = lock.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        ).scalar()
        lock.commit()
        if not acquired:
            raise HTTPException(409, "This recording is already being uploaded or processed.")
        try:
            with Session() as db:
                note = get_note(db, note_id)
                if note.status != Status.UPLOADING:
                    raise HTTPException(
                        409, "This upload is no longer open. Create a new audio note."
                    )
            token = note.run_token
            size, last_heartbeat = 0, time.monotonic()
            with tempfile.TemporaryDirectory(prefix="echonote-upload-") as directory:
                path = Path(directory) / "audio"
                with path.open("wb") as file:
                    async for block in request.stream():
                        size += len(block)
                        if size > note.file_size or size > settings().max_upload_bytes:
                            raise HTTPException(
                                413, "The uploaded file is larger than the declared limit."
                            )
                        await run_in_threadpool(file.write, block)
                        if time.monotonic() - last_heartbeat >= 5:
                            with Session.begin() as db:
                                db.execute(
                                    update(AudioNote)
                                    .where(
                                        AudioNote.id == note_id,
                                        AudioNote.status == Status.UPLOADING,
                                    )
                                    .values(updated_at=now())
                                )
                            last_heartbeat = time.monotonic()
                if size != note.file_size:
                    raise HTTPException(
                        400, "The upload was incomplete. Please upload the file again."
                    )
                await run_in_threadpool(storage.upload, path, note.storage_key, note.mime_type)
            with Session.begin() as db:
                result = db.execute(
                    update(AudioNote)
                    .where(
                        AudioNote.id == note_id,
                        AudioNote.run_token == token,
                        AudioNote.status == Status.UPLOADING,
                    )
                    .values(status=Status.QUEUED, attempts=1, updated_at=now())
                )
                if result.rowcount != 1:
                    raise HTTPException(409, "The upload expired. Upload the file again.")
            with Session() as db:
                return serialize(get_note(db, note_id))
        except (ClientDisconnect, ServiceError, HTTPException, SQLAlchemyError) as exc:
            with Session.begin() as db:
                db.execute(
                    update(AudioNote)
                    .where(AudioNote.id == note_id, AudioNote.status == Status.UPLOADING)
                    .values(
                        status=Status.FAILED,
                        updated_at=now(),
                        retryable=False,
                        error_message="The upload did not finish. Please upload the recording again.",
                    )
                )
            if isinstance(exc, HTTPException):
                raise
            log.exception("upload_failed", extra={"audio_note_id": str(note_id)})
            raise HTTPException(
                503, "The upload did not finish. Please upload the recording again."
            ) from exc
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            lock.commit()


@app.get("/api/audio-notes")
def list_notes(page: int = 1, db: DBSession = Depends(get_session)):
    if page < 1 or page > 10000:
        raise HTTPException(422, "Page must be between 1 and 10000.")
    recover_stale(db)
    total = db.scalar(select(func.count()).select_from(AudioNote))
    notes = db.scalars(
        select(AudioNote)
        .order_by(AudioNote.created_at.desc(), AudioNote.id.desc())
        .offset((page - 1) * 20)
        .limit(20)
    ).all()
    return {
        "items": [serialize(note, NoteSummary) for note in notes],
        "total": total,
        "page": page,
        "page_size": 20,
    }


@app.get("/api/audio-notes/{note_id}", response_model=NoteDetail)
def read_note(note_id: uuid.UUID, db: DBSession = Depends(get_session)):
    recover_stale(db)
    return serialize(get_note(db, note_id))


@app.get("/api/audio-notes/{note_id}/status", response_model=NoteStatus)
def status_note(note_id: uuid.UUID, db: DBSession = Depends(get_session)):
    recover_stale(db)
    return serialize(get_note(db, note_id), NoteStatus)


@app.get("/api/audio-notes/{note_id}/playback")
def playback(note_id: uuid.UUID, db: DBSession = Depends(get_session)):
    note = get_note(db, note_id)
    if note.attempts == 0:
        raise HTTPException(409, "This recording was not fully uploaded.")
    return {"url": storage.playback(note.storage_key), "expires_in": 3600}


@app.post("/api/audio-notes/{note_id}/retry", response_model=NoteDetail)
def retry_note(note_id: uuid.UUID, db: DBSession = Depends(get_session)):
    note = db.scalar(select(AudioNote).where(AudioNote.id == note_id).with_for_update())
    if note is None:
        raise HTTPException(404, "Audio note not found.")
    if (
        note.status != Status.FAILED
        or not note.retryable
        or note.attempts == 0
        or note.attempts >= settings().max_attempts
    ):
        raise HTTPException(
            409,
            "This note cannot be retried. Upload a new recording, or ask the workspace owner to check the service.",
        )
    note.run_token = uuid.uuid4()
    note.status, note.error_message, note.retryable = Status.QUEUED, None, False
    note.attempts += 1
    note.updated_at, note.dispatched_at = now(), None
    db.commit()
    return serialize(note)
