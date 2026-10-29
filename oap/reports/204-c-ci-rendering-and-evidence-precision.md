# OAP Objective 204-c — final report: CI rendering fix and evidence
precision corrections

Work order: `oap/orders/204-c-ci-rendering-and-evidence-precision.md`
(committed unchanged on the objective branch with `oap/active` =
`204-c` (5 bytes, no trailing newline); order sha256
`4dbf9b15d2402d72b1cf029f69762940bdde4aff12662b69edfffd6ffb3889e1`,
active pointer sha256
`1ba610ffdf9addab64e5429614cd9c95b9d2aa3f657854a0984617926f3fa39b`,
both verified before committing).
Branch: `oap/204-record-edits-config-inspection`; base: `main`
`6a523cb75b91899d1376c0ab7909404a242f44ac` (unchanged). PR mode:
CONTINUE_EXISTING_PR — PR #360,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/360 (unique PR for
objective 204); no auto-merge. The coding agent never merges; root
reviews independently and guard-merges.

204-a and 204-b are CLOSED and immutable: their orders and reports
(204-a report sha256
`d8499d9e9be6c572f3f06ded814fbbb895aa91e1cbf15564d733250508c59315`,
204-b report sha256
`8bcde2e29d0e382e513fc57416227c968acd4c37f0123ab155b59304463a12e4`)
are never rewritten.

Implementation head SHA: add056184cf383cb9be71a46a5560dfaeca1a768
Report publication commit: SELF
Starting head: f37afaf8af2e368f7afd0a82a9b1fc699448d856 (B SELF,
reconciled before Git execution: main 6a523cb, unique open PR #360 on
this branch, no auto-merge).

This report is concise around the C delta and its evidence; the
implementation narrative of record remains the immutable B report.

## Delta (test + documentation only; four allowed existing files)

1. `tests/unit/test_cli_record_edits.py` — the one final-head CI
   assertion. B-head CI (root-observed, job 123409569451 / run
   40862529503; root log /tmp/slaif204-root/final-b-unit-job.log)
   failed solely
   `test_cli_owner_update_reason_is_required`: on GHA the rich console
   forces terminal styling and interleaves per-segment ANSI codes inside
   the option name, so the raw `"--reason" in result.output` match is
   false even though the missing-option invocation correctly exits
   nonzero (SystemExit 2). Fixed with the established local pattern
   (`tests/unit/test_cli.py`, `test_cli_key_batch.py`): a tiny local
   `_plain()` helper (strips CSI escape sequences, normalizes
   whitespace) plus test-local
   `monkeypatch.setattr(typer.rich_utils, "FORCE_TERMINAL", True)` with
   a stable `COLUMNS=220` width, so the condition is exercised even off
   GHA; the assertion now matches `--reason` in the ANSI-normalized
   usage output. The nonzero-denial assertion and the actual invocation
   are retained; no CLI flag, runtime, or error-handling change; no
   shared fixture/helper framework or new library investigation. Local
   reproduction (venv Python 3.12, forced terminal rendering): raw
   match False, normalized match True, ANSI present in output, exit 2 —
   the same raw-false/normalized-true shape the 203-b reproduction
   established.
2. `tests/unit/test_cli_configuration_inspection.py` — code-quality
   thread PRRT_kwDOSLm-qM6xhWVh (comment 4411541206): `cli.main` was
   imported with both `import ... as main_cli` and
   `from ... import app`. Now one module-import style: `app =
   main_cli.app` (the module alias is retained for the callback
   monkeypatches and the SAME app object serves every invocation). All
   positive/negative/cold-subprocess/source/cached/no-secret assertions
   are preserved unchanged; test-only import cleanup, not a loader or
   runtime change. The four "statement has no effect" await comments
   (PRRT_kwDOSLm-qM6xhWU1/WVH/WVS/WVZ) are root-resolved false
   positives: the awaits join completion and propagate exceptions and
   are ESSENTIAL. All native code is preserved; no await was weakened
   or removed.
3. `docs/deployment.md` — removed the single duplicated adjacent
   `## Diagnostic Logging` heading; the actual new environment/restart/
   recreate/Nginx guidance and all other content are preserved (exactly
   one heading remains).
4. `docs/verification/2026-10-29-cli-record-edits-and-config.md` —
   evidence precision (prose only, no transaction machinery or test
   change):
   - "fresh autocommit observer" corrected to the source-accurate
     "independent observer session that explicitly clears the
     statistics snapshot (`pg_stat_clear_snapshot()`) before each poll
     (the default AsyncSession is not autocommit)";
   - the local full-file 8-PASS run (which predates the late-audit case
     strengthening, i.e. before its audit add+flush body was added) is
     now separated from the targeted single corrected-case re-run
     (1 PASS, 0 skip; overlaps the 8, not a 9th unique case), with the
     explicit note that the earlier full-file run did NOT execute the
     later audit-insertion body and that bullet's evidence is the
     targeted re-run;
   - the stored-current-canary receipt attribution corrected (see below);
   - a header note records this 204-c correction.
   No PG re-run was performed for prose and no overlaps were summed.

## B report overclaim clarification (B report stays immutable)

The immutable B report credits
`204-b-partial-record-boundary-probe.json` as "(baseline reproduction of
the stored-canary audit-leak, fixed with native regressions)". The
precise attribution: the native PG file covers the PROVIDED note canary
(actual-CLI `--notes` canary refusal on owned PG), NOT the retained-
current owner/cohort metadata cases. Those retained-current cases are
covered by the UNIT-level regressions (`tests/unit/test_record_edits.py`
fresh-current-metadata guard; `tests/unit/test_cli_record_edits.py`
stored-canary unrelated-edit/clear refusals with zero writes/audits)
plus the root actual-shared-service/FAKE-repository rechecks
(`204-b-final-draft-partial-record-recheck.json` retained-known-shape
cases and the four driver rechecks of
`204-b-final-draft-boundary-rechecks.json`, all PASS at stable bytes).
The live verification record is corrected; the B report is never
rewritten. Qualification: root's initial fake audit capture is not
proof of persisted real-audit leakage — the real `AuditRepository` also
sanitizes values. The new shared guard genuinely refuses unsafe fresh
current metadata before mutation/return/audit, and root's
positive/negative rechecks plus the source support that behavior. No
extra native tests were required to fix this reporting error; native
test bytes are unchanged in C.

## Verification evidence (this environment)

venv Python 3.12 (`/tmp/slaif192-coding-venv`), `env -u DATABASE_URL -u
TEST_DATABASE_URL PYTHONPATH=app`, JUnit XML, zero skips (repository
addopts suppress console summaries; counts derived from JUnit):

- `tests/unit/test_cli_record_edits.py` +
  `tests/unit/test_cli_configuration_inspection.py` (one JUnit run):
  32 PASS, 0 failures, 0 errors, 0 skipped, exit 0 —
  `test_cli_record_edits` 21, `test_cli_configuration_inspection` 11
  (XML sha256
  `1e2083b8b0cbfc12b9b3ffd63188395804b76c8bce08dd9d2bf80392bb196961`).
- Governance/documentation batch (one JUnit run): 69 PASS, 0 skipped,
  exit 0 — `test_oap_governance` 9, `test_documentation_inventory` 16,
  `test_documentation_contract_drift` 15, `test_documentation_asof` 13,
  `test_documentation_logo` 6, `test_product_scope_docs` 4,
  `test_rc2_feature_scope_docs` 5,
  `test_openai_assisted_import_contract_docs` 1 (XML sha256
  `bf133c5f199ab3d13f901be3464a5b73d085239d2a3efe0412f8d97fb8e2b500`).
- Hygiene: ruff (E4/E7/E9,F; line 100) clean on both changed test
  files; `python3 scripts/check_documentation.py` OK (131 files);
  `git diff --check` clean.

These are the C-scoped focused runs ordered for this delta; this is not
a claim that all 74 new B units or the 8 local native cases re-ran in
C. No PG/SMTP/backend/CLI-runtime/full-matrix re-run was performed
(not justified by these test-only/docs changes; ordinary final-head CI
covers the broad suites).

## GitHub / CI state

- B-head final CI was root-observed on the exact head: sole failure the
  renderer assertion fixed in item 1; broad count 6399 passed, 1
  failed, 1 skipped.
- C-head checks (on `add0561` and this report-only SELF) are pending at
  writing time; pending/missing/skipped/failed checks are not passes.
  Root independently gates ALL 10 final C-SELF checks / THREE
  workflows plus review dispositions before merge.

## Scope, safety, and limitations

- C changed ONLY the four allowed existing files listed above, plus the
  root-authored strategic order and exact active pointer committed
  unchanged. Against B SELF the tracked diff is exactly those paths; all
  product/migration/settings bytes and native test bytes are identical
  to B SELF (root 466-path baseline plus native hash). No
  services/schema/config/CLI/worker/models/auth/accounting/replay/
  queues/providers/adapters/modules/UI/mail/runtime/dependencies/
  workflows changes; no new fixtures/framework/test files.
- No schema or key-policy migration; the upgrade path remains an
  ordinary image rebuild + container recreate
  (`docker compose up -d --build` / `--force-recreate` as applicable).
- C claims no real-PG, current-client, backend, SMTP, or installed-205
  qualification; product work remains B provenance. 205 all-eleven
  installed-executable qualification stays inactive/unproven until 204
  terminal and actual-main checks pass. Protected untracked
  `CODEX-SESSIONS.md` / `codex.sh` preserved; permanent message.txt
  stays neutral.

Documentation updated: docs/deployment.md,
docs/verification/2026-10-29-cli-record-edits-and-config.md
