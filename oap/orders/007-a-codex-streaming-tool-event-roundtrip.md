# OAP Work Order — 007-a

## Objective

Implement the bounded Codex 0.147.0 client-tool act/observe protocol: admit the
exact required Responses tool/output/reasoning stream events under a third
explicit key/route gate, validate and forward them without buffering/content
persistence, accept the matching client tool-call replay/output continuation,
and prove a side-effect-free Codex loop against an isolated mock.

The gateway never executes tools. This is not hosted-tool/MCP/WebSocket/full
production compatibility.

## GitHub state

- Objective/round `007-a`; `CREATE_NEW_PR`.
- Repository/base `ulfe-lmi/slaif-api-gateway` / `main`.
- Starting main `e93fe2ff753392f26c84d468e6b9d18e8afc7365`.
- Objectives 005/006 and PRs #230/#231 merged.
- Branch `oap/007-codex-streaming-tool-event-roundtrip`.
- Title `[OAP 007] Support Codex client tool stream round trips`.
- Unrelated expected open PR: Dependabot #224 only.

Create one PR; continuations amend it.

## Pinned event contract

Use Codex release/source `rust-v0.147.0` and the immutable fixture. The pinned
SSE parser recognizes these relevant event families:

- `response.created`, `response.in_progress`;
- `response.output_item.added`, `response.output_item.done`;
- `response.function_call_arguments.delta`;
- `response.custom_tool_call_input.delta`;
- `response.reasoning_summary_part.added`;
- `response.reasoning_summary_text.delta` and `.done`;
- `response.reasoning_text.delta`;
- existing `response.output_text.delta`;
- terminal `response.completed`;
- provider failure/incomplete/error paths handled as safe failure, not raw
  arbitrary event pass-through.

Only event shapes required by the pinned client-owned function/custom taxonomy
are in scope. Unknown event types/fields/item types remain fail closed.

## Governing/start requirements

Read full AGENTS/OAP governance, merged 004–006 contracts/code/tests, streaming
live-burn/accounting/forwarding/security docs, provider SSE parser, pinned Codex
SSE/request/ResponseItem source, and fixture. Verify GitHub/main, PR #231 merge,
no objective-007 PR, clean tree, exact fixture SHA.

The strategic model atomically published this order and `oap/active=007-a`;
commit exact bytes and branch from current `origin/main`. Preserve user auth,
secrets, generated artifacts, and unrelated state.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/providers/streaming.py
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/responses_streaming_live_burn.py
docs/accounting.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/007-a-codex-streaming-tool-event-roundtrip.md
scripts/verify_codex_tool_roundtrip.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_key_template_service.py
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_route_capabilities.py
tests/unit/test_responses_streaming_live_burn.py
```

Final report-only commit adds only
`oap/reports/007-a-codex-streaming-tool-event-roundtrip.md`.

Do not edit fixture/capture script, API schema, DB/migrations/settings,
dependencies, CI, deployment, provider routing/adapters beyond bounded SSE
parsing if actually required, README, or prior history.

## Third capability gate

Add `codex_streaming_tool_events`, default false, to safe explicit key-template
and known route capabilities. Never default/calibration enable it.

A streaming Codex client-tool request requires all three capabilities on both
key and route:

```text
codex_request_envelope
codex_client_tools
codex_streaming_tool_events
```

No capability implies another. Deny missing/malformed key grants before route/
DB; deny route gaps before Redis/pricing/quota/provider. Non-Codex text streams
retain existing behavior.

## Exact stream-event validation

Replace the simple global event check with an explicit validator that receives
whether the request has the fully gated Codex event profile.

- Existing text-only events remain allowed exactly as before.
- Codex-only events above require all gates.
- Validate event `type` and bounded required scalar/index/id/call-id fields.
- For `output_item.added/done`, allow only pinned client-local
  `function_call`, `custom_tool_call`, ordinary assistant message, and bounded
  reasoning item shapes actually required by Codex. Reject hosted/MCP/shell/
  computer/search/provider-authority item types.
- Function/custom names must resolve to the declaration taxonomy admitted in
  the request; call/item IDs are bounded safe identifiers.
- Tool argument/input/reasoning/text delta values must be strings under bounded
  per-event and cumulative limits. Forward bytes unchanged only after shape
  validation.
- No arbitrary field pass-through if it creates authority or unbounded/private
  content. Preserve provider protocol fields required by the client while
  rejecting unknown authority markers.
- `response.completed` remains held until accounting finalization and provider
  final usage remains authoritative.
- `response.failed`, incomplete, malformed JSON/SSE, missing completion/usage,
  disconnect, and provider errors use existing safe error/accounting paths and
  never forward raw unsafe provider messages.

Do not buffer a full stream. Validate/forward frame-by-frame.

## Live-burn and accounting

Extend the provisional stream monitor to observe safely measurable visible
deltas from:

- output text;
- function-call arguments;
- custom-tool input;
- reasoning summary text (and reasoning text only if forwarded by the pinned
  contract).

Count/discard delta content immediately. Withhold the threshold-crossing event
and emit the existing safe typed quota error. Avoid double counting final
`output_item.done` content after deltas. Provider final usage/cost wins when
available. Missing usage, provider error after output, and disconnect after
output finalize as estimated interruption, never zero-cost success.

Safe ledger/metric evidence may contain event category, counts, estimated
tokens/bytes, stop reason, and call type—not arguments, tool input/output,
reasoning, item content, IDs, schema, or grammar.

## Continuation request policy

Under all three gates and exact declared taxonomy, accept bounded replay/output
items required for the client follow-up:

- `function_call` with exact approved name, call id, bounded string arguments,
  optional safe item id/status only where pinned;
- `custom_tool_call` for exact `functions.exec`, call id, bounded input, optional
  safe item id/status only where pinned;
- existing string-only `function_call_output` and `custom_tool_call_output`,
  now tied to an approved call/name/type relationship for this profile.

Reconstruct/deep-copy exact approved fields. Reject orphan/mismatched/duplicate
call IDs, unknown names/types, provider authority, arbitrary tool history,
non-string or oversized arguments/results, and tool output without the three
gates. Count replay/arguments/results conservatively as input material; never
store/log/audit/export content.

No gateway-side tool execution or provider-hosted authority.

## Side-effect-free actual Codex mock

Create `scripts/verify_codex_tool_roundtrip.py`, manually invoked only and never
called by pytest/CI/application/HPC. Reuse/import safe isolation/version/model/
profile/header/body limits from the capture tooling without changing the
immutable fixture.

The tool must:

1. require exact `/usr/bin/codex` 0.147.0 and isolated temporary home/workdir;
2. bind numeric `127.0.0.1`, dummy API key, no user config/auth/plugins/MCP,
   no real provider/network target;
3. capture the first request only in memory;
4. return a fixed custom `functions.exec` call whose only input is the
   side-effect-free Code Mode expression `text("SAFE_TOOL_RESULT")`—no shell,
   filesystem, network, nested tool, subprocess, or state mutation;
5. capture the second continuation request and prove it contains the matching
   custom call/output structure, without persisting raw content;
6. return a fixed final assistant text/completion sequence and prove Codex exits
   successfully;
7. print only a safe status/count/type summary, never prompts, arguments,
   results, IDs, headers, bodies, or subprocess logs.

If the installed client cannot execute this exact harmless custom tool without
broader authority, stop/report a blocker; do not substitute shell execution.

Normal unit tests mock subprocess/socket and test pure event/request validation;
they must never launch Codex or bind a listener.

This mock proves pinned client parser/executor/continuation shape composition.
Objective 011 still owns actual Codex-through-gateway E2E.

## Tests

Create `tests/unit/test_responses_codex_streaming_tools.py` and cover:

1. every key/route capability combination and pre-side-effect ordering;
2. exact allowed event table/required fields and malformed/unknown/hosted/
   authority negatives;
3. function/custom added/delta/done sequences and Codex-visible raw SSE order;
4. no full buffering and completed-event hold/finalization order;
5. replay + matching output continuation positive cases and orphan/duplicate/
   mismatch/unknown/size negatives;
6. provider error, failed/incomplete, missing usage, disconnect before/after
   output, malformed SSE/JSON, and unsupported event accounting;
7. live-burn across text/function/custom/reasoning deltas, threshold event
   withholding, no double count, provider usage authority;
8. redaction/no-storage canaries across logs/errors/ledger/metrics/audit/
   responses; safe categories/counts only;
9. normal text streams and current local-tool nonstreaming behavior unchanged;
10. templates explicitly propagate the third cap, never default it;
11. immutable fixture/capture baseline unchanged;
12. pure mock-harness tests prove no side effects/import execution and exact
    two-request safe summary.

Mock providers only. No real provider/tool service.

## Documentation

Update AGENTS and Codex/Responses/forwarding/accounting/security/compatibility
contracts with exact third gate, event/replay allowlists, client execution
ownership, live-burn/accounting/error/privacy behavior, harmless mock evidence,
and remaining state/reasoning/compaction/full-E2E gaps. Do not claim hosted tool
or production compatibility; README remains unchanged.

## Non-goals/test economy

No hosted tools/MCP/connectors, gateway shell/patch execution, real external
tool, WebSocket/background, broad state/reasoning replay (008), full CLI gateway
E2E (011), schema/settings/dependency/CI/fixture change, or production action.

Run only:

```bash
.venv/bin/python scripts/verify_codex_tool_roundtrip.py --codex-binary /usr/bin/codex --expected-cli-version 0.147.0 --model gpt-5.6-sol --profile api-key-responses-baseline
.venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_tools.py -q
.venv/bin/python -m pytest tests/unit/test_responses_codex_client_tools.py -q
.venv/bin/python -m pytest tests/unit/test_responses_request_policy.py -q
.venv/bin/python -m pytest tests/unit/test_responses_route_capabilities.py -q
.venv/bin/python -m pytest tests/unit/test_responses_streaming_live_burn.py -q
.venv/bin/python -m pytest tests/unit/test_key_template_service.py -q
.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q
.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py -q
.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q
.venv/bin/ruff check app/slaif_gateway/providers/streaming.py app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_route_capabilities.py app/slaif_gateway/services/responses_streaming_live_burn.py app/slaif_gateway/services/key_template_service.py scripts/verify_codex_tool_roundtrip.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py tests/unit/test_responses_streaming_live_burn.py tests/unit/test_key_template_service.py tests/unit/test_codex_protocol_capture.py
git diff --check
sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
git status --short
```

No full local suite/integration/E2E/browser/Docker/HPC. The one live mock is
loopback/dummy/side-effect-free. GitHub CI supplies broad evidence.

## Acceptance/PR/report gate

Success requires exact three-gated event/replay behavior, safe client execution
ownership, actual harmless two-request Codex mock, streaming/no-buffering,
honest accounting/failures, privacy, unchanged fixture, focused tests, and all
final checks.

Commit unchanged order/pointer, create one non-draft PR on required branch/title,
inspect checks, never merge/auto-merge. Publish one immutable report at
`oap/reports/007-a-codex-streaming-tool-event-roundtrip.md` with literal
implementation SHA, `SELF`, exact event/replay/live-mock/test/accounting/privacy
evidence, broad suites not run, and docs impact. Final commit only report with
implementation parent; push/verify/signal exact `OK`.

If safe harmless execution, event validation, continuation linkage, or
accounting cannot be proven, report a blocker rather than broaden. Do not merge.
