"""Configuration loading is fail-closed and never echoes rejected values."""

from __future__ import annotations

import dataclasses

import pytest

from ai_service.settings import (
    ACCEPTED_ENVIRONMENTS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    ConfigurationError,
    Settings,
    load_settings,
)

REJECTED_VALUE = "rejected-config-value-7f3a"


def test_missing_required_environment_fails_with_key_only() -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings({})
    assert excinfo.value.key == "APP_ENV"
    assert str(excinfo.value) == "Invalid or missing configuration key: APP_ENV"
    assert excinfo.value.args == ("Invalid or missing configuration key: APP_ENV",)


@pytest.mark.parametrize("environment", sorted(ACCEPTED_ENVIRONMENTS))
def test_accepted_environments_use_safe_loopback_defaults(environment: str) -> None:
    settings = load_settings({"APP_ENV": environment})
    assert settings == Settings(environment=environment, host=DEFAULT_HOST, port=DEFAULT_PORT)
    assert settings.host == "127.0.0.1"
    assert settings.port == 8080


@pytest.mark.parametrize(
    "value",
    ["", " ", "LOCAL", "local ", " test", "prod", "Production", "dev", REJECTED_VALUE],
)
def test_invalid_environment_is_rejected(value: str) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings({"APP_ENV": value})
    assert excinfo.value.key == "APP_ENV"


@pytest.mark.parametrize(
    ("key", "environ"),
    [
        ("APP_ENV", {"APP_ENV": REJECTED_VALUE}),
        ("HOST", {"APP_ENV": "test", "HOST": REJECTED_VALUE}),
        ("PORT", {"APP_ENV": "test", "PORT": REJECTED_VALUE}),
    ],
)
def test_rejected_values_are_absent_from_error_text(key: str, environ: dict[str, str]) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(environ)
    assert excinfo.value.key == key
    assert REJECTED_VALUE not in str(excinfo.value)
    assert REJECTED_VALUE not in repr(excinfo.value)
    assert REJECTED_VALUE not in repr(excinfo.value.args)


@pytest.mark.parametrize("port", ["1", "8080", "65535"])
def test_valid_port_boundaries_and_container_host_are_accepted(port: str) -> None:
    settings = load_settings({"APP_ENV": "test", "HOST": "0.0.0.0", "PORT": port})
    assert settings.host == "0.0.0.0"
    assert settings.port == int(port)


@pytest.mark.parametrize(
    "port",
    [
        "",
        " ",
        "0",
        "-1",
        "65536",
        "2147483648",
        "eight",
        "80.0",
        " 80",
        "80 ",
        "+80",
        "080",
        "8_0",
        "0x50",
        "80\n",
        "\u0668\u0660",  # Arabic-Indic digits: isdigit() but not ASCII
        "1" * 6,
        "9" * 5000,  # beyond int() conversion limits; must still be a ConfigurationError
    ],
)
def test_invalid_ports_fail_closed(port: str) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings({"APP_ENV": "test", "PORT": port})
    assert excinfo.value.key == "PORT"


@pytest.mark.parametrize(
    "host",
    ["", "localhost", "example.invalid", "::", "[::1]", "0.0.0.0 ", "127.0.0.1\n", "127.0.0.2"],
)
def test_unsupported_bind_hosts_are_rejected(host: str) -> None:
    with pytest.raises(ConfigurationError) as excinfo:
        load_settings({"APP_ENV": "test", "HOST": host})
    assert excinfo.value.key == "HOST"


def test_unrelated_environment_variables_are_ignored_not_loaded() -> None:
    settings = load_settings(
        {"APP_ENV": "test", "PROVIDER_API_KEY": "synthetic-not-a-secret", "MODEL": "none"}
    )
    assert {field.name for field in dataclasses.fields(settings)} == {"environment", "host", "port"}
    assert not hasattr(settings, "provider_api_key")


def test_settings_representation_withholds_values() -> None:
    settings = load_settings({"APP_ENV": "production", "HOST": "0.0.0.0", "PORT": "4321"})
    for text in (repr(settings), str(settings)):
        assert text == "Settings(<values withheld>)"
        for value in ("production", "0.0.0.0", "4321"):
            assert value not in text
