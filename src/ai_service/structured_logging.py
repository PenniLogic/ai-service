"""Structured JSON-lines logging for service lifecycle events.

Each log line is one JSON object. Lifecycle events carry only fixed event names,
readiness states and configuration *key names*; configuration values, secrets and
provider settings are never passed to :func:`log_event`.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from typing import TextIO

LIFECYCLE_LOGGER: str = "pennilogic.lifecycle"
HANDLER_NAME: str = "pennilogic-json-lines"
_ENGINE_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonLineFormatter(logging.Formatter):
    """Render mapping messages as compact JSON; wrap plain messages in a fixed envelope.

    Plain messages keep only their first line and attached exceptions contribute only
    their type name: tracebacks and exception messages can carry addresses or
    configuration values and are deliberately not serialized.
    """

    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, Mapping):
            payload: dict[str, object] = dict(record.msg)
        else:
            payload = {
                "event": "message",
                "logger": record.name,
                "level": record.levelname,
                "message": record.getMessage().partition("\n")[0],
            }
        if record.exc_info is not None and record.exc_info[0] is not None:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"))


def configure_logging(stream: TextIO | None = None) -> None:
    """Install the JSON-lines handler on the root logger, replacing only a previous instance.

    ``stream`` defaults to the current ``sys.stderr``. Engine loggers are raised to
    WARNING so that their informational startup lines, which include the bind
    address, are never emitted.
    """
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(JsonLineFormatter())
    root = logging.getLogger()
    for existing in list(root.handlers):
        if existing.get_name() == HANDLER_NAME:
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    for name in _ENGINE_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def log_event(event: str, **fields: str | int) -> None:
    """Emit one lifecycle event with fixed, non-disclosing fields."""
    logging.getLogger(LIFECYCLE_LOGGER).info({"event": event, **fields})
