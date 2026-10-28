# OAP Objective 197-b — final report: truthful CLI pagination, safe lookup/output guards

Work order: `oap/orders/197-b-cli-output-and-pagination.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `197-b` (5 bytes, no trailing newline); order sha256
`910295820eef40541b11680fddddfeab468a7ca787dca5eba70f9a0b3032618e`,
verified before and after committing).
Branch: `oap/197-effective-key-policy-and-waiting`; base: `main`
`6f6bc6fa7dc2aa9bb21ee2b0bc04f913e5d8c25c`.
PR mode: AMEND_EXISTING_PR — SAME unique PR #353,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/353, base `main`,
title "Explain effective key policy and expose bounded lazy throttling
in CLI". The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: 4b735f31f2fc97918fd1302b6bbd862ebe55ef1b
Report publication commit: SELF

## Predecessor state (unchanged)

197-a is immutable: implementation
`22b247dfa79c9fcb3fac8b528cfa3e86b54aea79`; report-only SELF
`e9f2e6c23274cf71c35f179002d54e0721380378` (first parent the literal
implementation head, report-only diff, tree
`b1b3759ec9464c13b4de64b888a53783d70f6222`). 197-a order sha256
`ee0540b8254088909b66b9e4d35c785e0a85ceda95784b8221f531b560a6b75d`;
197-a report sha256
`a8c27de43b62714b203311c1087f2d27706e66b8865fea5f39a12f799f18c554`.
Neither was edited. Objective 196 remains TERMINAL (PR #352 merged as
`6f6bc6fa7dc2aa9bb21ee2b0bc04f913e5d8c25c`). Objectives 198-205 remain
INERT. The only other open PR is the unrelated Dependabot PR #319
(preserved).

## 197-a final-head CI result (stated accurately)

At the 197-a report-only head, the unit job (122747119666 / run
40667776548) completed 3 FAILED / 5827 PASSED / 1 SKIPPED and the other
nine final-head checks SUCCEEDED, including owned PG. The three failing
nodes were: two Rich ANSI/wrapping style assertions in
`tests/unit/test_cli_keys_effective_policy.py`
(`test_set_lazy_throttling_help`, `test_set_lazy_requires_reason`) and
the existing consumer guard
`tests/unit/test_documentation_contract_drift.py::test_external_tool_policy_contract_consumers_remain_allowlisted`,
which correctly rejected the new `key_policy_inspection.py` import of the
external-tool policy contract. All three are addressed by 197-b within
the allowed paths (see review fixes); none was a product-behavior
failure.

## Implementation commit (this round)

1. `4b735f31f2fc97918fd1302b6bbd862ebe55ef1b` — "Truthful CLI
   pagination and safe lookup/output guards (197-b)": the strategic
   order (bytes verified unchanged, sha256 above) + exact
   `oap/active` = `197-b` + the bounded repairs, tests, docs, and
   verification addendum listed below.

No other product path, dependency, workflow, config, schema, migration,
model, or template was changed; no runtime auth/admission/accounting/
Redis/forwarding behavior was modified; no 198-205 feature was started.

## Allowed diff (implementation commit, 11 files)

Product (allowed paths only):

- `app/slaif_gateway/services/key_policy_inspection.py` — NEW shared
  finite safe projections reused by the legacy CLI reads:
  `safe_responses_policy_projection` (absent → `None`; valid block →
  strict shared 196 validator canonical members only;
  unknown/malformed/stale/non-object → fixed `{"state": "invalid"}`;
  canonical string members pass existing known-shape redaction),
  `safe_provider_policy_projection` (explicit `unrestricted` /
  `allow-list` / `deny-all` / `invalid` state; legitimate
  `None`-vs-`[]` preserved; surviving string members pass existing
  known-shape redaction), `safe_calibration_metadata_projection`
  (finite known members only, redacted; unknown/malformed members
  dropped, never copied), `safe_freeform_reason_projection`
  (known-shape redaction for free-form read values such as
  `revoked_reason`; ordinary text preserved; non-strings unchanged).
  The existing private `_provider_policy_inspection` was renamed to the
  public shared helper (behavior unchanged); the report's `key`
  section uses the reason projection. REMOVED: the unused
  `external_tool_policy_contract` import, its parse block, and the
  `external_tool_policy=...to_metadata()` DTO population — the parsed
  field was consumed NOWHERE in inspection/rate/endpoint/route output
  (source-verified; `AuthenticatedGatewayKey.external_tool_policy`
  keeps its `None` default), which is what the unchanged consumer guard
  required. No new consumer, path, or authority was added.
- `app/slaif_gateway/cli/keys.py` — R1: `keys list` fetches `limit + 1`
  (bounded lookahead; 201 internal for the 200 page bound) and returns
  only `limit` rows; `has_more` true ONLY when an extra real row
  exists; `next_offset` null at the true end; filters-before-paging,
  stable `created_at`+UUID ordering, 200 output bound, legacy `keys`
  array and additive `paging` JSON unchanged. R2: `_safe_gateway_key_dict`
  and the `policy show` payload now use the shared projections
  (additive `allowed_providers_state`; legacy members preserved) and
  the finite `calibration_metadata` projection; `_responses_policy_from_gateway_key`
  projects through the strict validator instead of copying raw. R3:
  `_resolve_gateway_key_reference` refuses credential-shaped
  references BEFORE any database query with the same fixed no-echo
  message (internal whitespace, `.` secret separator, case-insensitive
  `Bearer` header prefix, any configured accepted key prefix from
  `Settings.get_gateway_key_accepted_prefixes()`); valid UUID / exact
  public key ID behavior unchanged; no auth-parser or core-crypto
  change. R4: `--mode reject` WITH waiting bounds fails BEFORE any
  mutation (Typer usage error); plain reject and `--clear` remain the
  documented distinct verbs with the SAME stored outcome (no stored
  override / immediate rejection) and accept no waiting bounds; wait
  still requires BOTH positive bounds within the installation
  ceilings; help/docstring corrected (no more "validated but INACTIVE").
  The shared KeyService reject-canonicalization law is unchanged.

Tests (allowed paths only):

- `tests/unit/test_cli_keys_effective_policy.py` — the two
  CI-failing style assertions made style-independent (ANSI strip +
  whitespace normalization + stable terminal width via `env=`; product
  styles and global CI config unchanged); the bare
  `fake_inspection_runtime` expression removed (fixture parameter kept);
  the obsolete "reject bounds validated but inactive" oracle replaced
  with refusal-before-mutation (no service call) plus the retained
  over-ceiling wait refusal oracle; NEW: exact-final-page `has_more
  false` (limit 2 / 2 rows, plus partial final page), R2 canary
  cases (private Responses field, malformed provider member, unknown
  calibration member, wrong-type member; valid policy and
  None-vs-allow-list states retained; known-shape redaction of
  provider/calibration strings), R3 zero-lookup refusals (case-
  insensitive Bearer, whitespace, malformed short credential, known
  prefix; configured CUSTOM accepted prefix; valid UUID/public ID
  still work; repository call tracking proves zero queries), R4
  reject-with-bounds no-mutation, `revoked_reason` preserved-verbatim
  vs known-shape redacted.
- `tests/unit/test_cli_keys_status.py` — fake fetch limit assertion
  updated to the new lookahead meaning (`5` → `6`); all other real
  oracles kept.
- `tests/unit/test_key_policy_inspection.py` — NEW projection-helper
  cases: Responses projection states (absent/valid/unknown-field/
  non-dict/notes redaction), provider projection states incl.
  known-shape redaction, calibration finite-members-only + redaction,
  and the report-level `revoked_reason` preserved vs redacted canary
  (known secret shape absent from the whole report).
- `tests/integration/test_cli_key_effective_policy_postgres.py` —
  fixture lifecycle UNCHANGED; R5 non-mutating metadata absence check
  (no dictionary mutation in asserts) with the full snapshot
  comparison retained; NEW 4 cases: exact full final page against PG
  (2 rows / limit 2 → `has_more false`, `next_offset null`),
  end-to-end credential-shaped refusals (fixed message, no echo,
  valid public ID still resolves), safe-read canaries (unsupported
  Responses/provider/calibration data absent; legitimate values
  retained; known-shape redaction in provider members, calibration
  string, and `revoked_reason`), and reject-with-bounds failing with
  NO state change (audit/`updated_at`/metadata unchanged) followed by
  a successful plain reject (audit +1, override removed).

Docs (allowed paths only):

- `docs/cli-reference.md` — accurate lookahead/`has_more` semantics;
  credential-shaped refusal; safe default display projection
  description; reject/clear same-outcome alias + refused bounds
  (correcting the 197-a "validated but INACTIVE" text).
- `docs/cli-field-administration.md` — the 197 lazy row and safe
  lookup/paging row corrected to the exact 197-b semantics.
- `docs/verification/2026-10-28-cli-effective-key-policy.md` — APPENDIX
  ADDENDUM only (197-a history preserved, not rewritten): 197-a CI
  result stated accurately, corrected "any 197 stdout" privacy
  coverage (legacy show/list DID leak unsupported/known-shape data
  before 197-b; the new tested paths are named), the acknowledged
  scope exception, repairs, exact commands/counts/exits/layers, and
  limitations.

OAP: unchanged strategic order + exact `oap/active` = `197-b` bytes
(committed), plus this report. No root strategic plan/audit/timing
files in the PR.

## Review fixes (honest provenance)

Root-side strategic review during this execution (cited receipts, not
coding-agent artifacts):

- `197-b-cli-independent-wip1.json` — all FOUR original CLI defects
  confirmed fixed at an actual Typer WIP check.
- `197-b-known-secret-wip1.json` — demonstrated that KNOWN
  authentication/provider secret shapes (synthetic `sk-proj-` pattern)
  still survived in the provider allow-list and calibration string
  projections. Repaired by reusing the EXISTING
  `utils.redaction.redact_text` primitive at the safe display string
  boundaries (provider members, calibration strings, Responses
  `notes`, and — per the follow-up `197-b-read-reason-canary-wip1.json`
  — the free-form `revoked_reason` in BOTH the `_safe_gateway_key_dict`
  read and the inspection report). Known-shape protection only; NOT
  universal content sanitization and NOT a new sanitizer framework;
  legitimate values, `None`-vs-empty distinctions, and explicit
  invalid markers preserved. Focused positive (ordinary reason /
  ordinary values) and negative (known-shape canary) coverage added at
  unit and PG layers.
- CI regression re-checks (3 PASS under forced color) and
  read-canary positive/negative probes: complete per root.
- Root independently confirmed: no leftover `slaif197a.owner`
  containers; all hashes and protected files unchanged; scoped product
  functions accepted.
- Documentation precision: the evidence layers for the R3 claims were
  distinguished in the addendum (zero-lookup counts and the custom-
  accepted-prefix case proven in the unit layer with mocked-repository
  call tracking; normal-prefix refusal/no-echo and public-ID success
  proven end-to-end against owned PG without SQL lookup-count
  instrumentation).

## Scope exception (corrected record)

`tests/unit/test_cli.py` was not explicitly listed in the 197-a allowed
existing test paths although the 197-a report claimed all paths
allowed. Root inspected the 13-line additive paging JSON oracle and
explicitly authorized that narrow existing change; it is retained (not
reverted) and acknowledged here. 197-b made no further change to that
file.

## Actual focused verification (this execution)

Environment: `PYTHONPATH=app` with `/tmp/slaif192-coding-venv`
(Python 3.12); no ambient `DATABASE_URL` / foreign PG (the
integration layer's owned container is the only database).

- Focused unit set (6 files: `test_cli.py`, `test_cli_keys_status.py`,
  `test_cli_keys_effective_policy.py`, `test_cli_keys_create.py`,
  `test_key_policy_inspection.py`,
  `test_documentation_contract_drift.py`): 123 passed, 0 skipped, exit
  0. (The unchanged contract-drift guard node — the 197-a CI failure —
  is among these and now PASSES.)
- Owned-PostgreSQL-16 integration module (real CLI entry path): 13
  passed (9 retained + 4 new), 0 skipped, exit 0 (JUnit
  `/tmp/slaif197/integration-6.xml`). Fresh qualified owned fixture:
  unique `slaif197a-*` owner label, postgres:16, 127.0.0.1 loopback,
  tmpfs data directory, identity re-inspected BEFORE
  readiness/migration, exact-ID cleanup in `finally`; no leftover
  container after the run (label filter verified; root
  independently confirmed).
- Gates: Ruff on all changed Python — OK; `git diff --check` — OK;
  `scripts/check_documentation.py` — OK (files=124);
  `tests/unit/test_oap_governance.py` +
  `tests/unit/test_documentation_inventory.py` — 22 passed, exit 0.
- Root confirmed the focused 123 PASS and owned-PG 13 PASS / 0 skip
  independently; no passing suite was re-run for formatting.

## CI state (honest)

- 197-a report head: 3 FAILED / 5827 PASSED / 1 SKIPPED (unit job) +
  nine other checks SUCCESS — as stated in the addendum; those three
  failures are the direct subject of this 197-b repair.
- 197-b implementation head `4b735f31f2fc97918fd1302b6bbd862ebe55ef1b`:
  the normal FINAL-head CI is PENDING at publication and is the broad
  gate. Root independently owns final-head CI and strategic review;
  the coding agent did not wait on, merge, or act on CI results.

## Security / privacy / accounting statements

- Credential-shaped references are refused with a fixed no-echo error
  BEFORE any database query; valid UUID / exact public key ID lookups
  are unchanged (unit zero-lookup + custom-prefix; PG end-to-end).
- KNOWN authentication/provider secret shapes in stored provider
  members, calibration strings, Responses `notes`, and `revoked_reason`
  are redacted at the display boundary in BOTH the inspection report
  and the legacy `show`/`list` reads via the existing redaction
  primitive; ordinary values preserved verbatim. Unsupported/arbitrary
  private strings are handled by finite projections (fixed invalid
  markers / omission) — no universal-sanitization claim.
- No mutation-result, create/show-plaintext output channel, storage,
  schema, migration, dependency, workflow, auth, admission,
  accounting, or Redis behavior changed; no real
  provider/model/client/SMTP contact; synthetic data only.
- Waiting never relaxes hard quota, auth, security, or pricing;
  reject/clear still change only the key's lazy metadata,
  `updated_at`, and one audit row (proven).

## Limitations

- Final-head CI on the 197-b head is PENDING at record time; skipped/
  pending items are not passes. No full local unit/browser/HPC matrix
  rerun was performed; the 197-a local green suites plus the focused
  runs above stand.
- No release, RC, production, security, or compliance claim follows.
