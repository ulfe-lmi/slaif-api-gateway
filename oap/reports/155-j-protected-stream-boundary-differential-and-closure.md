# OAP 155-j report — PARTIAL / BLOCKED

Status: `PARTIAL` and blocked from acceptance because the protected differential
produced `ambiguous_stream_evidence`. No Gateway-owned evidence was established,
so no product correction was made.

## Topology and scope

- PR: #291.
- Base: `main` at `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Branch: `oap/155-local-coding-signed-server-module`.
- Starting head: `9c29eb5bb5d95d75dd600c3b629c589d797ab1d8`.
- 155-j activation head: `6a9634aa56a18c6fefe9229839a7455fed65d832`.
- 155-j implementation head:
  `c2b7cdaeb5d7c595a4882c2bf841b1fc8704a42f`.
- Report publication commit: `SELF`.
- Activation changed only `oap/active` and the exact 155-j order.
- Implementation changed only `scripts/verify_local_coding_full_stack.py` and
  `tests/unit/test_local_coding_full_stack_verifier.py`.
- No conditional Gateway product path was changed.

## Implementation and checks

The implementation commit sequence was:

- `6a9634aa56a18c6fefe9229839a7455fed65d832` — 155-j activation;
- `846c72874a1c7ad85082c7d6fb9a0fbb5e601b10` — bounded protected stream
  differential verifier;
- `037d178cb976ac5af5ac615dfc86407405e6ac0f` — accounting argument and
  ownership-classification correction;
- `c2b7cdaeb5d7c595a4882c2bf841b1fc8704a42f` — unknown-event regression.

Focused verifier tests passed: 59 tests. Ruff, Python compilation, and
`git diff --check` passed. All ten required PR checks passed on implementation
head `c2b7cdaeb5d7c595a4882c2bf841b1fc8704a42f` before the protected
differential: Analyze JavaScript/TypeScript, Analyze Python, Analyze Python,
CodeQL, Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E,
Playwright browser smoke, PostgreSQL integration tests, and Unit/lint/migration
head.

The verifier now records only boundary labels, numeric status/content-type
classes, ordered allowlisted SSE event facts, finite response field names,
duplicate/unknown/DONE flags, safe terminal relations, and lifecycle booleans.
The unit suite covers reordered, duplicated, unknown, sentinel, missing-terminal,
wrong-status/model/usage/output, non-SSE, truncation, bounds, accounting, and
ownership-classification cases.

## Protected differential ledger

The order-authorized maximum of two minimal text-only protected streaming
diagnostics was used exactly:

1. `direct_qwen`: ran once through the scrubbed task relay to protected Qwen.
2. `composed`: ran once through disposable PostgreSQL/Gateway, the signed
   Gateway-to-Local relay, Local Coding, and the scrubbed Qwen relay.

No Codex subprocess, compiler, cache, image, replay/tamper, tools, governance,
customer data, or full 155-i matrix traffic was run in this differential.

The decision-table result emitted by the verifier was exactly:

`RESULT=DIFFERENTIAL decision=ambiguous_stream_evidence`

The CLI emitted only that aggregate decision and discarded the returned safe
per-boundary observations. Consequently, this report does not claim which of
`direct_qwen`, `local_output`, or `gateway_output` lacked a valid
`response.completed`, nor which safe predicate (status, content type, event
sequence, usage, model, output shape, lifecycle, or official-client result)
caused ambiguity. The evidence is therefore not actionable ownership evidence.

One bounded handler fact was observed during the composed diagnostic:
`BrokenPipeError` while the relay was writing a response after the client-side
stream ended. No exception text, body, or private value was retained or used
for ownership classification.

Because the evidence was ambiguous, the verifier made no Qwen/Local/Gateway
ownership claim, made no Gateway correction, and did not run a full protected
acceptance matrix. No acceptance, qualification, deployment, release, or merge
claim follows. Any continuation must first make the CLI emit a fixed,
allowlisted per-boundary safe summary and prove that summary under fake tests;
no newly authorized protected diagnostic should run before that correction.

## Cleanup and privacy

After the differential, the Gateway worktree was clean; Local tracked/ignored
state was clean; task roots, relay processes, and task PostgreSQL containers
were absent. The mode-0600 runtime reference remained present only until this
report was published, as required by the order; it is removed in the final
post-publication cleanup without reading or rendering it.

No credential value, private endpoint value, source value, request body,
identity, session, signature, nonce, or derived private value was printed,
persisted, committed, or included in this report. No repository state other
than this report is to be changed after publication.

No merge was performed and auto-merge was not enabled.
