# HPC Supercomputer Verify

Use this skill when working in `slaif-api-gateway` on an HPC or other shared
Linux node where PostgreSQL, browser binaries, or browser runtime libraries may
be missing.

## Goal

Prepare a safe user-local test environment and run the repository's
supercomputer harness without `sudo`, `apt`, `yum`, or global package changes.
The user stays inside Codex on the HPC node; Codex runs the shell commands. Repo
scripts never invoke `codex`.

## When to use

Use this skill when the task is any of:

- run `scripts/test-supercomputer-sharded.sh` on an HPC node;
- prepare PostgreSQL locally for DB-backed tests;
- prepare Redis locally so Redis-backed integration tests execute instead of
  skipping;
- prepare Docker Compose config tooling without installing a Docker daemon;
- prepare Playwright Chromium locally for browser smoke tests;
- diagnose browser launch failures caused by missing shared libraries;
- produce a verification summary without modifying repository code.

Do not use this skill when the user asked for repository code changes unrelated
to test-environment preparation.

## Primary repo entry points

- `docs/testing-hpc.md`
- `scripts/setup-hpc-test-env.sh`
- `scripts/run-hpc-supercomputer-verify.sh`
- `scripts/test-supercomputer-sharded.sh`

## Workflow

1. Run a shell preflight.
2. Use a cleaned environment for `git` commands:
   `env -u LD_LIBRARY_PATH -u LIBRARY_PATH -u CPATH -u PKG_CONFIG_PATH -u PYTHONPATH git ...`
3. Run `scripts/setup-hpc-test-env.sh`.
4. Ensure the setup output includes user-local or module-provided Python,
   PostgreSQL, Redis, Playwright Chromium, and Docker Compose config tooling.
5. Prefer localhost TCP PostgreSQL instead of a Unix-socket-only `PGHOST` so
   DB-backed tests do not inherit percent-encoded socket paths in
   `TEST_DATABASE_URL`.
6. If browser launch fails, inspect the Playwright browser binary with `ldd`.
7. Install missing browser runtime libraries user-locally when practical.
8. Run `scripts/run-hpc-supercomputer-verify.sh 128` unless the user gave a
   different worker count.
9. Preserve the harness exit code and report `SUMMARY_PATH`.

## Rules

- Refuse `APP_ENV=production`.
- Never use `DATABASE_URL` for destructive setup.
- Unset `RUN_UPSTREAM_TESTS`, `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`, and
  `OPENROUTER_API_KEY` before the harness.
- Export `ENABLE_EMAIL_DELIVERY=false`.
- Keep E2E in default serial mode unless the caller explicitly opts into
  `SLAIF_SUPERCOMPUTER_PARALLEL_E2E=1`.
- Keep browser tests serial.
- Do not install system packages.
- Do not use `sudo`.
- Do not install or require a Docker daemon. Docker verification only needs
  `docker compose config`.
- If Docker is absent, use standalone Docker Compose plus the setup script's
  thin user-local `docker compose ...` wrapper.
- If Compose config needs environment values, copy `.env.example` to an ignored
  local `.env`; never commit `.env`.
- Distinguish clearly between environment blockers, harness bugs, and real test
  failures.
- Final reports must use two tables: `Validation phases` for non-pytest checks
  and `Test suites` for pytest counts.

## Known practical fixes

- User-local PostgreSQL can be installed with `micromamba` into a prefix under
  `/dev/shm/$USER`.
- User-local Redis can be installed with modules, conda-style package managers,
  or a pinned official Redis source build into a prefix under `/dev/shm/$USER`.
- Redis must be available on `PATH` before the harness so Redis-backed
  integration tests do not skip.
- Standalone Docker Compose plus a thin `docker` wrapper is enough for
  `docker compose config`; no Docker daemon installation is needed.
- Playwright Chromium can be installed with
  `python -m playwright install chromium`.
- Missing `libgbm.so.1` can be fixed with a user-local `micromamba` prefix that
  provides `libgbm` and `libdrm`.
