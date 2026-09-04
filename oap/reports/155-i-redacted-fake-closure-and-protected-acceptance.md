# OAP 155-i report — BLOCKED

Status: `BLOCKED`

Reason: the single permitted real composed attempt reached the protected
composition and failed the fixed gate `stream_completion_event_missing`.
There was no retry, acceptance, merge, or cutover claim.

## Topology and scope

- PR: #291, base `main`.
- Branch: `oap/155-local-coding-signed-server-module`.
- Starting head after 155-i activation: `0247a7cf68a6f5f3c8ea47b5e5ed5ca08d4e2246`.
- Activation parent and 155-h report head:
  `8b433ba740071733585bcf4ac1fddaaf83368ac3`.
- 155-h implementation head: `a7c63222d0995aa866d6733bd03d5b27a3c5bd1d`.
- Final implementation head:
  `621af9f74d0229db5bdb6d21b98e31b6dcefc73a` (clean remote/local
  implementation head).
- Report publication commit: `SELF`.
- Allowed implementation paths changed: `scripts/verify_local_coding_full_stack.py` and
  `tests/unit/test_local_coding_full_stack_verifier.py`.
- The 155-h report remains unchanged. The 155-h report was truthful but
  procedurally incomplete; this report restores the required ledger.

The implementation commit sequence after activation was:

`3768f12`, `a49a1ee`, `8ed854c`, `16bcb7e`, `4fe430a`, `f3b5782`,
`360187c`, `c27a5d8`, `38bb621`, `5277736`, `68d88a7`, `b0f92e9`,
`a3e866c`, `17c181f`, `5db358c`, `baeef5e`, `104c97d`, `3d851ba`,
`f6e740b`, `f083002`, `bf87a10`, `1e50ff4`, `88658ae`, `75036e3`,
`9ecd82f`, `7fa4212`, `8943b3d`, `621af9f`.

## Verification ledger

Focused verifier tests passed: 49 tests. Ruff, Python compilation, and
`git diff --check` passed. The exact task-local fake command was used with a
task-owned venv, task-root install log, `PYTHONDONTWRITEBYTECODE=1`, and the
required repository/application `PYTHONPATH`.

The bounded fake rehearsal progression, retaining only fixed codes, was:

1. Earlier fake attempts stopped at `ordinary_response_failed` and then
   `codex_session_a_turn_failed` while the diagnostic boundaries were being
   corrected.
2. The Codex-facing wire boundary was then classified as
   `codex_session_a_gateway_sse_missing`.
3. After enabling the exact custom-tools capability only on the disposable
   route fixture, the controlled failure path reached
   `failure_provider_call_count_invalid`.
4. After splitting the generic failure-only key and correcting the Local-key
   row invariant, the complete fake rehearsal passed:
   `FAKE_REHEARSAL=OK`.

The exact installed Codex 0.149.0 subprocess using `_exec_command_0149` and
the task fake Qwen/model catalog passed independently with fixed result
`direct_codex_fake=ok`. The fake SSE emits the pinned created/completed pair;
the Gateway-facing recorder checks ordered events and counts, no `[DONE]`, no
duplicates/unknowns, `resp_` ID equality, statuses, model, empty output, and
nonnegative usage fields. Reorder, duplicate, sentinel, and wrong-status
regressions passed.

The required real-mode command was run exactly once after fake PASS, clean
implementation state, and green checks. It failed with:

`RESULT=BLOCKED code=stream_completion_event_missing`

The protected attempt ledger is therefore: preflight ran; one protected
composed attempt ran; protected acceptance did not pass; no retry ran; no
report PASS or merge claim is made.

All ten required PR #291 checks were successful on implementation head
`621af9f`: Analyze (JavaScript/TypeScript), Analyze (Python), Analyze Python,
CodeQL, Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E,
Playwright browser smoke, PostgreSQL integration tests, and Unit/lint/migration
head.

## Cleanup and privacy

The verifier cleanup and post-run audit found: Gateway worktree clean; Local
checkout tracked/ignored state clean; no task fake/real/direct temporary roots;
the task-created install log absent; no Local repository `.venv`; no matching
Qwen relay process; and no task PostgreSQL container. No repository/OAP file
other than this report was changed for publication.

No credential value, private endpoint value, source value, request body,
identity, session, signature, or derived private value was printed, persisted,
committed, or included in this report. Bounded diagnostic/request data was
discarded during cleanup. The real result is limited to the fixed terminal
gate above; it is not product acceptance, production qualification, or a
merge authorization.

No merge was performed and auto-merge was not enabled.
