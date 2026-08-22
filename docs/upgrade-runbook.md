# Upgrade rehearsal, rollback, and forward recovery

Before upgrade: snapshot PostgreSQL, run Alembic preflight (`alembic history`,
`alembic heads`, and migration review), verify backup restore in a disposable
target, and record application/schema versions.

Rollback is possible only when migrations are reversible. If an irreversible or
data-transforming migration was applied, use the tested forward-recovery path:
fix forward with a corrective migration rather than pretending downgrade restores
semantic state. Never perform automatic destructive rollback.

Record RPO as time since last successful verified backup and RTO as measured
restore + verification duration. These are operational evidence only; no SLA
is claimed.
