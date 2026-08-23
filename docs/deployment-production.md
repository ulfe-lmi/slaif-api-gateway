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

cp /path/to/fullchain.pem secrets/tls/fullchain.pem
cp /path/to/privkey.pem secrets/tls/privkey.pem
```

`DATABASE_URL` must point at the production PostgreSQL service, for example:

```text
postgresql+asyncpg://slaif:PASSWORD@postgres:5432/slaif_gateway
```

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

Worker/scheduler services are intentionally not included in this bounded
production profile. Reconciliation is manual unless a future profile explicitly
adds them.
