# OAP 020-b execution report

Implementation head SHA: 4d8cc6d7f08574768d9b3c042943d0c6b5f36268
Report publication commit: SELF

## Delivery

- Existing PR amended: [#246](https://github.com/ulfe-lmi/slaif-api-gateway/pull/246)
- Title: `[OAP 020] Qualify generic Chat and Responses backends`
- Branch: `oap/020-generic-backend-chat-responses-conformance`
- Base: `main`
- Implementation head: `4d8cc6d7f08574768d9b3c042943d0c6b5f36268`
- PR remains open and unmerged; auto-merge was not enabled.
- Activated `020-b` and the exact order file were committed and pushed. Prior
  `020-a` order/report files were not modified.

## Required closures

The `chat_and_responses_vision_inline_v1` preset now enables only
`chat_image_inputs=true` and Responses `image_input=true` alongside its text,
stateless, streaming, and local-function controls. Broad `chat_multimodal` and
Responses `multimodal` remain false, as do file, audio, generation, storage,
background, hosted-tool, and Codex capabilities.

The existing official OpenAI Python-client E2E files now contain four focused
generic-provider cases using a real local gateway app, PostgreSQL setup, a
generic provider slug/base URL, configured route/pricing/key facts, and mocked
upstream responses:

- Chat non-streaming with two inline images and a local function tool,
  substitution to `qwen/a`, server-side generic bearer substitution, header
  isolation, and finalized usage.
- Chat SSE streaming with terminal usage and finalized accounting.
- Stateless Responses non-streaming with two inline images and a local
  function declaration/call output.
- Responses typed SSE streaming plus an official-client remote-image rejection
  that made zero upstream calls and zero reservation/ledger mutations.

The PostgreSQL gateway matrix executes actual ASGI gateway requests against
the real route, pricing, quota, and accounting services with a mocked generic
adapter. It proves Chat and Responses success with exact provider/model/
endpoint facts, finalized rows and zero reserved counters; generic remote
image rejection before provider/accounting mutation; a finite request quota
rejection after finalized usage; and a provider failure that produces a failed
accounting row without a false zero-cost success. Durable rows contain no
prompt/image/tool/key canaries or raw request/response columns.

## Verification evidence

Local focused unit and static checks:

- `.venv/bin/python -m pytest -q tests/unit/test_openai_compatible_setup.py tests/unit/test_openai_compatible_request_boundary.py tests/unit/test_v1_chat_completions_forwarding.py tests/unit/test_v1_chat_completions_streaming.py`: 56 passed.
- `.venv/bin/python -m pytest -q tests/e2e/test_openai_python_client_chat.py -k generic tests/e2e/test_openai_python_client_responses.py -k generic`: 4 passed.
- `.venv/bin/ruff check` on changed application and focused test files: passed.
- `python -m compileall -q` on changed application and focused test files: passed.
- `git diff --check`: passed.
- Alembic head remained the single `0015_external_tool_exclusive_fence` head.

Final disposable PostgreSQL verification:

- `.venv/bin/python -m pytest -q tests/integration/test_openai_compatible_setup_postgres.py tests/integration/test_openai_compatible_conformance_postgres.py`: 5 passed.
- The run used a generated database whose name contained `test`, a temporary
  local `ubuntu` role only when needed, and a Unix-socket asyncpg URL. The
  database and temporary role were dropped in cleanup. No production
  `DATABASE_URL` was used or modified.
- The gateway matrix left two finalized success ledgers and one failed
  provider-error ledger, no pending reservations, and no duplicate success
  ledger. The remote-image path created neither reservation nor ledger and did
  not call the adapter.

GitHub checks for implementation head `4d8cc6d7f08574768d9b3c042943d0c6b5f36268`
all passed:

- Unit, lint, and migration head: 3,223 passed, 11 warnings; Ruff passed.
- PostgreSQL integration tests: passed.
- OpenAI-compatible E2E tests: passed.
- Playwright browser smoke: passed.
- Docker Compose smoke: passed.
- Documentation hygiene: passed.
- CodeQL JavaScript/TypeScript and Python analyses: passed.

No full HPC/128-worker run was required or performed by this order. No real
provider calls, Qwen/vLLM/Codex qualification, production access, or real
email delivery occurred. No secrets, prompts, responses, image values, tool
arguments/results, cookies, client Authorization values, or internal headers
were logged or committed; the tests assert server-side bearer substitution and
durable privacy boundaries. Documentation now describes the result honestly as
`mocked_conformance`, with live targets reserved for objectives 022–023.

## Completion boundary

The implementation is pushed to PR #246. This coding round does not merge the
PR, enable auto-merge, select a subsequent order, or make release or
production-certification claims. The report publication commit must be the
final commit of this round and must change only this report file.
