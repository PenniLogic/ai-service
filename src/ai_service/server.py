"""Process entrypoint: validate configuration, bind the listener, then serve.

Configuration is validated before any socket is opened. The only lifecycle
output is the structured event log; the bind address is never written to it.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Mapping
from typing import Final, TextIO

import uvicorn
from fastapi import FastAPI

from ai_service.app import create_app
from ai_service.settings import ConfigurationError, Settings, load_settings
from ai_service.structured_logging import configure_logging, log_event

EXIT_OK: Final = 0
EXIT_FAILURE: Final = 1
GRACEFUL_SHUTDOWN_SECONDS: Final = 5


def engine_config(app: FastAPI) -> uvicorn.Config:
    """Build the engine configuration with every environment-derived option pinned.

    uvicorn otherwise reads ``WEB_CONCURRENCY`` and ``FORWARDED_ALLOW_IPS`` from the
    process environment; passing ``workers`` and ``forwarded_allow_ips`` explicitly
    keeps the validated :class:`~ai_service.settings.Settings` allowlist the only
    configuration source. No proxy headers are trusted: this scaffold is not
    deployed behind a reviewed proxy configuration.
    """
    return uvicorn.Config(
        app,
        workers=1,
        proxy_headers=False,
        forwarded_allow_ips=[],
        log_config=None,
        log_level="warning",
        access_log=False,
        server_header=False,
        lifespan="on",
        timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
    )


def serve_forever(settings: Settings) -> int:
    """Bind the configured address and serve until a termination signal arrives."""
    try:
        listener = socket.create_server((settings.host, settings.port))
    except OSError as error:
        log_event("bind_failed", errno=error.errno if error.errno is not None else -1)
        return EXIT_FAILURE
    with listener:
        server = uvicorn.Server(engine_config(create_app()))
        server.run(sockets=[listener])
    return EXIT_OK if server.started else EXIT_FAILURE


def run(
    environ: Mapping[str, str],
    *,
    serve: Callable[[Settings], int] = serve_forever,
    log_stream: TextIO | None = None,
) -> int:
    """Configure logging, validate ``environ`` and hand validated settings to ``serve``.

    Returns the process exit code. Invalid configuration logs only the offending
    key name and returns a failure code without starting the server. An unexpected
    engine failure is reported as a structured ``engine_failure`` event carrying the
    exception type name only, never as a traceback (which would echo paths and
    values). Logging goes to ``log_stream`` or, by default, standard error.
    """
    configure_logging(log_stream)
    try:
        settings = load_settings(environ)
    except ConfigurationError as error:
        log_event("configuration_invalid", key=error.key)
        return EXIT_FAILURE
    log_event("startup")
    try:
        return serve(settings)
    except Exception as error:  # last-resort boundary; reported structurally, never as a trace
        log_event("engine_failure", exception=type(error).__name__)
        return EXIT_FAILURE


def main() -> int:
    """Console-script entrypoint."""
    return run(os.environ)
