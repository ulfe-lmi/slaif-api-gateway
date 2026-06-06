# Test Parallelism

This project uses parallel unit tests by default and keeps database-backed suites
serial until each worker can get isolated database, Redis, and server resources.

## Unit Tests

`scripts/test-unit-parallel.sh` runs `tests/unit` with pytest-xdist. The default
worker count is:

```text
min(20, visible CPU cores)
```

The wrapper intentionally avoids `-n auto` as its default so CI and local runs
have an explicit target. Operators can still override the worker count and xdist
distribution arguments:

```bash
PYTEST_XDIST_WORKERS=1 scripts/test-unit-parallel.sh
PYTEST_XDIST_WORKERS=20 scripts/test-unit-parallel.sh
PYTEST_XDIST_ARGS="--dist loadscope" scripts/test-unit-parallel.sh
```

The current default distribution remains `--dist loadscope`.

## Current Parallel-Safety Status

| Suite | Default | Parallel-safe today? | Reason |
| --- | --- | --- | --- |
| `tests/unit` | xdist | Yes | Unit tests do not require PostgreSQL, Redis, Docker, real provider keys, or real email. |
| `tests/integration` | serial | Not with one shared DB | The suite shares `TEST_DATABASE_URL`, applies Alembic migrations, includes schema-destructive migration/readiness tests, and some tests use shared Redis state. |
| `tests/e2e` | serial | Not with one shared DB | Tests run Alembic and live Uvicorn app instances against the same `TEST_DATABASE_URL`; they need per-worker DBs and disciplined per-worker ports before xdist is safe. |
| `tests/browser` | serial | Not with one shared DB/browser setup | The Playwright smoke test seeds shared dashboard data, runs a live app on a local port, and needs per-worker DB, app port, and browser context isolation. |

`scripts/test-parallel-safe.sh` reflects that split: it runs unit tests in
parallel, then runs integration, E2E, and browser suites serially. It does not
create, mutate, or drop test databases.

## Shared-State Inventory

Database-backed tests must use `TEST_DATABASE_URL`, never `DATABASE_URL`, for
destructive test setup. Production safety checks reject database names that do
not include safe markers such as `test`, `dev`, or `local`.

Destructive or migration-sensitive tests include:

- `tests/integration/conftest.py`, which applies Alembic migrations once per
  shared test database before integration tests run.
- `tests/integration/test_readyz_postgres.py`, which drops the `public` schema
  in one readiness test and then upgrades it again.
- `tests/integration/test_gateway_key_prefix_migration_postgres.py`, which runs
  targeted Alembic revisions for migration validation.
- `tests/integration/test_migrations_postgres.py` and
  `tests/integration/test_alembic_fresh_upgrade_postgres.py`, which validate
  migration behavior and must not race other workers against the same schema.
- E2E files under `tests/e2e/`, which call `run_alembic_upgrade_head(...)`
  before live OpenAI-client gateway checks.
- `tests/browser/test_admin_dashboard_smoke.py`, which calls
  `run_alembic_upgrade_head(...)` and seeds dashboard rows before launching a
  live app.

Tests that use `async_test_session` from `tests/integration/conftest.py` get a
per-test rollback transaction. That makes those individual repository/service
tests safer, but it does not make the whole integration suite xdist-safe because
other tests use direct engines, CLI/app settings pointed at the shared database,
schema migration operations, and shared Redis resources.

Redis-backed tests include:

- `tests/integration/test_redis_rate_limit_service.py`
- `tests/integration/test_v1_rate_limits_redis.py`
- `tests/integration/test_v1_streaming_rate_limit_concurrency_postgres_redis.py`

They use `TEST_REDIS_URL` when provided or start a temporary user-owned
`redis-server` on a free localhost port when available. Parallel Redis tests
would need per-worker Redis databases, key prefixes, or separate Redis
instances, plus cleanup that cannot erase another worker's keys.

Live-server tests require unique ports and app instances. E2E and browser tests
already allocate free localhost ports for a single process, but xdist would also
need each worker to own its database and Redis state so two live apps do not
mutate the same records concurrently.

## Safe Per-Worker DB Plan

Do not run database-backed suites under xdist against one shared database. A
safe future workflow should:

1. Derive a worker ID from `PYTEST_XDIST_WORKER`, for example `gw0`, `gw1`.
2. Create one PostgreSQL database per worker, such as
   `slaif_gateway_test_xdist_gw0`.
3. Build each worker's effective `TEST_DATABASE_URL` from that database name.
4. Run Alembic `upgrade head` once per worker database before worker tests.
5. Never use `DATABASE_URL` for destructive setup.
6. Drop per-worker databases after the run unless an explicit debug flag keeps
   them.
7. Split destructive migration/schema tests into a serial-only subset, or give
   each migration worker an exclusive database that no transactional tests share.
8. Give Redis-backed workers isolated Redis DB numbers, key prefixes, or
   separate Redis instances.
9. Give E2E/browser workers unique app ports and browser contexts.

The likely implementation sequence is:

1. Keep the current serial integration/E2E/browser defaults.
2. Add an opt-in experimental script for per-worker DB creation and cleanup.
3. Mark migration/destructive tests as serial-only or run them in a separate
   job.
4. Once reliable, split integration into xdist-safe transactional tests and a
   serial migration/destructive subset.
5. Extend the same per-worker DB and port pattern to E2E. Keep browser tests
   serial until Playwright worker isolation is verified.

Until that workflow exists, CI and local scripts should not parallelize
integration, E2E, or browser suites.
