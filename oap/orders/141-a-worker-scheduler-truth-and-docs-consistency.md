# OAP Work Order — 141-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/141-worker-scheduler-truth-and-docs-consistency`
Base: main @ 586823dba7c8

## Objective and reason

Resolve the worker/scheduler packaging inconsistency identified in the MVP
closure audit and perform a final documentation consistency pass. The
compatibility matrix says reconciliation "can be explicitly enabled" via
Celery/Celery Beat, but the production Compose profile omits both services
without documenting this limitation.

## Scope

1. Add optional worker and scheduler services to `docker-compose.production.yml`
   behind a Docker Compose profile (e.g., `--profile async`).
2. Update `docs/deployment-production.md` to document:
   - Default production profile runs API + PostgreSQL + Redis + Nginx only.
   - Async operations (reconciliation, email delivery) require `--profile async`.
   - Reconciliation is available via CLI without worker/scheduler.
3. Final documentation consistency pass:
   - Verify README, product-scope, rc2-feature-scope, compatibility-matrix,
     deployment docs, and beta-readiness all consistently distinguish:
     implemented / mock-verified / real-provider-qualified / MVP-complete /
     optional / deferred / post-MVP.
   - Remove any stale caveats that claim something is untested after it has
     been genuinely qualified (e.g., Qwen real-provider, OpenAI/OpenRouter
     real-provider qualification from 140-a).

## What does NOT count as completion

- Adding worker/scheduler unconditionally to the default production profile.
- Documentation changes that overclaim capabilities not yet implemented.
- Ignoring existing stale caveats.

## Allowed paths

```
docker-compose.production.yml
docs/deployment-production.md
docs/product-scope.md
docs/rc2-feature-scope.md
docs/compatibility-matrix.md
docs/beta-readiness.md
README.md
oap/orders/141-a-worker-scheduler-truth-and-docs-consistency.md
oap/reports/141-a-worker-scheduler-truth-and-docs-consistency.md
oap/active
```

## Verification

```bash
docker compose -f docker-compose.production.yml config --quiet
docker compose -f docker-compose.production.yml --profile async config --quiet
git diff --check
```

## Acceptance

Both compose configs valid; docs updated; no contradictions remain;
all CI green; report-only SELF commit; never merge.
