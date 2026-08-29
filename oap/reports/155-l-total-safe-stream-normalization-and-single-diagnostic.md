# OAP 155-l report — total stream normalization and single diagnostic

Status: `PARTIAL/BLOCKED`

Reason: the single authorized no-retry protected differential completed with a
total safe summary, but the direct boundary contained `unknown_events=true`.
The decision is therefore `ambiguous_stream_evidence`; no ownership or
acceptance claim is made.

## Identity and topology

- PR: #291
- Repository: `ulfe-lmi/slaif-api-gateway`
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `cc2def438ee60cab92e0fb28305c89d2be7f4051`
- Activation commit: `cac5cd217219cb32f1a1bc2fcb1cfb2004c13657`
- Implementation head: `e1e2395c4d77ea9772a2471e6d5e55102484a440`
- Report publication commit: `SELF`
- Prior report parent and report-only topology were verified.
- No Gateway product paths or Local Coding files were changed.

The activation commit contains only `oap/active` and the exact strategic
155-l order. The implementation commit contains only the two unconditional
allowed verifier/test paths.

## Changed allowed paths

- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`
- `oap/active`
- `oap/orders/155-l-total-safe-stream-normalization-and-single-diagnostic.md`
- this report

Documentation impact: no product or contract documentation changed; all
implementation changes are bounded verifier/test evidence tooling.

## Implementation and fake ledger

The implementation provides:

- total, raw-free normalization for producer-valid and malformed internal
  observation shapes;
- compact ordered event runs with bounded counts, overflow facts, and terminal
  ordering preserved;
- repeated output-text deltas accepted without being treated as lifecycle
  duplicates;
- producer completion preserved across compact-trace overflow;
- fixed handler-error and upstream-truncation facts;
- strict rebuilding of already-normalized input, discarding unexpected keys;
- exclusive mode-0600 safe-output artifact creation inside a validated
  mode-0700 task root;
- explicit `ran` truth for all three boundaries and fail-closed decision codes.

Observed checks:

- focused verifier unit suite: pass;
- Ruff: pass;
- Python compilation: pass;
- `git diff --check`: pass;
- complete fake rehearsal: pass (`FAKE_REHEARSAL=OK`);
- Local Coding checkout clean and repo-local `.venv` absent after rehearsal;
- all ten PR checks on implementation head `e1e2395`: pass.

## Protected diagnostic ledger

- Differential invocations: exactly one, with no retry.
- Protected requests: one direct request; composed request not run because the
  direct normalized evidence did not contain an unambiguous valid completion.
- `direct_qwen`: ran.
- `local_output`: not run.
- `gateway_output`: not run.
- Decision: `ambiguous_stream_evidence`.
- Finite reason: `unknown_events=true` on the direct boundary.
- Ownership: none claimed.
- Full protected acceptance matrix: not run.
- Gateway correction: not authorized by evidence and not made.
- Acceptance, release, deployment, merge, and cutover: none claimed.

## Exact safe stdout artifact

The mode-0600 task artifact was retained until this report was published. Its
contents are reproduced byte-for-byte below; the artifact contains only the
allowlisted boundary schema and no raw values:

```text
STREAM_BOUNDARY {"boundary":"direct_qwen","completed_output_empty":false,"completed_status_completed":true,"completed_usage_valid":true,"content_type_class":"sse","created_status_in_progress":true,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"event_counts":{"other":1259,"response.completed":1,"response.created":1,"response.in_progress":1,"response.output_text.delta":386},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.in_progress"},{"count":1256,"event":"other"},{"count":386,"event":"response.output_text.delta"},{"count":3,"event":"other"},{"count":1,"event":"response.completed"}],"event_trace_overflow":false,"failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"none","normalization_status":"complete","official_client_completion":true,"ran":true,"response_completed":true,"response_id_relation":true,"terminal_output_shape":"nonempty_array","unknown_events":true,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"local_output","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"unknown","created_status_in_progress":false,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"event_counts":{},"event_trace":[],"event_trace_overflow":false,"failure_code":"none","first_event_before_upstream_completion":false,"handler_error":false,"http_status_class":"unknown","invalid":true,"model_matches":false,"normal_close":false,"normalization_reason":"not_run","normalization_status":"degraded","official_client_completion":false,"ran":false,"response_completed":false,"response_id_relation":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"gateway_output","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"unknown","created_status_in_progress":false,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"event_counts":{},"event_trace":[],"event_trace_overflow":false,"failure_code":"none","first_event_before_upstream_completion":false,"handler_error":false,"http_status_class":"unknown","invalid":true,"model_matches":false,"normal_close":false,"normalization_reason":"not_run","normalization_status":"degraded","official_client_completion":false,"ran":false,"response_completed":false,"response_id_relation":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
STREAM_DECISION "ambiguous_stream_evidence"
```

## Restored 155-k audit corrections

- The mode-0600 task-owned credential-source file temporarily persisted the
  protected credential declaration during 155-k.
- The credential value was never rendered, logged, hashed, or committed.
- The credential source and runtime reference were removed after 155-k report
  publication.
- Eleven mode-0700 `slaif-155k.*` test roots remained after interrupted local
  commands despite the 155-k cleanup claim; strategic cleanup validated and
  removed those exact roots.
- These corrections affect audit accuracy, not the protected ownership result.
- The immutable 155-k report was not rewritten.

## Final cleanup and privacy ledger

- The exact 155-l safe-output artifact and task root were removed after report
  publication and verified absent.
- The exact activation runtime reference and task-owned credential source were
  removed after report publication and verified absent.
- No task process, relay, listener, container, generated bytecode, or Local
  `.venv` remains.
- Gateway and Local tracked/ignored state is clean.
- No raw IDs, response fields/values, bodies/chunks, model text, prompts,
  endpoints, arbitrary paths, headers, credentials, identity/signature/nonce,
  or runtime-reference fields appear in the report.
- No merge or auto-merge was performed.

## Required continuation

No further protected request is authorized by this report. Any future
continuation must independently decide whether a new diagnostic is warranted
and must preserve this report unchanged.
