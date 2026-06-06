# HPC Supercomputer Verify

Use this skill when working in `slaif-api-gateway` on an HPC or other shared
Linux node where PostgreSQL, browser binaries, or browser runtime libraries may
be missing.

## Goal

Prepare a safe user-local test environment and run the repository's
supercomputer harness without `sudo`, `apt`, `yum`, or global package changes.

## When to use

Use this skill when the task is any of:

- run `scripts/test-supercomputer-sharded.sh` on an HPC node;
- prepare PostgreSQL locally for DB-backed tests;
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
4. Prefer localhost TCP PostgreSQL instead of a Unix-socket-only `PGHOST` so
   DB-backed tests do not inherit percent-encoded socket paths in
   `TEST_DATABASE_URL`.
5. If browser launch fails, inspect the Playwright browser binary with `ldd`.
6. Install missing browser runtime libraries user-locally when practical.
7. Run `scripts/run-hpc-supercomputer-verify.sh 128` unless the user gave a
   different worker count.
8. Preserve the harness exit code and report `SUMMARY_PATH`.

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
- Distinguish clearly between environment blockers, harness bugs, and real test
  failures.

## Known practical fixes

- User-local PostgreSQL can be installed with `micromamba` into a prefix under
  `/dev/shm/$USER`.
- Playwright Chromium can be installed with
  `python -m playwright install chromium`.
- Missing `libgbm.so.1` can be fixed with a user-local `micromamba` prefix that
  provides `libgbm` and `libdrm`.

