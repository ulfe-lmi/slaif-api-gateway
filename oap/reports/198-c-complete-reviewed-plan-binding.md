# OAP Objective 198-c — final report: complete reviewed-plan binding and consumable dry-run

Work order: `oap/orders/198-c-complete-reviewed-plan-binding.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `198-c` (5 bytes, no trailing newline); order sha256
`2907cbea2344447379d0f3e358294f5a745a883504e0eeaf9d529e8f1e2b8db3`,
verified in the working tree before committing and byte-identical in the
implementation commit).
Branch: `oap/198-faithful-key-cloning`; base: `main`
`b4bc8a5b0c15be51135c1a9e3fc644189b51222e`.
PR mode: AMEND_EXISTING_PR — the SAME unique PR #354,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/354, base `main`.
The coding agent never merges; no auto-merge; root reviews independently
and guard-merges.

Implementation head SHA: 5f653212e787862e91c071a1a7aeed2573d81595
Report publication commit: SELF

## Predecessor state (unchanged)

198-a: implementation `889d37b5a210f746699ecbb69c4c960b9d7e8448`, report
SELF `29b6c73b727aac5f28e13c6b4c7d4b768074a869`. 198-b: implementation
`ffb52182ab07f8d9c0ec933b2c0502de3bdb041c` (the literal parent of this
implementation commit), report SELF `e02d4cd96cf2ce15511910750ed2b4890502be1e`.
All 198-b report-head checks (ten) were observed SUCCESS at
2026-10-28T13:18Z; the b repairs were independently verified
(`198-b-independent-recheck.json`). GitHub state re-verified before edits:
remote `main` still `b4bc8a5b0c15be51135c1a9e3fc644189b51222e`; PR #354
OPEN / MERGEABLE / head `e02d4cd`; only other PR #319 (Dependabot,
preserved). Objectives 196/197 TERMINAL; 199-205 INERT.

## Implementation commit (this round)

1. `5f653212e787862e91c071a1a7aeed2573d81595` — "Bind complete reviewed
   clone identity, guarantee consumable dry-runs (198-c)": the strategic
   order (bytes verified unchanged, sha256 above) + exact `oap/active` =
   `198-c` + the bounded completion listed below.

No schema migration, no DDL, no new dependency, no workflow/config/
template/CSS change, and no runtime auth/admission/accounting/Redis/
forwarding behavior was modified. The allowed CLI and plan-schema paths
required NO change (the service-level repairs suffice; the CLI dry-run
build error already flows through the existing safe error path before any
file write). Objectives 199-205 were not started.

## Allowed diff (implementation commit, 11 files, +647/-57)

Product (allowed paths only, clone methods):

- `app/slaif_gateway/services/key_clone_service.py` —
  `KeyCloneReviewedPolicyMismatchError` message now covers reviewed
  validity; `build_plan` re-validates the BUILT document with the SAME
  strict parser (`parse_clone_plan_document`) before returning, so a
  successful dry-run always yields an executable plan and an over-bounds
  build (e.g. duration > documented 1,000-year maximum) fails with a
  fixed safe error, no file/audit/mutation; `execute_plan` on FIRST
  execution compares the reviewed COPY-SOURCE-EXPIRY
  `source_valid_until` (normalized ISO) to the fresh locked source's
  actual expiry and refuses a mismatch before any write;
  `attach_clone_receipt` gains `source_public_key_id` +
  `source_valid_until`; `_receipt_matches_plan` compares the FULL
  business identity including both new members (a/b-shape receipts
  lacking them fail controlled).
- `app/slaif_gateway/db/repositories/keys.py` (clone methods only) —
  `find_clone_receipts` bounded by SQL `LIMIT 2` (two matches prove
  ambiguity; no unbounded materialization); `attach_clone_receipt` stores
  the two new bounded safe identity members.

Tests:

- `tests/unit/test_key_clone_service.py` (26 → 34) — fake receipt carries
  the new identity members; +8 focused regressions: copy-expiry reviewed
  mismatch refused before create (no create/audit); changed public ID on
  a completed operation refused; changed reviewed expiry on a completed
  operation refused; original repeat after an ACTUAL source expiry edit
  still `already-applied` (same target); inert preview change remains
  inert; receipt carries the complete business identity (no `sk-`
  material); dry-run strict round trip at the documented maximum;
  duration maximum+1 fails safely (fixed message, value not echoed). The
  post-lock-clock test (review thread PRRT_kwDOSLm-qM6xIbdj) no longer
  assigns the module `_now` directly: dotted-target
  `monkeypatch.setattr` inside the lock callback so teardown restores the
  clock; the duplicate in-function module import was removed; the
  semantic expiry-during-lock test is kept.
- `tests/unit/test_cli_keys_clone.py` (28, count unchanged) — the bounded-
  read test (review thread PRRT_kwDOSLm-qM6xIbdN) replaces its empty
  broad `except/pass` with an assertion of the EXPECTED fixed error
  ("Clone plan file exceeds the bounded size", no path echo), retaining
  the cap+1 and before-DB oracles.
- `tests/integration/test_cli_key_clone_postgres.py` (7 → 8) — NEW
  `test_clone_reviewed_identity_and_expiry_binding`: exact valid
  copy-source-expiry plan creates; contradictory reviewed expiry on a
  FRESH plan's first execution refuses with no new rows/audits; changed
  reviewed public ID and changed reviewed expiry repeats refuse with no
  duplicate key; after an ACTUAL source validity edit the original exact
  repeat still returns the same target. The existing two-new-plans case
  now asserts both targets' canonical policy exports equal the source's
  and the source row is unchanged; the concurrency case now asserts the
  child CLI `exit_code == 0` in both processes.

Docs: `docs/cli-reference.md`, `docs/database-schema.md` (receipt JSON
contract only), `docs/cli-field-administration.md`, and the 198-c
ADDENDUM appended to `docs/verification/2026-10-28-cli-key-cloning.md`
(a/b history retained, not rewritten).

## Corrections to demonstrated 198-b limitations

1. Changed `source_public_key_id` on a completed plan still returned
   `already-applied` → now refused (`key_clone_plan_mismatch`).
2. The reviewed copy-source-expiry `source_valid_until` was inert: a
   tampered date created with the actual source expiry, and a differently
   dated repeat was accepted → first execution now verifies the reviewed
   date against the fresh source (refused, never substituted) and the
   receipt binds it for repeats.
3. A successful dry-run could emit a non-consumable plan (over-bounds
   duration) → the built document is re-validated with the same strict
   parser before the file is written.
4. Two review-thread test hygiene repairs (empty broad except/pass;
   leaking `_now` module assignment) fixed with semantic oracles kept.

## Exact verification

Environment: `PYTHONPATH=app /tmp/slaif192-coding-venv/bin/python -m
pytest` (no ambient `DATABASE_URL`; owned disposable `postgres:16`,
label prefix `slaif198a`; identity inspected before readiness/migration;
exact-ID cleanup).

- `pytest tests/unit/test_key_clone_service.py tests/unit/test_cli_keys_clone.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/unit-clone-c.xml`
  → **62 passed** (34 + 28), 0 failed / 0 errors / 0 skipped.
- `pytest tests/integration/test_cli_key_clone_postgres.py
  -p no:cacheprovider -q --junitxml=/tmp/slaif198/integration-clone-c.xml`
  → **8 passed** (7 retained + 1 new), 0 failed / 0 errors / 0 skipped;
  no leftover `slaif198a`-prefixed containers.
- Root repro re-run with FRESH receipts (old evidence preserved):
  `198-c-independent-recheck.json` then
  `198-c-independent-recheck-2.json` under
  `review-artifacts/cli-feature-round/`. The probe was adapted in two
  harness-only places (unguarded `build_plan` call now legitimately
  raises under the consumable-dry-run contract; the
  `different_source_expiry_repeat` case reordered to repeat AFTER
  completion, preserving intent). Outcomes: changed public ID repeat
  refused; tampered reviewed expiry first execution refused (0 creates);
  differently dated repeat refused (1 create retained); over-maximum
  duration refused by the builder (`KeyClonePlanError`); all previously
  fixed b cases remain fixed.
- `tests/unit/test_documentation_contract_drift.py` → 15 passed
  (unchanged consumer guard included);
  `tests/unit/test_documentation_inventory.py` +
  `tests/unit/test_oap_governance.py` → 22 passed;
  `scripts/check_documentation.py` → `OK files=125`; Ruff clean over all
  five changed product/test files; `git diff --check` clean.

## CI state

GitHub final-head CI for the 198-c head `5f65321` is PENDING (root-gated;
no CI result is claimed here). The coding agent never merges; all
final-head merge gates remain required.

## Security, privacy, atomicity, isolation, cleanup

The two new receipt members are bounded safe public identity data (a
public key ID string, an ISO datetime or null) — no key material, token
hashes, provider references, raw metadata, usage, or secrets; every new
error is a fixed safe message. Fingerprints remain dedup data, never
authentication/replay authority; no signatures, jobs, general serializer,
or new authority were introduced. Atomicity, the enforced READ COMMITTED
boundary, source-row lock serialization, and no-plaintext-recovery are
unchanged. No schema/column/constraint/migration added. No real
provider/model contact, real SMTP, Redis, or upstream smoke occurred.

## Documentation impact

- `docs/cli-reference.md`: consumable-dry-run guarantee; reviewed
  copy-source-expiry expiry revalidation (never substituted); FULL
  business identity (source public key ID + reviewed copy-source-expiry
  expiry) with two-bounded ambiguity lookup and retry-after-actual-source-
  edit behavior.
- `docs/database-schema.md`: `clone_receipt` JSON gained
  `source_public_key_id` + `source_valid_until`; lookup bounded to two
  matches; old-shape receipts as controlled refusal; actual source edits
  as non-identity-changing for completed operations.
- `docs/cli-field-administration.md`: the 198 row reflects the 198-c
  binding and consumable-dry-run behavior (199-205 remain proposed; the
  objective-205 installed-executable-only transcript remains mandatory).
- `docs/verification/2026-10-28-cli-key-cloning.md`: 198-c addendum
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
