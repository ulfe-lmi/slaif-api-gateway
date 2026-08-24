# Upgrade, rollback, and forward recovery

> **Status:** Current lifecycle principles
> **Procedure:** Use the [RC-beta upgrade checklist](runbooks/rc-beta-upgrade.md)
> for executable steps

## Before changing a deployment

1. Pin the candidate tag or full commit and review its release notes and
   migration diff.
2. Snapshot PostgreSQL and preserve every secret version needed to validate
   existing gateway keys or decrypt pending one-time delivery.
3. Run `alembic history` and `alembic heads`; confirm the candidate has one
   expected head.
4. Restore the backup into an explicitly disposable target and run
   `scripts/verify_restore.py`.
5. Rehearse the upgrade with the same Compose profiles and operator settings as
   the target deployment.

## Recovery decision

Application rollback is safe only when no incompatible migration or semantic
data transformation has occurred. If migration downgrade is explicitly
supported, test it against a disposable copy before relying on it. Otherwise:

- restore the pre-upgrade database and matching application together; or
- fix forward with a reviewed corrective migration.

Never pair an older application with a newer schema merely because the process
starts, and never automate a destructive downgrade without verified backups.

Record recovery point objective (RPO) as the age of the latest successfully
restored backup and recovery time objective (RTO) as measured restore plus
verification time. Those measurements are local operational evidence; the
project offers no RPO, RTO, or availability SLA.
