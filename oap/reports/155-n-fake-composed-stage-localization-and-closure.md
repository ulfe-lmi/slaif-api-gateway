# OAP 155-n report — fake composed stage localization and closure

Status: `PARTIAL/BLOCKED`

Reason: the corrected fake composed-only path passed all required safe gates,
but the single authorized protected composed-only request produced ambiguous
boundary evidence: current Local had `missing_structure` and current Gateway
had `error_event`. No direct request, Gateway product correction, or full
acceptance matrix was run.

## Identity and topology

- PR: #291
- Repository: `ulfe-lmi/slaif-api-gateway`
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `382549cb0e31b22a3464c6622b0f21e48d115944`
- Activation commit: `5bf6111ec3584d94db1f2645b4c0d0ddbc8948a5`
- Implementation head: `bd0cfd976bfd570561d7943be2d62686d4d48972`
- Report publication commit: `SELF`
- The activation commit contains only `oap/active` and the exact 155-n order;
  the order bytes matched the strategic source.
- The prior 155-m report parent/path and ancestry were verified.

## Changed allowed paths

The implementation commits changed only:

- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`

This report is the only 155-n report path. No Gateway product path or Local
Coding repository file was changed.

Documentation impact: no product or contract documentation changed; the
implementation is bounded verifier/test evidence tooling.

## Implementation and fake ledger

- Added the 155-n `--composed-only-fake` path using the same composed
  PostgreSQL/Gateway/Local/relay/client composition function as protected mode.
- Added finite composed stage tracking with fixed
  `unexpected_composed_<stage>` errors and primary-error preservation across
  cleanup.
- Added explicit 155-m report topology anchoring and positive path coverage.
- Preserved pinned direct provenance as `evidence_source=pinned_155l` and
  `ran_current_invocation=false`; current fake/protected boundaries use
  `evidence_source=current_155n` and `ran_current_invocation=true`.
- No direct diagnostic function is called by composed-only fake mode.

Observed fake checks:

- Focused verifier unit suite: pass.
- Ruff: pass.
- Python compilation: pass.
- `git diff --check`: pass.
- All ten checks on implementation head `bd0cfd9`: pass.
- Complete legacy fake rehearsal: pass.
- Exact composed-only fake rehearsal: pass.
- Fake safe artifact equals stdout byte-for-byte; stderr empty; artifact mode
  0600 under a mode-0700 task root.
- Fake decision: `terminal_boundaries_completed`.
- Fake artifact SHA-256:
  `a50471ab1c404a61bd687b66c25961dc43cf330082e99e170cb838e08ae71489`.

The initial fake reproductions were safely classified and corrected in order:
`gateway_report_not_report_only` (stale 155-l path),
`github_pr_state_mismatch` (checks pending),
`unexpected_composed_local_start` (launcher PATH omitted `uv`), and
`unknown_composition_stage` (two used stages were missing from the allowlist).
No protected request occurred during those reproductions.

## Protected ledger

- Protected health/model preflight: pass.
- Direct protected diagnostic: not run (`0` requests).
- Composed-only protected invocations: exactly one; no retry.
- Full protected Codex acceptance matrix: not run.
- Protected safe artifact equals stdout byte-for-byte; stderr empty; artifact
  mode 0600 under a mode-0700 task root.
- Protected artifact SHA-256:
  `039172330e2e3be9c476560fc92d231e53256a8054b0b057f28f1efe2a1979d0`.
- Protected decision: `ambiguous_stream_evidence`.

Boundary facts from the protected safe artifact:

| Boundary | Source | Current run | Normalization | Reason | Terminal valid | Vocabulary reviewed |
| --- | --- | --- | --- | --- | --- | --- |
| direct_qwen | pinned_155l | false | complete | none | true | false |
| local_output | current_155n | true | degraded | missing_structure | false | false |
| gateway_output | current_155n | true | degraded | error_event | false | false |

The protected artifact’s exact safe output was:

```text
STREAM_BOUNDARY {"boundary":"direct_qwen","completed_output_empty":false,"completed_status_completed":true,"completed_usage_valid":true,"content_type_class":"sse","created_status_in_progress":true,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_event":false,"event_counts":{"other":1259,"response.completed":1,"response.created":1,"response.in_progress":1,"response.output_text.delta":386},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.in_progress"},{"count":1256,"event":"other"},{"count":386,"event":"response.output_text.delta"},{"count":3,"event":"other"},{"count":1,"event":"response.completed"}],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"pinned_155l","failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"none","normalization_status":"complete","official_client_completion":true,"ran":true,"ran_current_invocation":false,"response_completed":true,"response_id_relation":true,"terminal_completion_valid":true,"terminal_output_shape":"nonempty_array","unknown_events":true,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"local_output","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"unknown","created_status_in_progress":false,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_event":false,"event_counts":{},"event_trace":[],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"current_155n","failure_code":"unknown_failure","first_event_before_upstream_completion":false,"handler_error":false,"http_status_class":"unknown","invalid":true,"model_matches":false,"normal_close":false,"normalization_reason":"missing_structure","normalization_status":"degraded","official_client_completion":true,"ran":true,"ran_current_invocation":true,"response_completed":false,"response_id_relation":false,"terminal_completion_valid":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
STREAM_BOUNDARY {"boundary":"gateway_output","completed_output_empty":false,"completed_status_completed":false,"completed_usage_valid":false,"content_type_class":"sse","created_status_in_progress":true,"decision":"ambiguous_stream_evidence","done_sentinel":false,"downstream_closed_early":false,"duplicates":false,"error_event":true,"event_counts":{"error":1,"response.created":1,"response.in_progress":1},"event_trace":[{"count":1,"event":"response.created"},{"count":1,"event":"response.in_progress"},{"count":1,"event":"error"}],"event_trace_overflow":false,"event_vocabulary_reviewed":false,"evidence_source":"current_155n","failure_code":"none","first_event_before_upstream_completion":true,"handler_error":false,"http_status_class":"2xx","invalid":false,"model_matches":true,"normal_close":true,"normalization_reason":"error_event","normalization_status":"degraded","official_client_completion":true,"ran":true,"ran_current_invocation":true,"response_completed":false,"response_id_relation":false,"terminal_completion_valid":false,"terminal_output_shape":"missing","unknown_events":false,"upstream_truncated":false,"valid_completion":false}
STREAM_DECISION "ambiguous_stream_evidence"
```

The safe evidence does not establish whether the protected failure is Local-,
Gateway-, or upstream-owned. No product correction was authorized by this
ambiguous result.

## Privacy, accounting, and cleanup ledger

- The composed path used no direct diagnostic and no retry.
- No raw request body, response body, headers, credentials, prompts,
  completions, opaque identities, private endpoint, or runtime-reference field
  appears in this report or the safe artifacts.
- Fake disposable accounting finalized successfully; no protected acceptance
  accounting claim is made because the protected boundary result was
  ambiguous.
- The fake and legacy task roots were removed after their runs; the protected
  task root and safe artifact were retained through report publication.
- Runtime reference and task credential source were not rendered and remain
  scheduled for exact post-report removal.
- No product acceptance, release, deployment, cutover, merge, or auto-merge was
  performed.

## Required continuation

This is a truthful partial report. Any continuation must first inspect the
allowlisted fake/protected boundary facts and obtain fresh authorization before
any new protected request. The direct protected diagnostic remains unrun, and
this report is immutable.
