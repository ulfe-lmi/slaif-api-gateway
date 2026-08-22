# OAP Work Order — 133-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/133-production-compose-appliance-hardening`
Base: main @ faf3edc184b2

## Objective and reason

Provide a supportable self-hosted deployment without requiring Kubernetes or a
platform team. Harden Docker Compose for production: images, users, filesystems,
networks, health, startup ordering, resource limits, TLS/Nginx, secrets, logs,
and migration jobs.

## Verified state

- main = faf3edc184b2; no open non-Dependabot PR.
- Objectives 118–132 merged. Phase 5 underway.

## Scope

1. Hardened Docker images:
   - Non-root user, minimal base, no dev dependencies.
2. Compose profiles:
   - Development (current), SME production, recovery.
3. Nginx/TLS:
   - Reverse proxy with TLS termination, security headers.
4. Secrets management:
   - No default passwords; startup fails closed on missing secrets.
   - Docker secrets or env-file with correct permissions.
5. Health checks and startup ordering.
6. Resource limits per service.
7. Installer/preflight/status helpers.
8. Provenance/SBOM outputs.

## Exact requirements

1. A clean Linux host can deploy the bounded profile from documented prerequisites.
2. Only intended ports/services are exposed; startup fails closed on errors.
3. Images contain no secrets; satisfy dependency/license/provenance policy.

## Allowed paths

```
docker-compose*.yml
Dockerfile*
nginx/
scripts/install.sh
scripts/preflight.sh
docs/deployment-production.md
oap/orders/133-a-production-compose-appliance-hardening.md
oap/reports/133-a-production-compose-appliance-hardening.md
oap/active
```

## Non-goals

No Kubernetes. No automatic public DNS/TLS. No privileged containers. No default passwords.

## Observable acceptance

- Clean Linux host deployment succeeds from documented prerequisites.
- Only intended ports exposed; startup fails closed on errors.
- Images contain no secrets; SBOM generated.
- All required final-head CI checks green.

## Verification commands

```bash
docker compose -f docker-compose.production.yml config --quiet
bash scripts/preflight.sh
git diff --check
```

## OAP contract

Objective 133-a creates one PR; remediation uses 133-b–z same PR.
Coding agent never merges.
