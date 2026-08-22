# OAP Work Order — 130-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/130-observability-slos-alerts-reconciliation`
Base: main @ 4edae1f52c30

## Objective and reason

Implement SME observability, SLOs, alerts, and reconciliation operations so
safe telemetry becomes actionable operation without exposing content or secrets.
This begins Phase 5 (operations/deployment).

## Verified state

- main = 4edae1f52c30; no open non-Dependabot PR.
- Objectives 118–129 merged (Phase 3 and Phase 4 gates passed).
- Existing metrics: basic request counting in usage_ledger.
- Redis rate limiting already operational.

## Scope

1. SLO definitions and metrics:
   - Availability: gateway uptime, provider reachability.
   - Latency: p50/p95/p99 for chat/responses endpoints.
   - Provider errors: 4xx/5xx rates per provider.
   - Quota rejections, holds, reconciliation lag.
   - Background job success/failure rates.
2. Alerting:
   - Alert thresholds for each SLO breach category.
   - Runbook links in alert metadata.
   - Safe correlation IDs (request_id) in alert payloads.
3. Dashboards:
   - Admin dashboard showing current SLO status.
4. Reconciliation scheduling:
   - Periodic reconciliation of pending holds and stale reservations.
5. OpenTelemetry/SIEM integration:
   - Metadata-only OTLP export with explicit operator opt-in.

## Exact requirements

1. Operators can detect and diagnose every material SME failure mode from redacted metadata.
2. Alerts link to tested runbooks and avoid unbounded cardinality.
3. Telemetry failures do not corrupt request/accounting correctness.
4. No raw prompt/tool/result telemetry.

## Allowed paths

```
app/slaif_gateway/services/observability.py
app/slaif_gateway/api/admin.py
tests/unit/test_observability*.py
tests/integration/test_observability*_postgres.py
docs/observability.md
oap/orders/130-a-observability-slos-alerts-reconciliation.md
oap/reports/130-a-observability-slos-alerts-reconciliation.md
oap/active
```

## Non-goals

No raw prompt/tool/result telemetry. No public metrics. No hosted telemetry requirement. No false uptime SLA.

## Observable acceptance

- Metrics are collected for all defined SLO categories.
- Alerts fire when thresholds are breached with runbook links.
- Reconciliation scheduling works correctly.
- OTLP export is opt-in only and metadata-safe.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_observability*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_observability*_postgres.py
git diff --check
```

## Boundaries

PostgreSQL-only truth. No content storage. Provider credentials never exposed. Non-production only.

## OAP contract

Objective 130-a creates one PR; remediation uses 130-b–z same PR.
Coding agent never merges.
