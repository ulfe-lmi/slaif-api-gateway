# OAP execution report — 026-a

## Objective

Record the OpenAI Pro model streaming limitation honestly in the compatibility matrix.

## Changes

Documentation-only addition to `docs/compatibility-matrix.md` under the Codex CLI model qualification area.

No code changes.

## Verification evidence

Observed during tier-2 basic-task qualification: Luna/Terra/Sol pass tier-1 hello but cannot sustain Codex CLI streaming sessions due to gateway streaming validator rejecting standard Responses SSE events when `codex_streaming_tool_events=False`.

## Test results

`git diff --check` passed. No unit/integration tests required for documentation-only change.

## Security review

No application code or trust boundary modified.

## Privacy/accounting evidence

No new provider calls or accounting rows created by this documentation round.
