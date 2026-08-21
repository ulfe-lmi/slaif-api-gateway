# OAP 018-a — Generic OpenAI-compatible backend runtime

## Objective and business reason

Create the runtime foundation for any number of operator-defined,
bearer-authenticated OpenAI-compatible backends (including LAN vLLM) without
adding a one-off provider module per server and without weakening SLAIF's
request policy, provider-secret isolation, PostgreSQL accounting, or honest
compatibility claims. This objective creates the provider/runtime contract
only; guided discovery and model setup belong to Objective 019.

Begin implementation after one bounded inspection of the named symbols. Do not
repeat broad repository, migration-style, environment, or test discovery. Read
another file only when a concrete symbol or failing focused test requires it.

## Verified state at activation

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Base/default branch: `main` at
  `51caf080ec94c9f25808a1b20db6c1eff071bfe4`, merge of PR #243.
- Objectives 000–017 are merged and terminal. Objective 017's final PR #242
  merged as `e7fd9ce95b0bfcf9630635aaca5d3f5a853fbacb`; its immutable 017-f report
  exists on `main`.
- PR #243 reconciled current documentation and merged with all ten checks green.
- The only open PR is unrelated Dependabot PR #224.
- No branch or PR exists for Objective 018.
- `provider_configs` already stores an arbitrary unique provider name,
  `kind=openai_compatible`, base URL, API-key environment-variable name,
  timeout, retries, and enabled state. Model routes already join provider names
  to configured routes/pricing.
- `RouteResolutionResult` already carries configured base URL, secret env-var
  name, timeout, and retries, but not provider kind.
- `get_provider_adapter()` still rejects every provider identity other than
  literal `openai` and `openrouter`.
- `OpenAIProviderAdapter` already owns the canonical OpenAI-shaped endpoint,
  stream, usage, safe-header, and error behavior that the generic adapter should
  reuse rather than duplicate. `OpenRouterProviderAdapter` retains its separate
  provider-reported-cost behavior.

## PR and branch contract

- PR mode: `CREATE_NEW_PR`.
- Create branch `oap/018-generic-openai-compatible-backend-runtime` from the
  verified current `origin/main`.
- Create exactly one ready-for-review PR titled
  `[OAP 018] Add generic OpenAI-compatible backend runtime` with base `main`.
- Do not create a second PR, merge, or enable auto-merge.

## Allowed paths

Implementation may change only the smallest necessary subset of:

```text
app/slaif_gateway/providers/factory.py
app/slaif_gateway/providers/openai.py
app/slaif_gateway/providers/openai_compatible.py
app/slaif_gateway/providers/headers.py
app/slaif_gateway/schemas/routing.py
app/slaif_gateway/services/route_resolution.py
app/slaif_gateway/services/provider_config_service.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/providers.py
app/slaif_gateway/web/templates/providers/create.html
app/slaif_gateway/web/templates/providers/edit.html
app/slaif_gateway/web/templates/providers/detail.html
tests/unit/test_provider_factory.py
tests/unit/test_openai_provider_adapter.py
tests/unit/test_openai_provider_streaming.py
tests/unit/test_provider_config_service.py
tests/unit/test_route_resolution_service.py
tests/unit/test_cli_providers.py
tests/unit/test_admin_provider_config_actions_routes.py
tests/unit/test_admin_catalog_templates_safety.py
tests/e2e/test_openai_python_client_chat.py
README.md
AGENTS.md
docs/configuration.md
docs/database-schema.md
docs/deployment.md
docs/openai-compatibility.md
docs/provider-forwarding-contract.md
docs/compatibility-matrix.md
docs/security-model.md
oap/active
oap/orders/018-a-generic-openai-compatible-backend-runtime.md
oap/reports/018-a-generic-openai-compatible-backend-runtime.md
```

If a concrete import/type/test requires one adjacent file, keep it minimal and
explain it in the report. No migration/version file is authorized: this
objective must use the existing provider-config schema.

## Required implementation

1. **Provider identity versus adapter kind**
   - Add provider kind to the safe route-resolution DTO and populate it from the
     selected `ProviderConfig`.
   - Preserve the configured provider slug throughout provider errors, pricing,
     ledger/audit facts, route policy, and logs.
   - Literal `openrouter` must still use `OpenRouterProviderAdapter` and its
     existing cost semantics. Literal `openai` must preserve exact current
     behavior, including the sole hosted-web-search contract.
   - Any other configured provider with exact kind `openai_compatible` may use a
     generic OpenAI-compatible adapter. A bare unconfigured string, unknown
     kind, disabled/missing provider row, or incomplete route facts remains
     unsupported/fail-closed.

2. **Adapter reuse without provider impersonation**
   - Reuse/refactor `OpenAIProviderAdapter`; do not copy its large endpoint and
     streaming implementation.
   - The generic adapter must expose its configured provider slug rather than
     claiming `openai`, while preserving canonical paths, body model
     substitution, safe response parsing, timeout/retry behavior, and header
     allowlists.
   - It may serve only gateway endpoint methods that already exist and only
     after an explicit matching route/capability/pricing decision. It adds no
     new public endpoint or accepted client request field.
   - Generic provider identity must never satisfy the exact `provider=openai`
     hosted `web_search` contract or inherit OpenRouter provider-cost authority.

3. **Bearer secret and URL contract**
   - Require a syntactically valid environment-variable name for every generic
     backend. Store/read only its name in PostgreSQL; the factory reads the
     value server-side and missing/empty values fail closed.
   - Continue reserving client `OPENAI_API_KEY` for SLAIF gateway keys; it may
     not be selected as a backend-secret env-var name.
   - Canonicalize/validate provider base URLs: exact `http` or `https`, host
     required, valid optional port, path exactly `/v1` with optional trailing
     slash canonicalized, and no userinfo, query, fragment, whitespace, or
     controls.
   - `https` uses normal certificate verification. Never add `verify=false` or
     a per-provider TLS bypass.
   - Plain `http` requires an explicit `confirm_insecure_http` input plus a
     non-empty audit reason in service, CLI, and admin create/edit paths. Make
     the warning clear that bearer credentials and request content traverse the
     LAN unencrypted and that firewall/reverse-proxy isolation is operator-owned.
   - Disable redirect following for generic provider requests so a backend
     credential or request body cannot move to another origin.

4. **Secret/content/security invariants**
   - Never accept a provider secret value in CLI/admin/JSON, never emit it in
     errors/audit/HTML/logs, and never forward the client Authorization header.
   - Preserve no-prompt/completion/tool/media storage defaults and safe bounded
     diagnostics.
   - Do not inspect or call the human's existing Qwen/vLLM LAN configurations,
     environment-secret values, or services in this objective. Use mocks only.

## Explicit non-goals

- No `/v1/models` provider discovery or wizard (Objective 019).
- No new Chat/Responses/vision compatibility claim or generic E2E phase gate
  (Objective 020).
- No Codex profile changes (Objectives 021–023).
- No anonymous/no-auth mode, YAML/JSON configuration file, schema migration,
  load balancing, fallback, health polling, GPU/systemd control, remote image
  fetching, hosted tools, MCP/connectors, provider-state widening, arbitrary
  vLLM extra fields, production deployment, or real network/provider call.

## Acceptance criteria

1. A configured provider such as `lan-qwen-text` with
   `kind=openai_compatible`, canonical base URL, and present secret env var
   resolves to a generic adapter whose provider name remains
   `lan-qwen-text`.
2. Existing OpenAI and OpenRouter factory/forwarding tests prove no regression.
3. Unknown kind, unconfigured/bare provider, missing env var, invalid URL,
   unconfirmed HTTP, redirect response, and any attempt to use client
   `OPENAI_API_KEY` as backend secret fail safely without provider work or
   secret/content disclosure.
4. Admin and CLI accept confirmed HTTP only with an audit reason and display
   env-var names/warnings only.
5. No migration exists; PostgreSQL provider/model/pricing truth and every
   existing route/capability/accounting gate remain unchanged.
6. Documentation states that this is a runtime foundation, not universal
   vLLM/Codex/backend qualification.

## Focused verification

Run, at minimum, the affected focused tests (adjust exact filenames only for
actual new files):

```bash
python -m pytest -q \
  tests/unit/test_provider_factory.py \
  tests/unit/test_openai_provider_adapter.py \
  tests/unit/test_openai_provider_streaming.py \
  tests/unit/test_provider_config_service.py \
  tests/unit/test_route_resolution_service.py \
  tests/unit/test_cli_providers.py \
  tests/unit/test_admin_provider_config_actions_routes.py \
  tests/unit/test_admin_catalog_templates_safety.py
python -m ruff check <changed Python files and focused tests>
python -m compileall -q <changed Python modules>
git diff --check
alembic heads
```

Do not run a complete local unit, integration, E2E, browser, or full-matrix
suite. Add a focused mocked official-client E2E only if the runtime factory
cannot otherwise be proven through the existing focused provider pipeline;
explain that decision. Routine broad GitHub CI remains required.

## Documentation requirements

Update current-facing contracts to distinguish:

- built-in OpenAI;
- built-in OpenRouter;
- operator-defined `openai_compatible` backend instances;
- configured runtime foundation versus endpoint/model/Codex qualification;
- bearer env-var isolation and explicit LAN HTTP risk;
- no generic hosted-tool/provider-cost/compatibility inheritance.

Preserve the README branding block and all historical release/review evidence.

## Publication and report duties

- Commit this activated order and exact `oap/active=018-a` unchanged with the
  implementation branch.
- Push all implementation commits and create the single PR.
- Inspect current PR checks and repair only in-scope failures.
- Publish exactly one immutable
  `oap/reports/018-a-generic-openai-compatible-backend-runtime.md` report in a
  final report-only commit. Record literal implementation head SHA and
  `Report publication commit: SELF`; only that report file may change in the
  report commit.
- Report exact tests/counts, skipped/not-run evidence, diff scope, security and
  privacy negatives, docs impact, PR URL/head/base, and current check state.
- Push and verify the report commit as PR head, then write exactly two bytes
  `OK` to the response FIFO and return to one blocking control-FIFO wait.
