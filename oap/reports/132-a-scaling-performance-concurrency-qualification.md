# OAP execution report — 132-a

Implementation head SHA: 10faf3d89081bb8380e90f62fc8a1ec461652e4d
Report publication commit: SELF

## Scope

Added bounded deterministic concurrency qualification profiles and sizing guidance:

- workshop burst: 10 concurrent reservations;
- SME daily load: 50 concurrent reservations;
- Codex loop: one sequential reservation.

Each profile uses PostgreSQL `SELECT ... FOR UPDATE`, rejects any projected
overspend, and asserts the final `used + reserved` total cannot exceed the limit.
`docs/sizing.md` maps profile to starting resource and pool guidance without
SLA or maximum-capacity claims.

## Verification

Focused suite against the safe disposable test database:

```text
PYTHONPATH=.:app TEST_DATABASE_URL="postgresql+asyncpg://slaif:slaif@localhost:15432/test_slaif_gateway" \
  .venv/bin/pytest -q tests/load/
# 4 passed
```

Ruff on changed paths passed. `git diff --check` passed. All ten final-head
GitHub checks were verified successful on implementation head
`10faf3d89081bb8380e90f62fc8a1ec461652e4d`.

## Honest limits

These are correctness-focused local concurrency tests, not internet-scale load,
multi-region, throughput benchmarking, or capacity certification. No accounting
bypass or fence bypass was introduced. PostgreSQL remains truth.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
