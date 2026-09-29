"""Health endpoints implementing the shared platform readiness contract.

The wire shape is the reviewed PenniLogic core API health response
(``docs/health.schema.json``): a JSON object with a single ``status`` field whose
value is ``up``, ``ready`` or ``not_ready``. Responses are fixed constants and
disclose no configuration.
"""

from __future__ import annotations

import json
import threading
from enum import StrEnum
from http import HTTPStatus

from fastapi import APIRouter, Response

LIVE_PATH: str = "/health/live"
READY_PATH: str = "/health/ready"
CACHE_CONTROL: str = "no-store"
MEDIA_TYPE: str = "application/json"


class HealthStatus(StrEnum):
    """Allowed ``status`` values of the shared health response schema."""

    UP = "up"
    READY = "ready"
    NOT_READY = "not_ready"


class Readiness:
    """Thread-safe, idempotent readiness flag toggled by the application lifespan."""

    def __init__(self) -> None:
        self._accepting = threading.Event()

    def is_ready(self) -> bool:
        return self._accepting.is_set()

    def started(self) -> None:
        self._accepting.set()

    def stopping(self) -> None:
        self._accepting.clear()


def health_response(status: HealthStatus, status_code: HTTPStatus = HTTPStatus.OK) -> Response:
    """Build the fixed JSON response for ``status`` with non-cacheable headers."""
    body = json.dumps({"status": status.value}, separators=(",", ":"))
    return Response(
        content=body,
        status_code=status_code,
        media_type=MEDIA_TYPE,
        headers={"Cache-Control": CACHE_CONTROL},
    )


def health_router(readiness: Readiness) -> APIRouter:
    """Routes for liveness and readiness bound to ``readiness``."""
    router = APIRouter()

    @router.get(LIVE_PATH)
    async def live() -> Response:
        return health_response(HealthStatus.UP)

    @router.get(READY_PATH)
    async def ready() -> Response:
        if readiness.is_ready():
            return health_response(HealthStatus.READY)
        return health_response(HealthStatus.NOT_READY, HTTPStatus.SERVICE_UNAVAILABLE)

    return router
