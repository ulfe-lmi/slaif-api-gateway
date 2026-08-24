# Verification Evidence

This directory indexes durable verification records for specific repository
commits and execution environments. A record describes what one bounded run
actually proved; it is not permanent certification of later commits, production
fitness, security, compliance, provider behavior, or scale.

- [`2026-08-17 current-main baseline`](2026-08-17-current-main-baseline.md) —
  one 24-worker full current-machine matrix, classified `RESULT=FAIL` because
  one of 2,534 tests failed. The separate post-PR-220 128-worker HPC
  qualification remains not run.
- [`2026-08-24 production-appliance qualification`](2026-08-24-production-appliance-qualification.md)
  — disposable production Compose, NGINX/TLS, PostgreSQL, Redis, worker/
  scheduler, provider-double, accounting, failure, privacy, persistence,
  backup/restore, and cleanup evidence for the named candidate. It is not a real-
  provider run, release decision, security certification, or production approval.
- [`2026-08-24 documentation architecture and truth audit`](2026-08-24-documentation-audit.md)
  — repository-wide cross-document and documentation-versus-code baseline for
  the documentation-modernization PR.
