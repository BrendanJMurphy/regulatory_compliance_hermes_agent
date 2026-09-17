"""Structured logging.

Operational logs (as opposed to the audit chain) are emitted as one JSON object per line on
stderr so the container platform can ship them without parsing. Each line carries a UTC
timestamp, level, logger name, message, and any extra fields passed via ``extra=``.

Usage::

    from .logging_setup import configure_logging, get_logger
    configure_logging(json_output=True)
    log = get_logger(__name__)
    log.info("draft created", extra={"draft_id": d.draft_id, "requester": upn})
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

# Attributes every LogRecord carries; anything else on the record was passed via ``extra``.
_STANDARD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(*, json_output: bool = True, level: int = logging.INFO) -> None:
    """Install a single stderr handler on the root logger. Idempotent."""
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if json_output else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
