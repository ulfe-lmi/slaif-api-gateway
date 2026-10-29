# Observability boundaries

> **Status:** Prometheus/logging are wired; SLO evaluation is a standalone foundation
> **Audience:** Operators and maintainers

The running Gateway provides structured, redacted logs, request/diagnostic IDs,
health/readiness endpoints, and bounded Prometheus metrics. Production NGINX
does not expose `/metrics`; direct metrics access is controlled by the API's
configured authentication/IP policy. See [configuration](configuration.md) and
the [metrics runbook](runbooks/metrics-alert-thresholds.md).

`services/observability.py` contains a bounded SLO catalog, safe-label helper,
and reconciliation planner with unit coverage. It is not wired to an exporter,
dashboard, paging service, or scheduler. There is no OpenTelemetry dependency,
OTLP setting, or OTLP runtime export in the current repository.

## Multi-worker metrics aggregation

The shipped dev and production topologies run the API under gunicorn with two
Uvicorn workers in one container. Both compose topologies set
`PROMETHEUS_MULTIPROC_DIR` to a `tmpfs` mount on the `api` service (shared
by the forked worker processes of that container), so prometheus_client's
multiprocess mode is active in the API
worker group: each worker writes its counter/histogram updates to
per-process files in the shared directory, and a single
`MultiProcessCollector` exposes the **aggregate of all live API workers**
under the original metric names (e.g. `gateway_http_requests_total`,
`gateway_provider_requests_total`, `gateway_tokens_total`,
`gateway_cost_eur_total`). A single authorized `/metrics` scrape therefore
reflects the whole worker group deterministically, regardless of which
worker serves the scrape.

On graceful worker exit (SIGTERM), each API worker process removes its own
per-process files during the application lifespan shutdown (wired in
`slaif_gateway.main`), which is the shutdown phase that deterministically
runs under the shipped UvicornWorker topology: after the graceful shutdown
uvicorn re-raises the captured SIGTERM under the restored default handler,
so the worker terminates by signal and neither `atexit` handlers nor
gunicorn's `worker_exit` hook can execute there. Gunicorn 26.x has no CLI
flag for the hook; `slaif_gateway.metrics.on_worker_exit` remains its
entry point for config-file deployments whose workers exit through a
normal interpreter shutdown (e.g. sync workers), and an
`atexit`-registered call of the same cleanup covers those normal-exit
paths. A worker killed with SIGKILL leaves its files behind; stale files
can only inflate, never zero or reduce, the aggregate, so scrape
determinism is unaffected (each Compose project gets a fresh tmpfs
mount at container start). The `/metrics` authentication/IP policy is unchanged by this.

Boundary: Celery worker and scheduler processes are not part of the API
worker group. Their `slaif_gateway.metrics` updates (e.g. reconciliation
counters) remain per-process in memory and are not aggregated or exposed;
that boundary is pre-existing and out of scope for the API metrics surface.

No prompt, completion, tool result, credential, or raw request/provider body is
intended for logs or metrics. That privacy boundary remains mandatory for any
future telemetry integration.

## Operator request capture (default OFF)

The optional operator request-capture facility is the single explicit,
human-authorized exception to the no-request-content rule above, and it is
bounded in every other respect:

- **Off unless armed.** No request content is ever written unless
  `REQUEST_CAPTURE_ENABLED=true` was loaded by the worker at start **and** an
  operator has armed a finite, expiring window for an exact endpoint.
- **Masked.** Known incoming authentication values are substituted in every
  stored byte; the full prompt/tool material itself is the
  operator-authorized consent for the finite armed window.
- **Collection is bounded; retention is explicit.** The armed window bounds
  how many requests are *collected* (finite count and absolute TTL).
  Collected artifacts persist on disk until the operator explicitly
  stops/cleans the session; expiry and exhaustion end collection only, they
  never delete retained artifacts.
- **Incomplete never persisted.** A body that was not fully captured stores
  zero body bytes plus precise counts and a stable
  `body_omitted_for_secret_safety` note.
- **Correlated and inspectable.** Each artifact pair (capture + record) is
  keyed by the `X-SLAIF-Diagnostic-ID` gateway request ID. The `0700`/`0600`
  file permissions are the access boundary (the owning OS user and root can
  read the files directly); the explicit
  `slaif-gateway request-capture inspect --request-id` command is the bounded,
  size-capped convenience path for operators. The record carries the public
  error code/param/message/status and, where the gateway selected one, the
  client-module id/version/digest.
- **No new telemetry channels.** No database schema, admin UI surface, remote
  export, or metric is introduced, and captured content is never written to
  logs (only safe, fixed, content-free startup/facility warnings exist).
  Storage is the operator's local directory with `0700`/`0600` modes and
  finite budgets.

Configuration and operator procedure: [configuration.md](configuration.md)
(Operator Request Capture) and
[runbooks/incoming-request-capture.md](runbooks/incoming-request-capture.md).

## Request failure diagnostics (default OFF)

The content-free request-failure diagnostics facility is a bounded
operational index for FAILED terminal `/v1` outcomes — it deliberately adds
NO new telemetry channels and stores NO request content:

- **Failure-only, content-free.** At most one bounded typed record per
  failed request: the public error code/param, the bounded classifier
  reason, actual observed numeric decision facts (e.g. context-window
  estimate/context/ceiling and output allowance for Codex rejections),
  route identity (configured pattern/UUID only — never a raw model suffix
  or URL value), key identity where auth succeeded, deployment revision,
  and the actual observed wire status/stream outcome. No bodies, prompts,
  tool arguments/results, media, headers, queries, raw paths, or
  credentials. Unknown fact FIELDS drop the write (never guessed), while
  unsafe optional code/reason/param PATH VALUES are projected to
  unavailable with the remaining failure facts preserved. The serialized
  record is hard-bounded to 8 KiB. Successful completions produce no
  record.
- **Correlated by diagnostic ID.** Every `/v1` response carries
  `X-SLAIF-Diagnostic-ID`; a recorded failure is retrievable with
  `slaif-gateway diagnostics request show --request-id ...` (stable gateway
  ID or recorded client ID, explicit namespace, ambiguity bounded at 100).
  Lookup IDs never establish authentication authority.
- **Best effort; response decisions unchanged.** One awaited write at
  terminal outcome in an independent bounded transaction under the
  configured write timeout; the awaited write may add bounded completion
  latency (up to the write timeout plus bounded cleanup), but any write
  failure (timeout, capacity, unavailable store) drops the record without
  changing the response, admission, accounting, or cancellation. There is
  no background expiry daemon: expired rows are pruned on writes and by
  `diagnostics cleanup`.
- **Log-binding protection.** Known incoming authentication aliases copied
  into the request-ID log binding are masked/omitted at the log boundary
  (the wire `X-Request-ID` echo and auth decisions are unchanged); this
  reuses the existing redaction primitives and is known-shape protection,
  not universal content sanitization.
- **Independent of capture.** The facility is default OFF, complements —
  and can never replace or arm — the operator request-capture facility,
  which remains the only request-content exception.

Configuration: [configuration.md](configuration.md) (Request Failure
Diagnostics, default OFF). Verification:
[verification/2026-10-29-cli-request-diagnostics.md](verification/2026-10-29-cli-request-diagnostics.md).
