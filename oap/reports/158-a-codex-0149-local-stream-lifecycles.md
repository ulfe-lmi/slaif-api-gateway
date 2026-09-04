# Objective 158-a report — Codex 0.149 Local stream lifecycles

RESULT=PASSED

Repository: `ulfe-lmi/slaif-api-gateway`
Base: `main` at `05fdbbc0ac623f49b87ee632d3f047120234941f`
Branch: `oap/158-codex-0149-local-stream-lifecycles`
PR: #295
Activation commit: `4ee5d47a353c274310967883a941b8f33b481c97`
Implementation head: `a72d9074952d00e70c3a45552f43c6eb632c3da9`
Report publication commit: SELF
Merge: not performed; auto-merge: disabled.

## Scope and topology

The implementation commit has exactly these changed paths:

- `app/slaif_gateway/providers/streaming.py`
- `app/slaif_gateway/services/responses_gateway.py`
- `tests/unit/test_responses_codex_streaming_tools.py`
- `tests/e2e/test_openai_python_client_responses.py`
- `docs/accounting.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`

The activation order and `oap/active` remain unchanged. No non-allowed app,
client-policy, Local, Qwen, replay, schema, migration, doctrine, or PR #291
path was changed. The implementation commit is the first parent required for
this report-only commit.

The required exact blobs are present:

- `app/slaif_gateway/providers/streaming.py`:
  `bd54aeb9a203be52b2cdba626344cf74adf46c0c`
- `tests/e2e/test_openai_python_client_responses.py`:
  `aa95589294f48f883b1c174a5a3a43428d9c44f0`

The Gateway semantic diff is limited to pair-local strict profile selection,
post-Local route capability enforcement, and omission of only
`prompt_cache_key` from the Local upstream body. The normalized policy body is
not mutated. No Objective-155 hook, qualification artifact, protected runtime,
second-turn request, replay admission, or replay-ownership behavior was added.

## Behavior and evidence

The strict profile is enabled only for the exact
`codex-0.149-responses-v1 -> local-coding-v1` pair, after Local context
resolution, with the independent request-envelope, client-tool, and streaming
capability gates. Non-Local and ordinary/default profiles retain their prior
behavior. Adapter-managed `tool_search`/`web_search` candidates remain
non-hosted and do not create external-tool authority.

The validator now covers bounded ordered `response.created`/
`response.in_progress`/`response.completed` events, exact reasoning lifecycle,
declared local function lifecycle, and assistant-message content lifecycle.
It rejects unknown, orphaned, reordered, duplicated, post-terminal, malformed,
oversized, coordinate-smuggled, undeclared, hosted/MCP, and provider-failure
events. Terminal output and vLLM-style detailed usage are checked independently;
completion requires no active item or part. Stream content, arguments,
identifiers, and raw events remain transient.

Pure validator coverage: 90 tests passed in
`tests/unit/test_responses_codex_streaming_tools.py`, including exact pair
containment, function/reasoning/message positives, terminal-ID independence,
event-specific shapes, lifecycle order/cardinality, coordinate and field
negatives, bounds, terminal output/usage, and authority smuggling. Existing
provider-streaming, policy, route-capability, Codex envelope/client-tool/
compaction, and quota regression suites passed. The selected mocked E2E
streaming set passed, including the exact Codex 0.149 Local streaming E2E.

The exact Local streaming E2E used a disposable PostgreSQL database and
loopback-mocked Local HTTP response. It observed one finalized strict-bounded
accounting row, zero pending reservation state, canonical candidate
preservation, and no external-tool facts. No Local Coding, Qwen, provider, or
protected process was contacted.

Verification commands observed passing:

```text
python -m ruff check app tests
python -m compileall -q app tests
python -m pytest -q tests/unit/test_responses_codex_streaming_tools.py
python -m pytest -q tests/unit/test_provider_streaming_sse.py tests/unit/test_openai_provider_streaming.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py
python -m pytest -q tests/unit/test_responses_codex_envelope.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_compaction.py tests/unit/test_v1_responses_quota.py
python -m pytest -q tests/e2e/test_openai_python_client_responses.py -k 'codex_0149 or streaming_text or generic_responses_stream'
git diff --check
```

No required test was skipped or environment-blocked in the final CI run. The
local preflight without PostgreSQL skipped the DB E2E; it was then rerun
successfully against the named disposable database.

## Final-head checks

All ten checks passed on implementation head `a72d907...` before report
publication, and the report-only commit is required to rerun them on its own
head:

```text
Analyze (python)                 pass
Analyze Python                   pass
Analyze (javascript-typescript)  pass
CodeQL                           pass
Unit, lint, and migration head   pass
PostgreSQL integration tests     pass
OpenAI-compatible E2E tests      pass
Playwright browser smoke         pass
Docker Compose smoke             pass
Documentation hygiene            pass
```

## Cleanup and limitations

The disposable database `slaif_gateway_158a_test` was dropped with the
explicit PostgreSQL owner boundary. The task roots
`/tmp/slaif-158a-check.flw7PP` and `/tmp/slaif-158a-check.zgGxNz` were removed
and verified absent. No protected runtime reference or credential was created.

Documentation records the exact pair-local stream state machine, strict usage
and accounting behavior, default-false containment, unknown-event rejection,
and transient content handling. This result is mocked/state-machine
conformance only. It does not claim second-turn admission, replay ownership,
protected Gateway→Local→Qwen qualification, deployment, release, or
production readiness.
