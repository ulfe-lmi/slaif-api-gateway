# Docker And Nginx Troubleshooting

## Validate Compose

```bash
docker compose config
docker compose --profile nginx config
```

Default services are `postgres`, `redis`, `mailpit`, `api`, `worker`, and
`scheduler`. The `nginx` service is enabled through the `nginx` profile.

## Build

```bash
docker compose build
```

If dependencies changed, rebuild before restarting services.

## Explicit Migrations

API, worker, and scheduler do not run migrations automatically.

```bash
docker compose up -d postgres redis mailpit
docker compose run --rm api slaif-gateway db upgrade
```

## Health And Readiness

```bash
curl -fsS http://localhost:8000/healthz
curl -fsS http://localhost:8000/readyz
```

`/healthz` checks process liveness. `/readyz` checks database/schema readiness,
Redis when enabled, and production provider-secret env var references.

## Startup Race Or Polling

Compose health checks wait for Postgres and Redis before starting API/worker,
but migrations remain explicit. If `/readyz` reports schema not current, run the
migration command and restart API.

## Logs

```bash
docker compose logs api
docker compose logs worker
docker compose logs scheduler
docker compose logs postgres
docker compose logs redis
docker compose logs mailpit
```

Follow API or background logs while reproducing an issue:

```bash
docker compose logs -f api
docker compose logs -f worker scheduler
```

Admin failure pages show a safe reference ID such as `gw-...`. Search API logs
for that diagnostic ID:

```bash
docker compose logs api | rg '<diagnostic-id>'
```

For local readable diagnostics, set these values in `.env` and restart the
affected services:

```bash
LOG_LEVEL=DEBUG
STRUCTURED_LOGS=false
GUNICORN_LOG_LEVEL=debug
CELERY_LOG_LEVEL=DEBUG
```

Production should normally remain at `LOG_LEVEL=INFO` with
`STRUCTURED_LOGS=true`. Logs are redacted and must not include plaintext gateway
keys, provider keys, raw request or response bodies, cookies, sessions, CSRF
tokens, encrypted payloads, or nonces, but they can still contain operational
metadata and should remain operator-side.

## Port Conflicts

Default host ports:

- API: `8000`
- Postgres: `15432`
- Redis: `16379`
- Mailpit SMTP: `1025`
- Mailpit web: `8025`
- Nginx profile: `8080`

Override with `API_HOST_PORT`, `POSTGRES_HOST_PORT`, `REDIS_HOST_PORT`,
`MAILPIT_SMTP_HOST_PORT`, `MAILPIT_WEB_HOST_PORT`, and `NGINX_HOST_PORT`.

## Nginx Streaming

Streaming `/v1` responses require anti-buffering and long timeouts:

```nginx
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

Validate the checked-in config with:

```bash
docker run --rm \
  -v "$PWD/deploy/nginx:/etc/nginx/conf.d:ro" \
  nginx:stable nginx -t
```

## Readiness And Metrics Exposure

The Nginx example allowlists `/readyz` to private networks and denies `/metrics`
by default. Review those controls before public exposure.

## Mailpit

Mailpit web UI is available at `http://localhost:8025` by default. Use it for
local email testing instead of real external email.

## Clean Shutdown

```bash
docker compose down
```

Use volume deletion only when intentionally deleting local PostgreSQL and Redis
state:

```bash
docker compose down -v
```
