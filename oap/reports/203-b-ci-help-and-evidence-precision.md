# OAP Objective 203-b — final report: CI help-text fix and evidence precision

Work order: `oap/orders/203-b-ci-help-and-evidence-precision.md`
(committed unchanged on the objective branch with `oap/active` =
`203-b` (5 bytes, no trailing newline); order sha256
`f01b7769014f526a51d04a02d232e68273e7342bb2bc44fcb5a1adbb0e883a00`,
active pointer sha256
`f93707411ba83c08224db2c616acbadb270d045c7c003e599dcb1875882fbc55`,
both verified before committing).
Branch: `oap/203-reviewed-key-batches`; base: `main`
`a1f7abdfc86b137e7bbece5c44face42b8e6b902` (unchanged). PR mode:
CONTINUE_EXISTING_PR — PR #359,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/359; no auto-merge.
The coding agent never merges; root reviews independently and
guard-merges. 203-a is CLOSED and immutable: its unique report
`oap/reports/203-a-reviewed-key-configuration-batches.md` (sha256
`4408319c40d488079a8d19b5f78b1eaf27d26faa37369853d0a6d62700df7840`)
and order (sha256
`c55bed7032eadff4bd59a38493f9a0206e9c5ec6338683701bd066ad9654dbed`)
are never rewritten; the sole 203-a response terminal was consumed by
root (CLOSED exit 0, exact RESPONSE_OK_EXACT) and is never re-polled or
re-signaled.

Implementation head SHA: 32fa6a8b9d8d9472a3a18af01855365dd0ad47e3
Report publication commit: SELF

## Implementation commits (this round)

1. `32fa6a8b9d8d9472a3a18af01855365dd0ad47e3` — "Fix CI help-text
   assertion and evidence/transaction prose precision (203-b)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `203-b` + the bounded allowed changes (7 files).
   First parent is the A-SELF report commit
   `4806b932724cdbdb756368c749ba8ea591652bda`. This is the single
   implementation commit.

## What changed (allowed paths only)

- `tests/unit/test_cli_key_batch.py` — the ONLY changed assertion is
  the A-SELF CI failure,
  `test_apply_fresh_fenced_confirmation_flag_passthrough`. It now uses
  the established local CLI help-test convention (renderer-stable
  `TERM_ENV = {"COLUMNS": "220", "NO_COLOR": "1"}` plus the
  ANSI/whitespace-independent `_plain()` normalization; the same
  pattern as `tests/unit/test_cli.py` and the 199-b R5 renderer-stable
  invocations) and test-locally forces the SAME ANSI-rich rendering CI
  produces by `monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL",
  True)` (auto-reverted; no shared runner/environment/framework
  change). Both real command invocations, the `confirm is False` /
  `confirm is True` passthrough assertions, and the help exit-0 check
  are retained unchanged. No CLI help/wiring/options change, no
  global color/rich disabling, no flag shortening.
- `tests/unit/test_key_batch.py` — ONE new focused durable schema case
  (`test_plan_file_writer_closes_descriptor_on_success_and_injected_faults`)
  proving `write_key_batch_plan_file` closes its exact descriptor on
  success and on both injected fault paths (injected `os.fdopen`
  OSError; injected `stream.write` OSError) via test-local monkeypatch
  and `os.fstat` EBADF checks. Production IO code is unchanged.
- `app/slaif_gateway/cli/key_batch.py` — DOCSTRING ONLY
  (`_batch_runtime`); `app/slaif_gateway/services/key_batch_service.py`
  — DOCSTRING ONLY (`KeyBatchService`). Verified by
  AST-sans-docstring comparison against A-SELF: for BOTH files the AST
  dump with docstrings removed is identical (plain-AST dump differs
  only in the docstring constants). No runtime AST change.
- `tests/integration/test_cli_key_batch_postgres.py` — COMMENT ONLY
  (the `_applier` "ROLLBACK on exit" comment, which claimed a rollback
  where nothing was written and normal exit is sufficient). No
  runtime/test-logic change.
- `docs/security-model.md` (objective-203 paragraph only) and
  `docs/verification/2026-10-29-cli-key-batches.md` (preview-law
  bullet, documentation-checker count, one negative-evidence bullet).
- `oap/active` = `203-b` (exact root bytes) and this round's strategic
  order (committed unchanged).

All other product/test/governance paths are byte-identical to A-SELF.
In particular `schemas/key_batch.py`, `services/key_service.py`,
`db/repositories/keys.py`, `cli/keys.py`, and
`services/key_policy_configuration.py` are untouched; no
migrations/schema/settings/UI/providers/adapters/modules/auth/
accounting/runtime/queue/mail/dependency/workflow changes.

## CI failure root cause and fix (order item 1)

A-SELF final CI job 123355689211 / run 40846576073 failed 1 of
6326 (6324 passed, 1 failed, 1 skipped); the sole failure was the
literal `assert "--confirm-external-tool-fenced" in help_res.output`.
Root cause (reproduced locally, typer 0.27.3 / click 8.5.0): typer's
`rich_utils` sets `FORCE_TERMINAL = True` when `GITHUB_ACTIONS` (or
`FORCE_COLOR`/`PY_COLORS`) is set — GitHub Actions sets
`GITHUB_ACTIONS` — so the rich help console forces terminal styling
and the `OptionHighlighter` wraps the option name in per-segment
start/reset pairs, e.g.
`--confirm-external-tool-fenced` is rendered as
`\x1b[1m-\x1b[0m\x1b[1m-confirm\x1b[0m\x1b[1m-external-tool-fenced\x1b[0m`.
The literal flag is therefore NEVER contiguous in raw output under
CI rendering (it IS contiguous locally, where no force flag is set,
which is why the test passed locally but failed in CI).

Local reproduction of the exact failing condition (same
`CliRunner`/`cli_app`/argument vector, `FORCE_TERMINAL` forced):
the OLD raw assertion evaluates False while the corrected
ANSI/whitespace-normalized assertion evaluates True; the corrected
assertion also passes with rendering unforced. The corrected test
therefore deterministically exercises the CI-style ANSI-rich
rendering on every run.

## Transaction prose corrections (order item 2)

The accurate semantics, unchanged in behavior: BOTH operations run
inside the ONE caller transaction (`session.begin()` in
`_batch_runtime`). A successful `plan` exits that read-only
transaction NORMALLY (a no-write transaction may still COMMIT),
releases its locks, and writes ZERO key/config/audit/material state.
`apply` commits only after the whole batch is validated and applied;
a failed atomic apply still PROPAGATES and rolls back ALL keys and ALL
provisional (flushed) audits. The incorrect "exits the caller
transaction WITHOUT commit" / "ROLLBACK on exit" prose was corrected
in the two product docstrings, the verification-record preview-law
bullet, the objective-203 security-model paragraph, and the native
`_applier` comment. Transaction behavior was NOT changed to fit
prose.

## Evidence precision (order items 3-4)

- Refusals cause zero CHANGES to existing keys/audits/material (the
  verification record's "leaves zero key/audit/material state" bullet
  now says so precisely).
- Documentation checker re-run: `python3 scripts/check_documentation.py`
  -> `DOCUMENTATION_CHECK=OK files=130` (exit 0). The verification
  record's earlier `files=129` figure (the A report already recorded
  the final `files=130`) is corrected in place with a re-verification
  note.
- Native run6 provenance: the retained-current-configuration canary
  WAS present in the green owned-PG run. Root's independent
  source-provenance receipt
  (`review-artifacts/cli-feature-round/203-a-native-canary-source-provenance.json`)
  shows the canary edit at 08:50:02Z (with post-write assertions),
  BEFORE the run6 JUnit at 08:53:48.458896Z
  (`/tmp/slaif203/pg-key-batch-6.xml`, sha256
  `3e12619272d80ee422ed8f82c600891e358a1da317231cce19df43f84e3dcd68`,
  13 pass / 0 skip), and the later 08:57:58Z native edit was
  comment-only. No native rerun was needed for the docstring/comment/
  help-assertion changes, and none is claimed.
- The ordered 37-key preview/apply pair remains the accepted full
  serial-module workflow used by CI; no fixture redesign and no
  independent `-k` apply-case qualification is claimed.

## A-report provenance corrections (explanatory only; A report/order
immutable)

- The A report's "four new product files" duplicated
  `schemas/key_batch.py`. Actual: THREE new product files
  (`schemas/key_batch.py`, `services/key_batch_service.py`,
  `cli/key_batch.py`) and THREE modified product files
  (`services/key_service.py`, `db/repositories/keys.py`,
  `cli/keys.py`).
- The A report's "selection/page parsing" phrasing does NOT describe a
  new paging CLI primitive: selection is bounded exact scope/cap+1
  (exactly one of `--cohort-id` or repeatable `--key-id`; selected+
  excluded combined 1,000-key bound; cap+1 overflow refused). No
  paging capability was invented; no new-203 documentation text
  implies one (the `keys list` paging sections in
  `docs/cli-reference.md` are the pre-existing surface).
- Documentation checker count: final actual run `files=130` (the
  dated verification record's 129 figure predates the final
  documentation set; corrected in place in 203-b).

## Static diagnostic disposition (order item 5; root owns thread
closure)

- The three `statement-no-effect` findings at the native lines
  (1095/1096/1099) are real `await <task>` joins essential for
  exception propagation; they are preserved unchanged.
- The schema writer line-607 "file-not-closed" finding is a false
  positive: root's actual local FD probe
  (`/tmp/slaif203-root/writer_descriptor_review.py`, receipt
  `203-a-writer-descriptor-review.json`, on schema sha256
  `2173abdc72d2dcfd07707a6c21586323446a5685a58dbc10a2ead6282acf7eed`)
  verified real descriptors closed on successful write, injected
  `os.fdopen` OSError, and injected `stream.write` OSError; the
  existing explicit `os.close` on conversion failure and the stream
  context manager cover those paths. No runtime rewrite was made to
  suppress the finding; instead 203-b adds the durable in-repo unit
  regression described above.

## Focused verification (this round)

All unit runs: `env -u DATABASE_URL -u TEST_DATABASE_URL
PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m pytest
<paths> -p no:cacheprovider -q` from the repository root; every
command exited 0.

- `tests/unit/test_key_batch.py tests/unit/test_cli_key_batch.py`
  with `--junitxml=/tmp/slaif203b/unit-203b.xml`: **51 PASS / 0 fail /
  0 error / 0 skip** (39 in `test_key_batch` = 38 existing + 1 new FD
  case; 12 in `test_cli_key_batch`), exit 0.
- `tests/unit/test_oap_governance.py` (9),
  `tests/unit/test_documentation_inventory.py` (16, including the
  literal `slaif-gateway keys batch plan` / `apply` naming),
  `tests/unit/test_documentation_contract_drift.py` (15),
  `tests/unit/test_documentation_asof.py` (13): **53 PASS, exit 0**
  (100% dot line; repository addopts suppress the verbose summary).
- `python3 scripts/check_documentation.py` ->
  `DOCUMENTATION_CHECK=OK files=130`, exit 0.
- Ruff `--select E4,E7,E9,F --line-length 100` on the five changed
  Python files: All checks passed, exit 0.
- `git diff --check`: clean, exit 0.
- AST proof: both product files docstring-only (AST-sans-docstring
  identical to A-SELF); native file comment-only (diff shows the
  single comment replacement).

Per the order, no full local unit matrix and no native/PG rerun was
performed; ordinary CI covers the broad checks.

## CI state at publication

At the time of this report the IMPL head
`32fa6a8b9d8d9472a3a18af01855365dd0ad47e3` checks were
in-progress/queued (run 40849721886 / 40849721846). The final SELF
head supersedes those IMPL checks; root gates ALL 10 final-SELF
checks and the review threads before guarded merge. The A-SELF
final-head failure (run 40846576073, 1 failed) is exactly the
assertion this order fixes.

## Limitations and honest scope

No full native rerun, no owned-PostgreSQL rerun, and no 205
installed-wheel, backend, client, provider, mail, Redis/broker, or
HPC qualification is claimed by this round. The A-round evidence
layers (38+1 unit schema/service, 12 CLI, 137 unchanged consumers,
56 governance/protocol/replay, 53 docs, 13 native) remain the A
provenance and are not re-claimed as B runs except where 203-b
re-ran them (the two new unit files and the focused docs/governance
sets above). Deployment is unchanged: no schema migration, no
key-policy migration, no new settings; the ordinary image
rebuild/recreate applies this surface (migration head stays
0026/33 tables).

Documentation updated: docs/security-model.md,
docs/verification/2026-10-29-cli-key-batches.md (203-b)
