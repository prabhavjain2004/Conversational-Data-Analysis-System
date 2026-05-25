"""
Decoupled Structured Logging Module
===================================
Provides structured JSON logging across all backend components, avoiding circular
dependencies between main.py, llm_service.py, and chart_engine.py.

Reference: PRD Section 14 (Observability)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict

from backend.config import settings


class JsonFormatter(logging.Formatter):
    """
    Custom JSON log formatter producing newline-delimited JSON entries.
    Directly ingestible by Datadog, CloudWatch, Grafana Loki, etc.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "backend",
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        # Merge any extra structured fields
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        if record.exc_info and record.exc_info[1]:
            log_entry["traceback"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def _setup_logging() -> logging.Logger:
    """Configure the root application logger with JSON formatting."""
    logger = logging.getLogger("cdas")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    # Prevent propagation to default handler (avoids duplicate output)
    logger.propagate = False
    return logger


logger = _setup_logging()


def log_event(
    event: str,
    request_id: str | None = None,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured log entry with an event name and arbitrary fields."""
    extra_fields: Dict[str, Any] = {"event": event, **fields}
    if request_id:
        extra_fields["request_id"] = request_id
    record = logger.makeRecord(
        name=logger.name,
        level=level,
        fn="",
        lno=0,
        msg=event,
        args=(),
        exc_info=None,
    )
    record.extra_fields = extra_fields  # type: ignore[attr-defined]
    logger.handle(record)
