from collections.abc import Callable

from .errors import ServiceError
from .providers import SummaryProvider

# UTF-8 bytes are a conservative token upper bound for the configured OpenAI model.
# This also handles Hindi and unbroken text without assuming English word lengths.
INPUT_BYTES = 12000


def split_text(text: str, budget: int = INPUT_BYTES) -> list[str]:
    parts, current, size = [], [], 0
    for char in text:
        char_size = len(char.encode("utf-8"))
        if size + char_size > budget:
            parts.append("".join(current))
            current, size = [], 0
        current.append(char)
        size += char_size
    if current:
        parts.append("".join(current))
    return parts


def summarize_long(text: str, provider: SummaryProvider, heartbeat: Callable[[], None]) -> str:
    if not text.strip():
        raise ServiceError("No speech was detected in this recording.", False)
    current = text
    for _ in range(8):
        chunks = split_text(current)
        summaries = []
        for chunk in chunks:
            heartbeat()
            summaries.append(provider.summarize(chunk))
            heartbeat()
        if len(chunks) == 1:
            return summaries[0]
        reduced = "\n\n".join(summaries)
        if len(reduced.encode("utf-8")) >= len(current.encode("utf-8")):
            raise ServiceError("The summary could not be condensed safely. You can retry.")
        current = reduced
    raise ServiceError("The transcript needs too many summary passes. Split this recording.", False)
