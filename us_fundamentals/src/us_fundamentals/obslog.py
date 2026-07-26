"""Structured JSON logging for pipeline components.

Every log line is one JSON object with the fields the backlog requires:
run ID, dataset version, component, duration, outcome, and accession where
relevant. Components get a logger via `component_logger` and wrap units of
work in `log_operation` so duration and outcome cannot be forgotten.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
import time
import uuid
from collections.abc import Iterator
from typing import Any

_RESERVED = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "component": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


class _MergingAdapter(logging.LoggerAdapter):
    """LoggerAdapter that merges per-call extra with its bound extra.

    The stdlib default *replaces* per-call extra, which would drop the
    operation fields (duration, outcome, accession); Python 3.13 added
    merge_extra but requires-python is 3.12.
    """

    def process(self, msg: str, kwargs: Any) -> tuple[str, Any]:
        merged = dict(self.extra or {})
        merged.update(kwargs.get("extra") or {})
        kwargs["extra"] = merged
        return msg, kwargs


def component_logger(
    component: str, run_id: str, dataset_version: str
) -> logging.LoggerAdapter:
    return _MergingAdapter(
        logging.getLogger(component),
        {"run_id": run_id, "dataset_version": dataset_version},
    )


@contextlib.contextmanager
def log_operation(
    logger: logging.LoggerAdapter,
    operation: str,
    accession: str | None = None,
    **context: Any,
) -> Iterator[dict[str, Any]]:
    """Log one unit of work with duration and outcome.

    Yields a mutable dict; keys set on it are emitted with the final line.
    """
    started = time.monotonic()
    fields: dict[str, Any] = dict(context)
    if accession is not None:
        fields["accession"] = accession
    try:
        yield fields
    except Exception as error:
        fields.update(
            duration_ms=round((time.monotonic() - started) * 1000, 1),
            outcome="error",
            error_category=getattr(error, "category", "unhandled"),
        )
        logger.error(operation, extra=fields, exc_info=True)
        raise
    fields.setdefault("outcome", "ok")
    fields["duration_ms"] = round((time.monotonic() - started) * 1000, 1)
    logger.info(operation, extra=fields)
