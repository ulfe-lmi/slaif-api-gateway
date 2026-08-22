# OAP execution report — 129-a

Implementation head SHA: b977de56932701422ecfaacbd8fcd9485e38d156
Report publication commit: SELF

## Scope

Added a hostile negative invariant suite and mapped invariant matrix for the
single-organization SME boundary model:

- cross-unit catalog drift fails closed;
- stale provider governance evidence blocks alternate routes;
- abuse/privilege retry ceiling holds;
- admin redirect escape is rejected;
- UUID aliasing does not bypass explicit scope allow-lists;
- auditor/manager/service-account role ceilings are negative-tested;
- PostgreSQL accounting constraints reject non-negative limit violations.

## Verification

Focused unit suite:

```text
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_boundary_invariants.py
# 8 passed
```

Focused PostgreSQL integration suite used the configured safe test database:

```text
PYTHONPATH=.:app TEST_DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway" \
  .venv/bin/pytest -q tests/integration/test_boundary_invariants_postgres.py
# 1 passed
```

Ruff on changed paths passed. `git diff --check` passed.

All ten final-head GitHub checks were verified successful on implementation head
`b977de56932701422ecfaacbd8fcd9485e38d156`.

## Honest limits

No claim is made of hostile public multi-tenancy, PostgreSQL row-level security,
complete authorization proof, penetration testing, or production certification.
The SME MVP remains one organization per deployment.

## Privacy/accounting evidence

Tests use synthetic UUIDs, local policy objects, and disposable PostgreSQL
schema probes. No prompt/completion content or provider credentials were stored.
PostgreSQL remains accounting truth.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
