"""ASGI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ai_service.health import HealthStatus, Readiness, health_router
from ai_service.structured_logging import log_event


def create_app(readiness: Readiness | None = None) -> FastAPI:
    """Create the health-only application.

    Readiness becomes true only after the ASGI lifespan startup completes and is
    withdrawn when shutdown begins. Interactive documentation, the OpenAPI document
    and trailing-slash redirects (which echo the client's Host header) are disabled:
    the service exposes nothing but the health contract.
    """
    state = readiness if readiness is not None else Readiness()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        state.started()
        log_event("readiness", status=HealthStatus.READY.value)
        try:
            yield
        finally:
            state.stopping()
            log_event("readiness", status=HealthStatus.NOT_READY.value)

    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        redirect_slashes=False,
    )
    app.include_router(health_router(state))
    return app
