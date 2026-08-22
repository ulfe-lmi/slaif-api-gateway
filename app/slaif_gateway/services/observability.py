"""Safe metadata-only SME observability, SLO evaluation, and alerting model."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal


Comparison = Literal["<=", ">="]


@dataclass(frozen=True, slots=True)
class SLO:
    key: str
    metric: str
    threshold: float
    comparison: Comparison
    runbook: str


@dataclass(frozen=True, slots=True)
class Alert:
    slo_key: str
    observed_value: float
    threshold: float
    comparison: Comparison
    request_id: str | None
    runbook: str


SLO_CATALOG: tuple[SLO, ...] = (
    SLO("availability", "gateway_uptime_ratio", 0.995, ">=", "runbook:availability"),
    SLO("provider_errors", "provider_5xx_rate", 0.01, ">=", "runbook:provider-errors"),
    SLO("responses_latency_p95_ms", "responses_latency_p95_ms", 2500.0, "<=", "runbook:latency"),
    SLO("quota_rejections", "quota_rejection_rate", 0.05, "<=", "runbook:quota"),
    SLO("reconciliation_lag", "reconciliation_pending_count", 100.0, "<=", "runbook:reconciliation"),
    SLO("background_failures", "background_job_failure_rate", 0.02, "<=", "runbook:background-jobs"),
)


def evaluate_slos(metrics: Mapping[str, float], *, request_id: str | None = None) -> list[Alert]:
    """Evaluate bounded SLO catalog and return metadata-only breach alerts."""
    alerts: list[Alert] = []
    for slo in SLO_CATALOG:
        observed = metrics.get(slo.metric)
        if observed is None:
            continue
        breached = (
            observed <= slo.threshold if slo.comparison == "<="
            else observed >= slo.threshold
        )
        if breached:
            alerts.append(
                Alert(
                    slo_key=slo.key,
                    observed_value=float(observed),
                    threshold=float(slo.threshold),
                    comparison=slo.comparison,
                    request_id=request_id,
                    runbook=slo.runbook,
                )
            )
    return alerts


def sanitize_metric_labels(labels: Mapping[str, object]) -> dict[str, str]:
    """Keep only bounded safe labels to avoid unbounded telemetry cardinality."""
    allowed = {"provider", "endpoint", "status_class", "model"}
    result: dict[str, str] = {}
    for key in allowed:
        value = labels.get(key)
        if isinstance(value, str) and len(value) <= 128:
            result[key] = value
    return result


def reconciliation_plan(rows: Iterable[Mapping[str, object]], *, now) -> dict[str, int]:
    """Classify pending holds into bounded reconciliation actions."""
    plan = {"finalize": 0, "release": 0}
    for row in rows:
        status = row.get("status")
        expires_at = row.get("expires_at")
        if status != "pending":
            continue
        if expires_at is not None and getattr(expires_at, "tzinfo", None) is not None and expires_at < now:
            plan["release"] += 1
        else:
            plan["finalize"] += 1
    return plan
