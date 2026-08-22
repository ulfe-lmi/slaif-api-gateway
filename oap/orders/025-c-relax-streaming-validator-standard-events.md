# OAP Work Order — 025-c

PR mode: `CONTINUE_EXISTING_PR`
PR: #257 (branch: `oap/025-model-qualification-basic-task`)
Branch: `oap/025-model-qualification-basic-task`

## Objective and reason

Relax the gateway's Responses streaming validator to accept the standard
OpenAI Responses SSE event types (`response.output_item.added`,
`response.output_item.done`, `response.content_part.added`,
`response.content_part.done`, `response.output_text.done`) for ALL streaming
requests, not just Codex requests with `codex_streaming_tool_events=True`.

## Root cause evidence

The gateway constructs a `ResponsesStreamValidationProfile` at
`responses_gateway.py:1049`. When the request does NOT declare Codex tool
events, `codex_streaming_tool_events=False`, and the validator falls back to
`RESPONSES_TEXT_STREAM_EVENT_TYPES` which only contains:
- `response.created`
- `response.in_progress`
- `response.output_text.delta`

But OpenAI's standard Responses API always emits these additional events in
every streaming response:
- `response.output_item.added`
- `response.output_item.done`
- `response.content_part.added`
- `response.content_part.done`
- `response.output_text.done`

These are rejected with `"Provider emitted a Responses streaming event that is
not supported by this gateway."`

All of these event types are already defined and validated in
`RESPONSES_CODEX_STREAM_EVENT_TYPES`. The fix is to use the full set as the
baseline for all streaming requests, rather than gating it behind
`codex_streaming_tool_events`.

## Exact requirements

1. In `app/slaif_gateway/providers/streaming.py`, change the validator so that
   when `codex_streaming_tool_events=False`, it still accepts the five standard
   event types listed above. The simplest approach: move these five types from
   `RESPONSES_CODEX_STREAM_EVENT_TYPES` into
   `RESPONSES_TEXT_STREAM_EVENT_TYPES` (they are valid for any Responses stream,
   not just Codex).
2. Add a focused unit test proving that a non-Codex streaming profile accepts
   `output_item.added` and `content_part.added`.
3. Verify live: `curl -N http://localhost:8000/v1/responses ... -d '{"stream":true}'`
   completes without error.
4. Re-run tier-2 task for Luna via gateway.

## Allowed paths

```
app/slaif_gateway/providers/streaming.py
tests/unit/test_openai_provider_streaming.py  # or existing streaming test file
oap/orders/025-c-relax-streaming-validator-standard-events.md
oap/reports/025-c-relax-streaming-validator-standard-events.md
oap/active
```

## Non-goals

No hosted tool enablement. No accounting change. No new capability flag.

## Verification

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_openai_provider_streaming.py
curl -N http://localhost:8000/v1/responses -H 'Authorization: Bearer <key>' \
  -d '{"model":"gpt-5.6-luna","input":"Say PING","stream":true}'
```

## Acceptance

Focused test passes; live curl streaming returns completed response with no
error event; final-head CI green; report-only SELF commit.
