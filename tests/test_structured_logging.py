"""Structured logging emits one JSON object per line and withholds exception details."""

from __future__ import annotations

import io
import json
import logging

from ai_service.structured_logging import (
    HANDLER_NAME,
    LIFECYCLE_LOGGER,
    JsonLineFormatter,
    configure_logging,
    log_event,
)


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_lifecycle_events_are_compact_json_lines() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    log_event("startup")
    log_event("readiness", status="ready")
    assert stream.getvalue() == '{"event":"startup"}\n{"event":"readiness","status":"ready"}\n'


def test_reconfiguration_replaces_the_managed_handler_only_once() -> None:
    first, second = io.StringIO(), io.StringIO()
    configure_logging(first)
    configure_logging(second)
    managed = [h for h in logging.getLogger().handlers if h.get_name() == HANDLER_NAME]
    assert len(managed) == 1
    log_event("startup")
    assert first.getvalue() == ""
    assert lines(second) == [{"event": "startup"}]


def test_engine_messages_are_wrapped_and_informational_lines_are_suppressed() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    engine = logging.getLogger("uvicorn.error")
    engine.info("Uvicorn running on http://127.0.0.1:8080 (Press CTRL+C to quit)")
    engine.warning("synthetic engine warning")
    assert lines(stream) == [
        {
            "event": "message",
            "logger": "uvicorn.error",
            "level": "WARNING",
            "message": "synthetic engine warning",
        }
    ]
    assert "8080" not in stream.getvalue()


def synthetic_bind_failure() -> None:
    raise OSError(98, "bind to 127.0.0.1:8080 refused-synthetic")


def test_exceptions_contribute_only_their_type_name() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    try:
        synthetic_bind_failure()
    except OSError:
        logging.getLogger(LIFECYCLE_LOGGER).exception({"event": "engine_failure"})
    assert lines(stream) == [{"event": "engine_failure", "exception": "OSError"}]
    assert "127.0.0.1" not in stream.getvalue()
    assert "Traceback" not in stream.getvalue()


def test_plain_messages_keep_only_their_first_line() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    traceback_like = (
        "Exception in 'lifespan' protocol\nTraceback (most recent call last):\n  port=8080"
    )
    logging.getLogger("uvicorn.error").error(traceback_like)
    assert lines(stream) == [
        {
            "event": "message",
            "logger": "uvicorn.error",
            "level": "ERROR",
            "message": "Exception in 'lifespan' protocol",
        }
    ]
    assert "8080" not in stream.getvalue()


def test_formatter_output_is_single_line_json() -> None:
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "multi\nline message", None, None)
    formatted = JsonLineFormatter().format(record)
    assert "\n" not in formatted
    assert json.loads(formatted)["message"] == "multi"
