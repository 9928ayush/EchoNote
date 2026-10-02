from datetime import datetime
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import Status

Language = Literal[
    "en-IN", "hi-IN", "gu-IN", "bn-IN", "kn-IN", "ml-IN", "mr-IN", "pa-IN", "ta-IN", "te-IN"
]
TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
}


class CreateNote(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)
    language: Language = "en-IN"
    upload_key: UUID

    @field_validator("filename")
    @classmethod
    def valid_name(cls, name: str) -> str:
        name = name.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not name or any(ord(c) < 32 for c in name):
            raise ValueError("Choose a valid filename.")
        if PurePosixPath(name).suffix.lower() not in TYPES:
            raise ValueError("Supported files: WAV, MP3, OGG, FLAC, AAC and M4A.")
        return name


class NoteStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: Status
    error_message: str | None
    retryable: bool
    attempts: int
    total_chunks: int
    updated_at: datetime
    completed_chunks: int = 0


class NoteSummary(NoteStatus):
    original_filename: str
    mime_type: str
    file_size: int
    language: str
    duration: float | None
    created_at: datetime


class NoteDetail(NoteSummary):
    transcript: str | None
    summary: str | None
    processing_started_at: datetime | None
    completed_at: datetime | None


def serialize(note, schema=NoteDetail):
    result = schema.model_validate(note)
    result.completed_chunks = len(note.chunks)
    return result
