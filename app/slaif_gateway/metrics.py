"""Prometheus metrics for the implemented gateway path."""

from __future__ import annotations

import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "gateway_http_requests_total",
    "HTTP requests handled by the gateway.",
    ("method", "endpoint", "status"),
)
HTTP_REQUEST_DURATION = Histogram(
    "gateway_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "endpoint"),
)
AUTH_FAILURES = Counter(
    "gateway_auth_failures_total",
    "Authentication failures by error code.",
    ("error_code",),
)
QUOTA_REJECTIONS = Counter(
    "gateway_quota_rejections_total",
    "Quota rejections.",
    ("error_code",),
)
PROVIDER_REQUESTS = Counter(
    "gateway_provider_requests_total",
    "Upstream provider requests.",
    ("provider", "endpoint", "status"),
)
PROVIDER_REQUEST_DURATION = Histogram(
    "gateway_provider_request_duration_seconds",
    "Upstream provider request duration in seconds.",
    ("provider", "endpoint"),
)
PROVIDER_HTTP_ERRORS = Counter(
    "gateway_provider_http_errors_total",
    "Upstream provider HTTP errors.",
    ("provider", "endpoint", "status_class"),
)
PROVIDER_DIAGNOSTICS_GENERATED = Counter(
    "gateway_provider_diagnostics_generated_total",
    "Sanitized provider diagnostics generated.",
    ("provider", "endpoint"),
)
TOKENS_TOTAL = Counter(
    "gateway_tokens_total",
    "Provider-reported token totals.",
    ("provider", "model", "token_type"),
)
COST_EUR_TOTAL = Counter(
    "gateway_cost_eur_total",
    "Gateway-accounted cost in EUR.",
    ("provider", "model"),
)
ACCOUNTING_FAILURES = Counter(
    "gateway_accounting_failures_total",
    "Accounting failures by error code.",
    ("error_code",),
)
RATE_LIMIT_REJECTIONS = Counter(
    "gateway_rate_limit_rejections_total",
    "Redis-backed operational rate-limit rejections.",
    ("error_code",),
)
RATE_LIMIT_RELEASE_FAILURES = Counter(
    "gateway_rate_limit_release_failures_total",
    "Redis-backed concurrency release failures.",
    ("error_code",),
)
RATE_LIMIT_HEARTBEAT_FAILURES = Counter(
    "gateway_rate_limit_heartbeat_failures_total",
    "Redis-backed concurrency heartbeat failures.",
    ("error_code",),
)
RECONCILIATION_BACKLOG = Counter(
    "gateway_reconciliation_backlog_total",
    "Reconciliation backlog items observed by type.",
    ("type",),
)
RECONCILIATION_RUNS = Counter(
    "gateway_reconciliation_runs_total",
    "Reconciliation task runs by type, status, and dry-run mode.",
    ("type", "status", "dry_run"),
)
RECONCILIATION_ITEMS = Counter(
    "gateway_reconciliation_items_total",
    "Reconciliation items handled by type, status, and dry-run mode.",
    ("type", "status", "dry_run"),
)


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
