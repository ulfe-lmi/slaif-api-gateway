# OAP 155-w report

RESULT=FAILED

155-w completed the exact live function `response.output_item.done` shape
correction, all ordered fake gates, and exactly one protected qualification
attempt. The protected command returned exit 1 and printed the fixed
`QUALIFICATION=FAILED` result class. The outer shell retained only that class,
then deleted the task root containing the sanitized JSON. Consequently, this
report deliberately makes no inference about the protected event contract,
owner boundary, hop counts, or terminal accounting.

## OAP and Git topology

- Objective: `155-w`
- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting/activation head: `43cfcd97af6b1d8a6eb5b31a2db0a6f8217da0b6`
- Prior 155-v report: `307a491e511638779c4ecc67a7f9f09dbff1143f`
- Prior 155-v implementation: `ce664052266b7a1cbd43b8083eaea22d3fa9c0fd`
- 155-w implementation head: `b7b7f7ec00ec365fb245185a7e7588aa6c41ccbc`
- Report publication commit: SELF
- Report path: `oap/reports/155-w-live-function-done-shape-and-final-acceptance.md`
- Activation parent: `307a491e511638779c4ecc67a7f9f09dbff1143f`
- Implementation parent: `1740ee99b190386dce891667f7e06e17415518c6`

The activation commit contained only `oap/active` and the exact 155-w order.
The implementation diff from activation changed only:

- `app/slaif_gateway/providers/streaming.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`
- `tests/unit/test_responses_codex_streaming_tools.py`

Local Coding 005-m and Qwen were not modified. No merge or release was
performed.

## Implemented and pre-live evidence

The exact pair-local validator now requires the reviewed completed function
item base fields and event-level `output_index`/`sequence_number`, while
rejecting inner item coordinates. The fake was updated to the same shape.
Focused negatives cover inner coordinate smuggling and missing, wrong, or
non-monotonic event coordinates.

The focused verifier and strict-stream tests passed. Ruff and compilation
passed. The pushed implementation head `b7b7f7ec00ec365fb245185a7e7588aa6c41ccbc`
passed all ten required checks: unit/lint/migration, PostgreSQL, E2E, browser,
Docker Compose, documentation, CodeQL, and both analysis checks.

The ordered composed fake gates all passed on the clean 155-w head:

- forced validator rejection: nonzero with bounded rejection evidence;
- provider/transport failure: nonzero with bounded summary-only evidence;
- valid two-turn qualification: two turns, one function result, one message,
  and two accounting rows.

No raw credentials, endpoints, IDs, prompts, arguments, results, bodies,
headers, exception text, or raw SSE were retained or reported.

## Protected qualification limitation

Exactly one protected qualification was attempted after the fake gates and
green qualification head. It returned exit 1 / `QUALIFICATION=FAILED`. The
outer shell deleted the sanitized JSON before this report was prepared. The
only retained protected fact is that wrapper result class and the fact that
the qualification did not pass. No event shape, Gateway/Local/Qwen count,
ownership classification, reservation state, ledger state, or acceptance
claim is made. No protected retry or hook-free final run was attempted.

## Cleanup and closure

The exact mode-0600 runtime reference was validated privately and removed.
Zero 155-w temporary roots remained, and zero verifier, Qwen-relay, Local, or
Uvicorn task processes remained. The repository was clean before publication.

This is the single immutable truthful FAILED report for 155-w. The wrapper
evidence-loss limitation must be corrected by a later continuation before any
new protected diagnostic is authorized. No merge was performed.
