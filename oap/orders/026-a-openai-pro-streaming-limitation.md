# OAP Work Order — 026-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/026-openai-pro-streaming-limitation`
Base: main @ f8e63ca

## Objective

Record the OpenAI Pro model streaming limitation honestly in the compatibility matrix. No code changes.

## Scope

Add to `docs/compatibility-matrix.md` under "Codex CLI model qualification":

A note that Luna/Terra/Sol pass tier-1 hello (single non-streaming request) but cannot sustain Codex CLI streaming sessions due to gateway streaming validator rejecting standard Responses SSE events when `codex_streaming_tool_events=False`. Fix requires separating standard-event acceptance from hosted-tool content validation.

## Allowed paths

```
docs/compatibility-matrix.md
oap/orders/026-a-openai-pro-streaming-limitation.md
oap/reports/026-a-openai-pro-streaming-limitation.md
oap/active
```

## Verification

`git diff --check`; docs hygiene CI check passes.

## Acceptance

Limitation documented; CI green; report-only SELF commit.
