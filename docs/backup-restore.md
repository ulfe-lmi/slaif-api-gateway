# Backup and restore

Use `pg_dump --format=custom` against a safe disposable/test database URL:

```bash
BACKUP_DATABASE_URL=postgresql://user@localhost/test_slaif_gateway \
BACKUP_OUTPUT=./slaif-test.dump scripts/backup.sh
```

Restore only into a clean disposable target:

```bash
RESTORE_DATABASE_URL=postgresql+asyncpg://user@localhost/restore_test \
BACKUP_INPUT=./slaif-test.dump scripts/restore.sh
```

Then verify structural readiness:

```bash
RESTORE_DATABASE_URL=postgresql+asyncpg://user@localhost/restore_test \
python scripts/verify_restore.py
```

Generated `.local-provider-catalog/`, logs, and temporary files are not backup
truth. HMAC key versions and one-time-secret encryption keys must be retained by
the operator; backups do not contain plaintext provider secrets.
