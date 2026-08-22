# Observability, SLOs, alerts, and reconciliation

SLAIF exposes metadata-only operational telemetry. The bounded SLO catalog
covers availability, provider errors, Responses latency p95, quota rejection,
reconciliation lag, and background job failures. Alerts include safe request IDs
and runbook links; labels are allow-listed to prevent unbounded cardinality.

Reconciliation classifies expired pending holds for release and active pending
holds for finalize/review in PostgreSQL. OTLP export is operator opt-in and
metadata-only. No prompt, completion, tool result, credential, or raw content is
telemetered.
