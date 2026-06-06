# Operator Runbooks

These runbooks are for RC-beta, pre-production, and production-like SLAIF API
Gateway deployments. They are practical operator guides for responding to
incidents and maintenance events in the current implemented system.

They are not a replacement for operator judgment, a formal security
certification, a compliance attestation, or a penetration-test report. Verify
the target environment before running destructive commands. Never use
`DATABASE_URL` for destructive test setup; use an explicit disposable database
through `TEST_DATABASE_URL` or a separately created restore target.

Do not paste real provider keys, gateway keys, SMTP passwords, webhook URLs with
tokens, HMAC secrets, one-time-secret encryption keys, session secrets, database
passwords, or bearer tokens into tickets, logs, Slack, GitHub, screenshots, or
audit reasons. Prefer safe identifiers such as UUIDs, public key IDs, request
IDs, delivery IDs, provider names, redacted values, and timestamps.

Admin pages may show a diagnostic/reference ID such as `gw-...` when an action
fails. Use that ID to search operator-side logs, for example
`docker compose logs api | rg '<diagnostic-id>'`. Production should normally use
`LOG_LEVEL=INFO` with `STRUCTURED_LOGS=true`; for local diagnostics, temporarily
use `LOG_LEVEL=DEBUG`, `STRUCTURED_LOGS=false`, `GUNICORN_LOG_LEVEL=debug`, and
`CELERY_LOG_LEVEL=DEBUG`. Logs are redacted, but they are not a dashboard-facing
secret store.

Runbooks:

- [Provider key rotation](provider-key-rotation.md)
- [Gateway key leak response](gateway-key-leak.md)
- [HMAC secret rotation](hmac-secret-rotation.md)
- [One-time-secret encryption key handling](one-time-secret-encryption-key.md)
- [Database backup and restore](database-backup-restore.md)
- [Stale reservation reconciliation](stale-reservation-reconciliation.md)
- [Provider-completed finalization recovery](provider-completed-reconciliation.md)
- [Ambiguous email delivery handling](ambiguous-email-delivery.md)
- [Redis outage and rate-limit degradation](redis-outage.md)
- [PostgreSQL pool exhaustion and readiness failure](postgresql-pool-readiness.md)
- [Metrics and alert thresholds](metrics-alert-thresholds.md)
- [Docker and Nginx troubleshooting](docker-nginx-troubleshooting.md)
- [Admin access and lockout](admin-access.md)
- [RC-beta upgrade checklist](rc-beta-upgrade.md)
- [HPC verification and local tool bootstrap](../testing-hpc.md)
  documents the Codex-inside-HPC workflow, user-local PostgreSQL/Redis/Compose
  provisioning, and the two-table validation/test-suite summary format.
