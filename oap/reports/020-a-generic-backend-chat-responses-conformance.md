# OAP 020-a execution report

Implementation head SHA: ba637ad4c9481aeac041e6bddff5476ab3bf18b3
Report publication commit: SELF

## Delivery

- PR: [#246](https://github.com/ulfe-lmi/slaif-api-gateway/pull/246)
- Title: `[OAP 020] Qualify generic Chat and Responses backends`
- Branch: `oap/020-generic-backend-chat-responses-conformance`
- Base: `main`
- PR state: open, ready for review; not merged and auto-merge not enabled.
- The active order `020-a` and unchanged `oap/active` were committed and pushed
  on the objective branch.

## Scope implemented

Added a pure provider-aware request boundary for generic
`provider_kind=openai_compatible` routes, after route/capability enforcement
and before request body forwarding, Redis, quota, pricing, or provider work.
It accepts bounded inline PNG/JPEG/WebP/GIF data URLs and rejects remote URLs,
file IDs, malformed/external image references, and credential/fragment-bearing
alternatives with safe OpenAI-shaped errors. Built-in OpenAI and OpenRouter
routes are unchanged, and tools/schemas are not recursively scanned.

Added the exact explicit setup preset
`chat_and_responses_vision_inline_v1`. It enables only the bounded Chat and
Responses inline-image/multimodal capabilities; files, audio, remote images,
hosted tools, and Codex capabilities remain disabled.

Added mocked generic Chat and Responses conformance coverage for non-streaming
and SSE/typed-SSE paths, local function tools, two inline images, model
substitution, generic provider routing, gateway-bearer substitution, and
header/redirect/privacy boundaries. Added focused PostgreSQL accounting and
privacy coverage and classified the result as `mocked_conformance`; live
vLLM/Qwen targets remain objectives 022–023.

No schema migration or new public endpoint was introduced. Documentation and
the provider setup UI/CLI were updated for the bounded status and preset.

## Tests and verification

Local focused tests, all passed:

- `tests/unit/test_openai_compatible_request_boundary.py`,
  `tests/unit/test_openai_compatible_setup.py`, and
  `tests/unit/test_v1_chat_completions_forwarding.py`: 42 passed.
- `tests/unit/test_v1_chat_completions_streaming.py -k forwards_chunks_and_finalizes_after_usage`: 1 passed.
- `tests/unit/test_v1_responses_quota.py -k 'generic_responses or streaming_responses_path_finalizes_from_completed_usage'`: 3 passed.
- `tests/unit/test_cli_providers.py tests/unit/test_admin_provider_config_actions_routes.py -k 'provider or discovery or setup'`: 21 passed.
- `tests/unit/test_responses_codex_multiturn_replay.py -k route_mismatch_denial_precedes_redis_pricing_quota_and_provider`: 1 passed.
- Ruff on changed application/tests: passed.
- Python compile checks on changed application/new integration code: passed.
- `git diff --check`: passed.
- Jinja template parse: passed.
- `python -m alembic heads`: one head, `0015_external_tool_exclusive_fence`.

Disposable PostgreSQL verification passed:

- `tests/integration/test_openai_compatible_setup_postgres.py`: 3 passed.
- `tests/integration/test_openai_compatible_conformance_postgres.py`: 1 passed.
- A temporary local PostgreSQL database was created with a temporary `ubuntu`
  login role when needed, used through a Unix socket, and dropped afterward;
  the temporary role was removed afterward. No `DATABASE_URL` was targeted.
- The accounting assertion covered exact generic provider/model/endpoint/route
  facts, counters, pricing, one finalized ledger row, no pending reservation,
  no duplicate ledger, and absence of sensitive content in ledger/audit DTO
  data. A rejected remote image performed no reservation, ledger, or provider
  call.

GitHub checks for implementation head `ba637ad4c9481aeac041e6bddff5476ab3bf18b3`
all passed:

- Unit, lint, and migration head: 3,223 passed, 11 warnings.
- PostgreSQL integration tests: passed.
- OpenAI-compatible E2E tests: passed.
- Playwright browser smoke: passed.
- Docker Compose smoke: passed.
- Documentation hygiene: passed.
- CodeQL JavaScript/TypeScript and Python analyses: passed.

The first CI attempt exposed one existing unit-test route stub without the new
`provider_kind` attribute. The bounded repair treats absent `provider_kind` as
non-generic, preserving existing test doubles and built-in behavior; the
focused regression and complete CI rerun then passed. No other failure remains.

No full HPC/128-worker run was required by this order and none is claimed.
No real provider calls, production access, or real email delivery occurred.
No secrets, prompts, responses, tool arguments/results, cookies, client
Authorization values, internal headers, or sensitive image values were logged
or committed. Generic forwarding substitutes the provider bearer server-side;
client cookies and Authorization are not forwarded, and redirects are not
enabled as an escape hatch.

## Completion and merge boundary

The implementation is pushed to PR #246. This coding round does not merge the
PR, enable auto-merge, select a subsequent order, or make release/production
claims. The report publication commit is intended to be the final commit of
this round and changes only this report file.
