# OAP Objective 163-a Immutable Report

RESULT=PASSED

## Publication and topology

- Repository: `ulfe-lmi/slaif-api-gateway`
- Base: `main` at `5ea38325ef3a3ebc69524b4679b795fab0c52935`
- Branch: `oap/163-local-coding-sse-framing-bounds`
- PR: #300, `https://github.com/ulfe-lmi/slaif-api-gateway/pull/300`
Implementation head SHA: e6f26db8ef27eb0657aaaad1d4b0571b97eb0e4b
- Implementation parent: `5ea38325ef3a3ebc69524b4679b795fab0c52935`
Report publication commit: SELF
- PR state at publication: open, not merged
- `oap/active`: `163-a`
- The exact strategic order is committed at
  `oap/orders/163-a-bound-local-coding-sse-framing.md`.

The implementation commit contains only the allowed Objective-163 paths: the
Local Coding adapter and framer, the narrowly required typed-validator bounds,
focused tests, the named contract documentation, and the unchanged strategic
order/active selector. No schema, migration, dependency, configuration, CI,
client-module, non-Local provider, identity/signing, verifier, or historical
OAP file changed. README is unchanged because the top-level endpoint/support
claim is unchanged; the affected contract documentation records the new
pair-local transport boundary.

## Root cause and implementation

The former production path called HTTPX `Response.aiter_lines()`, appended
every decoded line to `pending_lines`, waited for a blank line, joined all
`data:` values in `parse_sse_lines`, and only then called `json.loads`. HTTPX
could therefore hold an arbitrarily long unterminated decoded line before the
adapter or typed validator saw it, while a multi-line frame and joined payload
could also grow without a transport bound.

`BoundedSSEFramer` now consumes `aiter_raw()` bytes only for the Local Coding
adapter. It scans LF across arbitrary chunks, retains at most one bounded
partial line/frame, strips one CR for CRLF, strictly decodes complete lines,
joins `data:` segments with exactly one newline, ignores comments/other fields
while charging their bytes to the frame, parses only a complete bounded JSON
object, emits `[DONE]`, and dispatches a complete final event at EOF. It resets
event-local state after every dispatch and exposes only numeric peak-state
statistics. Generic OpenAI/OpenRouter streaming paths were not rewritten.

Only absent/identity `Content-Encoding` is accepted. Unsupported encoding is
rejected before raw iteration so the framer never relies on implicit
decompression that could inflate an unchecked chunk. Parse errors use closed
provider-domain codes:

`local_coding_sse_malformed_chunk`,
`local_coding_sse_content_encoding_unsupported`,
`local_coding_sse_invalid_utf8`, `local_coding_sse_invalid_json`,
`local_coding_sse_json_not_object`, `local_coding_sse_line_too_large`,
`local_coding_sse_frame_too_large`, `local_coding_sse_data_too_large`, and
`local_coding_sse_data_segments_too_many`.

Messages contain no raw line, JSON, identifier, argument, reasoning, endpoint,
credential, or arbitrary exception text. Parser error, overflow, cancellation,
consumer `aclose`, and adapter generator cleanup close the upstream response;
`CancelledError` is re-raised.

## Reviewed bound derivation

The static source/test/documentation derivation is:

| Quantity | Inequality/derivation | Reviewed value |
| --- | --- | ---: |
| reasoning summary bytes | `<= 1 MiB` cumulative | 1,048,576 |
| visible reasoning content bytes | `<= 1 MiB` cumulative | 1,048,576 |
| local function arguments | `<= 1 MiB` | 1,048,576 |
| assistant message text | `<= 1 MiB` | 1,048,576 |
| non-output/usage response envelope | serialized JSON `<= 1 MiB` | 1,048,576 |
| semantic event budget | `1 MiB + 1 MiB + 1 MiB + 1 MiB + 1 MiB` | 5,242,880 |
| joined data / largest `json.loads` input | `5,242,880 * 6 + 131,072` | 31,588,352 |
| one line | `joined data + len("data: ") + optional CR` | 31,588,359 |
| data segments | fixed cardinality | 2,048 |
| ignored-field allowance | charged raw comment/ignored bytes | 262,144 |
| complete frame | `31,588,352 + (2,048 * 8) + 2,047 + 262,144 + 2` | 31,868,929 |

The factor six is the worst-case JSON ASCII escaping expansion for a one-byte
control character (`\\u00XX`). The 128 KiB structural allowance covers bounded
field names, IDs, indexes, usage arrays, punctuation, and other fixed JSON
structure. Eight bytes per maximum CRLF data line covers `data: `, CR, and LF;
2,047 bytes are the inserted newlines between joined data segments; the final
2 bytes are a blank CRLF delimiter. The static hard ceilings cannot be raised
by provider/client/route data, response headers, or environment variables;
test-only limits may narrow them.

The exact Codex/Local response-envelope names are allowlisted as `id`,
`object`, `created_at`, `status`, `error`, `incomplete_details`,
`instructions`, `max_output_tokens`, `model`, `parallel_tool_calls`,
`previous_response_id`, `reasoning`, `store`, `temperature`, `text`,
`tool_choice`, `tools`, `top_p`, `truncation`, `metadata`, `service_tier`,
`prompt_cache_key`, and `max_tool_calls`; `output` and `usage` are separately
validated. Unknown names are rejected. Strict typed output is capped at three
items and four MiB aggregate output text/arguments. Reasoning summary bytes are
bounded cumulatively, and completed reasoning accounting includes both summary
and visible content. These are the smallest profile-correct semantic tightenings
needed to make the transport derivation finite; the Objective-162 zero-argument
and ordinary function/reasoning/message lifecycle semantics remain unchanged.

The maximum-event test constructs five one-MiB worst-case control-character
semantic fields, serializes with worst-case ASCII escaping, asserts the complete
response/event fits joined-data, line, and frame ceilings, and feeds the event
through the framer. Decoder-owned state is bounded to one event: line state is
at most 31,588,359 bytes, the current frame is at most 31,868,929 bytes,
joined data/JSON input is at most 31,588,352 bytes, and retained data segments
are at most 2,048 with aggregate joined bytes at most 31,588,352. No stream
history or content-bearing diagnostics are retained.

## Mandatory regression matrix

The literal map is
`LOCAL_CODING_SSE_OBLIGATION_TO_TEST_NODE` in
`tests/unit/test_local_coding_sse_framing.py`. Its 32 obligation entries map to
28 unique nodes. Collection of the framer/Codex/Responses set found 226 nodes;
all 28 unique mapped nodes were directly executed successfully and
`missing=[]`. New parameter IDs are explicit and descriptive; no mapped
parameter sibling is anonymous.

| Group | Stable mapped node(s) | Result |
| --- | --- | --- |
| 1 normal stream | `test_framer_preserves_normal_events_across_ordinary_network_chunks` | PASS |
| 2 byte-small/UTF-8 split | `test_framer_handles_normal_small_chunks_and_utf8_split_at_byte_boundaries` | PASS |
| 3 CRLF/split CR-LF | `test_framer_handles_crlf_split_boundary_and_multiline_data` | PASS |
| 4 multiline data newline semantics | `test_framer_handles_crlf_split_boundary_and_multiline_data` | PASS |
| 5 comments/ignored fields | `test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event` | PASS |
| 6 maximum reviewed event | `test_maximum_reviewed_semantic_event_serializes_within_all_wire_ceilings` | PASS |
| 7 exact one-byte-over bounds | `test_one_byte_over_bounds_fail_before_oversized_state_is_retained[line-one-byte-over]`, `[frame-one-byte-over]`, `[joined-data-one-byte-over]`, `[data-segments-one-byte-over]` | PASS |
| 8 unterminated line | `test_unterminated_line_fails_at_first_over_bound_byte` | PASS |
| 9 many small data lines | `test_many_small_data_segments_are_bounded_before_joining` | PASS |
| 10 valid final EOF event | `test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event` | PASS |
| 11 malformed EOF/comment-only EOF | `test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[invalid-json]`; comment-only branch of `test_comments_and_ignored_fields_are_bounded_and_eof_dispatches_final_event` | PASS |
| 12 parse contract | `test_invalid_utf8_json_and_non_object_data_fail_closed_without_echo[invalid-json]`, `[non-object-json]`, `[invalid-utf8]`, `[dangling-utf8]` | PASS |
| 13 close/cancel/error | `test_local_adapter_uses_bounded_framer_and_closes_after_parse_error`, `test_consumer_aclose_closes_upstream_stream_promptly`, `test_cancellation_closes_upstream_stream_and_is_not_swallowed` | PASS |
| 14 incremental many events | `test_done_marker_and_many_events_are_incremental_and_content_free_stats_only` | PASS |
| 15 Objective-162 lifecycle regressions | `test_codex_0149_zero_argument_source_lifecycle_accepts_without_synthetic_events`, `test_codex_0149_function_lifecycle_is_ordered_and_declared`, `test_reasoning_message_and_terminal_event_table_is_bounded`, `test_codex_0149_completed_requires_usage_and_no_active_output`, `test_event_and_replay_size_caps_fail_closed_without_echoing_content` | PASS |
| 16 unsupported encoding | `test_unsupported_content_encoding_fails_before_raw_iteration` | PASS |
| 17 Gateway accounting/privacy | `test_local_coding_malformed_stream_before_output_releases_accounting`, `test_local_coding_malformed_stream_after_output_records_interruption` | PASS |

Focused final collection/execution counts were:

| Test file/group | Collected | Passed |
| --- | ---: | ---: |
| `test_local_coding_sse_framing.py` | 24 | 24 |
| `test_local_coding_server_module.py` | 40 | 40 |
| `test_provider_streaming_sse.py` | 2 | 2 |
| `test_responses_codex_streaming_tools.py` | 176 | 176 |
| `test_v1_responses_quota.py` | 82 | 82 |
| OAP/agentic/provider governance tests | 13 | 13 |
| focused total | 337 | 337 |

The complete `tests/e2e/test_openai_python_client_responses.py` ran 26/26 on
fresh disposable PostgreSQL database
`slaif_oap163_test_final_1789254002_1783541`. The relevant PostgreSQL
integration files ran 3/3 on that same isolated database after migration:
the Local Coding pre-reservation boundary and both provider diagnostic paths.
The mapped-node direct execution ran 28/28 with return code 0. The E2E
pre-output malformed path recorded a released reservation/failed ledger and
zero reserved tokens. The post-output malformed path recorded finalized
estimated interruption/failed-success state with zero reserved tokens and no
success terminal or `[DONE]`. The malformed canary was absent from the client
error and ledger metadata.

## Corrected failures and safety boundaries

- The initial local test invocation failed before collection because the base
  interpreter lacked `structlog`; an isolated `/tmp/slaif-gateway-163-venv`
  environment installed the existing `.[dev]` dependencies without changing
  repository dependency files.
- The first focused implementation run found and corrected the many-segment
  expectation and output aggregate test construction. The first complete E2E
  rerun on a reused database found five uniqueness failures from fixed provider
  response/conversation IDs left by the previous run. That database was an
  explicitly named disposable test database, was dropped, a fresh database was
  created, and the complete E2E file then passed 26/26. No product defect
  remains from those setup failures.
- Final Ruff check/format, `compileall`, `git diff --check`, and the static
  allowed-path/no-secret scans passed. The only secret-like scan hit was the
  intentional non-secret `LOCAL_SSE_SECRET_CANARY` test sentinel; it was
  absent from client errors and durable metadata.
- No Local process, Qwen/vLLM process, GPU, protected endpoint, real upstream
  provider call, real email, production mutation, release, deployment, or
  Codex evidence-tool action was performed. No `DATABASE_URL` was used for
  destructive setup; only the explicitly named disposable `TEST_DATABASE_URL`
  databases were created/dropped. The final disposable database is retained
  only for the handoff evidence and is not project state.

## Implementation-head GitHub checks

All ten required checks were independently observed SUCCESS on implementation
head `e6f26db8ef27eb0657aaaad1d4b0571b97eb0e4b`:

- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL
- Docker Compose smoke
- Documentation hygiene
- OpenAI-compatible E2E tests
- Playwright browser smoke
- PostgreSQL integration tests
- Unit, lint, and migration head

No required check was skipped, pending, cancelled, blocked, or missing at the
implementation head. The report commit must be rechecked by the strategic agent
as the immutable PR head before any merge decision.

## Documentation, limitations, and labels

Updated contracts: `AGENTIC_CLIENT_INTEGRATION.md`,
`docs/module-architecture.md`, `docs/provider-forwarding-contract.md`,
`docs/responses-compatibility.md`, `docs/openai-compatibility.md`,
`docs/compatibility-matrix.md`, `docs/security-model.md`, `docs/accounting.md`,
and `docs/streaming-live-burn-margin.md`. The docs describe the Local-only
framing boundary, exact field/byte derivation, safe errors, close semantics,
and unchanged accounting law. README remained unchanged for the reason stated
above.

This is a static transport/resource-boundary qualification for synthetic
loopback and disposable database evidence. It is not a Local Coding deployment
qualification, vLLM/Qwen inference qualification, production certification,
security certification, compliance attestation, invoice truth, release
approval, or protected-system handoff. The generic parser remains available
for non-Local paths and is intentionally outside this objective. The hard
frame bound is finite but intentionally large enough for the reviewed typed
profile; provider route/client metadata cannot enlarge it.

PREPARSE-LINE-BOUND-ENFORCED = YES
PREPARSE-FRAME-BOUND-ENFORCED = YES
PREPARSE-DATA-AND-JSON-BOUND-ENFORCED = YES
BOUND-DERIVATION-CONSISTENT-WITH-TYPED-VALIDATOR = YES
INCREMENTAL-MANY-EVENT-STATE-BOUNDED = YES
UPSTREAM-CLOSE-AND-CANCELLATION-ACCEPTED = YES
ACCOUNTING-ZERO-PENDING-ACCEPTED = YES
OBJECTIVE-162-LIFECYCLES-REGRESSION-ACCEPTED = YES
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
