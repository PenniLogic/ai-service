"""Health endpoints implement the reviewed platform readiness contract exactly."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from ai_service.app import create_app
from ai_service.health import Readiness

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "docs" / "health.schema.json"
# Git blob SHA of docs/health.schema.json in PenniLogic/api main (6aebfe93). The copy
# must stay byte-identical; a shared-shape change is decided with the api owners first.
API_SCHEMA_BLOB_SHA = "ff83203982f1c7a4ef84550b102d3d9c0c7a229b"
SCHEMA_BYTES = SCHEMA_PATH.read_bytes()
SCHEMA = json.loads(SCHEMA_BYTES)

LIVE = "/health/live"
READY = "/health/ready"


def assert_conforms_to_schema(body: bytes) -> None:
    payload = json.loads(body)
    assert isinstance(payload, dict)
    assert set(payload) == set(SCHEMA["required"]) == {"status"}
    assert SCHEMA["additionalProperties"] is False
    assert payload["status"] in SCHEMA["properties"]["status"]["enum"]


def assert_health_headers(response: httpx2.Response) -> None:
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert "server" not in response.headers


def test_schema_copy_is_byte_identical_to_the_reviewed_api_schema() -> None:
    blob = b"blob %d\0" % len(SCHEMA_BYTES) + SCHEMA_BYTES
    assert hashlib.sha1(blob, usedforsecurity=False).hexdigest() == API_SCHEMA_BLOB_SHA
    assert SCHEMA == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "API scaffold health response",
        "type": "object",
        "additionalProperties": False,
        "required": ["status"],
        "properties": {"status": {"type": "string", "enum": ["up", "ready", "not_ready"]}},
    }


@pytest.mark.parametrize(
    ("path", "body"),
    [(LIVE, b'{"status":"up"}'), (READY, b'{"status":"ready"}')],
)
def test_started_application_serves_fixed_non_disclosing_responses(path: str, body: bytes) -> None:
    with TestClient(create_app()) as client:
        response = client.get(path)
    assert response.status_code == 200
    assert response.content == body
    assert_health_headers(response)
    assert_conforms_to_schema(response.content)


def test_readiness_is_withheld_until_lifespan_startup_completes() -> None:
    client = TestClient(create_app())  # no lifespan: startup has not run
    ready = client.get(READY)
    assert ready.status_code == 503
    assert ready.content == b'{"status":"not_ready"}'
    assert_health_headers(ready)
    assert_conforms_to_schema(ready.content)
    live = client.get(LIVE)
    assert live.status_code == 200
    assert live.content == b'{"status":"up"}'


def test_shutdown_withdraws_readiness_while_liveness_remains() -> None:
    readiness = Readiness()
    with TestClient(create_app(readiness)) as client:
        assert readiness.is_ready()
        assert client.get(READY).status_code == 200
        readiness.stopping()
        withdrawn = client.get(READY)
        assert withdrawn.status_code == 503
        assert withdrawn.content == b'{"status":"not_ready"}'
        assert_health_headers(withdrawn)
        assert client.get(LIVE).status_code == 200
    assert not readiness.is_ready()


def test_readiness_transitions_are_idempotent() -> None:
    readiness = Readiness()
    assert not readiness.is_ready()
    readiness.started()
    readiness.started()
    assert readiness.is_ready()
    readiness.stopping()
    readiness.stopping()
    assert not readiness.is_ready()


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/users",
        "/health",
        "/health/live/",
        "/health/ready/",
        "/openapi.json",
        "/docs",
        "/redoc",
    ],
)
def test_no_other_path_is_exposed(path: str) -> None:
    with TestClient(create_app()) as client:
        response = client.get(path, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers


@pytest.mark.parametrize("method", ["HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", [LIVE, READY])
def test_health_paths_accept_only_get(method: str, path: str) -> None:
    """GET only, as in the api reference (Ktor ``get`` without auto-HEAD).

    Serving HEAD or OPTIONS would be a deliberate shared-contract change made
    with the api and platform probe owners, not an accident of the framework.
    """
    with TestClient(create_app()) as client:
        response = client.request(method, path)
    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
