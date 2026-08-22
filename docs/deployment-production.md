# Production Compose deployment

Prerequisites: Linux host, Docker with Compose v2, TLS certificate files, and
operator-created secret files.

```bash
mkdir -p secrets
printf '%s' "$POSTGRES_PASSWORD" > secrets/postgres_password
printf '%s' "$DATABASE_URL" > secrets/database_url
chmod 700 secrets
bash scripts/preflight.sh
docker compose -f docker-compose.production.yml up -d
```

The API is bound only to loopback and exposed through Nginx/TLS. PostgreSQL and
Redis remain on an internal network. Startup fails closed when required secrets
are absent or invalid.
