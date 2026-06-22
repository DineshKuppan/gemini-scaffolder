import logging
import json
from datetime import datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    def __init__(self, service_name: str = "app") -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        # Prefer service name from the LogRecord extras, then logger name, then formatter default
        record_service = getattr(record, "service", None) or getattr(record, "name", None) or self.service_name
        payload: dict[str, Any] = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "service": record_service,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        # Include any extra attributes attached to the record (e.g., tenant)
        for k, v in record.__dict__.items():
            if k in ("name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs", "relativeCreated", "thread", "threadName", "processName", "process"):
                continue
            if k.startswith("_"):
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except Exception:
                payload[k] = str(v)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(service_name: str = "app", level: int = logging.INFO) -> None:
    """Configure root logger to emit structured JSON logs to stdout.

    Call this early in process startup (e.g., in main module).
    """
    root = logging.getLogger()
    # Avoid adding multiple handlers if already configured
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        # Replace existing stream handlers with JSON formatter
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler):
                h.setFormatter(JSONFormatter(service_name))
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter(service_name))
    root.handlers = [handler]
    root.setLevel(level)
