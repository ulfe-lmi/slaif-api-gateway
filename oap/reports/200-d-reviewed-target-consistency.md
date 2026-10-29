# OAP Objective 200-d — final report: reviewed-target consistency on first apply and repeat

Work order: `oap/orders/200-d-reviewed-target-consistency.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `200-d` (5 bytes, no trailing newline); order sha256
`be4c09ac223691bb861cb4a7379baf38d3e1372406ff2c1fb1806b915b444d78`
(9,520 bytes), active pointer sha256
`9e4e110fb1c7128bed9c99e024f36999b8e0febc2202b9b863227fa878f3c6ff`,
both verified before committing and re-verified at HEAD).
Branch: `oap/200-replay-reference-maintenance`; base: `main`
`4c265bc3c9668a66bb1643915d442fb8c411ff11` (unchanged).
PR mode: AMEND_EXISTING_PR — the SAME unique PR #356 created by
200-a, https://github.com/ulfe-lmi/slaif-api-gateway/pull/356, base
`main`, OPEN/MERGEABLE with head at this implementation at
publication. The coding agent never merges; no auto-merge; root
reviews independently and guard-merges.

Implementation head SHA: ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6
Report publication commit: SELF

## Predecessor state (immutable)

200-c is complete on this branch: implementation head
`d86bc0d3933481a2d4797ebdfc1bc4abbd775d97` and report commit
`032a3af883736c2e728c6d1b79323957edcd30b4` (order sha256
`32731646a5f93fa2e6c0715ceffff1199287a7c17f4cbb103f1325a059509761`,
report sha256 `57ae90b19688ddcaee698d4421e8a61c3ba87272cb2e5d231a8702534147e5c2`).
200-b: implementation `8466d9364bd93175a8a370e8f5bc51d6af86b628`,
report commit `32a9f0ca3c231eaf95d88667ce4ad089a5d08f3b`. 200-a:
implementation `9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f`, report
commit `64338b08ee146f4a66658a1d27ef3b50dba7afef`. The 200-c report
explicitly recorded the reviewed-target consistency gap as remaining
and deliberately did not broaden its service allowlist; that report
and all prior orders/reports are immutable and were NOT edited. Root's
200-c sole response was polled CLOSED with the exact response OK and
was never reopened or re-signaled. Objective 199 remains terminal;
201-205 remain INERT; the 205 installed-executable transcript/all-
11-DoD remains outstanding.

## Implementation commit (this round)

1. `ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6` — "Guard the reviewed
   expiry target and repeat post-state under the selected TTL
   (200-d)": the strategic order (bytes verified unchanged, sha256
   above) + exact `oap/active` = `200-d` + the allowed changes
   listed below (10 files total). First parent is the 200-c report
   commit `032a3af`.

Product-byte preservation: `git diff d86bc0d3933481a2d4797ebdfc1bc4abbd775d97
ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6 -- app/` shows EXACTLY two
files (`services/codex_replay_maintenance.py`,
`cli/codex_replay.py`); the 200-c schema/file-I/O file (retaining all
safe-input/FD/read fixes), the replay repository, runtime replay, and
every other product file are BYTE-IDENTICAL to 200-c. `tests/unit/
test_documentation_inventory.py` byte-identical. No schema/DDL, no
migration, no dependency, no workflow, no UI, no config, no signing
framework, no 201+ change; no release action.

## What changed (allowed paths only)

Product (2 files):

- `app/slaif_gateway/services/codex_replay_maintenance.py`
  (decision guards only; no lock/clock/flow change): the expected
  post-state is recomputed ONCE from the fresh locked rows, the
  actual classification, and the SELECTED TTL (`max(old, created +
  TTL)` per eligible row, the same pure helper the preview uses) and
  guards BOTH decision paths. FIRST apply, before any mutation: the
  recomputed post-state must equal
  `plan.expected_post_state_fingerprint`, and the saved report
  descriptors (old/new expiry ranges via the same formula as the
  preview, exclusion counts) must agree with the freshly derived
  eligible rows — including a zero-diff first apply. Already-applied
  repeat: the recomputed post-state must ALSO equal the saved
  post-state fingerprint, so a TTL-only edit of an applied plan that
  would require a different post-state fails stale instead of
  reporting `already_applied`, while a no-effect edit keeps the
  honest no-op and the unchanged plan stays exactly idempotent. All
  rejections use the existing fixed safe stale vocabulary with zero
  expiry writes / zero audits. No new plan fields, schema,
  signature, receipt, or table; no authority inferred from a hash.
- `app/slaif_gateway/cli/codex_replay.py` (execute output label
  only): the execute JSON gains one small additive field,
  `range_descriptors_source: "reviewed_plan"`, identifying its
  exclusion/range descriptors as REVIEWED-PLAN metadata (validated
  for consistency before any write) rather than newly measured
  historical values; the applied / already_applied /
  updated_references fields remain operation-derived. No command or
  existing field changed.

Tests (3 files): `tests/unit/test_codex_replay_maintenance.py` +8
(`TestReviewedTargetConsistency`: TTL-only / post-fingerprint-only /
range-only / exclusion-count-only edits refused stale with zero
writes and zero audits while the unedited plan still applies; zero-
diff first-apply range edit refused while the honest zero-diff plan
is a plain no-op; a regenerated 180-day plan applies exactly
`created + 180d` with truthful audit ranges and an idempotent
repeat; an edited-TTL repeat after a real 180d apply refuses stale
with no extra write/audit; a shorter no-effect TTL edit reports the
honest no-op); `tests/unit/test_cli_codex_replay.py` +1
(`TestExecuteRangeProvenance`); `tests/integration/test_cli_codex_
replay_maintenance_postgres.py` +1 focused case (15 → 16): save a
valid default-TTL plan, edit ONLY `ttl_seconds` to 180 days, execute
the strict file through the CLI => fixed refusal with all reference
columns byte-equal and zero audits; a genuine 180-day preview then
applies exactly `created + 180d` with one accurate audit (ranges
stored as ISO strings in the audit JSONB) and every other column
unchanged; a normal repeat adds no audit.

Docs (3 files): see Documentation impact below.

Order/active (2 files): committed unchanged as specified.

## Verification (exact layers and receipts)

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python`
with `env -u DATABASE_URL -u TEST_DATABASE_URL`; no ambient
`DATABASE_URL`, no foreign PostgreSQL/Redis/container; JUnit receipts
under `/tmp/slaif200a/` (disposable). Per-file counts below are
DERIVED FROM THE JUNIT TEST CASES (not estimated).

- New unit suites (pure layer + actual-Typer, no DB): **74 passed /
  0 failed / 0 errors / 0 skipped**, exit 0 (`d-unit-new.xml`) —
  service file 53 (including the 8 new consistency tests) + CLI file
  21 (including the 1 new provenance test).
- Focused affected batch: **182 passed / 0 failed / 0 errors / 0
  skipped**, exit 0 (`d-unit-affected.xml`) — unchanged
  `test_codex_replay_service` 24, `test_codex_replay_limits` 57,
  `test_cli_codex` 27, plus the 74 new-suite tests (INCLUDED in the
  182).
- Owned-PostgreSQL-16 suite (unique owned label, loopback, tmpfs,
  identity inspected before readiness/migration, exact-ID cleanup):
  **16 passed / 0 failed / 0 errors / 0 skipped**, exit 0
  (`d-pg.xml`) — the 15 ordered proofs (including the real
  reference-row waiter and the 20,451-reference / 26-key / 91-
  expired scale) re-run unchanged at these bytes plus the new 16th
  target-consistency case.
- Governance/inventory/drift: **40 passed / 0 failed / 0 errors / 0
  skipped**, exit 0 (`d-gov.xml`): `test_documentation_inventory`
  16 (file byte-unchanged), `test_oap_governance` 9,
  `test_documentation_contract_drift` 15 (disjoint from the unit
  batches).
- Gates: `ruff check app/ tests/` clean;
  `python3 scripts/check_documentation.py` -> `DOCUMENTATION_CHECK=OK
  files=127`; `git diff --check` clean.
- The two independent root real-PG clock/membership 200-c proofs are
  root evidence at c bytes and were NOT rerun (this change does not
  alter the pre-lock, clock, or membership flow).

## Factual correction recorded for the 200-c counts

Root grouped the actual `c-unit-new.xml` test cases by class: the
200-c new suites were **53 service-file + 21 CLI-file = 65**, while
the immutable 200-c report estimated 48 + 17. The 173 affected total
decomposes as 24 + 57 + 27 + 53 + 21. Totals, pass/fail/skip
results, and every other 200-c claim are unchanged; the 200-c report
was NOT edited. This correction is appended in the 200-d
verification addendum (root receipt
`200-c-unit-per-file-count-correction.json`).

## Remaining scope statement

The guards are consistency/reporting laws, not tamper-proof or
signed approval: a fully authorized operator can author a new
self-consistent plan, and the already-applied path still does not
(attempt to) reconstruct the original pre-apply expiry range. The
recommended operational change remains: generate and review a new
dry-run when changing the TTL, not edit one field of an inconsistent
plan. No other 200 gap is known to remain at this head; 201-205
remain INERT.

## Documentation impact

Documentation updated: docs/cli-reference.md,
docs/cli-field-administration.md,
docs/verification/2026-10-28-cli-replay-maintenance.md

- `docs/cli-reference.md`: the extend paragraph now states the
  before-write re-verification of the reviewed post-state
  fingerprint and saved report descriptors under the SELECTED TTL
  (both decision paths; no-effect edits keep the honest no-op) and
  the `range_descriptors_source: reviewed_plan` execute-output label.
- `docs/cli-field-administration.md`: the objective-200 row carries
  the same additions.
- `docs/verification/2026-10-28-cli-replay-maintenance.md`: 200-d
  addendum appended (guards, repeat-path edge, exact JUnit-derived
  evidence, product-byte preservation, the 200-c per-file count
  correction). All prior text unchanged.

## CI / final-head state

Final-head CI for the new head is PENDING at this publication and
remains the root-gated gate; no all-green claim is made here. All
final SELF checks are mandatory before any merge. No full local
verification matrix was run; no release, RC, production, security,
or compliance claim follows.

Same unique PR #356; the coding agent does not merge, auto-merge, or
self-activate.
