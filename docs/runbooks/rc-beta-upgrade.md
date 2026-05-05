# RC-Beta Upgrade Checklist

## Before Upgrade

- Back up PostgreSQL.
- Back up deployment secrets: HMAC secret versions, one-time-secret encryption
  key, admin session secret, provider keys, SMTP credentials, and database
  credentials.
- Read release notes and linked compatibility docs.
- Check whether migrations changed:

  ```bash
  alembic heads
  docker compose run --rm api slaif-gateway db current
  ```

- Confirm no real provider keys will be used in local or CI smoke tests.

## Upgrade

1. Pull the new code or image.
2. Build or pull images:

   ```bash
   docker compose build
   ```

3. Run migrations explicitly:

   ```bash
   docker compose run --rm api slaif-gateway db upgrade
   ```

4. Restart API, worker, and scheduler:

   ```bash
   docker compose up -d api worker scheduler
   ```

## After Upgrade

```bash
curl -fsS http://localhost:8000/healthz
curl -fsS http://localhost:8000/readyz
docker compose logs api
docker compose logs worker
docker compose logs scheduler
```

Also verify:

- Admin login.
- Safe key validation smoke with a test key if available.
- Worker and Beat are connected to the broker.
- Scheduled reconciliation settings are still as intended.
- `/metrics` remains internal or denied publicly.
- Nginx still has streaming buffering disabled.

## Rollback

If no migration ran, restore the previous image/code and restart services. If a
migration ran and downgrade is not explicitly supported, restore the database
backup and previous image/code together.

Do not mix an older application with a newer migrated schema unless the release
notes explicitly say it is supported.

## Pre-Release Caution

RC-beta is pre-release software for the implemented and documented scope. It is
not a production certification, compliance attestation, or penetration-test
report. Perform a staging upgrade rehearsal before upgrading a production-like
environment.
