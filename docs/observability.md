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

No prompt, completion, tool result, credential, or raw request/provider body is
intended for logs or metrics. That privacy boundary remains mandatory for any
future telemetry integration.
