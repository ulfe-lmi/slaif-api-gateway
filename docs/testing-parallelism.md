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

## Supercomputer Sharded Harness

`scripts/test-supercomputer-sharded.sh` is an opt-in harness for a trusted
single-node high-core environment such as an interactive supercomputer node. It
is not part of normal CI and is not required for local development.

Run it with exactly one positional argument: the requested maximum worker count.

```bash
scripts/test-supercomputer-sharded.sh 128
```

The script:

- records branch, commit, dirty working tree status, host, CPU/memory/disk, and
  tool versions;
- creates a unique run directory under `SLAIF_SUPERCOMPUTER_RAMDISK`, writable
  `/dev/shm`, or `${TMPDIR:-/tmp}`;
- stores logs, JUnit files, shard status files, and `SUMMARY.md` in that run
  directory;
- runs hygiene checks (`ruff`, Alembic heads, `git diff --check`, Docker Compose
  config when available, hidden Unicode scan, and safety scan);
- runs unit tests through `scripts/test-unit-parallel.sh` with
  `PYTEST_XDIST_WORKERS=<workers>`;
- discovers integration and E2E test files dynamically and runs them as
  file-level shards;
- runs integration files with max concurrency `<workers>`;
- runs E2E files serially by default, still with one isolated database per
  file, because E2E tests may need unique app/server/port resources;
- creates a fresh generated PostgreSQL database for every DB-backed shard and
  passes it only through `TEST_DATABASE_URL`;
- unsets `DATABASE_URL` and `TEST_REDIS_URL` for shard subprocesses so they do
  not share a destructive DB target or Redis state accidentally;
- runs browser tests serially with an isolated database unless
  `SLAIF_SUPERCOMPUTER_SKIP_BROWSER=1`;
- drops generated databases on cleanup unless
  `SLAIF_SUPERCOMPUTER_KEEP_DBS=1`;
- prints a copy-paste-friendly final summary and the summary path.

Optional environment variables:

| Variable | Purpose |
| --- | --- |
| `SLAIF_SUPERCOMPUTER_RAMDISK` | Preferred run-directory root. |
| `SLAIF_SUPERCOMPUTER_KEEP_DBS=1` | Keep generated shard databases for debugging. |
| `SLAIF_SUPERCOMPUTER_KEEP_WORKDIR=1` | Keep the run directory explicitly; summaries/logs are otherwise still printed and retained in the selected run root. |
| `SLAIF_SUPERCOMPUTER_SKIP_BROWSER=1` | Skip browser tests with a summary note. |
| `SLAIF_SUPERCOMPUTER_SKIP_DOCKER=1` | Skip Docker Compose config checks with a summary note. |
| `SLAIF_SUPERCOMPUTER_PARALLEL_E2E=1` | Opt into E2E file-level concurrency up to `<workers>` after verifying the environment has safe per-file app/server/port isolation. Default E2E concurrency is 1. |
| `SLAIF_SUPERCOMPUTER_PGHOST` | PostgreSQL host or Unix socket path override. |
| `SLAIF_SUPERCOMPUTER_PGPORT` | PostgreSQL port override. |
| `SLAIF_SUPERCOMPUTER_PGUSER` | PostgreSQL user override. |
| `SLAIF_SUPERCOMPUTER_DB_PREFIX` | Generated DB-name prefix; must include a test/hpc marker. |
| `SLAIF_SUPERCOMPUTER_START_POSTGRES=1` | Reserved future hook for a user-owned temporary cluster; the current script refuses it rather than pretending to support it. |

Requirements and safety behavior:

- The script refuses `APP_ENV=production`.
- The script refuses `RUN_UPSTREAM_TESTS=1`.
- It does not install dependencies by default; run
  `python -m pip install -e ".[dev]"` first.
- It needs `createdb`, `dropdb`, and `psql` for DB-backed shards. PostgreSQL is
  considered available only after the script creates and drops a generated
  probe database under the safe run prefix. If the commands, connection, or
  create/drop probe fail, integration, E2E, and browser phases are marked
  skipped with the exact reason.
- It never uses `DATABASE_URL` for destructive setup. If `DATABASE_URL` is set,
  the script records that it is ignored and unsets it for shard subprocesses.
- Generated DB names use a `slaif_hpc_test_...` prefix by default, and cleanup
  refuses to drop any DB outside the generated prefix.
- Normal tests still use mocked upstream HTTP and disabled real email behavior.

Known limitations:

- DB sharding is file-level. Each integration/E2E test file gets its own
  generated database and runs serially inside that file. Integration files are
  concurrent up to `<workers>`. E2E files are serial by default and may be made
  file-concurrent only with `SLAIF_SUPERCOMPUTER_PARALLEL_E2E=1`. This is
  conservative and intentionally avoids nested xdist against one DB.
- Browser tests are serial by default. Parallel browser execution needs a future
  per-worker database, app port, and Playwright isolation workflow.
- Redis-backed tests do not receive a shared `TEST_REDIS_URL` from the harness;
  they use their own test fallback behavior. A future version may add explicit
  per-worker Redis DB or instance isolation.
- The current script uses an existing PostgreSQL server reachable through normal
  user `createdb`/`dropdb`/`psql` commands. The temporary ramdisk PostgreSQL
  cluster hook is documented but not implemented yet; setting
  `SLAIF_SUPERCOMPUTER_START_POSTGRES=1` is refused rather than treated as
  supported.

Troubleshooting:

- If DB-backed phases are skipped, check the `environment` and summary logs for
  PostgreSQL command availability and connection details.
- If a single shard fails, inspect the shard log listed in `SUMMARY.md`; shard
  logs include the test file and generated DB name.
- If the run is interrupted, cleanup still attempts to drop all generated DBs
  whose names match the run prefix.

Copy-paste block for a remote Codex runner:

```bash
git fetch origin
git switch <branch>
python -m pip install -e ".[dev]"
scripts/test-supercomputer-sharded.sh 128
cat <reported-run-dir>/SUMMARY.md
```
