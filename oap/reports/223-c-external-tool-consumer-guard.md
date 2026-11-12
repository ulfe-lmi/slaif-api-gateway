# OAP Report — 223-c: external-tool consumer guard + explicit fence-fd closure

PR mode: AMEND_EXISTING_PR — PR #382, branch `oap/223-demo-file-snapshot`,
base remote main `2209e100552397407d9641fc2eeba1029710c1a3`.

## 1. Work order

- Order file: `oap/orders/223-c-external-tool-consumer-guard.md`
- Order SHA256: `598e6ed114aae847120c31304d0038726821dff4df623bf38af44efdf8cf79c7`
- Root-authored activation bytes (order + `oap/active` = exactly `223-c`,
  5 bytes, no trailing newline) committed first as
  `5f5e9cb497f7401727ab036f7382029350d66e40`.

## 2. Topology and diff scope

- Pre-existing remote head: `defb7f07c04c474ad57a4602cb5f263769297751`
  (223-b report-only SELF; report SHA256
  `ccf07718fbfaad1d1e14a0a232aa86dae4d00f3d94698240dc664924fecacd60`).
- Implementation head: `b915ccd959e1897842f6c62a83f022cb33c315ab`.
  Its diff versus `defb7f07`, excluding the activation bytes, is exactly the
  two allowed test files: `+14/-2`.
- This report is a report-only SELF commit: sole parent
  `b915ccd959e1897842f6c62a83f022cb33c315ab`, sole diff file this report.
- No other path was touched. `oap/reports/` has zero changed files versus
  `defb7f07`; all earlier orders and reports are byte-identical.

## 3. Changes (test-only)

1. `tests/unit/test_documentation_contract_drift.py`: added exactly one
   entry, `app/slaif_gateway/services/demo_snapshot_sanitize.py`, to the
   existing `allowed_consumers` set for `external_tool_policy_contract`,
   adjacent to the other reviewed read-only consumers, with a brief comment:
   the worker-only demo snapshot sanitizer parses copied route metadata to
   validate and fictionalize the `external_tools` block in per-login demo
   copies; it grants no runtime external-tool authority, cannot admit or
   forward requests, and never changes key/route permission. Nothing else in
   the guard was deleted, weakened, wildcarded, skipped, or expanded; the
   full-tree `rglob` walk and all other assertions are unchanged.
2. `tests/unit/test_demo_snapshot_files.py`,
   `test_runner_config_validation_failure_does_not_leak_fence`: the fence
   descriptor acquired after the injected config-validation failure is now
   held in an explicit `try` (with a non-negative-integer fd assertion) and
   released in a `finally`, so closure happens exactly once even if the
   assertion itself fails. The retained assertion that a fresh fence can be
   acquired after the failed run is unchanged. Production fence behavior
   (`release_fence` in `demo_snapshot.py`) was not touched.

## 4. Focused verification (actual exit codes)

All runs on the implementation head, host `.venv`, no database:

- `tests/unit/test_documentation_contract_drift.py::test_external_tool_policy_contract_consumers_remain_allowlisted`
  and
  `tests/unit/test_demo_snapshot_files.py::test_runner_config_validation_failure_does_not_leak_fence`
  together: `2 passed`, exit 0.
  - The governance test proves: it walks every `*.py` under
    `app/slaif_gateway` and fails on any unallowlisted file containing
    `external_tool_policy_contract`; with exactly one entry added, the
    sanitizer is the only newly permitted consumer and the guard's other
    assertions (`.env.example` ceiling, `config.py` default, no migration
    mentions) still execute and pass.
  - The fence test proves: the 221 base-config validation still happens
    before fence acquisition (injected failure raises before any fence), a
    fresh `acquire_fence` succeeds afterwards (no leaked fence), and the
    descriptor is now closed deterministically.
- Negative evidence (guard not weakened): after temporarily stashing only
  the allowlist hunk, the identical governance test FAILED with exit 1 on
  the same assertion (reproducing the CI defect); the stash was popped and
  the file restored byte-identical. Any new unreviewed consumer will still
  fail this test.
- Scoped Ruff: `ruff check` on the two modified test files:
  "All checks passed!", exit 0.
- `git diff --check`: exit 0.
- Per the order, 223-b's unchanged component evidence (33 custody / 66
  sanitizer / 68 files unit passes; owned PostgreSQL16 222 sanitizer 6/6 and
  full 221→222→223 handoff 1/1) is reused for unchanged code and was NOT
  rerun.

## 5. Hosted CI failure and repair

- On SELF `defb7f07`, `Unit, lint, and migration head` FAILED at
  2026-11-12T22:34:29Z (run `43320400080`, job `131539270408`, step
  `Run unit tests in parallel`). Exactly one test failed:
  `test_external_tool_policy_contract_consumers_remain_allowlisted`,
  detecting `app/slaif_gateway/services/demo_snapshot_sanitize.py`. The
  same job reported 7,523 passes and one skip. The later Ruff/Alembic/
  whitespace steps were skipped and are NOT final passes; the PostgreSQL
  integration check was still in progress at reconciliation; other completed
  checks were successful.
- The allowlist entry in §3.1 is the repair; §4's negative run reproduces
  the exact failure when the entry is absent.
- Code Quality inline comment on `tests/unit/test_demo_snapshot_files.py`
  line 1122 ("File is opened but is not closed", thread
  `PRRT_kwDOSLm-qM623HTT`): genuinely addressed by the explicit
  `try`/`finally` closure; the platform permitted resolution, so the thread
  was resolved via the `resolveReviewThread` mutation (confirmed
  `isResolved: true`).

## 6. Preserved-boundary proof

- Full diff `defb7f07..implementation head`: only `oap/active` (root
  activation bytes), `oap/orders/223-c-external-tool-consumer-guard.md`
  (root order bytes), and the two allowed test files.
- No product code, migration/schema, GUI, auth/session, provider routing,
  quota/accounting, normal image/Compose, or 224 demo browser changes.
  `docs/demo-admin.md` and every earlier OAP order/report are
  byte-for-byte unchanged.
- Protected untracked files remain untracked and were hash-only, never
  read, staged, or modified: `CODEX-SESSION.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
  `codex.sh` `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
  `uv.lock` `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
- No merge and no auto-merge; the coding agent did not and will not merge.

## 7. Limitations

- This round is a test-only guard alignment; public behavior is unchanged
  and no new docs were needed. The demo remains inaccessible until
  objective 224.
- All ten final-head PR checks on the new head, all three workflow
  identities, review/material gates, a SHA-guarded merge if green, and
  actual main verification are root's gate; skipped/pending checks are not
  passes. If hosted CI finds a different blocking defect, root issues a
  same-PR continuation.
- Synthetic only: no operator setup, configuration, database, deployment,
  production credentials, or real provider/mail/browser calls occurred this
  round.
- The reused 223-b component evidence retains its method caveat: host-Python
  pytest with PG16.15 client binaries on PATH against owned loopback
  servers — not an in-container run and not a real client/provider/browser
  run.
