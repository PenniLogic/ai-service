"""The configured static-analysis gates fail on planted violations.

These tests prove the lint, formatting and type-check commands documented in
``docs/development.md`` reject defects when run with this repository's
configuration, so a green pipeline is a real signal.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def run_tool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_planted_lint_violation_fails_ruff_check(tmp_path: Path) -> None:
    planted = tmp_path / "planted_lint_violation.py"
    planted.write_text(
        "import os\n\n\ndef leaves_an_unused_import() -> None:\n    return None\n",
        encoding="utf-8",
    )
    result = run_tool("ruff", "check", "--no-cache", "--config", str(PYPROJECT), str(planted))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "F401" in result.stdout


def test_planted_formatting_violation_fails_ruff_format_check(tmp_path: Path) -> None:
    planted = tmp_path / "planted_formatting_violation.py"
    planted.write_text("value  =  {'a':1}\n", encoding="utf-8")
    result = run_tool(
        "ruff", "format", "--check", "--no-cache", "--config", str(PYPROJECT), str(planted)
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "would be reformatted" in (result.stdout + result.stderr).lower()


def test_planted_type_error_fails_mypy(tmp_path: Path) -> None:
    planted = tmp_path / "planted_type_error.py"
    planted.write_text(
        "def amount_minor(units: int) -> int:\n"
        "    return units\n"
        "\n"
        "\n"
        "label: str = amount_minor(100)\n",
        encoding="utf-8",
    )
    result = run_tool(
        "mypy",
        "--config-file",
        str(PYPROJECT),
        "--cache-dir",
        str(tmp_path / ".mypy_cache"),
        str(planted),
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "error: Incompatible types in assignment" in result.stdout


def test_well_formed_file_passes_the_same_gates(tmp_path: Path) -> None:
    clean = tmp_path / "well_formed.py"
    clean.write_text(
        '"""A well-formed module used as the positive control."""\n'
        "\n"
        "\n"
        "def amount_minor(units: int) -> int:\n"
        "    return units\n",
        encoding="utf-8",
    )
    lint = run_tool("ruff", "check", "--no-cache", "--config", str(PYPROJECT), str(clean))
    assert lint.returncode == 0, lint.stdout + lint.stderr
    fmt = run_tool(
        "ruff", "format", "--check", "--no-cache", "--config", str(PYPROJECT), str(clean)
    )
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    types = run_tool(
        "mypy",
        "--config-file",
        str(PYPROJECT),
        "--cache-dir",
        str(tmp_path / ".mypy_cache"),
        str(clean),
    )
    assert types.returncode == 0, types.stdout + types.stderr
