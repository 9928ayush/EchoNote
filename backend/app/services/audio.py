import json
import math
import subprocess
from pathlib import Path

from ..config import settings
from .errors import ServiceError

CHUNK_SECONDS = 30


def inspect_audio(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "format=duration:stream=codec_type",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        if not any(s["codec_type"] == "audio" for s in data["streams"]):
            raise ValueError("no audio")
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("invalid duration")
    except (subprocess.SubprocessError, KeyError, ValueError, TypeError) as exc:
        raise ServiceError(
            "This recording cannot be decoded. Upload a valid audio file.", False
        ) from exc
    if duration > settings().max_duration_seconds:
        raise ServiceError(
            f"Recording exceeds the configured {settings().max_duration_seconds // 60}-minute limit. Split it and upload again.",
            False,
        )
    return duration


def extract_chunk(source: Path, output: Path, index: int):
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-protocol_whitelist",
                "file,pipe",
                "-ss",
                str(index * CHUNK_SECONDS),
                "-i",
                str(source),
                "-t",
                str(CHUNK_SECONDS),
                "-map",
                "0:a:0",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(output),
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
    except subprocess.SubprocessError as exc:
        raise ServiceError(
            "Part of this recording could not be decoded. Upload a new audio file.", False
        ) from exc
