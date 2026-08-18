# OAP Work Order — 009-f

## Objective

Resolve the exact pinned-client privacy mismatch reported by 009-e: accept and
drop bounded `internal_chat_message_metadata_passthrough` only on supported
fully gated Codex history item types, before canonical model input, forwarding,
metering, HMAC, logs, audits, or persistence. Preserve ordinary/unsupported
shape rejection and make the unchanged exact Codex 0.147.0 compact verifier
complete on existing PR #234.

## GitHub state

- Numeric objective `009`, round `009-f`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #234:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`.
- Branch `oap/009-codex-context-output-cache-compaction-accounting`; base
  `main`.
- Starting remote/report head:
  `973e8b9a20e3c1ad49c5efc66a00a9e900ddf66c`.
- 009-e implementation head:
  `32bded4c3881d1a4e70796dd6550c2ac81c1f9f7`.
- 009-e status: `BLOCKED` only because the unchanged verifier next hit safe
  code `responses_input_item_invalid` at
  `input[2].internal_chat_message_metadata_passthrough`. Its focused tests and
  all ten implementation-head checks passed.

Amend PR #234 only. Never create another objective-009 PR.

## Pinned-source and privacy finding

Pinned Codex source 0.147.0 preserves per-item
`internal_chat_message_metadata_passthrough` when the configured provider name
is exactly `OpenAI`, and clears it for non-OpenAI providers. The same version
enables remote V1/V2 compaction for configured OpenAI/Azure providers but marks
ordinary custom provider names as remote-compaction unsupported. Therefore the
qualified SLAIF profile must use the OpenAI provider identity to induce V1
compaction, and the exact compact history can contain this internal field.

Pinned source describes this as internal/warehouse-only metadata and bounds
attempted-tool metadata around 32 KiB. It can contain turn identity and executed
tool-call details/arguments. SLAIF neither needs nor permits that content in
provider input or local evidence.

Strategic decision:

- under the complete prior Codex key gates only, accept the exact field on
  supported history item types as a JSON object or null, with a fixed 32,768-
  byte canonical JSON cap;
- validate the type/size without interpreting nested contents, then delete it
  before item-specific validation and every downstream surface;
- it contributes zero model-input tokens because it is never forwarded;
- it must not enter the canonical/effective body, provider body, replay
  candidate, HMAC, accounting metadata, logs, metrics, audits, exports, errors,
  verifier output, or reports.

Supported item types for this drop are only:

```text
message (including omitted type)
reasoning
function_call
function_call_output
custom_tool_call
custom_tool_call_output
compaction
```

Do not allow/drop it on `additional_tools`, hosted/provider tools, unknown item
types, ordinary non-Codex requests, compact requests without the fifth gate, or
any other endpoint. Those retain current unknown-field rejection.

## Required work

1. Reconcile canonical GitHub, PR #234, all immutable 009 rounds, applicable
   AGENTS/OAP instructions, pinned source/tag/binary, and current privacy
   contracts/tests.
2. Commit the strategic `oap/active=009-f` pointer and this order unchanged.
3. Add one exact field constant and fixed 32,768-byte cap. In the Codex input
   array validation path, copy each item, validate/drop the field only when the
   complete request policy allows the applicable Codex history shape and the
   item type is in the exact list above, then pass the copy to existing strict
   validation. Never mutate the caller's input mapping in place.
4. Accept null or a JSON mapping only. Reject strings/lists/scalars/non-JSON,
   oversize values, and secret-like malformed values with a fixed safe error and
   exact parameter but no value/canary echo. Do not recursively inspect or
   whitelist nested authority; the entire object is discarded.
5. Prove ordinary and unsupported item paths still reject the field. Preserve
   all existing message/tool/reasoning/compaction fields, linkage, HMAC, byte
   caps, and provider-state denials.
6. Add focused privacy tests proving:
   - each supported gated item type drops the field and otherwise canonicalizes;
   - the field is absent from effective/upstream reconstruction, replay
     candidates, metering field lists, safe errors/evidence, and input object
     remains unmodified;
   - exact 32,768-byte canonical object passes and +1 fails (account for JSON
     syntax rather than raw string length);
   - null passes/drops; non-object/non-null fails;
   - ordinary, missing-gate, `additional_tools`, hosted, and unknown item types
     reject rather than drop;
   - no raw executed-tool argument/private canary is exposed.
7. Rerun the unchanged exact 009 verifier once. It must emit `RESULT=OK`,
   `REQUEST_COUNT=3`, `GATEWAY_COMPACT_POLICY_ACCEPTED=true`, and all prior fixed
   safety booleans without raw payload persistence/output.
8. Update only affected privacy/compatibility/accounting/forwarding contracts.

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
oap/orders/009-f-drop-bounded-internal-chat-metadata.md
tests/unit/test_responses_codex_compaction.py
tests/unit/test_responses_codex_multiturn_replay.py
```

Final report-only commit adds only:

```text
oap/reports/009-f-drop-bounded-internal-chat-metadata.md
```

The verifier must remain unchanged. Do not edit schemas/models/migrations,
settings/config, gateway/accounting/replay/pricing code outside the policy file,
dependencies, fixtures, prior OAP history, CI, deployment, README, or unrelated
paths.

## Focused verification and test economy

Run only:

- `tests/unit/test_responses_codex_compaction.py` and
  `tests/unit/test_responses_codex_multiturn_replay.py`;
- focused OAP/documentation contract tests;
- scoped Ruff/compile, `git diff --check`, exact path/topology, fixture digest;
- one final unchanged exact pinned Codex context/compaction verifier run.

Do not run full unit, integration, PostgreSQL, E2E, browser, Docker/Compose, or
HPC suites locally. GitHub CI owns broad coverage. Never call a real provider or
side-effecting external tool.

Report literal commands/counts, exact safe verifier keys, every broad suite NOT
RUN, and any failed development attempt honestly.

## Acceptance criteria

1. The bounded internal field is dropped only for exact supported fully gated
   Codex history; it is absent from every canonical/downstream/evidence surface.
2. Type/size/privacy negatives and exact cap edges fail safely; ordinary,
   missing-gate, additional-tools, hosted, and unknown paths remain denied.
3. Existing tool/reasoning/compaction validation, ownership, HMAC, accounting,
   route, and metering behavior is unchanged aside from zero-count dropped
   metadata.
4. The unchanged exact Codex 0.147.0 verifier completes its three-request V1
   compact loop and reports gateway policy accepted with no raw persistence/
   output or real provider call.
5. Focused tests/docs/quality/path/fixture checks and every report-head GitHub
   check pass; no broad local suite runs.
6. One existing PR only; coding agent never merges/enables auto-merge; immutable
   report topology satisfies `SELF`.

## PR/report requirements

Commit the unchanged 009-f order/pointer with the focused policy/test/docs
repair, push to PR #234, wait for all implementation-head checks, and never
merge or enable auto-merge. Publish exactly one immutable report at
`oap/reports/009-f-drop-bounded-internal-chat-metadata.md` with literal
implementation SHA, `Report publication commit: SELF`, exact drop/type/size/
privacy/verifier evidence, local/GitHub checks, broad suites not run,
documentation impact, and no-merge statement. Final commit changes only that
report and has the implementation head as first parent. Verify remote report
head, then signal exact `OK`.

If the unchanged verifier exposes another mismatch or the field cannot be
dropped before every downstream surface, report `BLOCKED`; do not forward or
persist it.
