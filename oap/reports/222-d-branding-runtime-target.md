# OAP Coding-Agent Report — 222-d

## Work order and result

- Identifier `222-d`; root-authored order `oap/orders/222-d-branding-runtime-target.md` SHA256 `42e007f910de191dc036c97a0224a2c9daac276606ec5c2dda54fcd62fa8e7d6`; `oap/active` exact `222-d` (5 bytes, no newline).
- RESULT: COMPLETE — single test-fixture build-target correction on the SAME objective-222 PR #381: `tests/integration/test_branding_container.py` now passes `target="runtime"` to the Docker SDK build, so the branding fixture builds the ordinary app image instead of the Dockerfile's LAST stage (the optional `demo-snapshot-worker` with its PGDG apt step). No Dockerfile, package-installation, application-source, branding-asset, sanitizer, authentication, accounting, CI-workflow or other-test change. Prior 222-a/b/c reports and orders preserved byte-for-byte. Report publication commit: SELF. No merge/auto-merge.

## Demonstrated CI blocker (exact state, not retried blindly)

- On exact SELF `a3326a27956cce5932848ce9b756c7551427f4fd` (immutable 222-c report-only SELF), hosted PostgreSQL integration job `131069186755` in CI run `43184793665` attempt 1 completed FAILURE at 2026-11-12T08:59:01Z: 678 passed, 50 skipped, and four errors ONLY at the branding-container fixture setup, each `docker.errors.BuildError` from the optional worker apt command exit 100 — the command failure occurs BEFORE any branding assertion. No apt/network root cause is claimed beyond exit 100 (not diagnosed further from the job logs).
- A single failed-job rerun (attempt 2) was started to test transience and cancelled by root after identifying the deterministic wrong-target fixture cause; the GitHub run reached terminal `cancelled` at 2026-11-12T09:02:26Z on the same head. It did not pass. No blind retry loop.
- The test file, Dockerfile and runtime app were unchanged by 222-c; the same suite passed on the predecessor 222-b head (10/10 checks green). The 222-c sanitizer's focused 58-unit and six owned-PG16 integration cases passed locally, and nine of ten 222-c hosted checks passed.

## Root cause and repair

Root cause (structural proof): `Dockerfile` stage 1 is `FROM python:3.12-slim AS runtime` (line 1) and the LAST stage is `FROM runtime AS demo-snapshot-worker` (line 43), which adds the PGDG repository and `postgresql-client-16` through `apt-get` (lines 52–61). A Docker SDK build without `target` builds the LAST stage, so the branding fixture needlessly built the worker image and depended on Debian/PGDG package retrieval. Repair: the fixture's `client.images.build(...)` now explicitly selects `target="runtime"` (the existing ordinary app stage), with a comment pinning the reason. Retained unchanged: owned-image/container labels (`slaif187a.owner`), loopback bind, read-only mount, nonroot assertion, exact-ID cleanup, synthetic settings, and all four browser/HTTP assertions.

## Verification (exact execution)

- Local focused run of the four affected branding-container integration tests against an owned labeled image/container with ACTUAL HTTP responses (loopback bind, read-only mount, synthetic settings): **4 passed in 75.07s**, direct pytest process exit 0. This is local synthetic-container proof, NOT hosted CI: the final-head hosted checks of the new SELF (ten checks / three workflows) are the strategic root's gate.
- Build-target proof: with `target="runtime"` the local build completes on the cached runtime layers without executing the worker's PGDG apt step; the Dockerfile stage layout above shows the default (last-stage) target is the optional worker.
- Cleanup verified: teardown removed ONLY the exact owned image/container; independent post-run check found 0 containers (label `slaif187a.owner`) and 0 images (reference `slaif187a-branding-*`), i.e. no port/mount leaks.
- Focused Ruff on the changed test file: pass. `git diff --check`: clean. Diff scope: exactly `tests/integration/test_branding_container.py` plus the unchanged strategic-authored order and `oap/active`.
- Unchanged 222-a/b/c sanitizer evidence is reused without rerunning broad local suites; no source/prod database, provider or mail access; no local Docker network/package outage occurred (the build succeeded).
- No actual source identifier, secret, raw row or canary token appears in this report or ordinary logs.

## Publication and strategic follow-up

This report is published once at `oap/reports/222-d-branding-runtime-target.md` via same-directory temp, file fsync, atomic replace (exactly once) and directory fsync. Its report-only SELF commit has sole parent the implementation head and changes ONLY this report. After verifying exact remote PR/head, order/active/report bytes and the three protected untracked hashes, exactly one two-byte response `OK` is sent to the canonical response FIFO and exactly one canonical control waiter is rearmed on tmux `%9`. Strategic root checks the final-head hosted ten checks / three workflows and review threads/material scope, guarded-merges only if all green, verifies actual main nine checks / three workflows, records timings, then activates 223. No release/tag/deploy.
