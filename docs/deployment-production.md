# Production Compose deployment

Prerequisites: Linux host, Docker with Compose v2, TLS certificate and private
key, and operator-created secret files under `secrets/` with directory mode
`0700`.

## Create secrets

```bash
mkdir -p secrets/tls
chmod 700 secrets

printf '%s' "$POSTGRES_PASSWORD" > secrets/postgres_password
printf '%s' "$DATABASE_URL" > secrets/database_url
python -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode(), end="")' \
  > secrets/token_hmac_secret_v1
printf '%s' "$ADMIN_SESSION_SECRET" > secrets/admin_session_secret
python -c 'import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode(), end="")' \
  > secrets/one_time_secret_encryption_key
printf '%s' "$OPENROUTER_API_KEY" > secrets/openrouter_api_key
printf '%s' "$OPENAI_UPSTREAM_API_KEY" > secrets/openai_upstream_api_key
printf '%s' "$REDIS_PASSWORD" > secrets/redis_password
printf 'redis://:%s@redis:6379/0' "$REDIS_PASSWORD" > secrets/redis_url

cp /path/to/fullchain.pem secrets/tls/fullchain.pem
cp /path/to/privkey.pem secrets/tls/privkey.pem
```

`DATABASE_URL` must point at the production PostgreSQL service, for example:

```text
postgresql+asyncpg://slaif:PASSWORD@postgres:5432/slaif_gateway
```

`REDIS_URL` is supplied to the containers through `secrets/redis_url`; it must
contain the same password as `secrets/redis_password`. Redis is configured with
authentication and protected mode. Do not publish the Redis port or put either
file in the image.

## Preflight

```bash
bash scripts/preflight.sh
```

Preflight fails closed if any secret is missing or empty, permissions are wrong,
TLS files are absent, Docker is unavailable, or Compose configuration is invalid.

## Deploy

```bash
docker compose -f docker-compose.production.yml up -d
```

Startup order is PostgreSQL → Redis → migrations → API → Nginx. The migration
service runs `alembic upgrade head` once and must complete successfully before
API starts. The API health check probes `/healthz`; Nginx starts only after the
API is healthy.

Only Nginx ports 80/443 are exposed. PostgreSQL, Redis, migrations, and the API
remain on the internal network; the API itself is loopback-bound.

The production Nginx configuration proxies the exact `/admin` landing path and
the `/admin/` subtree without canonical-slash redirects between Nginx and
FastAPI. It does not publish `/metrics`; the qualification-only Compose
override permits metrics solely from the API container's `127.0.0.1` loopback.

The default production profile runs API + PostgreSQL + Redis + Nginx only.

Async operations such as email delivery and scheduled reconciliation require the
optional `async` profile:

```bash
docker compose -f docker-compose.production.yml --profile async up -d
```

Without that profile, worker/scheduler do not run and reconciliation remains
available through the CLI.

The production image starts as root only long enough for the allowlisted
file-backed secret loader to read Docker/Compose secrets. It then executes the
requested command as the `slaif` application user. Direct production secret
environment variables are rejected; use the documented `*_FILE` inputs.

For a disposable qualification using a socket-level provider double, run:

```bash
python scripts/production-qualification/run.py
```

The harness generates a unique Compose project, TLS material, and secrets;
uses only the HTTPS Nginx boundary; exercises PostgreSQL/Redis/accounting and
backup/restore; scans logs and durable metadata for generated canaries; and
removes only its own project, volume, networks, and temporary runtime files.
It never calls a real upstream provider or sends email. A successful run is an
RC-beta appliance qualification, not a production certification or compliance
claim.
