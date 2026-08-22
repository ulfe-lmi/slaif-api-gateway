# OAP execution report — 027-a

## Objective

Record tier-3 (tool-use) qualification evidence for two models through SLAIF.

## Changes

Documentation-only addition to `docs/compatibility-matrix.md`.

No code changes.

## Live verification evidence

| Model | Exit | Reply | File content |
|---|---|---|---|
| nvidia/nemotron-3-super-120b-a12b:free | 0 | DONE | TOOL_TEST=PASS |
| moonshotai/kimi-k3 | 0 | DONE | TOOL_TEST=PASS |

Sandbox: workspace-write. Both models used `exec_command` to write the file.

## Test results

`git diff --check` passed. No unit/integration tests required for documentation-only change.

## Security review

No application code or trust boundary modified.

## Privacy/accounting evidence

No new provider calls or accounting rows created by this documentation round.
