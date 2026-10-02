import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        for key in ("audio_note_id", "task_id", "error_type", "provider", "http_status"):
            if hasattr(record, key):
                data[key] = getattr(record, key)
        # Exception text may include signed URLs, secrets, or private provider bodies.
        # Record stack locations and exception type, but not exception messages/locals.
        if record.exc_info and record.exc_info[0]:
            import traceback

            data["error_type"] = record.exc_info[0].__name__
            data["stack"] = [
                {"file": f.filename, "line": f.lineno, "function": f.name}
                for f in traceback.extract_tb(record.exc_info[2])
            ]
        return json.dumps(data)


def configure_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
