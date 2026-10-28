# OAP Objective 196-c — final report: safe stored-policy audit projection

Work order: `oap/orders/196-c-safe-stored-policy-audit.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `196-c`; order sha256
`7bb12fac15c9812727b05ebb7fda87a29e76a2c233db2a5d77ff72f7ce8739a3`,
verified before and after committing).
Branch: `oap/196-typed-key-policy`; base: `main`
`d8f6c8d731ad12f70d9b1fbd132d72cd6daaa9c7`.
PR mode: AMEND_EXISTING_PR — same unique PR #352,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/352.
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: c5ad27da49e197e6d06ab2eaf236db1e49261b79
Report publication commit: SELF

## Previous immutable state (unchanged by this round)

- 196-a: implementation `5609162281bf37eb7bcf487399bdcb07d42979d5`,
  report-only SELF `34850df80f8adffedb04bcfe1a9a4c8c4a1cd59b`; order
  sha256 `79e7071b6a0b15471adc36d82c94b085ab90d18eacb758491cb92809ac0e0190`,
  report sha256 `4561e32a6c810581280b9d781275ec67fca6525701ffde8b943e9ef0f15c7771`.
- 196-b: implementation `f622770e0a7f5e950d43c80e4cf9c87b04ad1d6a`,
  report-only SELF `d28d0a5c9d42e0930a96078ea53a52b6da755e30` (first
  parent the literal 196-b implementation head, tree
  `0f3d0d8f692823ecb4d4df91adbf20af34fb906f`); order sha256
  `91516ba44e59ddaffd81f2dc3305732a680f6fb2289f574854935dbe4c34a493`,
  report sha256 `65fff0759ec16d847dd1ddbcd1d709f6d4e70326dcc0f2b6e0245fcb39b02e79`.
- No prior order/report byte was touched in this round.

## Implementation commits (branch order, this round)

1. `c5ad27da49e197e6d06ab2eaf236db1e49261b79` — "Keep stored Responses
   canaries out of the configuration audit (196-c)": the strategic order
   (bytes verified unchanged, sha256 above) + exact `oap/active` =
   `196-c` (5 bytes) + the product repair + focused tests + the 196-c
   verification addendum.

No other product path, dependency, workflow, config, schema, migration,
or template was changed; no audit-external helper, registry, or update
function was edited; no 197-205 feature was started.

## Allowed diff (implementation commit)

- `app/slaif_gateway/services/key_service.py` — ONLY
  `_responses_policy_audit_projection` and its private
  constants/imports: `allowed_capabilities` values are now checked
  against the finite reviewed `SUPPORTED_RESPONSES_CAPABILITIES`
  vocabulary (in addition to the existing list/str type check);
  `client_module` is projected only when the pin-only block (version 1,
  the authoring contract's only version) passes the EXISTING strict
  authoring validator `validate_key_responses_policy` (exact keys,
  non-empty strings, module registered in this installation, matching
  current version/fixture). Unknown/stale/malformed values increment
  the fixed `unsupported_fields` count and are never copied or echoed;
  the projection never raises on its own inputs, so a failure in the
  audit projection itself cannot abort an unrelated provider/rate
  update. The now-unused `_RESPONSES_AUDIT_PIN_KEYS` constant was
  removed (the validator enforces the exact pin shape). The shared
  validator/registry were imported for reuse, not modified; all other
  `KeyService` functions are unchanged.
- `tests/unit/test_key_policy_configuration.py` — 4 focused cases
  through an ACTUAL unrelated provider-only configuration update with
  the existing repository fakes: the two exact reproduced known-field
  value canaries (old/new audit + `caplog` absence, fixed safe counts,
  one audit, unchanged raw stored policy), malformed types and a stale
  registered pin (unsupported fallback, update still succeeds, stored
  metadata unchanged), and the positive supported capability + current
  registered pin, including pin-only zero-grants (no auto-added
  grants). Existing negative/positive authoring, export, repin, and
  partial-update cases are unchanged and remain meaningful.
- `docs/verification/2026-10-27-cli-key-policy.md` — appended the 196-c
  verification addendum (exact bug boundary, minimal fix, focused
  evidence, root-independent recheck citation, malformed-stored-case
  scope, layers/limitations). No other doc file was edited.
- `oap/orders/196-c-safe-stored-policy-audit.md` (unchanged bytes),
  `oap/active` (exact `196-c`).

## Focused verification (actual results, 0 skipped)

Pure unit layer (existing repository fakes; no DB, no network, no real
provider/mail/client):

- `tests/unit/test_key_policy_configuration.py` (whole focused file) =
  **56 passed, 0 failed, 0 errors, 0 skipped, actual exit 0** (52 prior
  cases + 4 new). JUnit `/tmp/slaif196c/key-policy-config.xml`.
- `tests/unit/test_key_service_policy_update.py` = **19 passed, 0
  skipped, actual exit 0**. JUnit `/tmp/slaif196c/policy-update.xml`.
- Static gates (self-run): `ruff check` on the two changed Python files
  — all checks passed; `git diff --check` — clean;
  `scripts/check_documentation.py` — `DOCUMENTATION_CHECK=OK
  files=123`; `tests/unit/test_oap_governance.py` (9) +
  `tests/unit/test_documentation_inventory.py` (13) = **22 passed, 0
  skipped, actual exit 0** (at final state). JUnit
  `/tmp/slaif196c/gov-doc3.xml`.
- Root-independent recheck (cited as root-provided independently
  inspected evidence, receipt
  `196-c-root-audit-independent-recheck1.json` at working-tree source
  sha256 `cb0284ee8ecf89b495840d3a7bea33d256329f756a0d62d08e756985e9bc3045`):
  **7 successful** provider-only updates (unknown / mixed / wrong-typed
  capabilities, malformed pin, stale public pin, valid current
  pin-only, valid supported capability) — each with exactly one audit,
  raw stored policy unchanged, canaries absent from BOTH audit old/new
  values, and useful projections for the valid cases; plus **1
  explicitly fail-closed limitation case** (see below). Not claimed as
  self-run; no fabricated all-success.

## Scope limitation (stated accurately)

One pre-existing shape is OUTSIDE this audit-only repair and remains
unfixed: a stored `allowed_capabilities` list containing a non-string
(e.g. a dict) without an explicit `client_module` raises `TypeError` in
the unchanged `stored_module_binding` legacy resolver BEFORE any write
or audit (no state or audit mutation; the direct projection of that
block is canary-absent, and the new strict authoring rejects it). Root
classifies it a nonblocking unsupported corrupt-stored-DB shape, not a
remaining audit leak. Arbitrary corrupt stored JSON is not claimed
universally updatable, and this old pre-projection failure is NOT
claimed fixed by this round.

## CI state (honest, at publication)

- 196-a first implementation head `7762b08` (CI run 40609965209): only
  the PG integration job failed (381/9/2 — the two nodes reconciled by
  196-b); the other nine checks passed.
- 196-a report-only head `34850df`: final CI finished 9/10 (same two PG
  failures).
- 196-b report-only head `d28d0a5`: CI pending at 196-c start, not a
  pass.
- At this publication the fix-head CI for `c5ad27d` is **PENDING — not
  a pass**. The final normal matrix is supplied by final-head CI; root
  owns final-head monitoring; the coding agent never merges. ALL
  final-head merge gates (strategic review + all checks successful)
  remain required.

## Boundaries and limitations

- Audit-output-only behavior change: request acceptance and
  stored-policy behavior are unchanged; this is a projection-privacy
  repair, not a permission redesign, and not a completed runtime
  repair of any other kind.
- Synthetic legacy-metadata proof only (fakes); distinct from, and not
  a substitute for, real client/provider evidence. No
  PG/Redis/browser/CLI re-run in 196-c; the qualified 196-a and 196-b
  layers are cited unchanged (including the root export-probe
  correction).
- No runtime auth/admission/accounting/Redis/forwarding change; no
  schema, migration, or new key/migration instruction; no release
  claim. Objective 196 does not declare the full CLI field brief
  complete (197-205 remain the standing mandate); root activates the
  next continuation after the final-head gates.
