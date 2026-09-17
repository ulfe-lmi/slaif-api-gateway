"""Prometheus metrics for the implemented gateway path.

Multi-worker (gunicorn) deployments set ``PROMETHEUS_MULTIPROC_DIR`` to a
directory shared by all API worker processes (a tmpfs mount in the
shipped Compose topologies). In that mode prometheus_client's mmap-based
multiprocess mode is used: metric objects are created without registering
them on a registry, and a single ``MultiProcessCollector`` exposes the
aggregated samples of every live worker under the original metric names
(a registered metric object and the shared-directory collector cannot
coexist in one registry). Without the environment variable the previous
single-process behavior is unchanged (unit tests, CLI, Celery processes).
"""

from __future__ import annotations

import atexit
import glob
import os
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Histogram, generate_latest

# ---------------------------------------------------------------------------
# Multiprocess (multi-worker) wiring.
#
# The shipped dev and production topologies run the API under gunicorn with
# two Uvicorn workers in one container. prometheus_client (0.26.x,
# mmap-based multiprocess mode) aggregates the per-worker metric files in
# PROMETHEUS_MULTIPROC_DIR through a MultiProcessCollector; per-process
# identity lives in the mmap file names (``counter_<pid>.db``), not in the
# sample names, so the exposition keeps the original metric names.
# ---------------------------------------------------------------------------
_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR")

if _MULTIPROC_DIR and not os.path.isdir(_MULTIPROC_DIR):
    raise RuntimeError(
        "PROMETHEUS_MULTIPROC_DIR is set but is not a directory; mount the "
        "shared API metrics volume before starting the gateway"
    )


def _counter(name: str, documentation: str, labelnames: tuple[str, ...]) -> Counter:
    return Counter(name, documentation, labelnames, registry=None if _MULTIPROC_DIR else REGISTRY)


def _histogram(name: str, documentation: str, labelnames: tuple[str, ...]) -> Histogram:
    return Histogram(name, documentation, labelnames, registry=None if _MULTIPROC_DIR else REGISTRY)


HTTP_REQUESTS = _counter(
    "gateway_http_requests_total",
    "HTTP requests handled by the gateway.",
    ("method", "endpoint", "status"),
)
HTTP_REQUEST_DURATION = _histogram(
    "gateway_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "endpoint"),
)
AUTH_FAILURES = _counter(
    "gateway_auth_failures_total",
    "Authentication failures by error code.",
    ("error_code",),
)
QUOTA_REJECTIONS = _counter(
    "gateway_quota_rejections_total",
    "Quota rejections.",
    ("error_code",),
)
PROVIDER_REQUESTS = _counter(
    "gateway_provider_requests_total",
    "Upstream provider requests.",
    ("provider", "endpoint", "status"),
)
PROVIDER_REQUEST_DURATION = _histogram(
    "gateway_provider_request_duration_seconds",
    "Upstream provider request duration in seconds.",
    ("provider", "endpoint"),
)
PROVIDER_HTTP_ERRORS = _counter(
    "gateway_provider_http_errors_total",
    "Upstream provider HTTP errors.",
    ("provider", "endpoint", "status_class"),
)
PROVIDER_DIAGNOSTICS_GENERATED = _counter(
    "gateway_provider_diagnostics_generated_total",
    "Sanitized provider diagnostics generated.",
    ("provider", "endpoint"),
)
TOKENS_TOTAL = _counter(
    "gateway_tokens_total",
    "Provider-reported token totals.",
    ("provider", "model", "token_type"),
)
COST_EUR_TOTAL = _counter(
    "gateway_cost_eur_total",
    "Gateway-accounted cost in EUR.",
    ("provider", "model"),
)
ACCOUNTING_FAILURES = _counter(
    "gateway_accounting_failures_total",
    "Accounting failures by error code.",
    ("error_code",),
)
RATE_LIMIT_REJECTIONS = _counter(
    "gateway_rate_limit_rejections_total",
    "Redis-backed operational rate-limit rejections.",
    ("error_code",),
)
RATE_LIMIT_RELEASE_FAILURES = _counter(
    "gateway_rate_limit_release_failures_total",
    "Redis-backed concurrency release failures.",
    ("error_code",),
)
RATE_LIMIT_HEARTBEAT_FAILURES = _counter(
    "gateway_rate_limit_heartbeat_failures_total",
    "Redis-backed concurrency heartbeat failures.",
    ("error_code",),
)
RECONCILIATION_BACKLOG = _counter(
    "gateway_reconciliation_backlog_total",
    "Reconciliation backlog items observed by type.",
    ("type",),
)
RECONCILIATION_RUNS = _counter(
    "gateway_reconciliation_runs_total",
    "Reconciliation task runs by type, status, and dry-run mode.",
    ("type", "status", "dry_run"),
)
RECONCILIATION_ITEMS = _counter(
    "gateway_reconciliation_items_total",
    "Reconciliation items handled by type, status, and dry-run mode.",
    ("type", "status", "dry_run"),
)
RECONCILIATION_ALERTS = _counter(
    "gateway_reconciliation_alerts_total",
    "Reconciliation alert delivery attempts by status.",
    ("status",),
)
RECONCILIATION_ALERT_FAILURES = _counter(
    "gateway_reconciliation_alert_failures_total",
    "Failed reconciliation alert deliveries.",
    (),
)


if _MULTIPROC_DIR:
    from prometheus_client.multiprocess import MultiProcessCollector

    MultiProcessCollector(REGISTRY)


def _remove_multiproc_files_for_pid(pid: int) -> None:
    """Remove one process's multiprocess metric files from the shared dir."""
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if not path:
        return
    for filename in glob.glob(os.path.join(path, f"*_{pid}.db")):
        try:
            os.remove(filename)
        except OSError:
            pass


def cleanup_multiproc_metrics() -> None:
    """Remove this process's multiprocess metric files from the shared dir.

    The pid is resolved at call time, not registration time: gunicorn
    imports the application in the master process and forks the workers, so
    a pid captured at registration time would be the master's pid in every
    inherited handler. This is a no-op when ``PROMETHEUS_MULTIPROC_DIR`` is
    unset.
    """
    _remove_multiproc_files_for_pid(os.getpid())


def on_worker_exit(server: Any = None, worker: Any = None) -> None:
    """gunicorn ``worker_exit`` hook entry point (config-file deployments).

    Gunicorn 26.x exposes no CLI flag for the ``worker_exit`` hook, and in
    the shipped UvicornWorker topology the hook does not run on graceful
    SIGTERM: after the graceful shutdown uvicorn re-raises the captured
    SIGTERM under the restored default handler, so the worker terminates by
    signal before gunicorn's worker-exit finally block (and any ``atexit``
    handler) can execute. The application lifespan shutdown (wired in
    ``slaif_gateway.main``) is the reliable cleanup point there; this hook
    covers config-file deployments whose workers exit through a normal
    interpreter shutdown (e.g. gunicorn sync workers). A SIGKILL terminates
    a process before any mechanism can run; stale files then persist but
    can only inflate, never zero or reduce, the aggregate.
    """
    cleanup_multiproc_metrics()


if _MULTIPROC_DIR:
    atexit.register(cleanup_multiproc_metrics)


def prometheus_response_body() -> bytes:
    """Return metrics in Prometheus text exposition format."""
    return generate_latest()


def prometheus_content_type() -> str:
    """Return Prometheus text exposition content type."""
    return CONTENT_TYPE_LATEST


def observe_http_request(*, method: str, endpoint: str, status_code: int, duration_seconds: float) -> None:
    """Record a completed HTTP request."""
    HTTP_REQUESTS.labels(
        method=method.upper(),
        endpoint=endpoint,
        status=str(status_code),
    ).inc()
    HTTP_REQUEST_DURATION.labels(method=method.upper(), endpoint=endpoint).observe(duration_seconds)


async def observe_provider_call(
    *,
    provider: str,
    endpoint: str,
    call: Callable[[], Any],
):
    """Run and record a non-streaming provider call."""
    start = time.perf_counter()
    try:
        response = await call()
    except Exception:
        PROVIDER_REQUESTS.labels(provider=provider, endpoint=endpoint, status="error").inc()
        PROVIDER_REQUEST_DURATION.labels(provider=provider, endpoint=endpoint).observe(
            time.perf_counter() - start
        )
        raise

    PROVIDER_REQUESTS.labels(provider=provider, endpoint=endpoint, status="success").inc()
    PROVIDER_REQUEST_DURATION.labels(provider=provider, endpoint=endpoint).observe(
        time.perf_counter() - start
    )
    return response


def record_provider_call_result(
    *,
    provider: str,
    endpoint: str,
    status: str,
    duration_seconds: float,
) -> None:
    """Record a provider call whose execution is managed by the caller."""
    PROVIDER_REQUESTS.labels(provider=provider, endpoint=endpoint, status=status).inc()
    PROVIDER_REQUEST_DURATION.labels(provider=provider, endpoint=endpoint).observe(duration_seconds)


def increment_provider_http_error(
    *,
    provider: str,
    endpoint: str,
    upstream_status_code: int | None,
) -> None:
    """Record an upstream HTTP error with low-cardinality status class."""
    PROVIDER_HTTP_ERRORS.labels(
        provider=provider,
        endpoint=endpoint,
        status_class=_status_class(upstream_status_code),
    ).inc()


def increment_provider_diagnostic_generated(*, provider: str, endpoint: str) -> None:
    """Record generation of sanitized provider diagnostics."""
    PROVIDER_DIAGNOSTICS_GENERATED.labels(provider=provider, endpoint=endpoint).inc()


def increment_auth_failure(error_code: str | None) -> None:
    """Record an auth failure with a low-cardinality error code."""
    AUTH_FAILURES.labels(error_code=error_code or "unknown").inc()


def increment_quota_rejection(error_code: str | None) -> None:
    """Record a quota rejection with a low-cardinality error code."""
    QUOTA_REJECTIONS.labels(error_code=error_code or "unknown").inc()


def increment_accounting_failure(error_code: str | None) -> None:
    """Record an accounting failure with a low-cardinality error code."""
    ACCOUNTING_FAILURES.labels(error_code=error_code or "unknown").inc()


def increment_rate_limit_rejection(error_code: str | None) -> None:
    """Record an operational rate-limit rejection with a low-cardinality error code."""
    RATE_LIMIT_REJECTIONS.labels(error_code=error_code or "unknown").inc()


def increment_rate_limit_release_failure(error_code: str | None) -> None:
    """Record a concurrency release failure with a low-cardinality error code."""
    RATE_LIMIT_RELEASE_FAILURES.labels(error_code=error_code or "unknown").inc()


def increment_rate_limit_heartbeat_failure(error_code: str | None) -> None:
    """Record a concurrency heartbeat failure with a low-cardinality error code."""
    RATE_LIMIT_HEARTBEAT_FAILURES.labels(error_code=error_code or "unknown").inc()


def observe_reconciliation_backlog(*, reconciliation_type: str, count: int) -> None:
    """Record a low-cardinality reconciliation backlog observation."""
    if count <= 0:
        return
    RECONCILIATION_BACKLOG.labels(type=reconciliation_type).inc(count)


def increment_reconciliation_run(
    *,
    reconciliation_type: str,
    status: str,
    dry_run: bool,
) -> None:
    """Record a reconciliation task run."""
    RECONCILIATION_RUNS.labels(
        type=reconciliation_type,
        status=status,
        dry_run=str(dry_run).lower(),
    ).inc()


def add_reconciliation_items(
    *,
    reconciliation_type: str,
    status: str,
    dry_run: bool,
    count: int,
) -> None:
    """Record the number of reconciliation items handled."""
    if count <= 0:
        return
    RECONCILIATION_ITEMS.labels(
        type=reconciliation_type,
        status=status,
        dry_run=str(dry_run).lower(),
    ).inc(count)


def increment_reconciliation_alert(*, status: str) -> None:
    """Record a reconciliation alert result with low-cardinality status."""
    RECONCILIATION_ALERTS.labels(status=status).inc()
    if status == "failure":
        RECONCILIATION_ALERT_FAILURES.inc()


def add_tokens(*, provider: str, model: str, token_type: str, count: int | None) -> None:
    """Record provider usage token counts when available."""
    if count is None or count <= 0:
        return
    TOKENS_TOTAL.labels(provider=provider, model=model, token_type=token_type).inc(count)


def add_cost_eur(*, provider: str, model: str, cost_eur: Decimal | None) -> None:
    """Record finalized EUR cost when available."""
    if cost_eur is None or cost_eur <= 0:
        return
    COST_EUR_TOTAL.labels(provider=provider, model=model).inc(float(cost_eur))


def _status_class(status_code: int | None) -> str:
    if status_code is None:
        return "unknown"
    if status_code < 100 or status_code > 599:
        return "unknown"
    return f"{status_code // 100}xx"
