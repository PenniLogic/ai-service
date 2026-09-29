"""The real ``python -m ai_service`` process: configuration gate, wire contract and logs."""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STARTUP_DEADLINE_SECONDS = 30.0
EXIT_DEADLINE_SECONDS = 30.0
POLL_INTERVAL_SECONDS = 0.1
CONFIGURATION_KEYS = ("APP_ENV", "HOST", "PORT")


def free_port() -> int:
    with socket.create_server(("127.0.0.1", 0)) as probe:
        return int(probe.getsockname()[1])


def child_environment(**overrides: str) -> dict[str, str]:
    environment = {k: v for k, v in os.environ.items() if k not in CONFIGURATION_KEYS}
    environment.update(overrides)
    return environment


def launch(environment: dict[str, str]) -> subprocess.Popen[str]:
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return subprocess.Popen(
        [sys.executable, "-m", "ai_service"],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        creationflags=creationflags,
    )


def finish(process: subprocess.Popen[str]) -> str:
    """Wait for exit (killing on timeout) and return everything the process wrote."""
    try:
        output, _ = process.communicate(timeout=EXIT_DEADLINE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        output, _ = process.communicate(timeout=EXIT_DEADLINE_SECONDS)
        pytest.fail(f"process did not exit in time; output:\n{output}")
    return output


def request(port: int, method: str, path: str) -> tuple[int, bytes, http.client.HTTPMessage]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read(), response.headers
    finally:
        connection.close()


def wait_until_ready(process: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + STARTUP_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = finish(process)
            pytest.fail(f"process exited early with {process.returncode}; output:\n{output}")
        try:
            status, body, _ = request(port, "GET", "/health/ready")
        except OSError:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
        if status == 200:
            assert body == b'{"status":"ready"}'
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    process.kill()
    pytest.fail(f"process never became ready; output:\n{finish(process)}")


def request_graceful_stop(process: subprocess.Popen[str]) -> None:
    if sys.platform == "win32":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGTERM)


def graceful_stop_exit_codes() -> frozenset[int]:
    """Exit statuses after uvicorn re-raises the captured stop signal with its default handler.

    uvicorn restores the original signal handlers once shutdown completes and re-raises
    the signal it handled, so the process ends the way the stop signal would normally
    end it: killed by SIGTERM on POSIX (negative status from ``Popen``), exit status 3
    from the C runtime's default SIGBREAK disposition on Windows.
    """
    windows_sigbreak_exit_status = 3
    posix_sigterm_exit_status = -int(signal.SIGTERM)
    # A conditional expression keeps both branches type-checked on every platform.
    return frozenset(
        {windows_sigbreak_exit_status if sys.platform == "win32" else posix_sigterm_exit_status}
    )


def log_events(output: str) -> list[dict[str, object]]:
    lines = output.splitlines()
    assert lines, "expected structured log lines"
    assert all(line.startswith("{") and line.endswith("}") for line in lines), output
    return [json.loads(line) for line in lines]


def test_real_entrypoint_rejects_missing_configuration_before_binding() -> None:
    port = free_port()
    process = launch(child_environment(PORT=str(port)))
    output = finish(process)
    assert process.returncode == 1
    assert output.strip() == '{"event":"configuration_invalid","key":"APP_ENV"}'
    with pytest.raises(ConnectionRefusedError):
        request(port, "GET", "/health/live")


def test_real_entrypoint_never_echoes_a_rejected_value() -> None:
    rejected = "rejected-port-value-5d2f"
    process = launch(child_environment(APP_ENV="test", PORT=rejected))
    output = finish(process)
    assert process.returncode == 1
    assert output.strip() == '{"event":"configuration_invalid","key":"PORT"}'
    assert rejected not in output


def test_real_entrypoint_fails_closed_when_the_port_is_taken() -> None:
    with socket.create_server(("127.0.0.1", 0)) as occupied:
        port = int(occupied.getsockname()[1])
        process = launch(child_environment(APP_ENV="test", HOST="127.0.0.1", PORT=str(port)))
        output = finish(process)
    assert process.returncode == 1
    events = log_events(output)
    assert [event["event"] for event in events] == ["startup", "bind_failed"]
    assert str(port) not in output
    assert "127.0.0.1" not in output


def test_real_entrypoint_serves_the_shared_health_contract_and_logs_no_values() -> None:
    port = free_port()
    process = launch(child_environment(APP_ENV="test", HOST="127.0.0.1", PORT=str(port)))
    try:
        wait_until_ready(process, port)

        status, body, headers = request(port, "GET", "/health/ready")
        assert (status, body) == (200, b'{"status":"ready"}')
        assert headers["content-type"] == "application/json"
        assert headers["cache-control"] == "no-store"
        assert headers.get("server") is None

        status, body, headers = request(port, "GET", "/health/live")
        assert (status, body) == (200, b'{"status":"up"}')
        assert headers["content-type"] == "application/json"
        assert headers["cache-control"] == "no-store"
        assert headers.get("server") is None

        assert request(port, "GET", "/")[0] == 404
        assert request(port, "GET", "/openapi.json")[0] == 404
        assert request(port, "POST", "/health/ready")[0] == 405

        request_graceful_stop(process)
        output = finish(process)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=EXIT_DEADLINE_SECONDS)

    assert process.returncode in graceful_stop_exit_codes(), output
    assert "Traceback" not in output
    assert log_events(output) == [
        {"event": "startup"},
        {"event": "readiness", "status": "ready"},
        {"event": "readiness", "status": "not_ready"},
    ]
    assert str(port) not in output
    assert "127.0.0.1" not in output
