"""Process lifecycle: the configuration gate, structured startup log and exit codes."""

from __future__ import annotations

import io
import json
import socket

import pytest

from ai_service.app import create_app
from ai_service.server import (
    EXIT_FAILURE,
    EXIT_OK,
    GRACEFUL_SHUTDOWN_SECONDS,
    engine_config,
    run,
    serve_forever,
)
from ai_service.settings import Settings
from ai_service.structured_logging import configure_logging


def events(stream: io.StringIO) -> list[dict[str, object]]:
    lines = stream.getvalue().splitlines()
    assert all(line.startswith("{") and line.endswith("}") for line in lines)
    return [json.loads(line) for line in lines]


def test_startup_passes_validated_settings_to_the_engine() -> None:
    captured: list[Settings] = []
    stream = io.StringIO()

    def serve(settings: Settings) -> int:
        captured.append(settings)
        return EXIT_OK

    assert run({"APP_ENV": "local"}, serve=serve, log_stream=stream) == EXIT_OK
    assert captured == [Settings(environment="local", host="127.0.0.1", port=8080)]
    assert events(stream) == [{"event": "startup"}]


def test_configuration_failure_logs_only_the_key_and_never_starts() -> None:
    stream = io.StringIO()
    started = False

    def serve(_: Settings) -> int:
        nonlocal started
        started = True
        return EXIT_OK

    environ = {"APP_ENV": "test", "PORT": "port-value-9c1e"}
    assert run(environ, serve=serve, log_stream=stream) == EXIT_FAILURE
    assert started is False
    assert stream.getvalue() == '{"event":"configuration_invalid","key":"PORT"}\n'


def test_startup_log_contains_no_configuration_values() -> None:
    stream = io.StringIO()
    environ = {"APP_ENV": "staging", "HOST": "0.0.0.0", "PORT": "4321"}
    assert run(environ, serve=lambda _: EXIT_OK, log_stream=stream) == EXIT_OK
    log = stream.getvalue()
    for value in environ.values():
        assert value not in log
    assert events(stream) == [{"event": "startup"}]


def test_engine_exit_code_is_propagated() -> None:
    assert run({"APP_ENV": "test"}, serve=lambda _: 7, log_stream=io.StringIO()) == 7


def test_engine_failure_is_reported_structurally_without_a_traceback() -> None:
    stream = io.StringIO()
    sentinel = "synthetic-engine-failure-detail-c0ffee"

    def serve(_: Settings) -> int:
        raise RuntimeError(sentinel)

    assert run({"APP_ENV": "test"}, serve=serve, log_stream=stream) == EXIT_FAILURE
    assert events(stream) == [
        {"event": "startup"},
        {"event": "engine_failure", "exception": "RuntimeError"},
    ]
    assert sentinel not in stream.getvalue()
    assert "Traceback" not in stream.getvalue()


def test_engine_configuration_ignores_uvicorn_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WEB_CONCURRENCY", "synthetic-garbage-c0ffee")
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "*")
    config = engine_config(create_app())
    assert config.workers == 1
    assert config.proxy_headers is False
    assert config.forwarded_allow_ips == []
    assert config.server_header is False
    assert config.access_log is False
    assert config.lifespan == "on"
    assert config.timeout_graceful_shutdown == GRACEFUL_SHUTDOWN_SECONDS


def test_bind_failure_fails_closed_without_logging_the_address() -> None:
    stream = io.StringIO()
    configure_logging(stream)
    with socket.create_server(("127.0.0.1", 0)) as occupied:
        port = int(occupied.getsockname()[1])
        result = serve_forever(Settings(environment="test", host="127.0.0.1", port=port))
    assert result == EXIT_FAILURE
    logged = events(stream)
    assert len(logged) == 1
    assert logged[0]["event"] == "bind_failed"
    assert isinstance(logged[0]["errno"], int)
    assert str(port) not in stream.getvalue()
    assert "127.0.0.1" not in stream.getvalue()
