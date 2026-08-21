# OAP Work Order — 022-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Build the exact Codex 0.148/Qwen3.8-27B text qualification candidate and its
bounded live verifier. Prove the candidate locally through Codex, SLAIF, and a
numeric-loopback mock, but do not register or claim it as qualified until the
required non-production LAN vLLM phase gate succeeds. This advances the first
named operator-defined backend profile without turning a missing human target
into fabricated evidence.

Start implementation after one bounded read of the Objective 021 registry/
renderer, existing Codex capture/verifier helpers, Responses Codex gates, and
generic provider adapter. Do not repeat broad repository or test discovery.

## Verified activation state and live authorization

- Canonical `main` is
  `4ad592e190f6bfa1a8878814519569b6ce7e59a2`, merge of Objective 021 PR #247.
- Objectives 018–021 are merged. Generic OpenAI-compatible providers have
  mocked Chat/stateless-Responses conformance and the server-owned Codex profile
  framework; only the legacy OpenAI/GPT-5.6/Codex-0.147 profile is registered.
- Installed local binary reports `codex-cli 0.148.0`. Strategic inspection has
  already established the exact bundled catalog root `{"models":[...]}` and
  root config key `model_catalog_json`; do not repeat broad catalog dumping.
- The human explicitly chose bounded live LAN E2E as a prerequisite for both
  Qwen reference profiles and ordered this plan implemented on 2026-08-21. That
  authorizes one bounded non-production call only when the exact target and
  credential are supplied through the variables below. It does not authorize
  network scanning, a public target, production credentials, or printing either
  value.
- Exact live variables are
  `SLAIF_QWEN38_TEXT_BASE_URL` and `SLAIF_QWEN38_TEXT_API_KEY`. Neither name is
  currently present in the process environment or repository `.env`; no live
  call is currently possible. Do not add them to files, infer them from another
  credential, or fall back to OpenAI/OpenRouter.
- If both variables are still absent, complete the candidate/mock/verifier
  slice, keep the production registry unchanged, report `live_target_absent`,
  signal completion, and leave this one PR open for continuation 022-b. If both
  are present, validate them without reflection and perform the exact bounded
  live gate below.
- No Objective 022 branch/PR exists. Dependabot #224 is unrelated.

## PR contract

- Create `oap/022-qwen38-text-codex-qualification` from current `main`.
- Create exactly one ready PR titled
  `[OAP 022] Qualify Qwen3.8 text for Codex`, base `main`.
- Continuations amend this PR. Coding agent never merges or enables auto-merge.

## Allowed paths

Use the smallest necessary subset of:

```text
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/providers/openai.py
app/slaif_gateway/providers/openai_compatible.py
app/slaif_gateway/providers/streaming.py
scripts/capture_codex_protocol.py
scripts/verify_qwen38_text_codex.py
tests/fixtures/codex/0.148.0/qwen3.8-27b-text-api-key-responses.json
tests/unit/test_codex_profile_registry.py
tests/unit/test_codex_qualification.py
tests/unit/test_codex_protocol_capture.py
tests/unit/test_qwen38_text_codex_verifier.py
tests/unit/test_responses_codex_envelope.py
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_route_capabilities.py
tests/unit/test_openai_provider_adapter.py
tests/unit/test_openai_provider_streaming.py
tests/unit/test_documentation_contract_drift.py
README.md
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/openai-compatibility.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/security-model.md
oap/active
oap/orders/022-a-qwen38-text-codex-qualification.md
oap/reports/022-a-qwen38-text-codex-qualification.md
```

One exact adjacent runtime/test path proven necessary by the captured 0.148
wire shape is allowed and must be reported. Do not touch migrations, admin/RBAC,
hosted-tool policy, or unrelated providers.

## Exact candidate profile

Create one frozen server-owned candidate definition with these exact facts:

```text
profile ID: qwen3.8-27b-text-codex-0.148-v1
CLI: 0.148.0
public model: qwen3.8-27b-text
upstream model: qwen3.8-27b
provider kind: openai_compatible
provider slug: any exact configured slug (None in the definition)
wire API/endpoints: Responses; /v1/responses only
context window: 150000
default/max output: use one conservative exact pair proven by the candidate
client-local auto-compaction threshold: 125000
input modalities: text only
catalog source: replacement
live qualification required: yes
```

- The replacement catalog must be canonical, credential-free, and compatible
  with the Objective 021 finite schema. Use Responses-lite and only the exact
  safe metadata needed by Codex 0.148.
- Target an ordinary serial shell/function tool loop. Set search, parallel tool
  calls, remote compaction, encrypted-reasoning replay, image input, hosted
  tools, MCP/connectors, apps/plugins injection, and freeform apply-patch false
  or absent unless this objective separately proves an exact safe path. Do not
  claim generic Qwen/Codex compatibility.
- Required route gates may include only the exact captured needs among
  `codex_request_envelope`, `codex_client_tools`, and
  `codex_streaming_tool_events`; no `codex_compaction`, image, or encrypted
  reasoning gate.
- Keep the candidate outside `CODEX_PROFILE_REGISTRY` and unavailable to
  route declarations/CLI/admin until the live phase succeeds. It may be exposed
  only to pure artifact/capture/verifier code and tests. If a qualification-
  requirement field is needed to make this invariant structural, add it with
  legacy-compatible tests; no arbitrary admin qualification state.

## Hermetic Codex 0.148 phase

Using an isolated temporary Codex home/workspace, a numeric-loopback mock, and
only dummy gateway/provider keys:

1. Verify the exact binary version before execution and fail closed on drift.
2. Write the generated base/profile/catalog artifacts with private modes; prove
   Codex loads the exact public model and sends only to the SLAIF/loopback base.
3. Capture the initial Responses request, one ordinary serial shell/function
   tool call, tool result continuation, streaming completion, and safe final
   marker. Do not enable search, MCP, hosted tools, parallel calls, remote
   compaction, image input, encrypted reasoning replay, or provider-managed
   state.
4. Normalize the capture through the Objective 021 finite structural sanitizer.
   Commit only the bounded structural fixture/digest and safe catalog facts.
   Raw prompts, output, reasoning, tool description/schema/arguments/result,
   request/response bodies, auth, headers, URLs, paths, environment values, and
   process logs remain ephemeral and are deleted.
5. If Codex 0.148 reveals a wire field/event that the gateway rejects, implement
   only that exact captured shape behind the existing explicit Codex route/key
   gates, with negative tests. Do not make arbitrary generic traffic pass.

The hermetic phase proves client/profile/gateway protocol shape, not Qwen/vLLM
model behavior or live qualification.

## Bounded live verifier

Add `scripts/verify_qwen38_text_codex.py` and pure focused tests. The script must:

- accept no secret/URL command-line argument; read only the two exact env vars;
- require both-or-neither, reject redirects/credentials/query/fragment, and
  allow only an explicitly private/loopback LAN HTTP(S) `/v1` target; never
  reflect the URL, hostname, key, response body, prompt, or tool data;
- use an isolated disposable PostgreSQL/Redis/gateway namespace and temporary
  Codex home/workspace, collision-safe ports/names, private file modes, dead
  external proxies, and cleanup only resources it created;
- configure one `openai_compatible` provider with a dedicated server-side key
  env-var, exact public/upstream model route, explicit candidate gates and
  limits, finite standard gateway key, local-zero or explicit reviewed pricing,
  no allow-all, no hosted/external tools, and no image support;
- make the only backend-bound model interaction needed for Codex to execute one
  ordinary local file-marker tool loop and return one final marker; cap wall
  time, requests, tokens, output, tool calls, and cost; do not retry or follow
  redirects;
- prove route/provider/model identity, gateway-key auth and server-side backend
  credential substitution, no client key forwarded, successful final/tool
  markers, final usage, zero pending reservation, exact PostgreSQL ledger/key
  counters, following quota rejection when the bounded key is exhausted, and
  no prompt/output/tool/reasoning/credential/backend-URL canary in durable
  application tables or retained logs;
- emit only fixed booleans/counts/digests and a final safe pass/fail marker.

If the vLLM Responses usage or event shape is insufficient, fail safely and
leave the candidate unregistered. Do not patch around missing final usage or
accounting truth.

## Non-goals

No production profile registration without live success, vision/image work,
remote URL fetch, Chat translation, search/hosted/MCP tools, parallel tools,
freeform apply-patch, encrypted reasoning replay, remote compaction, recurring
budgets, schema migration, production/release/compliance claim, public backend,
or broad local suite.

## Acceptance and focused verification

1. Exact candidate facts/artifacts parse in Codex 0.148 hermetically and never
   become selectable/qualified without the live gate.
2. Sanitized structural fixture/digest is deterministic and contains no raw
   content, secret, URL, header, environment, workspace path, or arbitrary
   metadata.
3. Exact captured 0.148 envelope/serial tool/stream shapes pass only under
   explicit route+key gates; adjacent unknown/widened shapes fail pre-provider.
4. The live verifier has pure negative tests for env/URL/version/timeouts/
   redirects/usage/accounting/privacy/cleanup and does not reveal inputs.
5. If live variables are absent, report that fact only and do not register the
   candidate. If present, the bounded live phase must pass every marker and
   accounting/privacy assertion before registration/live qualification.
6. Run only focused candidate/capture/qualification/verifier/runtime tests,
   scoped Ruff, compileall, `git diff --check`, and routine GitHub CI. No full
   local suite.

## Documentation and publication

Document the exact candidate/evidence state and the distinction between local
protocol conformance and live Qwen qualification. Do not advertise the profile
while unregistered.

Commit this exact order and `oap/active=022-a`, push implementation, create the
one PR, and publish one immutable
`oap/reports/022-a-qwen38-text-codex-qualification.md` report-only final commit
with literal implementation head and `Report publication commit: SELF`. State
whether the live variables were absent/present and whether a live call ran,
without values. Report exact focused commands, fixture/artifact digest, Codex
version, gates, negative/privacy/accounting evidence, changed runtime shapes,
checks, and remaining qualification blocker. Verify remote head, send exact
response-FIFO `OK`, and return to one control wait. Never merge.
