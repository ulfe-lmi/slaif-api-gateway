# OAP Objective 196-a — final report: typed CLI key-policy configuration and provider parity

Work order: `oap/orders/196-a-typed-key-policy.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `196-a`; order sha256
`79e7071b6a0b15471adc36d82c94b085ab90d18eacb758491cb92809ac0e0190`,
verified before and after committing).
Branch: `oap/196-typed-key-policy` (new branch); base: `main`
`d8f6c8d731ad12f70d9b1fbd132d72cd6daaa9c7` (remote `main` unchanged at
publication).
PR mode: CREATE_NEW_PR — Objective 196 = exactly one PR, #352,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/352.
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: 5609162281bf37eb7bcf487399bdcb07d42979d5
Report publication commit: SELF

## Implementation commits (branch order, this round)

1. `7762b0835beaac5b2f4f4ba6327641a6258cb3e5` — "Add typed CLI key-policy
   configuration and provider parity": the strategic order (bytes verified
   unchanged, sha256 above) + exact `oap/active` = `196-a` + the
   implementation (8 product files, 5 test files, 4 doc files).
2. `5609162281bf37eb7bcf487399bdcb07d42979d5` — "Harden final authoring
   strictness (196-a)": closed chat streaming live-burn member vocabulary
   enforced before runtime projection on policy-file create, configuration
   update, and RAW stored export (fixed safe message, member names never
   echoed); export document re-parsed by the same strict version-1 schema
   before return (stored values the file contract refuses, e.g. a negative
   rate window, fail the export explicitly); bulk import rejects an explicit
   empty provider list combined with `allow_all_providers` (contradictory
   deny-all vs all; blank/omitted column remains the unrestricted default);
   export round-trip documentation qualified to compatible targets.

## Scope delivered

- Bounded version-1 key-configuration policy file (`--policy-file`, 64 KiB,
  strict schema, fixed safe error vocabulary, bounded I/O at most limit+1
  bytes) on `keys create` / `keys policy update`; the file is the only
  policy source when provided.
- Provider parity: `--allowed-provider` / `--provider-all` / `--provider-none`
  (mutually exclusive) on create/update; `null` (unrestricted) vs `[]`
  (deny-all) persisted distinctly; the same three-state policy carried
  through the existing bulk-import execution path.
- Safe `keys policy export` (explicit nulls for absent groups; never emits
  fresh confirmations; fails explicitly on stored policy it cannot
  administer; rendered document always satisfies the version-1 file
  contract; round-trips apply on compatible targets only).
- Strict Responses/Codex authoring: finite capability vocabulary,
  prerequisite closure, local-tool pairing, exact registered client-module
  pins, configured `CODEX_COMPATIBILITY_PROFILE_FILE` bootstrapped in the
  same CLI process BEFORE pin authoring (invalid configured profile fails
  closed), and the client-module migration law.
- Presence-aware updates (omission preserves; no-op rejected; per-member
  rate patch with strict vocabulary; one audit record per update).
- Explicit one-time key channel law for the new typed create surfaces
  (`--show-plaintext`, `--secret-output-file`, or an explicit
  `--email-delivery` mode required BEFORE creation); the pre-existing legacy
  flag-free create keeps its documented default plaintext-once behavior, and
  the existing `--json` secret guard is unchanged.

## Process honesty

This report closes the SAME continuously activated objective-196 execution:
the control `OK` for 196-a was delivered and consumed exactly once (no
re-signal, no new control reader before publication, no
profile/model/effort change, no objective 197+ activation). All WIP from
the execution was preserved; the order bytes were committed unchanged
(sha256 verified before and after). Multiple in-execution strategic review
notes (actual-CLI source tracking, bounded file I/O, profile bootstrap
ordering, service retention/export/migration laws, the default-secret guard
for typed surfaces, verification-evidence gaps, and final authoring
strictness) were incorporated into this single execution; each repair is
reflected in the implementation and the focused evidence below. No merge,
no auto-merge, no schema migration, no dependency change, and no edit to
the old admin-GUI bulk-import or lazy-throttling test/product paths that
appear in the CI known-fails below (those await root's bounded same-PR
continuation order).

## Focused verification (real process exits)

- New unit suites: **80 passed, 0 skipped**
  (`tests/unit/test_key_policy_configuration.py` 52 +
  `tests/unit/test_cli_key_policy_files.py` 28; JUnit
  `/tmp/slaif196/u1.xml`, `/tmp/slaif196/u2.xml`).
- Affected existing unit suites: **146 passed, 0 skipped** (JUnit
  `/tmp/slaif196/unit-affected-v2.xml`). Two oracles updated exactly where
  the mandated behavior changed; the import file gained the permanent
  empty-list + allow-all negative case.
- Real owned PostgreSQL 16 integration: **8 passed, 0 skipped** (JUnit
  `/tmp/slaif196/integration-196-v2.xml`): real CLI entry path over a fresh
  owned container; stored provider policy proven through the real
  `GatewayAuthService` + `ModelCatalogService` consumer (no provider HTTP;
  test-owned secret files; deliberately custom configured key prefix derived
  from Settings); forced LATE audit failures proving the caller-owned
  transaction rolls back (hook invocation asserted; same-transaction
  write-phase observation before the raise; fresh-session full-row
  comparison; no manual restore); bound-key repin rejected atomically;
  bulk-import provider parity.
- OAP governance 9 + documentation inventory 13: **22 passed, 0 skipped**.
- `ruff check` all changed python: clean. `git diff --check`: clean.
  `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK files=123`.

## CI status at publication (truthful)

- First implementation head `7762b08` (PR #352 initial head): run
  `40609965209` completed — 9 of 10 check runs successful;
  `PostgreSQL integration tests` **failed** with exactly two node IDs
  (381 passed / 9 skipped):
  1. `tests/integration/test_admin_bulk_key_import_execute_postgres.py::test_admin_bulk_key_import_execute_postgres` —
     an old admin-GUI bulk-import oracle that asserts provider policy is
     UNSUPPORTED in that execution path; it directly conflicts with the
     R5 provider-parity change this order mandates. That old test path is
     outside this order's allowed scope and was NOT edited in this PR.
  2. `tests/integration/test_lazy_throttling_postgres_redis.py::test_http_chat_waits_for_capacity_then_admits_once` —
     "app pool has 1 checked-out connection(s) while waiting", a
     pre-existing lazy-throttling timing/pool assertion not touched by this
     PR's diff. Root is independently re-testing the archived `d8f6c8d`
     baseline before classifying it; it is reported here as an unclassified
     CI failure, and no pool assertion or runtime was weakened.
- Second implementation head (this head) `5609162`: CI runs
  `40612250665` (CI) and `40612250630` (CodeQL) in progress at publication.
  The two known failures above are expected to persist on the PG job until
  the bounded same-PR test-scope continuation that root activates after
  this handoff.
- The report-only commit (SELF, below) becomes the new PR head; its run is
  the pending final-head gate. Pending is reported as pending, not as a
  pass. All final-head merge gates remain required. Root owns final-head CI
  and the guarded merge.

## Docs impact statement

- `docs/cli-reference.md`: typed key-policy configuration section (schema
  table with per-field create/update semantics, file/flag law, explicit
  one-time key channel law with the legacy exception accurately marked,
  Responses/Codex authoring rules, migration law, examples); lazy
  throttling wording corrected (typed file authoring/export available in
  196; dedicated setter deferred to 197; dashboard path remains); confirm
  field semantics clarified (fresh acknowledgement when a fenced block is
  SUPPLIED; omission of the block while updating unrelated fields creates no
  new requirement); export sentence qualified to compatible targets.
- `docs/cli-field-administration.md` (new): implemented-in-196 field table
  with exact per-operation provider semantics and the closed live-burn
  member set; proposed 197-205 with corrected future labels (198
  source-key clone with plan/fingerprint/expected live UUID; 200
  replay-reference inspection/expiry maintenance, NOT ownership
  administration; 204 owner/cohort edits plus non-secret config
  inspection, NOT generic key editing); intentionally-not-CLI surfaces.
  This page never declares the full historical brief complete.
- `docs/verification/2026-10-27-cli-key-policy.md` (new): the focused
  objective evidence record (exact commands, counts, layers, boundaries);
  unit fake first-write failure explicitly distinguished from the actual
  late-PG transaction rollback.
- `docs/verification/README.md`: index entry added.
- No other doc, template, CSS, or API file changed.

## Safe boundary statement

- No schema migration; no new dependencies; no API/template/CSS changes; no
  runtime forwarding/accounting/quota/permission redesign (the strict
  authoring checks reject BEFORE the existing validated service paths;
  runtime fallbacks and metadata readers are unchanged).
- One-time plaintext only; the typed surfaces require an explicit secure
  channel; no secret values, file bodies, paths, or operator-supplied
  values appear in any error message; audit values remain allowlisted
  (unknown stored fields counted, never copied).
- No real provider/model/email/credential use; no production data/DB/SSH/
  deploy/release/tag. No real Codex qualification, no real SMTP, no full
  matrix or HPC run.
- One PR (#352) and the report-only SELF topology preserved; remote `main`
  unchanged; no rebase or history rewrite. The coding agent never merged
  and did not enable auto-merge; PR #352 remains open for root's
  independent review, the bounded same-PR continuation for the two CI
  known-fails, all final-head gates, guarded merge, and actual-main
  verification. No new objective is activated by this execution.
