# AI service development

Health-only backend scaffold for the PenniLogic AI service (ADR-009: Python/FastAPI).
It validates its configuration, serves the shared health contract and nothing else.
There is no provider routing, provider key handling, inference, persistence or
outbound network client in this repository.

Repository-level foundation commands, review rules and safety invariants are in
[`AGENTS.md`](../AGENTS.md). This file documents the application toolchain.

## Toolchain

| Tool | Version | Role |
| --- | --- | --- |
| Python | 3.14 (`.python-version`) | baseline interpreter |
| uv | 0.11.x | environment, lock file, command runner |

Dependencies are declared in `pyproject.toml` and pinned with hashes for every
platform in `uv.lock`. `httpx2` (Starlette's test client transport), `pytest`,
`ruff` and `mypy` are in the `dev` dependency group only; the runtime dependency
set is `fastapi` and `uvicorn`, and `tests/test_boundaries.py` fails if that set
grows without review. `uv sync --locked --no-dev` installs the runtime set alone.

## Commands

Run from the repository root. `--locked` fails if `uv.lock` no longer matches
`pyproject.toml` instead of silently re-resolving.

```text
uv sync --locked
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest
```

To refresh the lock after editing dependencies: `uv lock`, then re-run everything.

## Run locally

```text
APP_ENV=local uv run --locked python -m ai_service
```

Or install and use the console script `ai-service`. The process exits with code 1
and a single `{"event":"configuration_invalid","key":"..."}` line when
configuration is rejected; it never prints the rejected value. On `SIGTERM`
(`Ctrl+Break` on Windows) it withdraws readiness, drains connections within the
graceful-shutdown timeout, logs `{"event":"readiness","status":"not_ready"}` and then
ends with the stop signal's default disposition, as uvicorn re-raises the signal it
handled.

## Configuration

All configuration comes from the environment. Names, defaults and accepted values
mirror the core API scaffold so both services are deployed the same way.

| Variable | Required | Accepted values | Default |
| --- | --- | --- | --- |
| `APP_ENV` | yes | `local`, `test`, `staging`, `production` | — |
| `HOST` | no | `127.0.0.1`, `0.0.0.0` | `127.0.0.1` |
| `PORT` | no | canonical decimal `1`–`65535` | `8080` |

There are no provider, model or credential settings. Keep it that way until the
AI harness epic introduces them behind their own reviewed contract.

## Observability

Lifecycle events are structured JSON lines on standard error; see
[`docs/health-contract.md`](health-contract.md). Engine (uvicorn) informational
output, which would include the bind address, is suppressed; engine warnings and
errors are wrapped as `{"event":"message",...}` lines that keep only the first line
of the message and, for attached exceptions, only the exception type name. No
timestamps are emitted by the process; the log collector stamps lines.

## Rollout and rollback

Merging this scaffold deploys nothing. Rollback is reverting the merge commit;
there is no data, schema, queue or external registration to unwind.
