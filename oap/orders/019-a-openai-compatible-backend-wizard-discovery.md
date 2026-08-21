# OAP Work Order — 019-a

## Objective and business reason

Build a guided, non-JSON setup workflow for the operator-defined
OpenAI-compatible runtime merged in Objective 018. An operator must be able to
select an existing generic provider, explicitly preview its bounded
`GET /v1/models` result, select models and conservative Chat/Responses presets,
choose zero or explicit local pricing, and atomically create reviewed route and
pricing rows. Discovery is explicit preview, never automatic catalog mutation.

After one bounded read of the named provider/route/pricing/admin/CLI symbols,
start implementation. Do not loop through broad reconnaissance, migration
styles, or the whole test tree; read another file only for a concrete symbol or
focused failure.

## Verified activation state

- Canonical repo `ulfe-lmi/slaif-api-gateway`; base `main` at
  `dcabe01a8fae5235a6c7d2b9e96b9850b05bf2d7`, merge of Objective 018 PR #244.
- Objectives 000–018 are terminal and merged. Objective 018 added generic
  `openai_compatible` adapter selection, canonical provider slugs, exact generic
  `/v1` URLs, server-side bearer env-var indirection, no redirects, explicit
  audited generic HTTP acknowledgement, and no built-in secret fallback.
- No Objective 019 branch/PR exists. Unrelated Dependabot PR #224 is open.
- `provider_configs`, `model_routes`, and `pricing_rules` already hold all
  durable data needed; no schema migration is required.
- Existing provider admin/CLI forms create metadata only. Existing route and
  pricing services already perform canonical creation/audit in one caller-owned
  DB transaction. Current route UI exposes optional raw capabilities JSON;
  this objective must make ordinary generic setup possible without it.
- Gateway `GET /v1/models` remains local metadata and must not become automatic
  upstream proxying. Provider discovery is a separate authenticated operator
  action.

## PR contract

- Create branch `oap/019-openai-compatible-backend-wizard-discovery` from the
  verified `origin/main`.
- Create exactly one ready PR titled
  `[OAP 019] Add guided OpenAI-compatible backend setup`, base `main`.
- Coding agent never merges or enables auto-merge; continuations 019-b…019-z
  amend only that PR.

## Allowed implementation area

Use the smallest necessary subset of:

```text
app/slaif_gateway/providers/openai_compatible.py
app/slaif_gateway/providers/headers.py
app/slaif_gateway/schemas/admin_catalog.py
app/slaif_gateway/schemas/providers.py
app/slaif_gateway/services/openai_compatible_discovery.py
app/slaif_gateway/services/openai_compatible_setup.py
app/slaif_gateway/services/provider_config_service.py
app/slaif_gateway/services/model_route_service.py
app/slaif_gateway/services/pricing_rule_service.py
app/slaif_gateway/db/repositories/provider_configs.py
app/slaif_gateway/db/repositories/routing.py
app/slaif_gateway/db/repositories/pricing.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/providers.py
app/slaif_gateway/web/templates/providers/detail.html
app/slaif_gateway/web/templates/providers/discover.html
app/slaif_gateway/web/templates/providers/discover_preview.html
tests/unit/test_openai_compatible_discovery.py
tests/unit/test_openai_compatible_setup.py
tests/unit/test_cli_providers.py
tests/unit/test_admin_provider_config_actions_routes.py
tests/unit/test_admin_catalog_templates_safety.py
tests/integration/test_openai_compatible_setup_postgres.py
tests/browser/test_admin_dashboard_smoke.py
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
oap/orders/019-a-openai-compatible-backend-wizard-discovery.md
oap/reports/019-a-openai-compatible-backend-wizard-discovery.md
```

One concrete adjacent import/template/test path is allowed if required and must
be explained. No migration file, public `/v1` route, or generated catalog
artifact is authorized.

## Required behavior

### 1. Bounded authenticated discovery

- Add an operator-only discovery service for an existing enabled configured
  provider whose slug is not `openai`/`openrouter` and whose kind is exactly
  `openai_compatible`.
- Use its canonical base URL, timeout, and exact server-side bearer env-var.
  Reuse central secret lookup/header rules; never accept or return the key.
- Issue only `GET <base_url>/models`, `Accept: application/json`, no redirects,
  no client/admin/cookie/CSRF/internal headers, and no retries that can multiply
  an operator action unexpectedly (discovery retry count zero).
- Bound response bytes before full JSON materialization (maximum 1 MiB), model
  rows (maximum 500), nesting/field count, and identifier length (1–255 UTF-8
  bytes). Require an object with `data` list; each selected item must be an
  object with a non-empty string `id`. Ignore ordinary extra model metadata
  after bounded shape validation; retain/return only unique IDs.
- Reject duplicate IDs, control characters, whitespace-only IDs, URLs,
  credential/bearer/cookie-like values, malformed JSON, wrong content type,
  redirect/3xx, non-2xx, oversize, timeout, disabled/built-in/missing provider,
  missing secret, or changed provider facts with a bounded content-free error.
- Discovery output/log/error/audit must not include the key, raw body, headers,
  arbitrary provider metadata, query/body content, or unsafe URLs.

### 2. Preview and confirmation model

- CLI: add `slaif-gateway providers discover-models <provider> --json` as an
  explicit read-only network preview. Human-readable output may list safe IDs;
  JSON is `{"provider": slug, "models": [ids...]}` only.
- Admin: provider detail links to a CSRF-protected discovery form. POST preview
  requires `confirm_discovery=true`; it performs the one bounded call and
  renders safe model IDs plus setup controls. Preview writes no provider,
  route, pricing, FX, key, usage, or audit row and does not persist raw preview
  state in session/cookie/URL/hidden JSON.
- Preview may carry selected safe model IDs and bounded scalar setup choices in
  the confirmation form. Execution must distrust them, re-load the provider,
  re-run discovery, and require every selected ID still exists before mutation.
- Both preview and execution reject zero selections, duplicate selections,
  models not in the fresh discovery result, over-limit selection (maximum 100),
  and secret-looking/public-ID inputs.

### 3. Server-generated presets without required JSON

Support these exact setup presets:

```text
chat_text_v1
responses_text_v1
chat_and_responses_text_v1
```

- For each selected upstream model, create a distinct exact public model ID.
  Default suggestion is `<provider>/<upstream_model>`; operator may replace it
  with a unique bounded safe ID. Public and upstream IDs are separate.
- `chat_text_v1` creates one exact `/v1/chat/completions` route with
  `chat_text=true`; streaming is a separate ordinary checkbox. All other Chat
  capabilities, especially hosted tools, media, custom tools, service tier,
  and multiple choices, are explicit false. An optional local-function checkbox
  may set only `chat_function_tools=true` and `chat_legacy_functions=true`.
- `responses_text_v1` creates one exact `/v1/responses` route with only
  `text=true`, `stateless=true`, optional `streaming`, and optional local
  `function_tools`; storage/state/background/media/Codex/hosted authority remain
  false. It does not create input-token, compact, lifecycle, or Conversation
  routes.
- Combined preset creates both independent rows. Route priority is a bounded
  scalar (default 100); visibility is explicit. Routes default disabled unless
  `confirm_enable_unqualified=true` is separately checked and audited. The UI
  states that configuration is not endpoint/model qualification; Objective 020
  owns conformance.
- Generate canonical capability objects server-side. No required JSON input,
  wildcard provider/model/endpoint, allow-all, hosted capability, external-tool
  policy, or silent inference from `/models` is allowed.

### 4. Explicit pricing and atomic execution

- Require exactly one pricing mode:
  - `local_zero`: exact Decimal zero input/output EUR price with safe metadata
    `pricing_basis=operator_confirmed_local_zero`, or
  - `explicit`: finite non-negative Decimal input/output EUR prices per 1M
    tokens supplied as strings.
- Zero is never inferred from a missing value. Neither mode is provider invoice
  truth. Do not create FX rows or fetch pricing.
- Create one pricing row per selected upstream model and endpoint with the same
  enabled state as its route, current aware `valid_from`, no source URL, and
  safe bounded note/reason. Cached/reasoning/request/tool prices remain unset.
- Before any mutation, preflight the full selection against existing exact
  routes and active/conflicting pricing. Any duplicate/conflict/invalid row
  rejects the whole request.
- Re-probe and create every route/pricing/audit record in one caller-owned
  PostgreSQL transaction. Any exception rolls back all created rows and audits.
  Use existing route/pricing services and repositories rather than duplicating
  their policy/audit semantics.
- Execution requires authenticated active admin, CSRF, `confirm_execute=true`,
  optional `confirm_enable_unqualified`, and a non-empty audit reason. CLI
  mutation requires equivalent flags and reason; if adding a CLI execute
  command is too large, CLI discovery preview is required now and CLI atomic
  execution may be explicitly deferred to 019-b only if admin execution is
  complete and the report says so. Prefer completing both.

## Security/privacy/non-goals

- No real Qwen/vLLM/LAN/provider call during implementation or tests; use
  mocked numeric/test hosts only.
- No automatic discovery, startup/readiness/periodic probe, silent refresh,
  health status persistence, provider row creation, YAML/JSON config import,
  anonymous auth, remote image URL, content request, tool execution, hosted
  tool, Codex profile, load balancing/failover, GPU/systemd action, schema
  migration, production access, or universal compatibility claim.
- Preserve provider-secret isolation, client Authorization substitution,
  PostgreSQL quota/accounting truth, no-content storage, and fail-closed unknowns.

## Acceptance evidence

1. Mocked discovery proves exact request URL/method/headers/no-redirect and all
   size/shape/secret/error negatives with no mutation.
2. CLI/admin preview is explicit, safe, bounded, and no-mutation.
3. Confirmed execution re-probes and atomically creates the exact selected
   disabled or explicitly enabled routes/pricing/audits; rollback and conflict
   tests prove no partial state.
4. Capability snapshots contain only the selected conservative fields; no raw
   JSON is required and no hosted/Codex/state/media permission appears.
5. Local-zero and explicit prices remain Decimal/string exact and are labeled
   non-invoice truth.
6. Existing provider/route/pricing admin/CLI behavior and Objective 018 factory
   security tests remain green.
7. Current-facing documentation explains the workflow and its qualification,
   LAN HTTP, secret, pricing, and no-automatic-mutation limitations.

## Focused verification economy

Run focused unit tests for new discovery/setup plus affected provider/route/
pricing/CLI/admin/template tests. Run the new PostgreSQL setup file against one
exact disposable `TEST_DATABASE_URL` with zero skips, and the smallest affected
Playwright provider-wizard test if browser behavior cannot be fully proven by
route/template tests. Run scoped Ruff, compileall, Alembic head, docs drift,
and diff check. Do not run complete local suites; routine GitHub CI is broad
evidence.

## Documentation and publication

Update all current contracts named in allowed paths, preserve historical files
and README branding, and state that vLLM bearer auth does not secure every
non-`/v1` server endpoint; firewall/reverse proxy remains operator-owned.

Commit this order and exact `oap/active=019-a` unchanged. Push implementation,
create the one PR, inspect checks, and publish exactly one immutable
`oap/reports/019-a-openai-compatible-backend-wizard-discovery.md` report in a
final report-only commit with literal implementation head and
`Report publication commit: SELF`. Verify remote PR head, send exact FIFO `OK`,
and return to one control wait. Never merge.
