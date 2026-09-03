# Objective 155-ah — Local turn-2 boundary diagnostic and evidence closure

RESULT=FAILED

Exactly one authorized protected diagnostic was executed. There was no retry,
alternate route, direct-provider request, product correction, acceptance, or
merge.

## OAP and Git topology

- Starting report head: `855a89b3c14c54da83798914dbc8ea077b122d07`
- Activation head: `7fc1b5a7cf9b9cce8677b64c4639f7a0ea0f97c1`
- Activation parent: `855a89b3c14c54da83798914dbc8ea077b122d07`
- Frozen product implementation: `b171ada9ed3320c57186283ed4ce6ffd4389a7c3`
- Diagnostic implementation head: `d9a30b966ade118df0b8ad61bd6d4a58455d5a51`
- Report publication commit: `SELF` (this commit; parent is the diagnostic implementation head)
- PR: #291, branch `oap/155-local-coding-signed-server-module`

Only the verifier, verifier tests, replay rotation tests, governance tests,
and documentation changed. The product, migrations, Local Coding checkout,
Qwen service, schema, and dependency lock state were unchanged.

## Evidence

- Hook-free fake composed gate: passed — two Gateway-to-Local turns, one
  function lifecycle, one message lifecycle, and one function result.
- Protected diagnostic: exactly one process/request, with no retry.
- Protected preflight and post-cleanup model checks ran in the dedicated runner.
- PostgreSQL replay and context-accounting integration tests passed against a
  uniquely owned disposable database; it was removed afterward.
- Focused verifier, replay-service, governance, documentation inventory,
  Ruff, compile, and diff checks passed.
- The full unit suite excluding the unrelated hard-coded `/usr/bin/codex`
  0.148 candidate test passed. The complete invocation had one environment-only
  failure because that pre-existing test invoked host Codex 0.149.1 instead of
  its pinned 0.148.0; its test file was not modified.
- All ten required PR checks passed on
  `d9a30b966ade118df0b8ad61bd6d4a58455d5a51`.

## Protected bounded result

The Codex process failed closed after Gateway recorded one 2xx SSE structure
containing one `error` event. Local recorded one 4xx JSON response with the
fixed code class `signed_identity_field_invalid`. Qwen inference was not
reached (`inference_count=0`), so no Qwen or external-provider ownership
conclusion is made. Accounting recorded one released reservation and one
failed ledger, with zero pending state.

Safe snapshot fields, in order, were:

```text
schema=composed_boundary_snapshot_v1
outcome=other
assertion_class=other
gateway=request_count=1 response_count=1 status_classes=[2xx] content_types=[sse] sse_structures=1 handler_error=false upstream_truncated=false downstream_closed_early=false normal_close=false error_codes=[other] error_params=[other] error_stages=[]
gateway.ordinal0=present=true invalid=false valid_completion=false events={error:1} trace=[error:1] trace_overflow=false created_once=false completed_once=false response_id_relation=false created_in_progress=false completed_completed=false model_matches=false terminal_output_shape=missing completed_usage_valid=false duplicates=false unknown_events=false error_event=true normal_close=true downstream_closed_early=false handler_error=false upstream_truncated=false
local=request_count=1 response_count=1 status_classes=[4xx] content_types=[json] sse_structures=0 handler_error=false upstream_truncated=false downstream_closed_early=false normal_close=false error_codes=[signed_identity_field_invalid] error_params=[other] error_stages=[other] boundary_states={tool_policy:not_reached,observation:not_reached,constitution:not_reached,upstream:not_reached}
local.ordinals=[]
qwen=request_count=0 response_count=0 status_classes=[] content_types=[] sse_structures=0 inference_count=0 successful_count=0 compiler_count=0 handler_error=false upstream_truncated=false downstream_closed_early=false normal_close=true
qwen.ordinals=[]
accounting=reservation_finalized=0 reservation_released=1 reservation_pending=0 ledger_finalized=0 ledger_failed=1 ledger_estimated=0 ledger_pending=0 query_ok=true zero_pending=true
codex=exit_success=false provenance_class=task_local_exact_npm
```

The bounded failure code was `composed_tool_roundtrip_first_local_rejection`.
This is a Local signed-identity boundary failure; no Qwen ownership or
provider diagnosis is claimed.

## Cleanup and disposition

- `/tmp/slaif-155f-runtime.env` was removed after private mode/owner/type
  validation and verified absent.
- `/tmp/slaif-155ah-tests.4OfcQJ` was removed as the task-owned test root and
  verified absent.
- Both exact disposable PostgreSQL databases used for integration evidence
  were removed and verified absent.
- No 155-ah task root, process, Local checkout `.venv`, or task listener
  remained; both Gateway and Local worktrees were clean.
- Existing unrelated task/container state was preserved.

The protected path is not accepted or qualified by this result. No merge,
cutover, release, or production-readiness claim follows.
