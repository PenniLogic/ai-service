# Health contract

The AI service implements the platform readiness contract already reviewed and
accepted in the PenniLogic core API scaffold. It does not define a second wire
shape.

## Source of truth

| Item | Value |
| --- | --- |
| Schema | [`docs/health.schema.json`](health.schema.json) |
| Copied from | `PenniLogic/api` `docs/health.schema.json` at main commit `6aebfe9325a30286c75013f77cf29947e519fbd5` |
| Git blob SHA (identical in both repositories) | `ff83203982f1c7a4ef84550b102d3d9c0c7a229b` |
| Reference implementation | `PenniLogic/api` `src/main/kotlin/com/pennilogic/bootstrap/Health.kt` |

The copy must stay byte-identical to the api file. A change to the shared shape is
an additive contract change that is decided with the api and platform probe owners
first, then applied to both repositories; it is not made here unilaterally.

## Endpoints

| Method and path | Condition | Status | Body |
| --- | --- | --- | --- |
| `GET /health/live` | process is serving | `200` | `{"status":"up"}` |
| `GET /health/ready` | lifespan startup completed, shutdown not begun | `200` | `{"status":"ready"}` |
| `GET /health/ready` | before startup completes or after shutdown begins | `503` | `{"status":"not_ready"}` |
| any other path, including trailing-slash variants (no redirect) | — | `404` | engine default |
| other methods on the health paths | — | `405` | engine default |

Every health response carries `Content-Type: application/json` and
`Cache-Control: no-store`, and no `Server` header is sent. Bodies are fixed
constants: they never include configuration, versions, dependency state, provider
settings or timestamps.

`/health/live` answers as soon as the listener serves requests, independent of
readiness. `/health/ready` is withdrawn when the ASGI lifespan shutdown begins;
with uvicorn that happens after the listener stops accepting new connections and
in-flight requests drain (bounded by the graceful shutdown timeout).

## Lifecycle log events

One JSON object per line on standard error, mirroring the api scaffold. Only event
names, readiness states and configuration *key names* appear; configuration values
are never logged.

```text
{"event":"configuration_invalid","key":"APP_ENV"}
{"event":"startup"}
{"event":"bind_failed","errno":98}
{"event":"readiness","status":"ready"}
{"event":"readiness","status":"not_ready"}
```

## Automated evidence

- `tests/test_health.py` asserts the exact bodies, status codes and headers, validates
  every body against the schema copy, and pins the schema copy's content.
- `tests/test_process.py` starts the real `python -m ai_service` process and asserts
  the same contract over a socket, that no `Server` header is sent, and that the
  startup log consists solely of the events above.
