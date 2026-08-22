# OAP execution report — 023-b

## Objective

Enable Qwen3.8-27B vision Codex qualification by adding namespace tool support
and vLLM streaming event compatibility to the SLAIF API gateway.

Implementation head SHA: cf522573c6a69d44d71c284bf0ad7a43324ebf67
Report publication commit: SELF

## Changes

1. providers/streaming.py:
   - Added missing vLLM SSE event types to RESPONSES_CODEX_STREAM_EVENT_TYPES:
     response.reasoning_part.added, response.reasoning_part.done,
     response.reasoning_text.done, response.content_part.added,
     response.content_part.done, response.output_text.done.
   - Added _validate_content_part_event() and _validate_output_text_done_event().
   - Updated _validate_reasoning_event() to handle reasoning_part and reasoning_text.done.
   - Relaxed _validate_response_progress_event() and _validate_response_completed_event()
     to accept provider-specific extra fields in the response object.

2. services/responses_request_policy.py:
   - Added namespace tool support in _validate_local_tool(), gated behind
     allow_codex_client_tools flag (enforced per-key).
   - Added "status" field to _SUPPORTED_CODEX_REASONING_REPLAY_FIELDS.
   - Allow encrypted_content=null for Codex reasoning replay items (vLLM does not encrypt).

3. scripts/verify_qwen38_vision_codex.py: Updated verifier prompt and configuration.

4. services/responses_gateway.py: No functional changes (debug cleanup only).

## Root cause analysis

The LAN vLLM build emits SSE events with additional fields not present in
OpenAI's canonical Responses streaming format (e.g., content_part events with
logprobs arrays, reasoning_part events with plaintext content). The gateway's
streaming validator rejected these unrecognized event shapes, causing stream
interruption before response.completed was delivered.

Additionally, vLLM includes "status" on reasoning replay items and sends
encrypted_content=null (local models do not encrypt), which the policy
validator previously rejected.

## Live verification evidence

- Chain tested: Codex CLI → SLAIF API Gateway (:8000) → image-cap proxy (:18021) → vLLM (:18020)
- Model correctly identified a synthetic red image as "Red"
- turn.completed received with usage accounting (26110 input tokens, 80 output tokens)
- All three sequential requests returned HTTP 200 from both SLAIF and vLLM

## Test results

- tests/unit/test_responses_codex_streaming_tools.py: PASS
- tests/unit/test_responses_codex_client_tools.py: PASS
- tests/unit/test_qwen38_vision_codex_candidate.py: PASS
- tests/unit/test_qwen38_text_codex_candidate.py: PASS
- tests/unit/test_codex_profile_registry.py: PASS
- tests/unit/test_upstream_payload_reconstruction.py: PASS
- tests/unit/test_responses_codex_multiturn_replay.py: PASS
- git diff --check: PASS
- Ruff lint: PASS (all checks passed)

## Security review

- Namespace tool acceptance is gated behind allow_codex_client_tools capability
  (per-key authorization required)
- Streaming event validation additions are gated behind codex_streaming_tool_events=True
  (per-key + per-route authorization required)
- No new hosted tool types accepted; namespace tools remain client-side local tools
- Encrypted replay still requires codex_encrypted_reasoning_replay capability
- Null encrypted_content is now accepted (vLLM/local model behavior); non-null
  non-string values are still rejected

## Privacy/accounting

- PostgreSQL remains quota/accounting truth
- No prompts/completions/media persisted beyond existing accounting requirements
- Provider keys never appear in logs or responses
