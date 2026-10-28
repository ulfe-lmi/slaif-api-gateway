# OAP Objective 198-b — final report: clone plan and retry guards

Work order: `oap/orders/198-b-clone-plan-and-retry-guards.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `198-b` (5 bytes, no trailing newline); order sha256
`af709e1c9dc2d0af8f8e6ecf476352f621a1556edcbbe0e8d9e22de90781a539`,
verified in the working tree before committing and byte-identical in the
implementation commit).
Branch: `oap/198-faithful-key-cloning`; base: `main`
`b4bc8a5b0c15be51135c1a9e3fc644189b51222e`.
PR mode: AMEND_EXISTING_PR — the SAME unique PR #354,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/354, base `main`.
The coding agent never merges; no auto-merge; root reviews independently
and guard-merges.

Implementation head SHA: ffb52182ab07f8d9c0ec933b2c0502de3bdb041c
Report publication commit: SELF

## Predecessor state (unchanged)

Objective 198-a on this same branch: implementation `889d37b5a210f746699ecbb69c4c960b9d7e8448`,
198-a report-only SELF `29b6c73b727aac5f28e13c6b4c7d4b768074a869` (the
parent of the 198-b implementation commit). The 198-a final-head CI run
FAILED: 15 failed / 5,868 passed / 1 skipped (unit job 122804543472 / run
40684723649) on the settings-cache leak that limitation 8 below repairs.
Objectives 196/197 are TERMINAL (PRs #352/#353 merged into `main`).
Objectives 199-205 remain INERT; the only other open PR is the unrelated
Dependabot PR #319 (preserved). No new objective was activated.

## Implementation commit (this round)

1. `ffb52182ab07f8d9c0ec933b2c0502de3bdb041c` — "Bind reviewed clone
   plans, enforce isolation, preserve recovery (198-b)": the strategic
   order (bytes verified unchanged, sha256 above) + exact `oap/active` =
   `198-b` + the bounded repair, tests, docs, and verification addendum
   listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, and no runtime auth/admission/accounting/Redis/
forwarding behavior was modified. Objectives 199-205 were not started.

## Allowed diff (implementation commit, 14 files, +1041/-101)

Product (allowed paths only):

- `app/slaif_gateway/schemas/key_clone.py` — `compute_policy_fingerprint`
  (sha256 over sort-keys canonical JSON), `_aware_datetime` (naive → UTC,
  so mixed aware/naive absolute windows are compared predictably and
  rejected), `MAX_VALIDITY_DURATION_SECONDS` (documented 1,000-year
  bound).
- `app/slaif_gateway/services/key_clone_service.py` — three new errors:
  `KeyCloneUnsupportedIsolationError`
  (`key_clone_unsupported_isolation`), `KeyCloneReceiptAmbiguousError`
  (`key_clone_receipt_ambiguous`),
  `KeyCloneReviewedPolicyMismatchError`
  (`key_clone_reviewed_policy_mismatch`); `_now()` clock hook;
  `_seconds_to_timedelta` overflow guard. `execute_plan` order: source
  `FOR UPDATE` lock → execution time sampled AFTER the lock →
  `find_clone_receipts` (list, owner-independent; more than one →
  ambiguous refusal) → isolation check (`current_setting` must equal
  `read committed`, refused BEFORE any write) → eligibility →
  live-burn → target exists → fresh canonical export → known-shape
  secret refusal → stale check → reviewed
  policy/`source_public_key_id`/`requires_fenced_confirmation`
  revalidation → confirmation → validity → create + delivery + receipt +
  audit in one caller-owned transaction. `_receipt_matches_plan` compares
  the FULL business identity (source fingerprint, policy fingerprint,
  target owner, target cohort, all four validity parameters,
  fenced-confirmation requirement); legacy 198-a-shape receipts (missing
  the new fields) are refused as a mismatch rather than adopted.
- `app/slaif_gateway/db/repositories/keys.py` —
  `find_clone_receipt` → `find_clone_receipts` (returns the full match
  list, NO owner scope); `current_transaction_isolation()` (bounded
  `current_setting('transaction_isolation')` read); `attach_clone_receipt`
  gains `target_owner_id`, `policy_fingerprint`, and
  `requires_fenced_confirmation`.
- `app/slaif_gateway/cli/keys.py` (clone-only) — mixed-mode refusal:
  execute refuses the dry-run-only flags (`--source-key-id`,
  `--target-owner-id`, `--target-cohort-id`, `--validity-*`) and dry-run
  refuses the execute-only flags (`--show-plaintext`,
  `--secret-output-file`, `--email-delivery` other than `none`,
  `--confirm-external-tool-fenced`); `_read_bounded_plan_file` (at most
  128 KiB + 1 byte read, fixed safe errors, no path echo, oversized
  refused before any DB access); the pre-database
  `secret_output_file.exists()` check removed (the fresh operation
  commits first; the exclusive write then fails after commit);
  `FileExistsError` refusal without path echo; post-commit output
  channels wrapped so any failure produces a safe `recovery` block
  (target key, one-time secret, delivery IDs, fixed guidance,
  `plaintext_recoverable: false`) and exit 1 without rollback.

Tests:

- `tests/unit/test_key_clone_service.py` (26) — fake repository updated
  (`find_clone_receipts`, `current_transaction_isolation`, `isolation`
  attribute, new receipt fields); +7 focused regressions: changed-owner
  retry still dedups; edited-reviewed-policy before create refused; same
  operation with a different policy after commit refused; REPEATABLE READ
  isolation refused before writes; post-lock clock expiry refused;
  ambiguous multi-receipt refused; legacy a-shape receipt refused.
- `tests/unit/test_cli_keys_clone.py` (28) — secret-file-existing case
  rewritten to fresh-commits-then-recovers; + exact repeat with an
  existing file (dedup, no clobber), both mixed-mode refusals, bounded
  plan read (exactly 128 KiB + 1 read, oversized refused before any DB
  access), oversized-before-DB proof, overwrite refusal without path
  echo, post-commit mail-failure recovery.
- `tests/integration/test_cli_key_clone_postgres.py` (7, owned PG) —
  concurrency test switched to `--email-delivery pending` (asserts
  exactly one pending delivery for the target); late-audit test likewise;
  + REPEATABLE READ refusal through a real `KeyService`
  (`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` → refused, no rows,
  no audits, rollback) and + two DIFFERENT plans for the same source
  create two independent keys (same cohort, distinct token hashes);
  oversized-plan and cohort-UUID assertions fixed.
- `tests/unit/test_cli_key_policy_files.py` — `_clean_profile_env`
  (autouse) now clears the settings cache in `try/finally` (CI cache-leak
  repair).

Docs: `docs/cli-reference.md`, `docs/database-schema.md`,
`docs/cli-field-administration.md`, and the 198-b ADDENDUM appended to
`docs/verification/2026-10-28-cli-key-cloning.md` (198-a history
retained, not rewritten).

## Corrections to demonstrated 198-a limitations

1. Retry lookup was scoped to the target owner → now namespaced by
   `(source, operation)` ONLY, INDEPENDENT of target selection; multi-
   receipt ambiguity refused.
2. Reviewed plan content was not revalidated after locking → reviewed
   policy/`source_public_key_id`/`requires_fenced_confirmation` rechecked
   against the fresh locked source before any write (refused, never
   silently ignored).
3. READ COMMITTED documented but not enforced → now ENFORCED before any
   write (any other isolation level refused).
4. Execution time sampled before the lock → now sampled AFTER the lock.
5. Plan-file read unbounded → now bounded at 128 KiB + 1, oversized
   refused before any database access.
6. Post-commit output/mail exception surfaced as a generic error → now a
   safe `recovery` block with fixed guidance and nonzero exit, no
   rollback of the committed clone.
7. Exact repeat through `--secret-output-file` was refused pre-dedup →
   the fresh operation commits first, the exclusive write then fails
   after commit (recovery); a true exact repeat reaches dedup before any
   file channel and never clobbers.
8. Settings-cache CI leak → autouse teardown clears the settings cache in
   `try/finally`.

## Exact verification

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m
pytest` (no ambient `DATABASE_URL`; PG tests against an owned disposable
`postgres:16` instance, label prefix `slaif198a`).

- `pytest tests/unit/test_key_clone_service.py tests/unit/test_cli_keys_clone.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/unit-clone-b.xml`
  → **54 passed** (26 + 28), 0 failed / 0 errors / 0 skipped.
- `pytest tests/integration/test_cli_key_clone_postgres.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/integration-clone-b.xml`
  → **7 passed**, 0 failed / 0 errors / 0 skipped (concurrency
  serialization, exactly-one pending delivery, REPEATABLE READ refusal
  with no rows/audits, two independent plans → two keys, oversized-plan
  refusal, cohort-UUID comparison).
- Cache-leak regression: `test_cli_key_policy_files.py::test_create_invalid_configured_profile_fails_closed`
  run in ONE process with `test_v1_chat_completions_pricing.py` and
  `test_v1_endpoint_allowlist.py` → all pass; full
  `test_cli_key_policy_files.py` file 28 passed.
- `tests/unit/test_documentation_contract_drift.py` → 15 passed;
  `tests/unit/test_documentation_inventory.py` +
  `tests/unit/test_oap_governance.py` → 22 passed;
  `scripts/check_documentation.py` → `OK files=125`; Ruff clean over all
  eight changed product/test files; `git diff --check` clean.
- Owned-PG cleanup: no leftover `slaif198a`-prefixed containers remain.

## CI state

GitHub final-head CI for the 198-b head `ffb5218` is PENDING (root-gated;
no CI result is claimed here). The 198-a head CI FAILED (15/5,868 PASS/1
SKIP; unit job 122804543472 / run 40684723649) on the cache leak repaired
above. All final-head merge gates remain required; the coding agent never
merges.

## Security, privacy, atomicity, isolation, cleanup

No key material, token hashes, provider references, raw metadata, usage,
or secrets are stored in the receipt, echoed in errors, or added to
logs; every new error is a fixed safe message. Key creation, one-time
secret, optional pending delivery, receipt, and audits commit atomically
in one caller-owned transaction; nothing (no SMTP, no output file, no
enqueue) happens before commit. READ COMMITTED is now the ENFORCED
deduplication boundary; same-source executions serialize on the existing
source-row `FOR UPDATE` lock and the post-lock receipt read sees the
prior commit. No schema, column, constraint, or migration was added. No
real provider/model contact, real SMTP, Redis, or upstream smoke
occurred.

## Documentation impact

- `docs/cli-reference.md`: `keys clone` section documents (source,
  operation) retry safety independent of target selection with full
  business-identity comparison and ambiguity refusal, reviewed-plan
  revalidation, post-lock execution time, mixed-mode refusals, bounded
  plan read, the enforced isolation boundary, and post-commit output
  recovery.
- `docs/database-schema.md`: `clone_receipt` JSON contract gained
  `target_owner_id`, `policy_fingerprint`,
  `requires_fenced_confirmation`; lookup documented as (source,
  operation) only; repeat comparison as FULL business identity; READ
  COMMITTED documented as ENFORCED.
- `docs/cli-field-administration.md`: the 198 row reflects the 198-b
  guards (199-205 remain proposed; the objective-205
  installed-executable-only transcript remains mandatory).
- `docs/verification/2026-10-28-cli-key-cloning.md`: 198-b ADDENDUM
  appended; `docs/verification/README.md` unchanged (record already
  indexed).

## Limitations

- Synthetic data only: fictional owners/cohorts, fake provider
  configuration, canned routes; no real provider/model contact, no real
  SMTP delivery, no Redis, no upstream smoke.
- The objective-205 installed-executable transcript is still outstanding;
  this report does not declare the full brief or the eleven DoD complete.
- No release, RC, production, security, or compliance claim follows from
  this report.
