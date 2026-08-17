# 2026-08-17 Current-Main Baseline Verification

## Result

`RESULT=FAIL`

One full current-machine matrix was run at the execution host's actual
24-worker capacity. The wrapper exited 1 and emitted `RESULT=FAIL_REAL_TEST`:
2,533 of 2,534 tests passed, with one unit-test failure. This is a meaningful
repository/test failure, not an environment-blocked result.

The successful portions do not make the overall gate green. In particular:

```text
128-worker post-PR-220 HPC qualification: NOT RUN
```

## Identity and time

- Date: 2026-08-17
- Timezone: Europe/Ljubljana (CEST, UTC+02:00)
- Matrix start: 2026-08-17 22:01:39 CEST
- Matrix duration: 202 seconds
- Repository: `ulfe-lmi/slaif-api-gateway`
- Starting merged `main`: `f137d0467cbc6fb2a61ce99494ea724a173cd633`
- Exact tested commit: `0f09de476f643e5879baeaf08eeb1d7393529758`
- Tested-commit relationship: the tested commit's parent is the starting
  `main`; it adds only the immutable OAP 001-a active pointer and work order.
- OAP objective: `001-a`
- PR: [#226](https://github.com/ulfe-lmi/slaif-api-gateway/pull/226)
- Branch: `oap/001-current-main-baseline-verification`

## Execution environment

- Operating environment: Linux 6.18.33.2 WSL2, x86_64
- Logical CPU capacity: 24
- Requested harness workers: 24
- Memory at preflight: approximately 47 GiB RAM and 48 GiB swap
- `/dev/shm` capacity at preflight: 24 GiB
- Python: 3.12.3
- pytest: 9.0.3
- Ruff: 0.15.16
- PostgreSQL: 16.15
- Redis: 7.0.15
- Docker CLI: 29.1.3
- Docker Compose: 2.40.3
- Playwright: 1.60.0
- OpenAI Python package: 2.41.0
- RESPX: 0.23.1

The setup helper logged several conda-forge package-shard network timeouts, but
provisioning completed: PostgreSQL, Redis, Compose tooling, and Chromium were
available, and no required phase skipped because of those warnings.

## Exact command

The following command block was executed exactly once:

```bash
unset DATABASE_URL TEST_DATABASE_URL RUN_UPSTREAM_TESTS OPENAI_API_KEY OPENAI_UPSTREAM_API_KEY OPENROUTER_API_KEY
export ENABLE_EMAIL_DELIVERY=false
export SLAIF_HPC_GIT_PULL=0
export SLAIF_HPC_RUN_LOG=/tmp/slaif-oap-001-current-main.log
export SLAIF_HPC_SETUP_ENV_FILE=/tmp/slaif-oap-001-hpc.env
scripts/run-hpc-supercomputer-verify.sh 24
```

- Wrapper exit code: 1
- Objective classification: `RESULT=FAIL`
- Harness classification: `RESULT=FAIL_REAL_TEST`
- Run directory:
  `/dev/shm/slaif-gateway-tests-ubuntu-20260817-200139-1150731`
- Summary path:
  `/dev/shm/slaif-gateway-tests-ubuntu-20260817-200139-1150731/SUMMARY.md`
- Summary SHA-256:
  `220f837d2ede0647455d5f946f6cd041d20d375513b2b71962f4d0592430d97b`
- Wrapper log: `/tmp/slaif-oap-001-current-main.log`

The raw log, summary, environment exports, virtual environment, browser assets,
and database files are temporary local artifacts and are not committed.

## Validation phases

| Phase | Status | Duration (s) | Note |
| --- | --- | ---: | --- |
| environment | PASS | 0 | Clean tracked tree recorded at tested commit |
| dependency_sanity | PASS | 0 | pytest, xdist, Ruff, and Alembic available |
| ruff | PASS | 0 | Complete configured lint command |
| alembic_heads | PASS | 0 | One migration head |
| git_diff_check | PASS | 0 | No tracked diff at test time |
| hidden_unicode | PASS | 2 | Repository scan passed |
| safety_scan | PASS | 0 | Harness safety assertions passed |
| docker_compose_config | PASS | 0 | Config validation; no daemon required |

No validation phase failed or skipped.

## Test suites

| Suite | Status | Duration (s) | Tests | Passed | Failed | Skipped | Execution note |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| unit | FAIL | 53 | 2,359 | 2,358 | 1 | 0 | 24 xdist workers |
| integration | PASS | 40 | 130 | 130 | 0 | 0 | 59 file shards, max concurrency 24 |
| E2E | PASS | 90 | 43 | 43 | 0 | 0 | 8 file shards, default serial concurrency 1 |
| browser | PASS | 14 | 2 | 2 | 0 | 0 | Serial, isolated database |
| **Total** | **FAIL** |  | **2,534** | **2,533** | **1** | **0** |  |

There were no skipped tests or coverage-weakening skipped phases. The default
serial E2E mode was retained; browser execution also remained serial.

## Failure

The single failure was:

```text
FAILED tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr
assert "one numeric objective as exactly one PR" in order_text
1 failed, 2358 passed, 30 warnings in 52.81s
```

The active `001-a` order correctly declares `PR mode: CREATE_NEW_PR` and says to
create exactly one new PR, but it does not contain the separate literal phrase
the existing governance test requires for every `-a` order. Neither the
strategic-authored order nor the test was modified in this verification-only
round. No repair or second harness run was attempted.

The full unit log is at
`/dev/shm/slaif-gateway-tests-ubuntu-20260817-200139-1150731/logs/unit.log`.
There were no failing integration/E2E shard entries or failing shard logs.

## Slowest shards

| Seconds | Suite | Test file |
| ---: | --- | --- |
| 24 | integration | `tests/integration/test_cli_routing_pricing_postgres.py` |
| 22 | E2E | `tests/e2e/test_openai_python_client_responses.py` |
| 20 | integration | `tests/integration/test_cli_keys_postgres.py` |
| 19 | integration | `tests/integration/test_cli_admin_owner_records_postgres.py` |
| 18 | integration | `tests/integration/test_admin_key_actions_postgres.py` |
| 18 | integration | `tests/integration/test_admin_web_auth_postgres.py` |
| 17 | integration | `tests/integration/test_admin_route_actions_postgres.py` |
| 17 | integration | `tests/integration/test_admin_email_delivery_actions_postgres.py` |
| 16 | E2E | `tests/e2e/test_openai_python_client_chat.py` |

## PostgreSQL, Redis, browser, and Compose evidence

- PostgreSQL create/drop probing passed before the matrix.
- `DATABASE_URL` was unset and was not used for destructive setup.
- Every database-backed shard received a generated, isolated
  `TEST_DATABASE_URL` under the safe run prefix.
- Integration used at most 24 concurrent database file shards; E2E used one;
  browser used one isolated serial database.
- The harness's safe per-shard cleanup dropped generated databases because
  `SLAIF_SUPERCOMPUTER_KEEP_DBS` was not enabled.
- The user-local PostgreSQL cluster on `127.0.0.1:55432` was stopped by the
  wrapper and independently verified stopped after exit. Its transient cluster
  files remain only under `/dev/shm` as the wrapper's reusable local cache.
- Redis-backed integration tests ran instead of skipping: 10 tests passed
  across the Redis rate-limit service, v1 rate-limit, and streaming concurrency
  files.
- Docker Compose configuration validation passed through local Compose tooling;
  no Docker daemon was installed or required.
- Playwright Chromium ran; the serial browser suite passed 2/2.

## Safety and scope

- The full 24-worker harness was run exactly once.
- No 128-worker run was attempted on this 24-core host.
- No separate unit, integration, E2E, browser, or other broad suite was run.
- `RUN_UPSTREAM_TESTS` and all OpenAI/OpenRouter credential variables were
  unset; no real provider call occurred.
- `ENABLE_EMAIL_DELIVERY=false`; no real email was sent.
- No production or staging database, data, credential, deployment, or provider
  catalog was accessed.
- No prompt, response, provider secret, gateway secret, or email body was
  recorded in this evidence.
- No application, existing test, script, CI workflow, migration, dependency,
  deployment, or provider-catalog file changed.
- `.local-provider-catalog/` remained ignored and untouched.
- No raw log, virtual environment, browser binary, PostgreSQL data, or `/tmp` or
  `/dev/shm` artifact is committed.
- Prior OAP orders and reports remain unchanged.

## Evidence boundaries

This record is one current-machine result for the exact tested commit. It must
not be conflated with:

- the historical May 2026 counts in `docs/beta-readiness.md`;
- GitHub CI, which is a separate standard PR matrix;
- the still-unrun full 128-worker post-PR-220 HPC qualification;
- real OpenAI/OpenRouter behavior, which was not exercised;
- production, security, penetration-test, compliance, reliability, or scale
  certification; or
- an RC2 tag or release decision, which remains with the maintainer/strategic
  authority.

## Release recommendation

Do not use this run as a green current-main release gate. Preserve it as failed
baseline evidence and require a deliberately authorized, focused continuation
to resolve the OAP governance contract mismatch before any fresh verification
gate. The 128-worker post-PR-220 qualification and RC2 release decision remain
outstanding regardless of that future result.

## Focused remediation — OAP 001-b

OAP continuation `001-b` repairs the narrow governance contract mismatch in
commit `76e99e2598e0ceadd98baadba82890249e4b5bd2` without changing or rerunning the
historical matrix above.

Root cause: the original test duplicated the one-objective/one-PR invariant by
requiring every active `NNN-a` strategic order to repeat the literal prose
fragment `one numeric objective as exactly one PR`. The active 001-a order
already declared `PR mode: CREATE_NEW_PR`, required exactly one new PR, and
prohibited a second PR, but did not contain that exact fragment.

Focused change: the test remains identifier-generic and continues to require
`PR mode: CREATE_NEW_PR` from the active `NNN-a` order. Its second assertion now
reads the durable coding-agent protocol and requires:

```text
`NNN-a` creates exactly one new PR for that numeric objective.
```

This is structural rather than weaker: active-order mode and durable protocol
invariant are both asserted, while arbitrary repeated order wording is not.

Observed focused results:

- `python -m pytest tests/unit/test_oap_governance.py -q`: PASS — 8/8.
- `python -m ruff check tests/unit/test_oap_governance.py`: PASS.
- No full unit, integration, E2E, browser, Docker, HPC, or other broad local
  suite was run.
- The 24-worker harness was not run a second time.
- Implementation-head GitHub CI had not started at documentation time; its
  actual observed result is recorded in the immutable OAP 001-b report and on
  PR #226 rather than predicted here.

Evidence interpretation:

- The original one-pass full matrix remains the historical `RESULT=FAIL` record
  with its original tables, counts, command, timestamps, and failure.
- Focused remediation plus final standard PR CI can qualify the corrected PR
  candidate without rewriting the original failed run as green.
- The 128-worker post-PR-220 HPC qualification remains **NOT RUN**.
- No production, RC2 release, security, penetration-test, compliance, or scale
  claim follows from the focused repair or standard CI.

## Post-publication outcome — 2026-08-17

The observations above describe the matrix and the documentation-time state
accurately and remain unchanged. Later GitHub evidence established a separate
outcome for the focused repair:

- PR #226 report head `24431512a993df81f15de4e0268c40ad61e0ad57`
  completed all ten final-head checks successfully;
- PR #226 merged as `adaefdc45ddd13e172955c14e02cb6c97d49b629`;
- the 24-worker matrix was not run a second time; and
- its original 2,533/2,534 `RESULT=FAIL` classification remains the immutable
  full-matrix result.

The focused repair and green standard PR checks qualify only that corrected PR
candidate. They do not establish a clean post-PR-220 128-worker qualification,
which remains **NOT RUN**, and they do not authorize an RC2 release or any
production, security, penetration-test, compliance, reliability, or scale
claim.
