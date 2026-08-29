# OAP 155-p report — restore 155-o artifacts and Local handoff

Status: `COMPLETE` (zero-traffic audit continuation)

This continuation restored the exact safe artifacts omitted from immutable
155-o report `c6b33c9…`. It made no product, Local Coding, verifier, test, or
protected-service changes and sent zero traffic.

## Identity and topology

- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `c6b33c9d1527d35d987bf10f8276f30797bc892c`
- Activation/declared implementation head: `a8a2a7a8a2e84fbe7dd42658173dd6358f709444`
- Report publication commit: `SELF`
- Activation commit changed only `oap/active` and the exact 155-p order.
- Prior 155-o report parent/path and report-only topology were verified.

## Scope and checks

- Allowed repository changes: `oap/active`, the exact 155-p order, and this
  report only.
- Gateway product changes: none.
- Local Coding changes: none.
- Tests beyond artifact validation/check gates: none.
- Artifact validation: pass — exact hashes, mode/owner, strict five-line safe
  grammar, allowlisted keys/enums/count classes, and forbidden-marker scan.
- Activation-head checks: all ten pass.
- Protected health/direct/composed/full-matrix traffic: zero.
- Merge/auto-merge: none.

## Exact artifact comparisons

Each fenced block below was extracted from this report and compared
byte-for-byte, including line endings and the final newline, with its retained
mode-0600 source file before publication.

Fake artifact SHA-256:
`a75b0a627c4dcadd55cce59ab61b3d3425595f97ddfc038d70a97726d999be08`

```text
STREAM_BOUNDARY {"boundary":"direct_qwen","completed_output_empty":false,"completed_status_completed":true,"completed_usage_valid":true,"content_type_class":"sse","created_status_in_progress":true,"decision":"terminal_boundaries_completed","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown","error_event":false,"error_field_names":[],"error_type_class":"unknown","event_counts":{"other":1259,"response.completed":1,"response.created":1,"response.in_progress":1,"response.output_text.delta":386},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.in_progress"},{"count":1256,"event":"other"},{"count":386,"event":"response.output_text.delta"},{"count":3,"event":"other"},{"count":1,"event":"response.completed"}],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"pinned_155l","failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"none","normalization_status":"complete","official_client_completion":true,"ran":true,"ran_current_invocation":false,"response_completed":true,"response_id_relation":true,"terminal_completion_valid":true,"terminal_output_shape":"nonempty_array","unknown_events":true,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"local_output","completed_output_empty":true,"completed_status_completed":true,"completed_usage_valid":true,"content_type_class":"sse","created_status_in_progress":true,"decision":"terminal_boundaries_completed","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown","error_event":false,"error_field_names":[],"error_type_class":"unknown","event_counts":{"response.completed":1,"response.created":1},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.completed"}],"event_trace_overflow":false,"event_vocabulary_reviewed":true,"evidence_source":"current_155o","failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"none","normalization_status":"complete","official_client_completion":true,"ran":true,"ran_current_invocation":true,"response_completed":true,"response_id_relation":true,"terminal_completion_valid":true,"terminal_output_shape":"empty_array","unknown_events":false,"upstream_truncated":false,"valid_completion":true}
STREAM_BOUNDARY {"boundary":"gateway_output","completed_output_empty":true,"completed_status_completed":true,"completed_usage_valid":true,"content_type_class":"sse","created_status_in_progress":true,"decision":"terminal_boundaries_completed","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown","error_event":false,"error_field_names":[],"error_type_class":"unknown","event_counts":{"response.completed":1,"response.created":1},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.completed"}],"event_trace_overflow":false,"event_vocabulary_reviewed":true,"evidence_source":"current_155o","failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"none","normalization_status":"complete","official_client_completion":true,"ran":true,"ran_current_invocation":true,"response_completed":true,"response_id_relation":true,"terminal_completion_valid":true,"terminal_output_shape":"empty_array","unknown_events":false,"upstream_truncated":false,"valid_completion":true}
COMPOSED_PATH {"decision":"terminal_boundaries_completed","gateway_accounting_terminal":true,"gateway_error_code_class":"unknown","gateway_error_event":false,"gateway_error_field_names":[],"gateway_error_type_class":"unknown","gateway_to_local_request_count_class":"one","gateway_to_local_response_count_class":"one","local_downstream_closed_early":false,"local_handler_error":false,"local_rejected":false,"local_response_content_type_class":"sse","local_response_status_class":"2xx","local_terminal_completion_valid":true,"local_to_qwen_inference_call_count_class":"one","local_upstream_truncated":false,"qwen_handler_error":false,"qwen_path_rejection":false,"qwen_terminal_completion_valid":true,"qwen_upstream_content_type_class":"sse","qwen_upstream_response_count_class":"one","qwen_upstream_status_class":"2xx","qwen_upstream_truncated":false}
STREAM_DECISION "terminal_boundaries_completed"
```

Protected artifact SHA-256:
`267bc63db0da17eabd08c129f7df87f941b7165e3f037014a73e05e9937bb0d6`

```text
STREAM_BOUNDARY {"boundary":"direct_qwen","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"unknown","created_status_in_progress":false,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown","error_event":false,"error_field_names":[],"error_type_class":"unknown","event_counts":{},"event_trace":[],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"current_155o","failure_code":"unknown_failure","first_event_before_upstream_completion":false,"handler_error":false,"http_status_class":"unknown","invalid":true,"model_matches":false,"normal_close":false,"normalization_reason":"invalid_shape","normalization_status":"invalid","official_client_completion":false,"ran":true,"ran_current_invocation":true,"response_completed":false,"response_id_relation":false,"terminal_completion_valid":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"local_output","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"unknown","created_status_in_progress":false,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown","error_event":false,"error_field_names":[],"error_type_class":"unknown","event_counts":{},"event_trace":[],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"current_155o","failure_code":"unknown_failure","first_event_before_upstream_completion":false,"handler_error":false,"http_status_class":"unknown","invalid":true,"model_matches":false,"normal_close":false,"normalization_reason":"missing_structure","normalization_status":"degraded","official_client_completion":true,"ran":true,"ran_current_invocation":true,"response_completed":false,"response_id_relation":false,"terminal_completion_valid":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"gateway_output","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"sse","created_status_in_progress":true,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_code_class":"unknown","error_event":true,"error_field_names":["code","message","param","request_id","sequence_number","type"],"error_type_class":"unknown","event_counts":{"error":1,"response.created":1,"response.in_progress":1},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.in_progress"},{"count":1,"event":"error"}],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"current_155o","failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"error_event","normalization_status":"degraded","official_client_completion":true,"ran":true,"ran_current_invocation":true,"response_completed":false,"response_id_relation":false,"terminal_completion_valid":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
COMPOSED_PATH {"decision":"ambiguous_stream_evidence","gateway_accounting_terminal":false,"gateway_error_code_class":"unknown","gateway_error_event":true,"gateway_error_field_names":["code","message","param","request_id","sequence_number","type"],"gateway_error_type_class":"unknown","gateway_to_local_request_count_class":"one","gateway_to_local_response_count_class":"zero","local_downstream_closed_early":false,"local_handler_error":false,"local_rejected":false,"local_response_content_type_class":"unknown","local_response_status_class":"unknown","local_terminal_completion_valid":false,"local_to_qwen_inference_call_count_class":"one","local_upstream_truncated":false,"qwen_handler_error":false,"qwen_path_rejection":false,"qwen_terminal_completion_valid":false,"qwen_upstream_content_type_class":"sse","qwen_upstream_response_count_class":"zero","qwen_upstream_status_class":"unknown","qwen_upstream_truncated":false}
STREAM_DECISION "ambiguous_stream_evidence"
```

The protected `STREAM_DECISION` above is reproduced exactly as captured:
`ambiguous_stream_evidence`. Separately, applying the corrected enum-only
projector to the retained safe `COMPOSED_PATH` facts yields
`local_qwen_owned`: one Gateway-to-Local request, zero Local responses, one
Local-to-Qwen inference call, zero Qwen upstream responses, false Qwen terminal
completion, and a Gateway error event. This derivation is not a rewrite of the
captured decision and did not trigger traffic.

## Local Coding handoff

The safe evidence supports the following handoff and no Gateway correction:

- Gateway-to-Local request count: one;
- Gateway-to-Local response count: zero;
- Local response status/content: unknown/unknown;
- Local rejected, handler-error, truncation, and downstream-close facts: false;
- Local-to-Qwen inference count: one;
- Qwen upstream response count/status/content: zero/unknown/SSE;
- Qwen terminal completion, handler-error, truncation, and path-rejection:
  false;
- Gateway emitted an error stream and protected accounting was not terminal.

Local Coding should next instrument/correct protected Qwen stream
consumption/termination and return a tested clean head. No Local repository
mutation was made in this round.

## Cleanup and limitations

- Activation checks passed on `a8a2a7a…` before publication.
- The two retained 155-p source files were compared to the fenced blocks before
  publication and will be removed only after report-head checks.
- No runtime reference, credential source, database, container, listener,
  process, product artifact, or protected traffic was created by this round.
- The immutable 155-o report remains unchanged; its procedural omission is
  corrected here by complete byte-identical artifact blocks.
- No merge, release, acceptance, or Gateway product ownership claim follows.
