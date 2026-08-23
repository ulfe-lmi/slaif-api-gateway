# OAP execution report — 133-a

Implementation head SHA: 7ce5dc738202058d7a74c4ab7dee0c95bd604fc1
Report publication commit: SELF

## Scope

Added a bounded self-hosted production Compose profile:

- `docker-compose.production.yml` with PostgreSQL, Redis, API, and Nginx/TLS;
- internal-only database/Redis network; API bound to loopback;
- Docker secret files, no default passwords, fail-closed preflight;
- health checks and startup ordering;
- per-service CPU/memory limits;
- TLS termination and security headers in `nginx/production.conf`;
- `scripts/preflight.sh`;
- `docs/deployment-production.md`.

No Kubernetes, privileged containers, automatic DNS/TLS, or default credentials
were introduced. Images remain the existing bounded runtime target.

## Verification

Local verification:

```text
docker compose -f docker-compose.production.yml config --quiet   # passed
bash scripts/preflight.sh                                        # PREFLIGHT_OK
git diff --check                                                 # passed
```

Preflight was tested both for failure on missing secrets and success with
temporary disposable secret files under mode `0700`; those local test secrets
were removed before commit.

All ten final-head GitHub checks were verified successful on implementation head
`7ce5dc738202058d7a74c4ab7dee0c95bd604fc1`.

## Security evidence

Only Nginx edge ports are exposed externally; the API is loopback-bound.
Database and Redis are internal-network only. Secrets use file-backed Docker
secrets, never committed defaults. No provider credential or raw content is
embedded in configuration or documentation.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
