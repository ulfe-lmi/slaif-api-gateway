# Deployment

> **Status:** Current development/self-hosted deployment reference
> **Production path:** See [deployment-production.md](deployment-production.md)

This document describes the repository Docker Compose packaging and the
deployment boundaries operators must keep explicit. It is not a production
certification or a complete site reliability runbook.

For the canonical local walkthrough, start with the
[QUICKSTART](../QUICKSTART.md); the detailed variant is the
[first-time operator guide](first-time-operator-guide.md). For RC-beta scope
and the release checklist, see [`rc-beta.md`](rc-beta.md) and the dated
[verification index](verification/README.md). For operator incident and
maintenance procedures, see [`runbooks/README.md`](runbooks/README.md).

## Overview

The Compose packaging defines these services:

- `api`: FastAPI application served by Gunicorn with Uvicorn workers.
- `worker`: Celery worker for background jobs such as key email delivery and
  optional reconciliation tasks.
- `scheduler`: Celery Beat scheduler. Scheduled reconciliation remains disabled
  unless explicitly enabled through environment variables.
- `postgres`: PostgreSQL 16, the source of truth for keys, quotas, accounting,
  audit logs, admin state, catalog metadata, and email delivery state.
- `redis`: Redis 7 for Celery broker state and optional operational rate limits.
- `mailpit`: local/development SMTP sink and web mailbox.
- `nginx`: optional reverse proxy profile using `deploy/nginx/slaif-api-gateway.conf`.

API, worker, and scheduler containers do not run migrations automatically.
Migrations are explicit operator actions.

## Local Docker Compose

The canonical first-time local sequence — clone, `.env`, secret
generation, build, infrastructure, explicit migrations, API start,
health/readiness, first admin, dashboard login, local metadata, and the first
client request — lives in the [QUICKSTART](../QUICKSTART.md); the detailed
variant with real-provider wiring is the
[first-time operator guide](first-time-operator-guide.md). This section keeps
the deployment-level facts operators need beyond a first boot.

- `.env.example` already points `DATABASE_URL`, `REDIS_URL`,
  `CELERY_BROKER_URL`, and `SMTP_HOST` at the Compose service names. `.env`
  is clear-text local runtime configuration; do not commit it, and on shared
  systems restrict it with `chmod 600`.
- Secret generation must use the bind-mounted `run-cli` workflow from the
  quickstart; do not assume a plain `docker compose run api ... --env-file
  .env --write` updates the host `.env` file unless the project directory is
  explicitly mounted.
- Migrations are explicit: `docker compose run --rm api slaif-gateway db
  upgrade`; API, worker, and scheduler never migrate on startup.
- Before sending real traffic, bootstrap local catalog metadata (provider,
  routes, reviewed pricing) and issue keys with explicit `/v1` endpoint and
  model policy. The bootstrap command creates local OpenAI Chat Completions
  metadata only. It does not call OpenAI, fetch pricing, create gateway keys,
  or store provider key values. Legacy `/v1/completions` is not implemented.
- Users call the local gateway with the standard `OPENAI_API_KEY` /
  `OPENAI_BASE_URL` variables; `OPENAI_API_KEY` is always the
  gateway-issued key, never the upstream provider key.

Runtime install/build dependency note: the async database stack uses
SQLAlchemy's asyncio extension, which requires the `greenlet` bridge.
Both `pyproject.toml` and `requirements.txt` therefore declare the
runtime dependency as `sqlalchemy[asyncio]`; a runtime-only install
(without dev extras) must include `greenlet` as a result. A bare
`sqlalchemy` declaration fails the explicit migration step with
`ImportError: The SQLAlchemy asyncio module requires that the Python
'greenlet' library is installed`. This is a runtime dependency
declaration only; it changes no ordinary operator commands.

Mailpit is available at `http://localhost:8025` by default. Its SMTP endpoint
is `mailpit:1025` from containers and `localhost:1025` from the host. Compose
host ports are configurable with `API_HOST_PORT`, `POSTGRES_HOST_PORT`,
`REDIS_HOST_PORT`, `MAILPIT_SMTP_HOST_PORT`, `MAILPIT_WEB_HOST_PORT`, and
`NGINX_HOST_PORT`; the default Postgres and Redis host ports are `15432` and
`16379` to avoid common collisions with host-local services.

Stop the local stack non-destructively:

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to delete local
PostgreSQL and Redis volumes; [INSTALL](../INSTALL.md) documents the stop and
destructive-cleanup semantics.

For non-destructive local refreshes, use:

```bash
./scripts/docker-refresh.sh --env-only  # after .env changes
./scripts/docker-refresh.sh --pull      # after upstream code updates on main
./scripts/docker-refresh.sh             # after local code changes
```

The script builds API/worker/scheduler images, runs migrations unless skipped,
recreates runtime services, shows Compose status, and checks `/healthz` and
`/readyz`. It never removes Docker volumes or overwrites `.env`. It is a
local convenience, not a production upgrade tool.

## Optional Operator Branding

A read-only appearance directory can be mounted onto the existing `api`
service with the bundled overlay — same image, no rebuild, no new service:

```bash
install -d -m 755 deploy/branding   # add at most one file per slot

# local:
docker compose -f docker-compose.yml -f docker-compose.branding.yml up -d

# production-shaped:
docker compose -f docker-compose.production.yml -f docker-compose.branding.yml up -d
```

The overlay adds only `SLAIF_BRANDING_DIR=/branding` and the
`./deploy/branding:/branding:ro` bind to the `api` service. Precreate the
directory readable by the application user (`slaif` in the image) and keep
only public appearance assets in it. If your stack uses an explicit
Compose project name (`-p`), profiles, or an env file, pass the same
values with the overlay so it joins the existing project rather than
launching a different one. Asset changes are picked up on the next
request without a restart; invalid files fall back to the packaged default
per slot. Slots, formats, limits, refresh, and fallback semantics are
documented in [Operator branding](branding.md).

## Optional Browser Smoke Tests

The Playwright admin dashboard smoke tests are optional and are not part of the
normal unit, integration, or OpenAI-compatible E2E commands. They require an
explicit test database and an explicitly installed browser:

```bash
python -m playwright install chromium
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/browser -m playwright
```

The suite starts the local FastAPI app, seeds safe dummy dashboard data, drives
admin login/navigation/logout in Chromium, checks representative CSRF-protected
forms are present, and verifies rendered normal dashboard pages do not expose
token hashes, encrypted one-time-secret material, provider keys, plaintext
gateway keys, prompts, completions, or session data. It does not call real
OpenAI/OpenRouter providers and does not send real email.

## GitHub CI Packaging Smoke

The public GitHub Actions CI includes a Docker Compose smoke job for the
repository packaging. It copies `.env.example` to `.env`, validates
`docker compose config`, builds the image, starts PostgreSQL, Redis, and
Mailpit, runs `slaif-gateway db upgrade` explicitly, starts API/worker/scheduler
services, checks `/healthz` and `/readyz`, validates the Nginx config with the
official `nginx:stable` image, and then runs `docker compose down -v` in
cleanup.

The CI smoke does not use real provider keys, does not call OpenAI/OpenRouter,
does not send real external email, and does not run migrations implicitly from
API/worker/scheduler startup.

## Production Notes

The hardened production appliance is defined separately in
[`deployment-production.md`](deployment-production.md). It uses file-backed
Docker/Compose secrets, authenticated Redis, a named PostgreSQL volume, private
networks, and Nginx for the public HTTPS boundary. Follow that document rather
than adapting the local `.env` workflow for production.

Docker Compose is local/development packaging and a clear service layout. It is
not full production hardening by itself.

Before production use:

- Replace every placeholder secret in `.env`.
- Use strong values for HMAC, admin session, one-time-secret encryption,
  provider, SMTP, and database secrets.
- Run migrations explicitly during controlled deploy steps.
- Use real PostgreSQL/Redis services or managed equivalents if appropriate.
- Put API traffic behind HTTPS, usually through Nginx or a managed ingress.
- Keep `/metrics` internal or allowlisted.
- Keep `/readyz` internal or allowlisted.
- Protect `/admin` with HTTPS, strong admin passwords, login rate limiting, and
  preferably an IP allowlist, VPN, or equivalent ingress control.
- Provide upstream provider secrets through environment variables, Docker
  secrets, or a deployment secret manager. Do not store provider key values in
  `provider_configs`; that table stores env var names only.
- Use a deployment secret manager or Docker secrets for production where
  appropriate. The `slaif-gateway secrets generate ...` CLI can produce strong
  initial values for local or self-hosted setup, but it is not a full
  secret-management system.
- Do not leave `LOG_LEVEL=DEBUG` running indefinitely in production except for a
  time-bounded incident diagnosis.
- Prefer `STRUCTURED_LOGS=true`, `GUNICORN_LOG_LEVEL=info`, and
  `CELERY_LOG_LEVEL=INFO` for production log aggregation.
- Monitor Redis rate-limit availability and choose fail-open/fail-closed
  behavior deliberately. PostgreSQL quotas and accounting remain authoritative.
- Replacing `TOKEN_HMAC_SECRET_V1` invalidates gateway keys signed with that
  secret unless the old secret remains configured.
- Replacing `ADMIN_SESSION_SECRET` invalidates active admin sessions.
- Replacing `ONE_TIME_SECRET_ENCRYPTION_KEY` can make existing encrypted
  one-time secrets undecryptable.

The server-side OpenAI upstream secret is `OPENAI_UPSTREAM_API_KEY`.
`OPENAI_API_KEY` is reserved for clients carrying gateway-issued keys.

## Changing Settings (Environment, Restart Scope, And `config show`)

The operator CLI reads the environment of the shell that starts it; a shell
does NOT auto-load `.env`. Two common patterns:

```bash
# 1) Export the intended deployment values in the shell, then run the CLI
set -a; source .env; set +a
slaif-gateway config show --json

# 2) Or run the CLI inside the API container, where Compose already
#    injected the service environment (adjust the service name as needed)
docker compose exec -it api slaif-gateway config show
```

`slaif-gateway config show` reports the CURRENT CLI process's cached
`Settings` snapshot (finite reviewed allowlist, no credential values). It is
NOT live API/worker state: if the CLI shell and the containers were
started from different environments, the reported snapshot reflects only
the CLI process. The admin GUI's read-only Process configuration page
(Dashboard -> Usage and operations -> Operations) displays the SAME
finite allowlist for the API process with the same restart/recreate
scope and no settings writer: changing any value still requires the
environment change plus recreating/restarting the affected containers
described below.

Restart scope for environment-driven settings:

- Changing Compose `env_file` / `.env` content requires RECREATING the
  affected containers (`docker compose up -d --force-recreate api worker
  scheduler`); a plain `docker compose restart` does not reload a
  container's existing environment.
- A process restart loads a changed environment only when its supervisor
  actually supplies it (Compose `env_file`, Kubernetes config, systemd unit,
  etc.).
- Use `config show` after recreation to confirm the intended values in the
  process you expect; a configured database URL is not connectivity or
  authentication proof.

Example: `CODEX_REPLAY_REFERENCE_TTL_SECONDS` changes affect only NEWLY
persisted replay reference expiries; the existing
`slaif-gateway codex replay inspect/extend` commands manage already-persisted
references separately.

External reverse-proxy request-size limits are NOT observed by `config show`.
The shipped Nginx examples set `client_max_body_size 128m` inside
`location /v1/` (see [Streaming And Nginx](#streaming-and-nginx)); that is an
example, not live proxy truth. Validate Nginx changes with `nginx -t` and
reload as described there.

## Diagnostic Logging

Production should normally stay at `LOG_LEVEL=INFO` with
`STRUCTURED_LOGS=true`, so API logs remain structured JSON and suitable for
operator log systems. Admin pages return generic browser-safe errors and a
server-generated reference such as `gw-...`; they do not render stack traces,
raw request bodies, cookies, CSRF tokens, session tokens, plaintext gateway
keys, provider keys, encrypted payloads, nonces, prompts, or completions.

For local diagnosis of an admin or worker issue, set:

```bash
LOG_LEVEL=DEBUG
STRUCTURED_LOGS=false
GUNICORN_LOG_LEVEL=debug
CELERY_LOG_LEVEL=DEBUG
```

Then inspect logs from the relevant services:

```bash
docker compose logs -f api
docker compose logs -f worker scheduler
docker compose logs api | rg '<diagnostic-id>'
```

Logs are redacted but can still contain sensitive operational metadata. Keep
them operator-side; this project intentionally does not expose a dashboard log
viewer.

## Streaming And Nginx

`deploy/nginx/slaif-api-gateway.conf` is a starting point. It proxies `/v1`,
`/admin`, and `/healthz` to the API service. `/readyz` is allowlisted to private
networks by default, and `/metrics` is denied by default.

Both shipped Nginx templates (`deploy/nginx/slaif-api-gateway.conf` and
`nginx/production.conf`) set the API transport allowance inside
`location /v1/`:

```nginx
client_max_body_size 128m;
```

This is 128 MiB for the complete request body, including JSON, base64 media,
conversation history and tool declarations. Base64 adds roughly one third to
the original binary size. Gateway endpoint/media validation, model context,
key policy, quotas and request-capture budgets remain independent. This does
not add video support or guarantee that a 128 MiB body is valid model input.
Admin upload limits remain separate. Custom ingress configurations need the
same explicit API setting; omitting it leaves Nginx's default 1 MiB limit,
which returns an HTML 413 before the gateway can authenticate or validate.

The reviewed key-batch admin transport (objective 209) needs its own
bounded allowance: the signed `batch_review_intent` review envelope
expands an 8 MiB canonical plan to ~10.67 MiB (11,184,812 base64url
characters, 10.67 MiB) plus the small form fields, which exceeds
Nginx's default 1 MiB `client_max_body_size`. Both shipped templates
therefore carry a dedicated location for the batch endpoints ONLY:

```nginx
location /admin/key-batch/ {
    client_max_body_size 16m;
    ...
}
```

16 m is the derived envelope headroom (10.67 MiB envelope plus the
bounded form fields), and every other admin and `/v1` limit, proxy
header, and security behavior is unchanged. The gateway side enforces
the same bound: the apply route parses the form with a bounded
per-field headroom and refuses oversized envelopes with a fixed safe
400, so the Nginx value is a transport allowance, not an authorization.

Upgrading a deployment that predates 209 is an application upgrade
plus a proxy update in the SAME maintenance window: rebuild the
API/assets image and recreate/restart the API so the new batch code
runs, and update the reverse-proxy configuration from the shipped
templates (or add the `location /admin/key-batch/` block above to a
custom ingress), then `nginx -t` and reload Nginx - a new app behind
an old proxy 413s large reviewed batches before they reach the
gateway. No database migration and no existing-key change or rotation
follow this upgrade.

Editing ONLY the proxy setting (the 16 m batch location, for example on
an already-upgraded app) needs just `nginx -t` and a Nginx reload: for
that proxy-only configuration change no application rebuild or API
restart is needed - the application upgrade itself (new code) still
requires the API/assets rebuild and API recreate/restart described
above.

Upgrading a deployment that predates 210 (objective 210-a: reviewed
route configuration and provider preparation) is an application
upgrade ONLY: rebuild the API/assets image and recreate/restart the
API so the new code runs. There is **no Nginx change**: the signed
route review envelope is bounded to ~175 KiB (178,858 base64url
characters), well inside the existing default `client_max_body_size`,
and no new location or allowance is introduced. No database migration
and no existing-key or existing-route change or rotation follows this
upgrade. Installed completion-service profiles are a process-local
cache: deploy the profile files to the configured profile directory,
then recreate/restart the API so the process picks them up.

Upgrading a deployment that predates 211 (objective 211-a: admin GUI
request diagnostics and read-only process configuration) is an
application upgrade ONLY: rebuild the API/assets image and
recreate/restart the API so the new code runs. There is **no Nginx
change** - no new location, allowance, or proxy setting is introduced -
and **no database schema migration**; no existing-key, route, or
profile change or rotation follows this upgrade. Request-capture
configuration and request-failure diagnostics recording state are
untouched by the upgrade; changing those environment settings later
still requires the normal env change plus recreate/restart of the
affected containers.

Streaming routes require anti-buffering and long timeouts:

```nginx
proxy_http_version 1.1;
proxy_buffering off;
proxy_cache off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
```

Chat Completions and the supported stateless text-output Responses streaming
live-burn behavior in
[`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) remain
gateway-side provisional interruption controls. They must not require Nginx
buffering, raw stream capture, prompt/completion logging, Redis-only quota
accounting, or provider-final-usage bypasses.

TLS certificates, real domains, request-size limits, access logs, and network
allowlists are deployment-specific and must be reviewed by the operator.

## Worker And Scheduler

The `worker` service runs:

```bash
celery -A slaif_gateway.workers.celery_app:celery_app worker --loglevel=${CELERY_LOG_LEVEL:-INFO}
```

The `scheduler` service runs:

```bash
celery -A slaif_gateway.workers.celery_app:celery_app beat --loglevel=${CELERY_LOG_LEVEL:-INFO}
```

The worker handles explicit key email delivery tasks and — when the optional
catalog workspace is enabled — the bounded read-only catalog refresh/proposal
job family. Celery payloads carry IDs only, never plaintext gateway keys or
email bodies.

Scheduled reconciliation is disabled by default. Enabling
`ENABLE_SCHEDULED_RECONCILIATION=true` schedules safe backlog inspection only.
Automatic reconciliation mutation requires the matching
`RECONCILIATION_AUTO_EXECUTE_*` flag and `RECONCILIATION_DRY_RUN=false`.
Scheduled reconciliation tasks reuse existing service-layer logic, do not call
providers, and return safe summaries only.

Optional reconciliation alert webhooks are disabled by default. When
`ENABLE_RECONCILIATION_ALERTS=true` is configured with a generic webhook URL,
the scheduled backlog inspection task can send safe backlog counts to an
operator-managed alerting bridge. Alert webhooks do not mutate quota/accounting,
do not call providers, and do not send email. Payloads are counts-only by
default; `RECONCILIATION_ALERT_INCLUDE_IDS=true` adds only safe reservation and
usage-ledger IDs. Treat the webhook URL as a secret if it contains tokens.

Operational procedures for stale reservations and provider-completed recovery
are in [`runbooks/stale-reservation-reconciliation.md`](runbooks/stale-reservation-reconciliation.md)
and [`runbooks/provider-completed-reconciliation.md`](runbooks/provider-completed-reconciliation.md).

## Catalog Refresh Custody (Optional, Default Off)

The admin GUI catalog workspace (G15, see
[Catalog Refresh](catalog-refresh.md#admin-gui-workspace-g15-delivered-by-217-a)
and [Configuration](configuration.md#catalog-refresh-admin-gui-217-a)) stores
its job records, uploads, and sealed runs in operator custody — files only,
never PostgreSQL. Enabling it requires:

1. **Shared custody volume**: `docker-compose.yml` already mounts the named
   volume `catalog-refresh-data` into BOTH the `api` and `worker` services at
   `/var/slaif/catalog-refresh`, so queued jobs (worker) and page reads (API)
   see one state tree. The volume contents must be owned by the container
   service user with mode `0700`. The app opens this root only; it never
   creates, repairs, or re-chowns it.
2. **OFFLINE seal key**: the operator generates the 64-hex seal key OUTSIDE
   the container (or on a host-managed mount) with mode `0600`, owned by the
   same service user, and points `CATALOG_REFRESH_SEAL_KEY` at it. The GUI
   never creates or replaces the key.
3. **Location rule**: the root and key must be OUTSIDE the repository
   source/package tree and outside any local PostgreSQL data directory;
   configured paths inside those locations are refused.
4. **Restart scope**: after changing any `CATALOG_REFRESH_*` value,
   recreate/restart the `api` and ALL `worker` services (they read the
   settings at startup). A reverse-proxy change (the scoped nginx
   `client_max_body_size 48m` for the bounded 8 MiB bundle / 32 MiB baseline
   uploads) takes effect for new connections only after the established
   `nginx -t` + reload/recreate procedure ([Streaming And
   Nginx](#streaming-and-nginx)); editing the proxy file alone changes
   nothing.
5. **Backup/rollback**: custody files are operator state, not database
   state. Back them up with your normal file-state procedure if the sealed
   runs matter to you; removing the volume or disabling
   `CATALOG_REFRESH_GUI_ENABLED` never touches PostgreSQL, and no schema or
   key-policy migration is performed by this feature.

### New install / upgrade procedure (copy-ready)

Two proxy shapes are supported, and the steps distinguish them explicitly:
the Compose stack ships an OPTIONAL nginx profile (the `nginx` service,
`profiles: [nginx]`, included in `docker compose up` only when
`--profile nginx` is passed - it is NOT always-on), while an
external/host-level Nginx deployment uses your own proxy. Steps marked
**[manual host]** are host/proxy controls you run yourself; they are
documented, not automated. No new init service, dependency, or
production-execution step is introduced.

```bash
# 1) [manual host] Dedicated custody ownership + service UID, ONCE before
#    first use. A fresh named volume is root-owned while the
#    api/worker/scheduler containers run as the non-root `slaif` user,
#    so prepare it with a one-off container of the EXISTING api image,
#    explicitly as root (--user root) and with no dependency services
#    started (--no-deps); no network is needed. This reports the ACTUAL
#    service uid/gid from the image (not root's):
docker compose run --rm --no-deps --user root --entrypoint sh api -c '
  id -u slaif && id -g slaif &&
  mkdir -p /var/slaif/catalog-refresh &&
  chown $(id -u slaif):$(id -g slaif) /var/slaif/catalog-refresh &&
  chmod 0700 /var/slaif/catalog-refresh
'
#    If you bind-mount a host directory instead of the named volume in
#    your own compose override, apply the SAME ownership (the uid/gid
#    reported above) and mode 0700 to that host path instead.

# 2) [manual host] The EXISTING 0600 seal key - preserve or create
#    OFFLINE. PRESERVE an existing key byte-for-byte: it is the identity
#    of every sealed run, and replacing it makes old runs unverifiable.
#    NEVER print or paste the key contents, and never use an
#    overwrite-style generator (for example `openssl rand -hex 32 >
#    seal.key`) against a path where a key may already exist. The
#    OFFLINE create-if-absent step reuses the EXISTING application
#    function through the same image and the same volume, run as the
#    service user after step 1: it creates the 0600 key ONLY when
#    absent, loads and validates an existing key without modifying it
#    (an invalid existing key is refused, never replaced), prints
#    nothing, and performs no live collection. The GUI itself NEVER
#    creates, replaces, or rewrites the key - it only opens the
#    existing one:
docker compose run --rm --no-deps --entrypoint sh api -c '
  python -c "from slaif_gateway.services.catalog_refresh.filesystem import ensure_seal_key; ensure_seal_key(\"/var/slaif/catalog-refresh/seal.key\")"
'
#    (If your custody root is a host bind mount, the SAME in-container
#    command applies; the key ends up 0600, owned by the service uid
#    reported in step 1.)

# 3) The three GUI settings in .env (see docs/configuration.md):
#    CATALOG_REFRESH_GUI_ENABLED=true
#    CATALOG_REFRESH_ROOT=/var/slaif/catalog-refresh
#    CATALOG_REFRESH_SEAL_KEY=/var/slaif/catalog-refresh/seal.key
#    (both paths OUTSIDE the repository source tree and any local PGDATA;
#     the finite knobs CATALOG_REFRESH_MAX_ACTIVE_JOBS /
#     CATALOG_REFRESH_MAX_RETAINED_RUNS / CATALOG_REFRESH_MAX_TOTAL_BYTES /
#     CATALOG_REFRESH_READ_ONLY_TIMEOUT_SECONDS keep their defaults unless
#     you change them deliberately)

# 4) Apply: build the NEW checkout code into the image, then recreate
#    the API and ALL worker services (settings are read at startup;
#    on upgrades --build matters - --force-recreate alone would
#    relaunch the stale existing image):
docker compose up -d --build --force-recreate api worker scheduler

# 5) Proxy (only if your proxy fronts the admin uploads) [manual host]:
#    a) SHIPPED optional nginx profile (the `nginx` service,
#       `profiles: [nginx]`, nginx:1.27-alpine, mounting
#       deploy/nginx/slaif-api-gateway.conf read-only): the scoped
#       `location /admin/operations/catalog/ { client_max_body_size
#       48m; ... }` allowance is already in that template. Enable the
#       profile once with:
#         docker compose --profile nginx up -d nginx
#       and, after any template change, config-test + reload (or
#       recreate) the EXISTING service:
#         docker compose --profile nginx exec nginx nginx -t \
#           && docker compose --profile nginx exec nginx nginx -s reload
#         # or re-read the config from scratch:
#         docker compose --profile nginx up -d --force-recreate nginx
#    b) EXTERNAL/host-level Nginx: update your own proxy config from
#       the same template and run ITS established `nginx -t` +
#       reload/recreate procedure (see Streaming And Nginx).
#    Either way, editing the proxy file alone does NOTHING for new
#    connections until the configuration-test + reload/recreate runs;
#    until then uploads still use the old limit.

# 6) Verify setup-ready (browser): sign in at /admin and open
#    Operations -> Catalog workspace. The Setup section must read READY
#    (root + seal key verified) with the storage summary; while it is not
#    ready the page shows fixed setup help and NO catalog action is
#    dispatchable. Optionally queue one read-only Export baseline job and
#    download the document as an end-to-end check.

# 7) Backup of the SAME seal key + runs (periodic) [manual host]. A named
#    volume is NOT a host path: /var/slaif exists only inside the
#    containers, so a host `tar -C /var/slaif ...` cannot reach the
#    custody - and a `tar | gzip` pipeline can produce an EMPTY archive
#    that still exits 0. The EXISTING image therefore streams the shared
#    volume to the host with the stdlib only and NO buffering: the
#    required inputs are checked first, the archive is written with
#    tarfile's streaming gzip writer, and any failure exits non-zero.
#    The key contents are never printed.
#    For a coherent file-state backup, first quiesce the writers (or use
#    your established maintenance procedure): `docker compose stop
#    api worker scheduler` - take the archive - then `docker compose
#    start api worker scheduler`. Without quiescing, the archive is a
#    best-effort snapshot, not a transactional backup. The archive
#    covers the current key + runs tree size (gzip-compressed).
#    The archive name is created with mktemp: a NEWLY CREATED private
#    file (0600), so an earlier backup is never overwritten and the
#    permissions do not depend on the shell umask:
archive=$(mktemp "./backup-catalog-refresh-$(date -u +%Y%m%d).tar.gz.XXXXXX") || exit 1
if docker compose run --rm --no-deps -T --entrypoint sh api -c '
python - <<PY
import os, sys, tarfile
root = "/var/slaif/catalog-refresh"
seal = os.path.join(root, "seal.key")
runs = os.path.join(root, "runs")
if not os.path.isfile(seal):
    sys.exit("backup refused: seal key missing")
if os.path.exists(runs) and not os.path.isdir(runs):
    sys.exit("backup refused: runs path is not a directory")
with tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as t:
    t.add(seal, arcname="seal.key")
    if os.path.isdir(runs):
        t.add(runs, arcname="runs")
PY
' > "$archive"; then
  ls -l "$archive"   # -rw------- (0600) created by mktemp
else
  status=$?
  # Failed run: remove ONLY this owned partial file; never report success.
  rm -f -- "$archive"
  exit "$status"
fi
#    If your custody root is a host bind mount, you MAY instead archive
#    that host path directly with your normal file-state tooling - apply
#    the same checks (non-empty archive containing seal.key + the runs
#    tree, restrictive archive permissions, non-zero failure
#    propagation). The seal key is INSIDE that tree (it is identity, not
#    a recoverable secret): protect the archive as you protect the key;
#    never print the key. "Rotating" means generating a NEW key file and
#    re-pointing CATALOG_REFRESH_SEAL_KEY - old sealed runs remain bound
#    to their original key.
```

Upgrade note: upgrading a deployment that predates 217 is an application
upgrade plus the optional proxy allowance in the SAME maintenance window:
rebuild/recreate `api`, `worker`, and `scheduler` so the new code and
settings run, and - only if your proxy fronts the admin uploads - add the
scoped `/admin/operations/catalog/` allowance to the active proxy shape
and run its established configuration-test + reload/recreate (step 5
above). No database migration, no schema change, and no key-policy change
follow this upgrade; an existing-but-disabled deployment gains nothing
until step 3/4 above.

## Backups

Back up PostgreSQL. It is the source of truth for key metadata, HMAC digests,
quota counters, usage ledger rows, catalog metadata, audit logs, admin sessions,
and email delivery state.

Plaintext gateway keys are not stored, so they cannot be recovered from backups.
Protect these secrets separately from the database:

- `TOKEN_HMAC_SECRET_V*`
- `ADMIN_SESSION_SECRET`
- `ONE_TIME_SECRET_ENCRYPTION_KEY`
- upstream provider keys
- SMTP credentials

Losing an HMAC secret invalidates keys created with that HMAC version. Losing a
one-time-secret encryption key prevents recovery of pending encrypted delivery
secrets; rotate affected gateway keys instead of attempting to resend old
plaintext.

Backup/restore and secret-rotation procedures are documented in
[`runbooks/database-backup-restore.md`](runbooks/database-backup-restore.md),
[`runbooks/provider-key-rotation.md`](runbooks/provider-key-rotation.md),
[`runbooks/hmac-secret-rotation.md`](runbooks/hmac-secret-rotation.md), and
[`runbooks/one-time-secret-encryption-key.md`](runbooks/one-time-secret-encryption-key.md).

Docker and Nginx troubleshooting guidance is in
[`runbooks/docker-nginx-troubleshooting.md`](runbooks/docker-nginx-troubleshooting.md).

## Limitations

- This deployment packaging is not a formal production certification,
  compliance attestation, or penetration test.
- No CI/CD system is required or added by this repository packaging.
- Native Anthropic API, `/v1/files`, image-generation endpoints, Responses audio,
  and Responses hosted tools other than the exact bounded OpenAI canonical
  `web_search` contract remain unsupported. Current implemented endpoint
  families include bounded standalone Audio speech/transcription/translation,
  Embeddings, Realtime client-secret admission, Responses create/input-token/
  compact operations, owned response lifecycle, owned Conversations and
  Conversation items, and the separately fenced OpenAI Responses web-search
  runtime. OpenRouter hosted tools, remote MCP/connectors, file search, file
  IDs, and every other hosted family remain denied. See the compatibility
  matrix for the exact capability, provider, accounting, and storage gates.
- Admin bulk/import/upload workflows are application features documented in
  README.md, `docs/security-model.md`, and `docs/compatibility-matrix.md`; the
  deployment packaging does not add separate asynchronous import/export job
  infrastructure beyond the implemented app and Celery services.
- Slack/PagerDuty-specific SDK integrations are not implemented; use the
  optional generic reconciliation webhook with an operator-managed bridge.

Operator-defined `openai_compatible` backends may target an operator-owned LAN
service, but generic HTTP sends bearer credentials and request content without
encryption. Require the explicit audited HTTP acknowledgement, firewall or
reverse-proxy controls, and an exact `/v1` URL. The runtime does not perform
automatic discovery, qualify, load-balance, or follow redirects to these
services. Operators may run the explicit bounded discovery/setup wizard after
provider configuration; it is not a health check or qualification system.
