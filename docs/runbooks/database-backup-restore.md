# Database Backup And Restore

## Source Of Truth

PostgreSQL is authoritative for key metadata, HMAC digests, quotas,
reservations, usage ledger rows, audit logs, provider configs, routes, pricing,
FX, admin users, sessions, one-time-secret rows, and email delivery metadata.

Plaintext gateway keys are not stored and cannot be recovered from a database
backup.

## Backup Goals

- Take regular `pg_dump` or managed database backups.
- Periodically test restore into a fresh database.
- Store database backups separately from runtime secrets.

## Docker Compose Backup Example

```bash
docker compose exec -T postgres pg_dump \
  -U slaif \
  -d slaif_gateway \
  --format=custom \
  --file=/tmp/slaif_gateway.dump

docker compose cp postgres:/tmp/slaif_gateway.dump ./backups/slaif_gateway.dump
```

Adjust database name and user to match the deployment. Protect the dump as
sensitive operational data.

## Docker Compose Restore Into A Fresh DB

Create a fresh target database first. Do not restore over a live database until
the operator has explicitly approved downtime and data loss implications.

```bash
docker compose cp ./backups/slaif_gateway.dump postgres:/tmp/slaif_gateway.dump

docker compose exec -T postgres createdb -U slaif slaif_gateway_restore

docker compose exec -T postgres pg_restore \
  -U slaif \
  -d slaif_gateway_restore \
  --clean \
  --if-exists \
  /tmp/slaif_gateway.dump
```

Point a separate restore environment at the restored database before running
application checks.

## Managed PostgreSQL Notes

For managed PostgreSQL, prefer provider-native scheduled backups plus periodic
logical export/restore tests. Confirm restore time, retention, encryption,
point-in-time recovery, and who can access backup material.

## Migration Ordering

1. Restore the database.
2. Check current migration state:

   ```bash
   docker compose run --rm api slaif-gateway db current
   alembic heads
   ```

3. Run an explicit upgrade only if the restored database is behind the deployed
   code:

   ```bash
   docker compose run --rm api slaif-gateway db upgrade
   ```

The application and `/readyz` do not run migrations automatically.

## Secrets Needed Alongside The DB

- `TOKEN_HMAC_SECRET_V*`
- `ACTIVE_HMAC_KEY_VERSION`
- `ONE_TIME_SECRET_ENCRYPTION_KEY`
- `ADMIN_SESSION_SECRET`
- `OPENAI_UPSTREAM_API_KEY`
- `OPENROUTER_API_KEY`
- SMTP credentials when email delivery is enabled

If the DB is restored but HMAC secrets differ, existing gateway keys for missing
versions will not validate. If the one-time-secret encryption key differs,
pending encrypted delivery secrets cannot be decrypted. If the admin session
secret differs, existing admin sessions should be treated as invalid.

## Verification

- `curl -fsS http://localhost:8000/healthz`
- `curl -fsS http://localhost:8000/readyz`
- `docker compose run --rm api slaif-gateway db current`
- Admin login with a known admin account.
- Key validation smoke with a known test key if one is available and safe to
  use.

## Caution

Never use `DATABASE_URL` for destructive test setup. Use `TEST_DATABASE_URL` for
tests and a clearly separate restore target for restore rehearsals.
