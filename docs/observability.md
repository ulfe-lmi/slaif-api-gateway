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
