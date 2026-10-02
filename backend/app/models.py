import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Enum, Float, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


class Status(str, enum.Enum):
    UPLOADING = "UPLOADING"
    QUEUED = "QUEUED"
    TRANSCRIBING = "TRANSCRIBING"
    SUMMARIZING = "SUMMARIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AudioNote(Base):
    __tablename__ = "audio_notes"
    __table_args__ = (
        Index("ix_notes_created", "created_at", "id"),
        Index("ix_notes_dispatch", "status", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    upload_key: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(300))
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    language: Mapped[str] = mapped_column(String(10))
    duration: Mapped[float | None] = mapped_column(Float)
    status: Mapped[Status] = mapped_column(
        Enum(Status, native_enum=False, length=20), default=Status.UPLOADING
    )
    transcript: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    chunks: Mapped[list] = mapped_column(JSON, default=list)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(300))
    retryable: Mapped[bool] = mapped_column(default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_token: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
