# OAP Objective 200-e — final report: held-fence reconciliation tests isolated to their own reservation

Work order: `oap/orders/200-e-reconciliation-test-isolation.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `200-e` (5 bytes, no trailing newline); order sha256
`47cc1bb909c2f65a0d680ea2b0c8a924658229723d6bb1617f031271c7860e23`
(10,241 bytes), active pointer sha256
`7306bd7f9633bd601f1bf5359d414032c8300c4113bc6fc685c9945ef6718f52`,
both verified before committing and re-verified at HEAD).
Branch: `oap/200-replay-reference-maintenance`; base: `main`
`4c265bc3c9668a66bb1643915d442fb8c411ff11` (unchanged).
PR mode: AMEND_EXISTING_PR — the SAME unique PR #356 created by
200-a, https://github.com/ulfe-lmi/slaif-api-gateway/pull/356, base
`main`, OPEN/MERGEABLE with head at this implementation at
publication. The coding agent never merges; no auto-merge; root
reviews independently and guard-merges.

Implementation head SHA: 96c9436c2bf40842e32fd98f77c2ffb67d9d8cdb
Report publication commit: SELF

## Predecessor state (immutable)

200-d is complete on this branch: implementation head
`ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6` and report commit
`f38d92dee1815f7a6bad6c87360ae8dc1277e6ca` (order sha256
`be4c09ac223691bb861cb4a7379baf38d3e1372406ff2c1fb1806b915b444d78`,
report sha256
`f55d18a3c51579856c04e0e638edceec850a7189aaac547c8fda9b506884bb9a`).
200-c: implementation `d86bc0d3933481a2d4797ebdfc1bc4abbd775d97`,
report commit `032a3af883736c2e728c6d1b79323957edcd30b4`. 200-b:
implementation `8466d9364bd93175a8a370e8f5bc51d6af86b628`, report
commit `32a9f0ca3c231eaf95d88667ce4ad089a5d08f3b`. 200-a:
implementation `9873a4a7a95e4df1fe1ed7d02b97c338d69fa48f`, report
commit `64338b08ee146f4a66658a1d27ef3b50dba7afef`. Objective 199
remains terminal; 201–205 remain INERT; the 205
installed-executable transcript/all-11-DoD remains outstanding. All
prior orders/reports are immutable and were NOT edited.

## Implementation commit (this round)

1. `96c9436c2bf40842e32fd98f77c2ffb67d9d8cdb` — "Isolate held-fence
   reconciliation tests to their own reservation (200-e)": the
   strategic order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `200-e` + the allowed changes listed below
   (5 files total). First parent is the 200-d report commit
   `f38d92dee1815f7a6bad6c87360ae8dc1277e6ca`.

Product-byte preservation:
`git diff ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6 96c9436c2bf40842e32fd98f77c2ffb67d9d8cdb -- app/`
is EMPTY — the ENTIRE product tree is byte-identical to 200-d,
including `app/slaif_gateway/services/reservation_reconciliation.py`
and `app/slaif_gateway/db/repositories/quota.py`. No schema/DDL, no
migration, no dependency, no workflow, no config, no CLI/contract
docs, no accepted replay implementation, no inventory checker change;
no release action. The `ReconciliationInvariantError`
provider-completed guard was never weakened, no core method was faked,
and no batch was given an empty candidate list to avoid the guard.

## What changed (allowed paths only)

- `tests/integration/test_external_tool_fence_postgres.py`:
  - added a tiny per-file-private
    `_OwnQuotaReservationsRepository(QuotaReservationsRepository)`
    that overrides ONLY `list_expired_pending_reservations`: the real
    PostgreSQL-backed pending/expired predicate with the test's own
    reservation UUID filtered at DB selection time, BEFORE the bounded
    limit (unrelated expired rows can never crowd the owned row out of
    the selection); all other repository methods, including the
    per-reservation get-for-update, are the unchanged production
    methods, and the unchanged service performs the real candidate
    conversion, guards, and mutations;
  - the `test_held_fence_blocks_and_never_auto_releases` batch now uses
    the real `ReservationReconciliationService` with that scoped
    repository and asserts exactly `checked_count ==
    candidate_count == skipped_count == 1`, `reconciled_count == 0`,
    the original oracles (reservation still `pending`, key fence state
    still `held`), and reserved cost/tokens/requests unchanged against
    the pre-batch key snapshot;
  - the service import moved from a function-local import to the
    module top (no other import/behavior change).
- `tests/integration/test_external_tool_hold_postgres.py`: the same
  per-file-private selector class;
  `test_hold_survives_engine_restart_expiry_and_ordinary_reconciliation`
  uses it, asserts the same exact scoped-batch counts, retains every
  original oracle (key `held`, reservation `pending`, the
  `list_holds(limit=10)` matching candidate with
  `partial_total_tokens == 0`), and adds the reserved-counters-
  unchanged assertions against a pre-batch key snapshot.
- `docs/verification/2026-10-28-cli-replay-maintenance.md`: 200-e
  addendum APPENDED (all prior text byte-unchanged), containing the
  fix description, the exact verification evidence, the exact CI
  context, the factual correction table below, and limitations.
- `oap/orders/200-e-reconciliation-test-isolation.md` + `oap/active`:
  unchanged strategic bytes committed as-is.

No other test, product, migration/schema, config, dependency,
workflow, doc contract, or replay file was changed. The generic global
candidate query and the ordinary provider-completed fail-closed law
remain unchanged, and their existing coverage was not removed,
skipped, xfailed, or suppressed. No monkeypatches, no
conftest/shared-fixture framework, no new committed harness, no new DB
infrastructure.

## Verified evidence (exact layers, commands, exits, JUnit)

Agent-run evidence (this execution, pane %9, same profile/session):

- Two REAL pytest nodes on a fresh owned PostgreSQL 16 (existing
  `owned_pg_url` fixture: fixed Unix socket, unique owner label,
  loopback binding, tmpfs data dir, identity inspected BEFORE
  migration, exact-ID removal afterward):
  `pytest tests/integration/test_external_tool_fence_postgres.py::test_held_fence_blocks_and_never_auto_releases tests/integration/test_external_tool_hold_postgres.py::test_hold_survives_engine_restart_expiry_and_ordinary_reconciliation`
  with `TEST_DATABASE_URL` pointed ONLY at the freshly created owned
  endpoint — JUnit `tests=2 failures=0 errors=0 skipped=0`,
  actualexit0; owned container `9d1a8885f6aa` (owner
  `slaif200a-d46ce96333b8480c80991527a3657b62`) removed after the
  run; zero owned containers remaining.
- Governance/inventory/drift: 40 = 16 + 9 + 15
  (`test_documentation_inventory.py` + `test_oap_governance.py` +
  `test_documentation_contract_drift.py`) — JUnit
  `tests=40 failures=0 errors=0 skipped=0`, actualexit0.
- Ruff (pinned 59-rule set) over `app/ tests/`: all checks passed.
  `python3 scripts/check_documentation.py`: OK (127 files), run both
  before and after the addendum. `git diff --check`: clean.
- Preservation re-verified at HEAD: `git diff ce4a1ec5eaf9ef3ac43791e5a538d8aed4d3b9f6 HEAD -- app/`
  empty; only tracked changes vs 200-d report commit are the two named
  test files, the verification doc, `oap/active`, and the new order.

Root-independent evidence (root-run; credited as ROOT evidence, not an
agent run; no duplicate fixture/framework rerun performed here):

- Post-fix isolation harness (strategic receipt
  `review-artifacts/cli-feature-round/200-e-independent-after-isolation-proof.json`,
  2026-10-29T00:36:39Z, root terminal 49936 CLOSED actualexit0): ONE
  pytest harness (`tests=1 failures=0 errors=0 skipped=0`, 7.85s)
  calls both actual test functions on a fresh DB (both PASS), then
  both again with 102 unrelated expired
  provider-completed/`needs_reconciliation` rows present — more than
  the production list's default 100-row first page (both PASS, and ALL
  foreign rows/ledgers/key reserved counters unchanged) — and a direct
  ordinary single-reservation reconcile on a foreign row STILL raises
  the exact fixed reason "Provider completed before accounting
  finalization failed; do not release as zero-cost stale
  reservation". It ran at exactly the 200-e test file SHAs
  (`0edc0d907895c5569beea0eff93635e890edd07107212c4e32df36fa050cc4e3`
  fence / `8a3af6de592fdd7adf638b03fbb7e0914381af2ebf8f745b4c71e1dad12bc1b6`
  hold; sources stable during the proof) and removed its exact owned
  container (`slaif200-root-recon-isolation-after-e-4793f7727f01430fba9e522b23394127`).
  Layer: actual unchanged services/repositories and the original test
  functions with the new scoped test selectors on real owned PG16; no
  provider/client/SMTP/production qualification.
- D final-head CI receipt
  `200-d-final-ci-success-observed-during-e.json`
  (2026-10-29T00:19:31Z).

## CI context (exact and honest)

- C-SELF `032a3af` (CI run 40789904468, job 123172757105): PostgreSQL
  integration `2 failed / 448 passed / 9 skipped`; the failures were
  EXACTLY the two tests repaired here. That is real historical flake
  evidence (plus root's deterministic owned-PG foreign-row
  counterexample), not a claim that the old tests pass with foreign
  candidates.
- D-SELF `f38d92d`: ALL 10 final-head checks SUCCESS (PostgreSQL
  completed 2026-10-29T00:12:10Z). The 200-e activation order's
  "dSELF checks partly pending" wording was a stale snapshot at
  activation; current GitHub truth is D green.
- The new E-SELF still requires ALL 10 final-head checks; they are
  PENDING at this publication (see CI / final-head state below).

## Factual documentation correction (recorded in the addendum)

The immutable 200-d report's attempted correction of the c counts
copied the d counts and made the impossible claim 53+21=65. That d
correction was itself wrong; the 200-e addendum is its correction.
Genuine per-file counts from the recorded JUnit XMLs (root
`200-c-unit-per-file-count-correction.json`):

| Recorded run | Service maintenance file | CLI replay file | Other unchanged files | Actual total |
|---|---:|---:|---|---:|
| c-unit-new.xml | 45 | 20 | none | 65 |
| c-unit-affected.xml | 45 | 20 | replay_service24 + replay_limits57 + cli_codex27 | 173 |
| d-unit-new.xml | 53 | 21 | none | 74 |
| d-unit-affected.xml | 53 | 21 | replay_service24 + replay_limits57 + cli_codex27 | 182 |

Both c/d governance runs 40 = inventory 16 + governance 9 + drift 15;
c owned PG 15, d owned PG 16; all of those focused runs had 0
failures/errors/skips. The c/d per-file wording errors did NOT change
the genuine 65/173/74/182 totals or outcomes; old reports are
preserved and were NOT edited. The 200-e test-isolation evidence above
has its own counts and does not replace the c/d proofs.

## Limitations

- No full verification matrix was rerun (no 173/182 unit reruns, no
  replay PG suites, no root clock/membership probes); final-head CI
  for the new E-SELF remains the broad mandatory root-gated gate and
  is PENDING at this publication.
- The scoped selector is test-local dependency injection, not a
  production path: the production global batch keeps the exact same
  query/limit/guard semantics.
- No API/provider/mail/client qualification follows; the full CLI
  goal 201–205 and all 11 installed-executable DoD items remain
  unproven; no release claim.

## Documentation impact

Documentation updated: docs/verification/2026-10-28-cli-replay-maintenance.md

- 200-e addendum appended (scope/fix, exact verification evidence with
  layers/commands/exits/JUnit, exact CI context, the factual
  correction table, limitations). All prior text byte-unchanged.

## CI / final-head state

Final-head CI for the new E-SELF head is PENDING at this publication
and remains the root-gated gate; no all-green claim is made here. All
final SELF checks are mandatory before any merge. No merge,
auto-merge, or self-activation by the coding agent; no 201 activation;
no new control signal sent by this report. Same unique PR #356.
