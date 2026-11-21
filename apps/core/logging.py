"""JSON-логи с request-id (§2.24)."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

_request_id: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in (
            "event",
            "actor",
            "game_id",
            "session_id",
            "duration_ms",
            "job_id",
            "task_id",
            "package_hash",
            "zip_bytes",
            "extracted_bytes",
            "file_count",
            "outcome",
            "error_code",
            "attempts",
            "queue",
            "limits",
            "task_name",
            "redelivered",
            "retries",
            "exception_type",
            "worker",
            "worker_pid",
            "exitcode",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False)
