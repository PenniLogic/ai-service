"""Scaffold boundaries: no outbound client, no provider dependency, no provider settings.

The AI harness epic will widen these deliberately, under its own reviewed
contracts. Until then any change here is a review event, not an accident.
"""

from __future__ import annotations

import ast
import dataclasses
import re
import tomllib
from pathlib import Path

from ai_service.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "ai_service"
PYPROJECT = ROOT / "pyproject.toml"

ALLOWED_RUNTIME_DEPENDENCIES = frozenset({"fastapi", "uvicorn"})
OUTBOUND_CLIENT_MODULES = frozenset(
    {
        "aiohttp",
        "anthropic",
        "boto3",
        "botocore",
        "ftplib",
        "http.client",
        "httpx",
        "httpx2",
        "litellm",
        "openai",
        "requests",
        "smtplib",
        "urllib.request",
        "urllib3",
        "websockets",
        "xmlrpc.client",
    }
)


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def requirement_name(requirement: str) -> str:
    return re.split(r"[\s\[<>=!~;@]", requirement, maxsplit=1)[0].lower()


def test_runtime_package_imports_no_outbound_client() -> None:
    sources = sorted(PACKAGE.rglob("*.py"))
    assert sources, "runtime package sources not found"
    for source in sources:
        offending = {
            name
            for name in imported_modules(source)
            if name in OUTBOUND_CLIENT_MODULES or name.split(".")[0] in OUTBOUND_CLIENT_MODULES
        }
        assert not offending, f"{source.relative_to(ROOT)} imports {sorted(offending)}"


def test_runtime_dependency_set_is_the_reviewed_allowlist() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert {requirement_name(entry) for entry in project["dependencies"]} == (
        ALLOWED_RUNTIME_DEPENDENCIES
    )
    assert "optional-dependencies" not in project


def test_test_client_stack_is_confined_to_the_dev_group() -> None:
    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dev_group = {requirement_name(entry) for entry in document["dependency-groups"]["dev"]}
    assert {"httpx2", "pytest", "ruff", "mypy"} <= dev_group
    assert dev_group.isdisjoint(ALLOWED_RUNTIME_DEPENDENCIES)


def test_settings_carry_no_provider_configuration() -> None:
    assert {field.name for field in dataclasses.fields(Settings)} == {"environment", "host", "port"}
