# OAP Work Order — 157-b

## Objective

Continue Objective 157 on existing PR #294 solely to transition the two stale
Objective-156 no-pair assertions now that 157 deliberately activates the exact
`codex-0.149-responses-v1 -> local-coding-v1` pair.

The 157-a production implementation, documentation, fixtures, mocked E2E,
PostgreSQL evidence, and 16-row actual-Local consumer conformance are complete.
Do not change them. This is a test-expectation closure only.

## Verified state

- Repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #294, branch
  `oap/157-local-coding-server-signed-identity`, base main
  `f45bbd6f0eb9dbccbe39f9c9bd785c12218d2459`.
- PR mode: `AMEND_EXISTING_PR`.
- 157-a implementation head:
  `f3bdd0bcccc7e7c6b643e75d3cb30d4931967600`.
- Immutable 157-a FAILED report/current starting head:
  `067c1dee47dce5aa17fd92fb3c9c26c813e8bd3e`.
- Nine final-head checks pass. `Unit, lint, and migration head` fails only two
  assertions in `tests/unit/test_codex_client_modules.py` that encode the
  intentionally superseded no-pair state.
- No production, Local, Qwen, protected, provider, or accounting defect is
  indicated.
- PR #291 and Local Coding head `4d3ab2f...` remain read-only and unchanged.

Do not create a new PR, merge, or enable auto-merge.

## Allowed paths

- `tests/unit/test_codex_client_modules.py`
- `oap/active`
- `oap/orders/157-b-pair-state-test-transition.md`
- `oap/reports/157-b-pair-state-test-transition.md`

No other path may change.

## Required test transition

Change only the two stale pair-state tests, following the final accepted
Objective-155 behavior without importing later 158–160 tests:

1. Replace `test_0149_has_no_active_server_pair_before_objective_157` with an
   exact-pair test equivalent to final accepted
   `test_0149_has_only_the_local_coding_server_pair`:
   - Codex 0.147 -> OpenAI remains accepted;
   - Codex 0.149 has a server pair;
   - Codex 0.149 -> `local-coding-v1` is accepted;
   - every other registered server for Codex 0.149 rejects;
   - Codex 0.147 -> Local Coding rejects.
2. Preserve `test_responses_handler_denies_0149_before_policy_or_provider_work`
   as an early-denial regression, but make it test deliberately stale module
   metadata rather than the now-valid pair:
   - supply module version literal `"1"` with the current fixture digest;
   - retain the monkeypatch proving request policy/provider work is not reached;
   - require exact error code `client_module_fixture_mismatch`.

Do not delete the second early-denial regression. Do not add Local behavior,
streaming, reasoning, replay, or provider assertions to this file.

## Verification

Before reporting:

- prove the implementation diff from `f3bdd0b...` is exactly the one allowed
  test file and the two bounded transitions above;
- run the complete `tests/unit/test_codex_client_modules.py` file;
- run the focused exact-pair and stale-metadata tests directly;
- run repository Ruff check and Python compilation for that file;
- carry forward unchanged 157-a product, fixture, E2E, PostgreSQL, actual-Local,
  security/privacy/accounting, and cleanup evidence only after verifying all
  non-test non-OAP paths remain byte-identical to `f3bdd0b...`;
- require all ten GitHub checks on the exact final report head to pass.

Skipped, pending, cancelled, missing, xfailed, or failed required evidence is
not a pass.

## Non-goals

Do not modify product code, docs, fixtures, other tests, Local Coding, Qwen,
PR #291, inherited doctrine, streaming/replay behavior, schema, accounting, or
routing. Do not run protected/provider traffic. Do not activate Objective 158,
merge, or auto-merge.

## Report

Publish exactly one immutable report:

`oap/reports/157-b-pair-state-test-transition.md`

It must contain `RESULT=PASSED` or `RESULT=FAILED`, exact PR/base/branch/
starting/implementation/report topology, `Report publication commit: SELF`,
the exact test diff, focused results, unchanged 157-a evidence manifest, all
ten final-head check states, cleanup, documentation-impact statement, and
explicit no-158/no-merge state.

The report-only commit must have the test-transition implementation commit as
its first parent and change only the report. Verify the remote PR head and all
claims, write exactly `OK` to the response FIFO, then return to one blocking
control-FIFO read.
