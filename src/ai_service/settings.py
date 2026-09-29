"""Environment-driven configuration with fail-closed validation.

The accepted keys, defaults and validation rules mirror the reviewed
``ServerConfig`` of the PenniLogic core API scaffold so both services are
configured the same way by the platform. Rejected values are never echoed in
errors, logs or representations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

ENVIRONMENT_KEY: Final = "APP_ENV"
HOST_KEY: Final = "HOST"
PORT_KEY: Final = "PORT"

ACCEPTED_ENVIRONMENTS: Final = frozenset({"local", "test", "staging", "production"})
# Loopback for local runs; all interfaces only for the container case, as in the core API.
ACCEPTED_HOSTS: Final = frozenset({"127.0.0.1", "0.0.0.0"})  # noqa: S104
DEFAULT_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8080
PORT_RANGE: Final = range(1, 65536)
_MAX_PORT_DIGITS: Final = len(str(PORT_RANGE[-1]))


class ConfigurationError(ValueError):
    """A required configuration key is missing or its value is not accepted.

    Only the key name is carried; the rejected value is deliberately discarded.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"Invalid or missing configuration key: {key}")
        self.key = key


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    """Validated service settings. Holds no provider or secret configuration."""

    environment: str
    host: str
    port: int

    def __repr__(self) -> str:
        return "Settings(<values withheld>)"


def load_settings(environ: Mapping[str, str]) -> Settings:
    """Validate ``environ`` into :class:`Settings` or raise :class:`ConfigurationError`."""
    environment = environ.get(ENVIRONMENT_KEY)
    if environment not in ACCEPTED_ENVIRONMENTS:
        raise ConfigurationError(ENVIRONMENT_KEY)

    host = environ.get(HOST_KEY, DEFAULT_HOST)
    if host not in ACCEPTED_HOSTS:
        raise ConfigurationError(HOST_KEY)

    raw_port = environ.get(PORT_KEY)
    port = DEFAULT_PORT if raw_port is None else _parse_port(raw_port)

    return Settings(environment=environment, host=host, port=port)


def _parse_port(raw_port: str) -> int:
    # Only the canonical decimal spelling is accepted: no sign, padding, whitespace
    # or underscores, so the value that was configured is the value that binds. The
    # length guard also keeps oversized input away from int() conversion limits.
    if len(raw_port) > _MAX_PORT_DIGITS or not raw_port.isascii() or not raw_port.isdigit():
        raise ConfigurationError(PORT_KEY)
    port = int(raw_port)
    if port not in PORT_RANGE or str(port) != raw_port:
        raise ConfigurationError(PORT_KEY)
    return port
