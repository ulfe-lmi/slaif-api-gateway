# OAP Work Order — 020-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Prove that operator-defined `openai_compatible` backends satisfy SLAIF's
existing Chat Completions and stateless Responses contracts rather than merely
receiving HTTP. Add the first inline-image setup preset without imposing a
Qwen-specific image-count ceiling. Remote image URLs remain denied for this
backend category so a LAN inference server does not become a provider-side URL
fetch/SSRF surface.

Perform one bounded inspection of the existing Chat/Responses route resolution,
pre-Redis ordering, image validators, generic adapter, setup presets, and exact
test helpers, then implement. Do not repeat broad discovery or run broad local
suites.

## Verified activation state

- Canonical `main` is
  `4267d7b55d79b5a707f216524ad72077865608de`, merge of Objective 019 PR #245.
- Objectives 000–019 are merged. Objective 018 provides generic runtime/secret/
  URL safety; Objective 019 provides bounded discovery and confirmed atomic
  setup with conservative text presets and explicit local pricing.
- No Objective 020 branch/PR exists. Dependabot #224 remains unrelated.
- Existing gateway APIs already implement bounded Chat text/function/image and
  stateless Responses text/function/image/typed-SSE behavior behind route
  capabilities. This objective must reuse those contracts, not introduce new
  request fields or endpoint semantics.
- Existing global image count/byte/MIME/data-URL caps remain authoritative. The
  gateway currently also permits remote image URLs on selected built-in routes;
  generic providers require an additional route/provider boundary before Redis,
  quota mutation, or forwarding.

## PR contract

- Create `oap/020-generic-backend-chat-responses-conformance` from current main.
- Create exactly one ready PR titled
  `[OAP 020] Qualify generic Chat and Responses backends`, base `main`.
- Continuations amend that PR. Coding agent never merges or enables auto-merge.

## Allowed paths

Use the smallest necessary subset of:

```text
app/slaif_gateway/services/openai_compatible_request_boundary.py
app/slaif_gateway/services/openai_compatible_setup.py
app/slaif_gateway/services/chat_completion_gateway.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/chat_completion_route_capabilities.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/request_policy.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/providers/openai.py
app/slaif_gateway/providers/openai_compatible.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/providers.py
app/slaif_gateway/web/templates/providers/discover_preview.html
tests/unit/test_openai_compatible_request_boundary.py
tests/unit/test_openai_compatible_setup.py
tests/unit/test_v1_chat_completions_forwarding.py
tests/unit/test_v1_responses_quota.py
tests/unit/test_openai_provider_adapter.py
tests/unit/test_openai_provider_streaming.py
tests/unit/test_cli_providers.py
tests/unit/test_admin_provider_config_actions_routes.py
tests/integration/test_openai_compatible_conformance_postgres.py
tests/e2e/test_openai_python_client_chat.py
tests/e2e/test_openai_python_client_responses.py
tests/browser/test_admin_dashboard_smoke.py
README.md
AGENTS.md
docs/accounting.md
docs/configuration.md
docs/database-schema.md
docs/deployment.md
docs/openai-compatibility.md
docs/provider-forwarding-contract.md
docs/compatibility-matrix.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/020-a-generic-backend-chat-responses-conformance.md
oap/reports/020-a-generic-backend-chat-responses-conformance.md
```

One exact adjacent helper/test path is allowed when required and must be
reported. No schema migration or new public endpoint is authorized.

## Required implementation

### 1. Generic provider request boundary

- Add one pure provider-aware request-boundary service called after route
  resolution/capability enforcement but before upstream-body construction,
  Redis reservation, pricing lookup, PostgreSQL reservation, or provider work.
- For routes whose `provider_kind=openai_compatible` and provider slug is not
  built-in `openai`/`openrouter`, inspect only endpoint-defined image URL control
  positions:
  - Chat user content `image_url.url`;
  - Responses `input_image.image_url`.
- Permit bounded `data:image/png|jpeg|webp|gif;base64,...` values already
  accepted by the existing endpoint validator. Reject `http`/`https`, URL-like
  alternatives, credentials/fragments, file IDs, malformed positions, and any
  other external fetch marker with a safe OpenAI-shaped error identifying the
  field, never the value.
- Do not recursively keyword-scan function schemas/descriptions/tool payloads.
  Existing endpoint validators remain authoritative for shape/size/secret caps.
- Built-in OpenAI/OpenRouter behavior must remain unchanged.
- Prove generic remote-image denial occurs before Redis/quota/provider mutation.

### 2. Inline-vision setup preset

Add exact preset:

```text
chat_and_responses_vision_inline_v1
```

- It creates the same independent Chat and `/v1/responses` routes as the
  combined text preset, plus only Chat image-input/multimodal and Responses
  image-input capabilities required by current runtime. Streaming and local
  function tools remain explicit existing checkboxes.
- It does not grant file/audio input, image generation, remote URL fetch,
  hosted tools, external MCP, storage/state/background, Codex capabilities, or
  any unimplemented media output.
- Do not add a route/profile-specific image count. Multiple inline images are
  allowed up to existing global endpoint caps; changing those caps is out of
  scope.
- Expose the preset in the shared admin and CLI setup surfaces without JSON.
  Routes still default disabled unless explicitly enabled as unqualified.

### 3. Generic adapter conformance

Using mocked generic upstreams and ordinary gateway keys/routes/pricing, prove:

- Chat non-stream text success and SSE text success with provider usage;
- current bounded local Chat function-tool declaration/result behavior when
  selected by route capability, without gateway tool execution;
- stateless Responses non-stream text and typed-SSE text success;
- current bounded local Responses function-tool shape only where already
  supported and explicitly enabled;
- inline Chat and Responses data-image forwarding, including at least two
  images in one request within existing global caps;
- resolved upstream model substitution, exact generic provider slug, bearer
  substitution, no client Authorization/cookies/internal headers, no redirects,
  safe response/error normalization, and no OpenAI hosted/OpenRouter cost
  inheritance.

Do not accept vLLM-only `extra_body` fields or relax unknown-field policy.
Do not claim endpoint/model families not directly tested.

### 4. PostgreSQL accounting/privacy proof

- Add one focused disposable-DB gateway/integration matrix for generic Chat and
  Responses successful finalization, zero pricing and explicit pricing,
  streaming final usage, quota exhaustion/following rejection, provider error,
  and missing-usage behavior under existing contracts.
- Assert exact provider/model/endpoint/route IDs, used/reserved counters, pricing
  basis, one ledger per request, no pending reservations, and no duplicate
  charge.
- Assert prompts, completions, image data/base64, tool schemas/arguments/results,
  provider key, client key, Authorization, raw request/response, and arbitrary
  metadata never persist in ledgers/audits/log-facing DTOs.
- Remote image URL rejection must create no reservation/ledger/provider call.

### 5. Compatibility status

- Add a safe route/setup summary marking these server-generated profiles as
  `mocked_conformance` only. It is not a live vLLM/Qwen/Codex qualification.
- Current docs/UI must say Objective 020 proves the gateway/provider-category
  contract with mocks; Objectives 022–023 own named live targets.

## Non-goals

No real LAN/OpenAI/OpenRouter/vLLM call, Codex envelope/profile, encrypted
reasoning, compaction, remote image URL, file IDs, provider URL fetch, hosted
tool, MCP, automatic discovery, health/failover/load balancing, new endpoint,
schema migration, production access, or universal OpenAI compatibility claim.

## Acceptance and focused verification

1. The vision-inline preset is canonical, no-JSON, multiple-image-capable under
   existing global caps, and grants nothing else.
2. Generic remote image URLs fail before Redis/quota/provider; two inline images
   pass through mocked Chat and Responses routes without local content storage.
3. Official OpenAI-client mocked E2E proves generic Chat/Responses non-stream/
   stream and selected local-function behavior.
4. Focused PostgreSQL tests pass with zero skips and prove accounting/privacy/
   failure invariants.
5. Existing built-in OpenAI/OpenRouter, hosted-web-search denial boundary, route
   presets, admin/CLI setup, and docs-drift focused regressions pass.
6. Run scoped Ruff, compileall, Jinja parse, Alembic head, diff check, and only
   the smallest affected browser test. No complete local suite; GitHub CI is
   broad evidence.

## Publication

Update every current-facing contract in allowed paths, preserving historical
evidence and README branding. Commit this exact order and `oap/active=020-a`,
push implementation, create the one PR, and publish one immutable
`oap/reports/020-a-generic-backend-chat-responses-conformance.md` in a final
report-only commit with literal implementation head and
`Report publication commit: SELF`. Verify remote head/check state, send exact
FIFO `OK`, and return to one control wait. Never merge.
