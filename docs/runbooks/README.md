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
