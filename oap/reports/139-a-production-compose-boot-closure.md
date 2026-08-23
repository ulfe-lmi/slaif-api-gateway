# OAP execution report — 139-a

Implementation head SHA: ed9d34c49280fa3f21e4596c31ebe3acc14db894
Report publication commit: SELF

## Root cause and fixes

The production Compose path previously failed closed at startup. This round fixed
all five identified root causes:

1. Added required application secrets:
   `token_hmac_secret_v1`, `admin_session_secret`,
   `one_time_secret_encryption_key`.
2. Wired all application secrets into API and migration containers using the
   existing `*_FILE` secret-file pattern.
3. Mounted TLS certificate material at `/etc/nginx/certs` from
   `secrets/tls/{fullchain.pem,privkey.pem}`.
4. Added optional provider credential secrets:
   `openrouter_api_key`, `openai_upstream_api_key`.
5. Added a one-shot `migrations` service running `alembic upgrade head`, ordered
   after healthy PostgreSQL and required by API startup.
6. Added an API healthcheck probing `/healthz`; Nginx starts only after API health.

Updated `scripts/preflight.sh` to fail closed on any missing/empty secret,
wrong permissions, missing TLS files, Docker absence, or invalid Compose config.
Updated `docs/deployment-production.md` with complete secret generation,
TLS placement, startup ordering, and explicit manual reconciliation limitation.

No worker/scheduler was added, as prohibited by this order.

## Verification

Local disposable preflight with temporary test secrets/TLS:

```text
bash scripts/preflight.sh
# PREFLIGHT_OK

docker compose -f docker-compose.production.yml config --quiet
# COMPOSE_CONFIG_OK
```

Temporary local secrets and TLS files were removed before commit; no real or
production credentials were committed. A full clean-host boot was not performed
because this environment has no clean Linux VM target; deterministic config/
preflight validation plus code-path inspection is therefore the evidence for
this round, not a boot claim.

All ten final-head GitHub checks were verified successful on implementation head
`ed9d34c49280fa3f21e4596c31ebe3acc14db894`.

## Honest limits

This proves configuration validity and startup ordering, not a completed
clean-host production deployment or provider success. Worker/scheduler remain
excluded and reconciliation remains manual in this profile. No production claim
or release approval is made.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
