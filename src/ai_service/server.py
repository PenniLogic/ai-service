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

from ai_service.app import create_app
from ai_service.settings import ConfigurationError, Settings, load_settings
from ai_service.structured_logging import configure_logging, log_event

EXIT_OK: Final = 0
EXIT_FAILURE: Final = 1
GRACEFUL_SHUTDOWN_SECONDS: Final = 5


def serve_forever(settings: Settings) -> int:
    """Bind the configured address and serve until a termination signal arrives."""
    try:
        listener = socket.create_server((settings.host, settings.port))
    except OSError as error:
        log_event("bind_failed", errno=error.errno if error.errno is not None else -1)
        return EXIT_FAILURE
    with listener:
        config = uvicorn.Config(
            create_app(),
            log_config=None,
            log_level="warning",
            access_log=False,
            server_header=False,
            lifespan="on",
            timeout_graceful_shutdown=GRACEFUL_SHUTDOWN_SECONDS,
        )
        server = uvicorn.Server(config)
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
    key name and returns a failure code without starting the server. Logging goes
    to ``log_stream`` or, by default, the current standard error stream.
    """
    configure_logging(log_stream)
    try:
        settings = load_settings(environ)
    except ConfigurationError as error:
        log_event("configuration_invalid", key=error.key)
        return EXIT_FAILURE
    log_event("startup")
    return serve(settings)


def main() -> int:
    """Console-script entrypoint."""
    return run(os.environ)
