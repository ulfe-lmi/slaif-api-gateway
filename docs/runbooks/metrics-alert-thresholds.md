# Metrics And Alert Thresholds

## Endpoint Security

`/metrics` exposes Prometheus text metrics when `ENABLE_METRICS=true`.
Production access is restricted by default through `METRICS_REQUIRE_AUTH`,
`METRICS_ALLOWED_IPS`, and `METRICS_PUBLIC_IN_PRODUCTION`. The provided Nginx
configuration denies `/metrics` by default.

Do not expose `/metrics` publicly. Use an internal network, allowlist, or an
authenticated metrics path supplied by the deployment environment.

## Recommended Alert Categories

- Readiness down: `/readyz` returns non-2xx or reports database, schema, Redis,
  or provider secret problems.
- Schema not current.
- Provider failures or provider latency increase.
- Quota rejection spike.
- Accounting/finalization failures.
- Reconciliation backlog.
- Reconciliation alert delivery failures.
- Redis unavailable when Redis-backed rate limits are enabled.
- DB pool timeout, statement timeout, or connection errors.
- Admin login brute-force lockouts.
- Ambiguous email delivery count.

## Starter Threshold Examples

These are examples, not universal truth. Tune them to normal traffic volume.

- `/readyz` failing for 2 consecutive minutes: page operator.
- Schema not current in production: page before accepting traffic.
- Provider 5xx or normalized provider errors above 5 percent for 5 minutes:
  investigate provider status and routing.
- Quota rejections above 3x normal baseline for 10 minutes: inspect whether a
  cohort exhausted limits or a client is looping.
- Any provider-completed finalization recovery backlog older than 5 minutes:
  investigate and run the provider-completed reconciliation runbook.
- Expired pending reservations above 0 for more than 15 minutes: run stale
  reservation dry-run.
- Redis unavailable for 2 minutes while `ENABLE_REDIS_RATE_LIMITS=true`:
  follow the Redis outage runbook.
- Any `ambiguous` email delivery: investigate recipient receipt or rotate the
  key.
- Admin login lockouts above baseline: review source IPs and consider ingress
  controls.

## Useful Metrics

Implemented metric families include provider requests, provider latency,
provider HTTP errors, sanitized provider diagnostics, quota rejections,
rate-limit rejections, rate-limit release/heartbeat failures, token totals, EUR
cost totals, reconciliation backlog, reconciliation runs, reconciliation items,
and reconciliation alerts.

## Tuning

Start with low-noise thresholds in staging. Record baseline traffic by endpoint,
provider, model, and institution/cohort before paging on spikes. Separate pages
from tickets: not every quota rejection needs a page, but every accounting
failure deserves operator visibility.

## Webhook Reconciliation Alerts

Optional generic reconciliation webhooks are disabled by default. They are sent
from backlog inspection only and do not mutate quota/accounting. Payloads are
counts-only by default; safe IDs are included only when
`RECONCILIATION_ALERT_INCLUDE_IDS=true`.

Treat webhook URLs as secrets if they contain tokens.

## Redaction Expectations

Logs and metrics must not contain plaintext gateway keys, provider keys,
passwords, token hashes, encrypted payloads, nonces, prompts, completions, email
bodies, session tokens, or bearer tokens.
