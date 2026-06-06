# HPC Testing Environment Preparation

This guide documents a safe, reproducible way to prepare a user-owned HPC node
for `scripts/test-supercomputer-sharded.sh` without `sudo`, `apt`, `yum`,
`dnf`, or system-wide package changes.

It is written for local/Codex/HPC verification runs where the caller:

- controls only a user account;
- may have CVMFS modules and `micromamba`;
- may not have PostgreSQL or Chromium on `PATH`;
- must not use `DATABASE_URL` for destructive setup;
- must not run upstream/provider smoke tests;
- must not send real email.

This workflow is environment preparation only. It is not a request to change
repository code.

## Scope

Use this guide when all of the following are true:

- you are on an HPC or other shared Linux host;
- Docker is optional or unavailable;
- browser tests should run if practical, but must remain serial;
- you need a safe temporary PostgreSQL instance for DB-backed tests.

The repository includes two helper scripts for this workflow:

- `scripts/setup-hpc-test-env.sh`
- `scripts/run-hpc-supercomputer-verify.sh`

There is also a repo-local Codex skill:

- `agents/skills/hpc-supercomputer-verify/SKILL.md`

## Safety rules

Always preserve these constraints:

- Refuse `APP_ENV=production`.
- Never use `DATABASE_URL` for destructive test setup.
- Unset `RUN_UPSTREAM_TESTS`, `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`, and
  `OPENROUTER_API_KEY` before the harness.
- Export `ENABLE_EMAIL_DELIVERY=false`.
- Keep E2E in default serial mode unless there is a separate explicit decision
  to opt into `SLAIF_SUPERCOMPUTER_PARALLEL_E2E=1`.
- Keep browser tests serial.
- Do not install system packages.
- Do not use `sudo`.

## Practical constraints observed on a real HPC node

The following issues were observed and are now part of the recommended
workflow:

### Python

- The system `python3` may be too old.
- A newer Python may exist only through CVMFS modules or an explicit path.
- `.venv/bin/python` may fail unless the matching Python shared-library
  directory is present in `LD_LIBRARY_PATH`.

### Git

- `git fetch` / `git pull` may fail in polluted environments because of mixed
  OpenSSL/Kerberos shared libraries.
- Run git commands in a cleaned environment:

```bash
env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH git pull
```

### PostgreSQL

- `psql`, `createdb`, `dropdb`, `initdb`, `pg_ctl`, and `postgres` may be
  unavailable.
- PostgreSQL may need to be provisioned user-locally, for example with
  `micromamba`.
- A user-owned temporary PostgreSQL cluster under `/dev/shm` is a valid
  verification setup.

### Alembic and Unix socket URLs

The harness supports Unix-socket PostgreSQL hosts, but DB-backed test helpers
may still be fragile when the resulting URL is written through Alembic's config
parser. A URL shaped like:

```text
postgresql+asyncpg://user@/db_name?host=%2Fpath%2Fto%2Fsocket&port=55432
```

can trigger `ConfigParser` interpolation errors because of the `%` escapes.

For HPC verification, prefer localhost TCP:

```bash
export PGHOST=127.0.0.1
export PGPORT=55432
```

### Playwright / Chromium

- `python -m playwright install chromium` may succeed, but the browser can
  still fail to launch due to missing runtime libraries.
- A real observed failure was:

```text
libgbm.so.1: cannot open shared object file
```

- `ldd` on the Playwright browser binary is the fastest way to identify missing
  shared libraries.
- Installing `libgbm` and `libdrm` user-locally via `micromamba` was sufficient
  on the observed node.

## Recommended order of work

1. Clean-git preflight and optional `git pull`.
2. Discover Python 3.11+ or configure an explicit Python root/module.
3. Create or reuse `.venv`.
4. Install `.[dev]`.
5. Ensure user-local PostgreSQL tools exist.
6. Ensure Playwright Chromium exists.
7. Inspect Chromium with `ldd`; add missing user-local runtime libraries if
   needed.
8. Start a user-owned PostgreSQL cluster on localhost TCP.
9. Unset dangerous env vars.
10. Run `scripts/test-supercomputer-sharded.sh`.

## Recommended environment variables

The helper scripts understand these optional variables:

- `SLAIF_HPC_PYROOT`
  Use an explicit Python installation root that contains `bin/python3` and
  usually `lib/libpython*.so`.
- `SLAIF_HPC_PYTHON_MODULE`
  HPC module name to load when a good Python is not already on `PATH`.
- `SLAIF_HPC_POSTGRES_PREFIX`
  User-local PostgreSQL install prefix. Default is under `/dev/shm/$USER`.
- `SLAIF_HPC_BROWSER_LIB_PREFIX`
  User-local browser runtime library prefix. Default is under `/dev/shm/$USER`.
- `SLAIF_HPC_PLAYWRIGHT_BROWSERS_PATH`
  Browser download location. Default is under `/dev/shm/$USER`.
- `SLAIF_HPC_PGPORT`
  Port for the temporary PostgreSQL cluster. Default is `55432`.
- `SLAIF_HPC_RUN_LOG`
  Run log path for the wrapper script. Default is
  `/tmp/slaif-supercomputer-run.log`.
- `SLAIF_HPC_GIT_PULL`
  Set to `1` if the wrapper should run `git fetch`, `git switch main`, and
  `git pull --ff-only origin main` using a cleaned git environment before the
  harness.

## Setup script

Use:

```bash
scripts/setup-hpc-test-env.sh
```

This script:

- validates that `APP_ENV` is not `production`;
- discovers a suitable Python runtime;
- creates or reuses `.venv`;
- installs `.[dev]`;
- installs PostgreSQL 16 user-locally with `micromamba` when needed;
- installs Playwright Chromium user-locally when needed;
- checks Chromium with `ldd`;
- installs `libgbm` / `libdrm` user-locally when needed;
- prints shell `export` lines or writes them to a file.

Example:

```bash
scripts/setup-hpc-test-env.sh --write-env-file /tmp/slaif-hpc.env
source /tmp/slaif-hpc.env
```

## Full verification wrapper

Use:

```bash
scripts/run-hpc-supercomputer-verify.sh 128
```

This wrapper:

- calls `scripts/setup-hpc-test-env.sh`;
- starts a temporary PostgreSQL cluster under `/dev/shm` or `$TMPDIR`;
- uses localhost TCP instead of a Unix-socket-only database URL;
- exports `SLAIF_SUPERCOMPUTER_PGHOST`, `SLAIF_SUPERCOMPUTER_PGPORT`, and
  `SLAIF_SUPERCOMPUTER_PGUSER`;
- exports `PLAYWRIGHT_BROWSERS_PATH`;
- exports `PYTHON=$PWD/.venv/bin/python`;
- unsets provider-key and dangerous DB env vars;
- runs `scripts/test-supercomputer-sharded.sh`;
- preserves the harness exit code;
- prints `SUMMARY_PATH=...` and the summary body when present.

## Example: manual browser smoke after setup

If you need to validate browser support independently of the full harness:

```bash
source /tmp/slaif-hpc.env
export TEST_DATABASE_URL="postgresql+asyncpg://$USER@127.0.0.1:55433/slaif_browser_test_local"
python -m pytest tests/browser -m playwright -vv -rs
```

If browser launch still fails, inspect the browser binary:

```bash
find "$PLAYWRIGHT_BROWSERS_PATH" -type f -name chrome-headless-shell -o -name chrome
ldd /path/to/browser/binary
```

## Current known-good outcome on a real HPC node

With:

- Python 3.12 from a CVMFS root;
- PostgreSQL 16 installed user-locally via `micromamba`;
- Playwright Chromium installed user-locally;
- `libgbm` and `libdrm` installed user-locally;
- temporary PostgreSQL running on `127.0.0.1:55432`;

the harness produced:

- `unit`: PASS
- `integration`: 56/57 files passed
- `e2e`: 5/5 files passed
- `browser`: PASS

The remaining failing integration test was a repository behavior issue, not an
HPC environment-preparation issue.

## What to do when a phase still skips or fails

### PostgreSQL suites skip

Check:

- `psql --version`
- `createdb --version`
- `dropdb --version`
- `psql -d postgres -Atc "select 1"`

If tools are missing, rerun `scripts/setup-hpc-test-env.sh` and confirm
`micromamba` is available.

### Browser skips

Check:

- `python -m playwright install chromium`
- `echo "$PLAYWRIGHT_BROWSERS_PATH"`
- `ldd` output for the downloaded Chromium binary

If `libgbm.so.1` is missing, install user-local browser libs with the setup
script.

### Git fails

Retry with a cleaned environment:

```bash
env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH git pull
```

### Summary file missing

On current `main`, the summary counting bug is already fixed. If summary output
is still missing, inspect:

- `scripts/test-supercomputer-sharded.sh`
- `/tmp/slaif-supercomputer-run.log`
- the newest `/dev/shm/slaif-gateway-tests-*` run directory

## Files related to this workflow

- `scripts/test-supercomputer-sharded.sh`
- `scripts/setup-hpc-test-env.sh`
- `scripts/run-hpc-supercomputer-verify.sh`
- `docs/testing-parallelism.md`
- `tests/browser/test_admin_dashboard_smoke.py`
- `tests/integration/db_test_utils.py`
