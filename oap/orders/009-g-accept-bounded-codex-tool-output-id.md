# OAP Work Order — 009-g

## Objective

Resolve the exact pinned-client tool-output mismatch reported by 009-f: accept
and meter the optional bounded Responses item `id` defined by Codex 0.147.0 for
fully gated `function_call_output` and `custom_tool_call_output`, while
preserving immediate HMAC-owned call/call_id linkage, request-wide item-ID
uniqueness, ordinary output rejection, and all privacy/accounting bounds. Then
make the unchanged exact compact verifier complete on existing PR #234.

## GitHub state

- Numeric objective `009`, round `009-g`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #234:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`.
- Branch `oap/009-codex-context-output-cache-compaction-accounting`; base
  `main`.
- Starting remote/report head:
  `77dd6a3e0ad9a73b2edd435cd8c505feb330eee5`.
- 009-f implementation head:
  `3a427e9abd039c22e9309c4e767f772369f7496a`.
- 009-f status: `BLOCKED` only because the unchanged verifier next hit safe
  code `responses_codex_tool_roundtrip_invalid` at `input[8].id`. Its privacy
  repair, focused tests, and ten implementation-head checks passed.

Amend PR #234 only. Never create another objective-009 PR.

## Pinned-source and ownership finding

Pinned source `rust-v0.147.0` at
`be6e8eac029b183056b7e4402879f15d2c85f61b`, `ResponseItem` in
`codex-rs/protocol/src/models.rs`, defines an optional `id` on both
`FunctionCallOutput` and `CustomToolCallOutput`. The captured failing item is a
`custom_tool_call_output`; safe diagnostics establish only that its ID is a
41-character/41-byte ASCII string matching SLAIF's existing bounded item-ID
pattern. There is no duplicate ID in the captured compact history.

The output remains authorized by its immediately preceding call, exact output
type, unique bounded `call_id`, declared namespace/name/type, and the HMAC-owned
tool-call reference. The optional output item ID does not grant a tool, route,
provider, or execution authority. It is transient provider/model history
identity only.

Strategic decision:

- in only the fully gated Codex function/custom output validator, allow optional
  `id` and validate it through the existing bounded Codex item-ID validator;
- include it unchanged in the canonical/upstream output item when present;
- include its complete canonical bytes in input-token/cost estimation;
- subject it to the existing request-wide item-ID uniqueness check;
- do not create a separate replay/HMAC reference for output IDs: the output is
  usable only as the immediately linked result of the HMAC-owned call/call_id;
- ordinary non-Codex function/custom outputs continue to reject `id`.

## Required work

1. Reconcile canonical GitHub, PR #234, all immutable 009 rounds, applicable
   AGENTS/OAP instructions, pinned source/tag/binary, and current output/linkage
   validators/tests.
2. Commit the strategic `oap/active=009-g` pointer and this order unchanged.
3. Add Codex-specific output allowed-field sets (or equivalent) containing
   exactly current output fields plus optional `id`. Do not add `name`, status,
   authority, metadata, or unknown fields.
4. Validate a present ID with the existing exact Codex item-ID helper and fixed
   safe error code/parameter. Add it to the canonical dict before canonical JSON
   material-byte calculation. Absent ID retains existing canonical behavior.
5. Preserve `_validate_codex_tool_roundtrip_items` immediate adjacency,
   call/output type matching, call-id uniqueness, output uniqueness, declaration
   matching, request-wide item-ID uniqueness, and complete set equality. Do not
   relax HMAC ownership or route checks.
6. Add focused tests proving:
   - pinned 41-byte custom output ID and a valid function output ID pass;
   - absent ID still passes;
   - non-string, empty, invalid-character, too-long, and unknown fields fail
     safely without ID/output echo;
   - duplicate output IDs and collision with call/reasoning/message IDs fail;
   - orphan/reordered/mismatched/cross-type call/output remains denied;
   - ordinary function/custom outputs with ID remain denied;
   - ID bytes increase canonical material/token estimation exactly and do not
     enter safe evidence or replay/HMAC candidates.
7. Rerun the unchanged exact 009 verifier once. It must emit `RESULT=OK`,
   `REQUEST_COUNT=3`, `GATEWAY_COMPACT_POLICY_ACCEPTED=true`, and all prior fixed
   safety booleans with no raw persistence/output or real provider call.
8. Update only affected compatibility/accounting/security/forwarding contracts.

## Allowed paths

Implementation may change only:

```text
app/slaif_gateway/services/responses_request_policy.py
docs/accounting.md
docs/codex-compatibility.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/009-g-accept-bounded-codex-tool-output-id.md
tests/unit/test_responses_codex_compaction.py
tests/unit/test_responses_codex_multiturn_replay.py
tests/unit/test_responses_codex_streaming_tools.py
```

Final report-only commit adds only:

```text
oap/reports/009-g-accept-bounded-codex-tool-output-id.md
```

The verifier must remain unchanged. Do not edit schemas/models/migrations,
settings/config, gateway/accounting/replay/pricing code outside the policy file,
dependencies, fixtures, prior OAP history, CI, deployment, README, or unrelated
paths.

## Focused verification and test economy

Run only:

- `tests/unit/test_responses_codex_compaction.py`,
  `tests/unit/test_responses_codex_multiturn_replay.py`, and
  `tests/unit/test_responses_codex_streaming_tools.py`;
- focused OAP/documentation contract tests;
- scoped Ruff/compile, `git diff --check`, exact path/topology, fixture digest;
- one final unchanged exact pinned Codex context/compaction verifier run.

Do not run full unit, integration, PostgreSQL, E2E, browser, Docker/Compose, or
HPC suites locally. GitHub CI owns broad coverage. Never call a real provider or
side-effecting external tool.

Report literal commands/counts, exact safe verifier keys, every broad suite NOT
RUN, and any failed development attempt honestly.

## Acceptance criteria

1. Optional bounded IDs pass only on fully gated Codex function/custom outputs,
   are canonicalized/metered, and remain globally unique.
2. Immediate HMAC-owned call/call_id linkage and all negative round-trip cases
   remain intact; no separate output-ID authority/reference is created.
3. Malformed/duplicate/unknown IDs fail safely and ordinary output behavior is
   unchanged; no ID/output enters safe evidence/persistence.
4. The unchanged exact Codex 0.147.0 verifier completes its three-request V1
   compact loop and reports gateway policy accepted with no raw persistence/
   output or real provider call.
5. Focused tests/docs/quality/path/fixture checks and every report-head GitHub
   check pass; no broad local suite runs.
6. One existing PR only; coding agent never merges/enables auto-merge; immutable
   report topology satisfies `SELF`.

## PR/report requirements

Commit the unchanged 009-g order/pointer with the focused policy/test/docs
repair, push to PR #234, wait for all implementation-head checks, and never
merge or enable auto-merge. Publish exactly one immutable report at
`oap/reports/009-g-accept-bounded-codex-tool-output-id.md` with literal
implementation SHA, `Report publication commit: SELF`, exact ID/linkage/
metering/privacy/verifier evidence, local/GitHub checks, broad suites not run,
documentation impact, and no-merge statement. Final commit changes only that
report and has the implementation head as first parent. Verify remote report
head, then signal exact `OK`.

If the unchanged verifier exposes another mismatch or output IDs require any
authority beyond existing call/call_id ownership, report `BLOCKED`; do not
generalize the allowance.
