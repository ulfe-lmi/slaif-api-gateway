# Objective 155-ai — Signed identity grammar interoperability and acceptance

RESULT=FAILED

This report records one completed 155-ai qualification attempt. No protected
retry, alternate route, direct-provider request, Local/Qwen change, merge,
cutover, or release action was performed.

## Topology

- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting report head: `3999a524a7306dfd2ac3e6477600b5549d3045ea`
- Activation head: `0f8ef83832fee90efe9f780894fb8d1d54056eeb`
- Activation parent: `3999a524a7306dfd2ac3e6477600b5549d3045ea`
- Terminal implementation head: `3cce1a7612fc9919adf26df9952baabaf703c348`
- PR: #291, branch `oap/155-local-coding-signed-server-module`
- Report publication commit: `SELF` (parent is the terminal implementation head)
- Report path: `oap/reports/155-ai-signed-identity-grammar-interoperability-and-acceptance.md`

The implementation changed only the allowed Local Coding identity/contract,
verifier, tests, governance, and documentation paths. No migration, schema,
dependency lock, Local Coding checkout, Qwen service, or unrelated path was
changed. The prior order/report bytes remain unchanged.

## Deterministic and synthetic evidence

- The old unprefixed producer was reproduced with two fixed synthetic vectors:
  one legacy encoding began with `-`, and one began with `_`; both violate the
  pinned Local-v1 leading-character grammar.
- The corrected producer uses an unconditional `h` prefix followed by the
  complete unpadded base64url encoding of the 32-byte HMAC digest. Fixed
  stability, injectivity, full-digest decode, route grammar, signer
  fail-closed, tamper, and replay regressions passed.
- The actual unchanged Local verifier matrix passed for eight synthetic rows,
  including body tamper, signature tamper, and nonce replay rejection. No raw
  identity, nonce, signature, owner/key UUID, or digest was emitted.
- Hook-free fake composed roundtrip passed with two turns, one function
  lifecycle, one message lifecycle, and one function result.
- Fake non-prefixed/ID-less roundtrip passed.
- Fake provider-failure and validator-failure paths returned their required
  bounded nonzero results with terminal accounting evidence.
- Fresh PostgreSQL replay and context-accounting integration tests passed
  without skip; the disposable database was removed afterward.
- Focused tests, documentation inventory, Ruff, compile, and source/scope
  checks passed. All ten PR checks passed on the terminal implementation head.
- The broader local unit invocation had one unrelated environment failure from
  the pre-existing hard-coded host Codex candidate test (`/usr/bin/codex` was
  not the pinned version). The test file was not modified; the host binary was
  not substituted.

The prior 155-ag evidence that real turn 2 was forwarded through Gateway to
Local remains distinct and is not superseded. The 155-ah diagnostic separately
failed on its first Local turn. This 155-ai request tested the corrected
producer and completed both turns.

## Single protected qualification

The one authorized task-local Codex 0.149.0 process reached the unchanged
Gateway, Local Coding, and protected Qwen path. Both Local-bound requests had
all signed identity predicates true: exact required-header cardinality,
service Bearer equality, principal/session/repository/route grammar, exact
body participation, signature verification, route match, method/path/query,
version, timestamp, nonce, and no extra internal headers.

Both Local and Qwen emitted valid terminal-completion structures and Qwen
recorded two successful inference turns. PostgreSQL accounting finalized two
reservations and two ledgers with zero pending state.

The verifier nevertheless rejected the Gateway-facing SSE structure as
`composed_tool_roundtrip_gateway_sse_invalid`. The bounded structure contained
reviewed lifecycle events plus 34 and 24 events projected as `other`; its
`unknown_events` predicate was true. The safe closed classification is
`producer_boundaries_valid_verifier_expectation_wrong`, not Local/Qwen/provider
ownership. No product correction or second protected request is authorized by
this result.

### Complete safe boundary snapshot

```text
schema=composed_boundary_snapshot_v1
outcome=producer_boundaries_valid_verifier_expectation_wrong
assertion_class=gateway_sse_invalid
gateway=request_count=2 response_count=2 response_status_classes=[2xx,2xx] content_type_classes=[sse,sse] sse_structure_count=2 handler_error=false upstream_truncated=false downstream_closed_early=false normal_close=false error_code_classes=[other,other] error_param_classes=[other,other] error_stage_classes=[] signed_identity_facts=[]
gateway.ordinal0=present=true invalid=false valid_completion=true events={other:34,response.completed:1,response.created:1,response.function_call_arguments.delta:9,response.function_call_arguments.done:1,response.in_progress:1,response.output_item.added:2,response.output_item.done:2} trace=[response.created:1,response.in_progress:1,response.output_item.added:1,other:34,response.output_item.done:1,response.output_item.added:1,response.function_call_arguments.delta:9,response.function_call_arguments.done:1,response.output_item.done:1,response.completed:1] trace_overflow=false created_once=true completed_once=true response_id_relation=true created_in_progress=true completed_completed=true model_matches=true terminal_output_shape=nonempty_array completed_usage_valid=true duplicates=false unknown_events=true error_event=false normal_close=true downstream_closed_early=false handler_error=false upstream_truncated=false
gateway.ordinal1=present=true invalid=false valid_completion=true events={other:24,response.completed:1,response.content_part.added:1,response.content_part.done:1,response.created:1,response.in_progress:1,response.output_item.added:2,response.output_item.done:2,response.output_text.delta:33,response.output_text.done:1} trace=[response.created:1,response.in_progress:1,response.output_item.added:1,other:24,response.output_item.done:1,response.output_item.added:1,response.content_part.added:1,response.output_text.delta:33,response.output_text.done:1,response.content_part.done:1,response.output_item.done:1,response.completed:1] trace_overflow=false created_once=true completed_once=true response_id_relation=true created_in_progress=true completed_completed=true model_matches=true terminal_output_shape=nonempty_array completed_usage_valid=true duplicates=false unknown_events=true error_event=false normal_close=true downstream_closed_early=false handler_error=false upstream_truncated=false valid_completion=true
local=request_count=2 response_count=2 response_status_classes=[2xx,2xx] content_type_classes=[sse,sse] sse_structure_count=2 handler_error=false upstream_truncated=false downstream_closed_early=false normal_close=false error_code_classes=[none,none] error_param_classes=[other,other] error_stage_classes=[other,other] boundary_states={tool_policy:transformed,observation:not_reached,constitution:not_reached,upstream:succeeded}
local.signed_identity_facts=[{service_bearer_equal:true,required_header_cardinality_class:exact,principal_grammar_valid:true,session_grammar_valid:true,repository_grammar_valid:true,route_grammar_valid:true,canonical_bytes_reconstructed:true,raw_body_canonical_participates:true,signature_verifies:true,route_matches:true,method_path_query_valid:true,version_shape_valid:true,timestamp_shape_valid:true,nonce_shape_valid:true,no_extra_internal_headers:true,signed_identity_class:verified},{service_bearer_equal:true,required_header_cardinality_class:exact,principal_grammar_valid:true,session_grammar_valid:true,repository_grammar_valid:true,route_grammar_valid:true,canonical_bytes_reconstructed:true,raw_body_canonical_participates:true,signature_verifies:true,route_matches:true,method_path_query_valid:true,version_shape_valid:true,timestamp_shape_valid:true,nonce_shape_valid:true,no_extra_internal_headers:true,signed_identity_class:verified}]
qwen=request_count=2 response_count=2 response_status_classes=[2xx,2xx] content_type_classes=[sse,sse] sse_structure_count=2 inference_count=2 successful_count=2 compiler_count=0 handler_error=false upstream_truncated=false downstream_closed_early=false normal_close=true error_code_classes=[] error_param_classes=[] error_stage_classes=[]
qwen.ordinal0=present=true invalid=false valid_completion=true events={other:34,response.completed:1,response.created:1,response.function_call_arguments.delta:9,response.function_call_arguments.done:1,response.in_progress:1,response.output_item.added:2,response.output_item.done:2} trace=[response.created:1,response.in_progress:1,response.output_item.added:1,other:34,response.output_item.done:1,response.output_item.added:1,response.function_call_arguments.delta:9,response.function_call_arguments.done:1,response.output_item.done:1,response.completed:1] trace_overflow=false created_once=true completed_once=true response_id_relation=true created_in_progress=true completed_completed=true model_matches=true terminal_output_shape=nonempty_array completed_usage_valid=true duplicates=false unknown_events=true error_event=false normal_close=true downstream_closed_early=false handler_error=false upstream_truncated=false
qwen.ordinal1=present=true invalid=false valid_completion=true events={other:24,response.completed:1,response.content_part.added:1,response.content_part.done:1,response.created:1,response.in_progress:1,response.output_item.added:2,response.output_item.done:2,response.output_text.delta:33,response.output_text.done:1} trace=[response.created:1,response.in_progress:1,response.output_item.added:1,other:24,response.output_item.done:1,response.output_item.added:1,response.content_part.added:1,response.output_text.delta:33,response.output_text.done:1,response.content_part.done:1,response.output_item.done:1,response.completed:1] trace_overflow=false created_once=true completed_once=true response_id_relation=true created_in_progress=true completed_completed=true model_matches=true terminal_output_shape=nonempty_array completed_usage_valid=true duplicates=false unknown_events=true error_event=false normal_close=true downstream_closed_early=false handler_error=false upstream_truncated=false
accounting=reservation_finalized=2 reservation_released=0 reservation_pending=0 ledger_finalized=2 ledger_failed=0 ledger_estimated=0 ledger_pending=0 query_ok=true zero_pending=true
codex=exit_success=true provenance_class=task_local_exact_npm
failure_code=composed_tool_roundtrip_gateway_sse_invalid
```

The snapshot intentionally contains no raw values, IDs, digests, prompt text,
headers, endpoint, credential, or exception text.

## Cleanup and disposition

- The mode-0600 runtime reference was privately validated, then unlinked and
  verified absent.
- Every exact 155-ai temporary root and Codex installation was removed.
- The exact 155-ai PostgreSQL database/container namespace was absent after
  cleanup.
- Local ignored bytecode state and `.venv` were absent; Local and Gateway
  worktrees were clean.
- No protected process or listener remained, and unrelated existing container
  state was preserved.

The signed-identity producer correction is implemented and tested, but this
single protected run does not establish full Objective-155 acceptance or make
PR #291 a merge candidate. No merge, release, cutover, or production claim
follows.
