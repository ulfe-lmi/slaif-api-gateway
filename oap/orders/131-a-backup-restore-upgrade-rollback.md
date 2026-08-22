# OAP Work Order — 131-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/131-backup-restore-upgrade-rollback`
Base: main @ b12a9a38d981

## Objective and reason

Prove backup, restore, upgrade, and rollback/forward-recovery so the
organization deployment is recoverable rather than an irreplaceable hand-built
server. Tests restoration of identities, policies, budgets, accounting, holds,
audit, and provider metadata without plaintext secrets.

## Verified state

- main = b12a9a38d981; no open non-Dependabot PR.
- Objectives 118–130 merged. Phase 3+4 gates passed, Phase 5 underway.
- Docker Compose with PostgreSQL, Redis, API worker already operational.

## Scope

1. PostgreSQL backup/restore:
   - Documented pg_dump/pg_restore procedure for full and incremental backups.
   - Restore verification script checking row counts, integrity, readiness.
   - Secret/key-version handling (HMAC keys, encryption keys) in backup metadata.
2. Upgrade rehearsal:
   - Alembic migration preflight checks before applying.
   - Forward-recovery path when rollback is not possible (irreversible migrations).
   - Versioned upgrade documentation with explicit pre/post conditions.
3. Generated artifact exclusions:
   - `.local-provider-catalog/` excluded from backup truth.
   - Temporary files, logs excluded from restore verification.
4. Operator runbooks:
   - Backup creation, restore procedure, upgrade rehearsal, rollback decision tree.

## Exact requirements

1. A clean environment restores a representative SME dataset and passes integrity/readiness checks.
2. Upgrade failure has a tested recovery path and honest migration constraints.
3. Runbooks include RPO/RTO evidence without contractual SLA claims.
4. No production backup target mutation or automatic destructive rollback.
5. No promise that irreversible migrations reverse.

## Allowed paths

```
docs/backup-restore.md
docs/upgrade-runbook.md
scripts/backup.sh
scripts/restore.sh
scripts/verify_restore.py
tests/integration/test_backup_restore_postgres.py
oap/orders/131-a-backup-restore-upgrade-rollback.md
oap/reports/131-a-backup-restore-upgrade-rollback.md
oap/active
```

## Non-goals

No production backup target mutation. No automatic destructive rollback.
No cross-region service. No promise that irreversible migrations reverse.

## Observable acceptance

- Backup → destroy → restore → verify cycle completes successfully.
- Upgrade rehearsal documented with forward-recovery path.
- Runbooks include RPO/RTO evidence.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_backup_restore_postgres.py
bash scripts/backup.sh && bash scripts/restore.sh && python scripts/verify_restore.py
git diff --check
```

## Boundaries

Non-production only. Provider credentials never exposed. Disposable environment only.

## OAP contract

Objective 131-a creates one PR; remediation uses 131-b–z same PR.
Coding agent never merges.
