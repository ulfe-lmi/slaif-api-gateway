# Objective 155-r — retained event qualification and final stream

RESULT=OK

## Publication and topology

- Report publication commit: SELF
- PR: #291
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main`
- Starting head: `a5154d68db3999c3df7c8d03cb13eed86c7fcea2`
- Activation head: `a08655180dcd280529ca798b3509d4f28e7f8ab7`
- Final implementation head: `19d9686636b0fbf27ab96d41c610a37dad3c087a`
- Report parent: `19d9686636b0fbf27ab96d41c610a37dad3c087a`
- Report path: `oap/reports/155-r-retained-event-qualification-and-final-stream.md`
- The report commit changes this report only.

The final implementation retains the exact Codex 0.149 reasoning and
standard assistant-message stream validators, scoped to the resolved
`codex-0.149-responses-v1` and Local Coding server pair. It also removes the
temporary qualification hooks, environment variables, production rejection
writer, verifier artifact sanitizer/output path, qualification-only CLI modes,
and their temporary tests. The immutable historical 155-l direct baseline was
not modified.

Allowed implementation files changed before this report were:

- `app/slaif_gateway/providers/streaming.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`
- `tests/e2e/test_openai_python_client_responses.py`

## Qualification result

Exactly one protected qualification request was consumed under 155-r. It was
not retried or repeated. The Gateway returned its typed stream-validation
failure, and the corrected verifier surfaced the following bounded safe shape
before the temporary root was removed:

```json
{"event_type":"response.output_item.added","nested_object_fields":[{"fields":[{"name":"content","type":"null"},{"name":"encrypted_content","type":"null"},{"name":"id","type":"string"},{"name":"status","type":"string"},{"name":"summary","type":"array"},{"name":"type","type":"string"}],"name":"item"}],"rejection":{"code":"responses_stream_event_not_supported","outcome":"validator_rejected"},"schema":"responses_stream_rejection_v1","top_level_fields":[{"name":"item","type":"object"},{"name":"output_index","type":"integer"},{"name":"sequence_number","type":"integer"},{"name":"type","type":"string"}],"validator_profile":{"codex_encrypted_reasoning_replay":false,"codex_streaming_tool_events":false,"declared_client_tools_class":"none","web_search":false,"web_search_max_tool_calls_class":"none"}}
```

The qualification shape was compared with:

1. pinned official OpenAI Python 2.41.0 Responses types, source commit
   `2d955a1ac69df0288b8072bbcd25905639e9b2ed`;
2. official vLLM 0.27.1 Responses streaming/response-builder sources, source
   commit `6e448d0ea9bf3d88d898b65449ca6dc2aec170ac`;
3. the version-owned Codex 0.149 pair contract and ordered validator.

The shape is legitimate reasoning-item metadata. The permanent validator now
requires the ordered reasoning lifecycle: added/in-progress, one reasoning
part, accumulated deltas, matching text.done, matching part.done, and
completed output_item.done. It separately requires the exact standard
assistant-message lifecycle, including event-specific annotation/logprob
nullability, bounded completed output, detailed usage, and token-total
reconciliation. Tool, hosted-search, message-smuggling, orphan, duplicate,
reordered, mismatched-index, missing-field, and overflow cases remain
fail-closed.

## Rehearsal and final protected run

The hook-free fake rehearsal ran as:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD:$PWD/app" <task-venv>/bin/python scripts/verify_local_coding_full_stack.py --composed-only-fake
```

It completed with `terminal_boundaries_completed`, nonempty terminal output,
valid detailed usage, finalized accounting, one Gateway-to-Local response,
one Local-to-Qwen inference call, normal close, and no rejection artifact.

The protected model/health preflight passed privately for the configured
protected service. Exactly one final protected composed request then ran:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD:$PWD/app" <task-venv>/bin/python scripts/verify_local_coding_full_stack.py --composed-only
```

No direct-provider request and no retry occurred. The final run produced 2xx
SSE, exactly one `response.created`, exactly one terminal
`response.completed`, valid completed status/output/usage, finalized
PostgreSQL accounting, one Gateway-to-Local call, one Local-to-Qwen call,
normal Local/Gateway close, zero downstream-closed-early facts, no Gateway
error, and no stream-validation rejection.

The bounded structural recorder classified the additional reasoning event
names as `other` because its safe vocabulary summary is narrower than the
permanent production validator. It retained only bounded counts/field facts;
this is disclosed as an observation limitation, not converted into an event
shape or ownership claim. The production validator accepted the strict
reasoning/message stream and the final terminal predicate passed.

## Tests and checks

Observed local results:

- full verifier unit file: passed;
- focused streaming/verifier/unit suites: passed;
- full Ruff check: passed;
- AST/bytecode compilation and whitespace checks: passed;
- hook-symbol absence scan over `app`, `scripts`, and `tests`: passed;
- hook-free fake composed rehearsal: passed.

The final implementation head `19d9686...` has ten successful PR checks:
JavaScript analysis, Python analysis, Analyze Python, CodeQL, Docker Compose
smoke, documentation hygiene, OpenAI-compatible E2E, Playwright browser
smoke, PostgreSQL integration, and Unit/lint/migration head.

## Privacy, cleanup, and disposition

- No credential, protected endpoint, session, installation alias, signature,
  request body, response text, or raw event value was persisted in the report,
  repository, or committed artifact.
- The qualification safe shape above contains field names, type classes, and
  fixed rejection facts only.
- The exact mode-0600 runtime reference was removed after the final protected
  run.
- The exact mode-0600 task credential source was removed after the final
  protected run.
- The exact mode-0700 task root and contents were removed with bounded
  non-trash deletion.
- Gateway and detached Local checkouts were clean at handoff.
- PR #291 remains open; no merge, auto-merge, release, cutover, certification,
  or production-completion claim is made.

This report is the immutable 155-r handoff for the remaining Local Coding
acceptance matrix.
