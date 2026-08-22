# OAP Work Order — 025-b

PR mode: `CONTINUE_EXISTING_PR`
PR: #256
Branch: `oap/025-model-qualification-basic-task`

## Objective and reason

Fix the gateway's Responses streaming validator to accept OpenAI's
`obfuscation` field on `response.output_text.delta` SSE events. This field is
emitted by the real OpenAI Responses API but is not in the validator's allowed
field set, causing all OpenAI Pro model calls (Luna/Terra/Sol) through SLAIF to
fail with `"Provider emitted a Responses streaming event that is not supported
by this gateway."`.

## Root cause evidence

Direct capture from `api.openai.com/v1/responses` with `"stream": true`:

```json
{
  "type": "response.output_text.delta",
  "content_index": 0,
  "delta": "HI",
  "item_id": "msg_...",
  "logprobs": [],
  "obfuscation": "0soI4pWDqWR2vm",
  "output_index": 0,
  "sequence_number": 4
}
```

The gateway's `_validate_delta_event()` (providers/streaming.py, line ~691)
defines `allowed = {"type", "item_id", "output_index", "content_index",
"delta", "sequence_number", "logprobs"}` — missing `"obfuscation"`.

## Exact requirements

1. In `app/slaif_gateway/providers/streaming.py`, inside `_validate_delta_event()`,
   add `"obfuscation"` to the `allowed` set.
2. Add a focused unit test proving that an `output_text.delta` payload containing
   `"obfuscation"` passes validation.
3. Re-run the live Codex → SLAIF → OpenAI Pro hello test and confirm it succeeds.
4. No other changes.

## Allowed paths

```
app/slaif_gateway/providers/streaming.py
tests/unit/test_responses_streaming.py   # or existing test file for streaming
oap/orders/025-b-fix-openai-sse-streaming-validator.md
oap/reports/025-b-fix-openai-sse-streaming-validator.md
oap/active
```

## Non-goals

No other streaming validator relaxation.
No profile/catalog change.
No pricing or accounting change.

## Verification

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_responses_streaming.py
# Live re-test:
OPENAI_API_KEY=<gateway key> \
OPENAI_BASE_URL=http://localhost:8000/v1 \
~/codex-work/codex-subscription pro -p slaif-openai -m gpt-5.6-luna exec \
  --skip-git-repo-check --sandbox read-only -o /tmp/t2.txt \
  'Read /tmp/oap-025-fixture/config.env and reply with exactly one line ANSWER=<value of MAX_CONNECTIONS>.'
```

## Acceptance

Focused test passes; live tier-2 task returns `ANSWER=25`; final-head CI green;
report-only SELF commit; never merge.

## Boundaries

Non-production only. Provider credentials remain in env/local scripts.
