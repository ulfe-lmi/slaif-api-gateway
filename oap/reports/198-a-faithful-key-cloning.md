# OAP Objective 198-a — final report: faithful standard-key cloning

Work order: `oap/orders/198-a-faithful-key-cloning.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `198-a` (5 bytes, no trailing newline); order sha256
`81194bce626d8fa7b2b9daf6c2bc08d3c6e31ec5262e4428ffb24833633dc82b`,
verified before and after committing).
Branch: `oap/198-faithful-key-cloning`; base: `main`
`b4bc8a5b0c15be51135c1a9e3fc644189b51222e`.
PR mode: CREATE_NEW_PR — NEW unique PR #354,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/354, base `main`,
title "Clone standard keys from a reviewed canonical policy plan". The
coding agent never merges; no auto-merge; root reviews independently and
guard-merges.

Implementation head SHA: 889d37b5a210f746699ecbb69c4c960b9d7e8448
Report publication commit: SELF

## Predecessor state (unchanged)

Objective 197 is TERMINAL: its unique PR #353 was merged into `main` as
`b4bc8a5b0c15be51135c1a9e3fc644189b51222e` (the base of this branch).
197-b implementation `4b735f31f2fc97918fd1302b6bbd862ebe55ef1b`, 197-b
report-only SELF `dba087238d60a44f78671fac01a56311df25afcb`. Objective
196 is TERMINAL (PR #352 merged as
`6f6bc6fa7dc2aa9bb21ee2b0bc04f913e5d8c25c`). Objectives 199-205 remain
INERT. The only other open PR is the unrelated Dependabot PR #319
(preserved). No 198 suffix and no 199 were activated.

## Implementation commit (this round)

1. `889d37b5a210f746699ecbb69c4c960b9d7e8448` — "Clone standard keys
   from a reviewed canonical policy plan (198-a)": the strategic order
   (bytes verified unchanged, sha256 above) + exact `oap/active` =
   `198-a` + the bounded implementation, tests, docs, and verification
   record listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, and no runtime auth/admission/accounting/Redis/
forwarding behavior was modified. Objectives 199-205 were not started.

## Allowed diff (implementation commit, 15 files)

Product (allowed paths only):

- `app/slaif_gateway/schemas/key_clone.py` (NEW, 371 lines) — strict
  version-1 NON-secret clone-plan document (128 KiB envelope bound).
  Unknown/duplicate JSON fields, wrong types, non-UTF-8, and oversized
  files are rejected with fixed safe errors that never echo file bodies,
  paths, or values; optional non-authoritative `preview` block
  (validated, re-rendered, execute-ignored). `compute_source_fingerprint`
  = sha256 over source public_key_id/status/valid_from/valid_until/
  key_purpose/capability_policy_mode/policy (usage drift excluded).
- `app/slaif_gateway/services/key_clone_service.py` (NEW, 564 lines) —
  shared service. Errors (`KeyCloneError(KeyManagementError)` +
  Eligibility / UnsupportedSourcePolicy / SourceSecretShape /
  TargetMissing / StalePlan / PlanMismatch / ConfirmationRequired /
  TargetValidity) and `KeyCloneResult` (status `planned` | `created` |
  `already-applied`; `plaintext_key` in-process only). `build_plan` is
  read-only (no audit). `execute_plan` order: source `FOR UPDATE` lock
  → receipt lookup FIRST (dedup stays identifiable even if the source is
  later edited/ineligible) → eligibility (standard+standard, active,
  in-window, unfenced) → Responses-live-burn default check → target
  exists → fresh canonical export → recognized secret-shape scan →
  fingerprint stale check → fresh fenced confirmation → target-validity
  window (rejects `until<=from` and `until<=now`; naive ISO = UTC) →
  `build_create_gateway_key_input` + override `confirm_external_tool_
  fenced` from the CLI flag → create + optional pending delivery +
  receipt + `gateway_key_cloned` audit, all in one caller-owned
  transaction. The secret-shape guard reuses the existing
  `app/slaif_gateway/utils/redaction.py` patterns
  (`_GATEWAY_KEY_TEXT_PATTERN`, `_BEARER_PATTERN`,
  `_PROVIDER_KEY_PATTERN`, `_SENSITIVE_ASSIGNMENT_PATTERN`) on policy
  values only — known-shape protection, not universal sanitization.
- `app/slaif_gateway/db/repositories/keys.py` (+73) — `find_clone_
  receipt` (JSONB containment on `(source_gateway_key_id, operation_
  uuid)`, owner-scoped) + `attach_clone_receipt` (stores source/target/
  ots/delivery UUIDs, fingerprint, `target_cohort_id`,
  `validity_mode/duration_seconds/from/until`, `status:"created"`) — no
  DDL; the receipt lives on the NEW target key's `metadata_json`.
- `app/slaif_gateway/cli/keys.py` (+518) — `keys clone` with
  `--dry-run PATH` / `--execute PATH` (exactly one), explicit validity
  mode options (copy-source-expiry / duration-from-now / absolute),
  fresh `--confirm-external-tool-fenced` + `--actor-admin-id`, and
  EXACTLY ONE one-time key channel for execute (`--show-plaintext` |
  `--secret-output-file` | `--email-delivery pending|send-now|enqueue`).
  Strict pre-DB plan parse with fixed no-echo errors
  (`KeyClonePlanError` → `CliKeyError`); dry-run writes 0600 and never
  overwrites; JSON stdout byte-equivalent to the file; text = safe
  summary; post-commit file write / `_send_pending_key_email_now` /
  `_enqueue_pending_key_email` + warnings; already-applied repeats emit
  safe IDs + warning and NEVER plaintext/re-send; post-commit failure
  exits 1 with a `recovery` block (safe IDs, `plaintext_recoverable:
  false`, `email send-pending-key` guidance) and never re-clones. Clone
  uses its own show/file/existence checks (not the legacy
  `_validate_secret_output_options`, whose JSON rule would wrongly block
  `pending + --json`).

Tests (allowed paths only):

- `tests/unit/test_key_clone_service.py` (NEW, 740 lines) — 19 service
  cases (fakes, no DB).
- `tests/unit/test_cli_keys_clone.py` (NEW, 608 lines) — 21 actual-
  Typer CLI cases (DB helpers faked).
- `tests/integration/test_cli_key_clone_postgres.py` (NEW, 1174 lines)
  — 5 owned-PG cases.
- `tests/unit/test_documentation_contract_drift.py` (+5) — one
  justified exact allowlist entry for the clone service's read-only
  consumption of `external_tool_policy_contract` (fenced-policy
  detection only; no runtime authority). Guard discovery/assertion
  coverage preserved, not weakened.

Docs (allowed paths only):

- `docs/cli-reference.md` (+96) — new `keys clone` section with actual
  plan→review→execute→repeat/failure-recovery commands + command
  inventory.
- `docs/cli-field-administration.md` — the 198 row moved from "Proposed
  for later objectives" to a new "Implemented in objective 198" row
  (199-205 remain proposed; the full brief / eleven DoD are NOT declared
  complete).
- `docs/database-schema.md` (+38) — bounded `clone_receipt` JSON
  contract on `gateway_keys.metadata` (JSON only; no DDL) + the
  supported READ COMMITTED deduplication boundary.
- `docs/verification/2026-10-28-cli-key-cloning.md` (NEW, 243 lines) —
  this objective's dated verification record.
- `docs/verification/README.md` (+11) — this record indexed (newest
  first).

OAP: unchanged strategic order (sha256 above) + exact `oap/active` =
`198-a` (committed), plus this report. No root strategic
plan/audit/timing files in the PR.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app` with `/tmp/slaif192-coding-venv`
(Python 3.12); no ambient `DATABASE_URL` / foreign PG (the integration
layer's owned container is the only database).

- New unit suites (pure layer, no DB): 40 passed (19 service + 21 CLI),
  0 failed / 0 errors / 0 skipped, exit 0 (JUnit
  `/tmp/slaif198/unit-clone.xml`).
- Owned-PostgreSQL-16 integration module: 5 passed, 0 failed / 0 errors
  / 0 skipped, exit 0 (JUnit `/tmp/slaif198/integration-clone.xml`).
  Fresh qualified owned fixture: unique `slaif198a.owner` label,
  postgres:16, 127.0.0.1 loopback, tmpfs data directory, identity
  re-inspected AFTER creation and BEFORE readiness/migration, exact-ID
  cleanup in `finally`; no leftover container verified after the run;
  no ambient/unverified `DATABASE_URL`, no shared/foreign DB, no
  apt/HPC/production. Covers: student-source exact canonical `keys
  policy export` equality + independence + unchanged source (planted
  finalized usage + replay evidence intact); beta-source `[]` deny-all
  + rate block + already-applied repeat + same-operation tamper
  `key_clone_plan_mismatch` + unknown-field/oversized pre-DB refusal;
  forced LATE clone-audit failure full rollback (same-transaction
  visibility asserted in the hook); TWO separate OS processes
  concurrently executing the SAME plan ⇒ exactly
  {created, already-applied} with one key/secret/receipt/audit
  (`transaction_isolation = read committed`); simulated post-commit
  send-now mail failure ⇒ commit + exit 1 + exact retry already-applied.
- Gates: `tests/unit/test_oap_governance.py` +
  `tests/unit/test_documentation_inventory.py` — 22 passed (9 + 13),
  exit 0; `tests/unit/test_documentation_contract_drift.py` — 15
  passed, exit 0; Ruff on all 8 changed Python files — OK (E4/E7/E9/F,
  line-length 100); `git diff --check` — clean;
  `scripts/check_documentation.py` — OK (files=125).
- Passed suites were not repeated for display/count formatting; no full
  local unit/browser/HPC matrix was run.

## CI state (honest)

At publication the implementation head
`889d37b5a210f746699ecbb69c4c960b9d7e8448` and this report-only head have
NO completed final-head CI result recorded here; the normal FINAL-head
CI is the broad gate and was PENDING at the time of this record. Root
independently owns final-head CI and strategic review; the coding agent
did not wait on, merge, or act on CI results.

## Security / privacy / accounting statements

- The plan file, ordinary stdout, JSON, audit rows, and logs never
  contain a complete key, token hash, provider environment name or base
  URL, raw metadata, usage, or replay rows. The one-time plaintext
  exists only in the in-process result and the operator's explicitly
  chosen channel; `already-applied` repeats never recover or re-send it.
- Key + one-time secret + pending delivery + receipt + audits commit
  atomically in one caller-owned transaction; late failures roll back
  all new rows (proven in PG). No SMTP, output-file write, or enqueue
  happens before commit. There is no exactly-once SMTP promise; recovery
  is the existing explicit `email send-pending-key` for still-unconsumed
  material, otherwise rotation.
- Deduplication is bounded and honest: proven under the PostgreSQL
  default READ COMMITTED isolation (source `FOR UPDATE` lock +
  per-statement snapshot), not by pretending row locks guarantee
  arbitrary-isolation dedup. No schema, uniqueness constraint, or new
  receipt registry was introduced.

## Documentation impact

Required by AGENTS.md §5.1. Changed documented CLI and schema
contracts: `docs/cli-reference.md` (new `keys clone` section +
inventory), `docs/cli-field-administration.md` (198 row → implemented;
199-205 proposed), `docs/database-schema.md` (bounded `clone_receipt`
JSON contract, no DDL; READ COMMITTED boundary), and
`docs/verification/README.md` (this record indexed).

## Limitations

- Synthetic data only: fictional owners/cohorts, fake provider
  configuration, canned routes; no real provider/model contact, no real
  SMTP delivery (send-now targeted a refused local port
  127.0.0.1:1), no Redis, no upstream smoke.
- The objective-205 installed-executable transcript is still
  outstanding; this record does not declare the full brief or the
  eleven DoD complete.
- Final-head CI on this head is PENDING at record time; skipped/pending
  items are not passes. No full local unit/browser/HPC matrix rerun was
  performed.
- No release, RC, production, security, or compliance claim follows.
