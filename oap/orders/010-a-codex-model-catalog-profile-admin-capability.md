# OAP Work Order — 010-a

## Objective

Turn the pinned Codex protocol/accounting implementation into an honest,
operator-manageable capability: define strict route-pair qualification
metadata, render a credential-free user-level Codex profile using the safe
bundled catalog strategy, expose qualification/readiness in CLI and admin route
views, and let the admin key-create workflow explicitly select the complete
Codex pilot capability preset without widening endpoint/model/provider policy.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote default branch: `main`.
- Starting remote `main`:
  `250ee751cffb8cc7632aaa793385eaa498ed6d08`, merge commit for PR #234.
- Objectives 004 through 009 are merged. Objective 009 proved the exact pinned
  Codex CLI 0.147.0 three-request client-tool/cache/V1-compaction loop on numeric
  loopback with strict route/accounting/HMAC/privacy policy.
- Current Alembic head is `0014_codex_context_accounting_compaction`; this
  objective has no schema migration.
- PR mode: `CREATE_NEW_PR`.
- Required branch:
  `oap/010-codex-model-catalog-profile-admin-capability`.
- Required PR title:
  `[OAP 010] Manage Codex qualification and user profiles`.
- No existing PR was found for that branch at activation.
- The only unrelated open PR is Dependabot #224. Do not modify or reuse it.
- Preserve `.local-provider-catalog/`, linked worktrees, local user config,
  secrets, and all unrelated artifacts.
- Frozen 004 fixture SHA-256 remains
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.

Reconcile canonical GitHub and all of this again before editing. Start the new
branch from current remote `main`, never from the merged 009 feature branch.

## Pinned client and official configuration evidence

Use only this qualification identity:

```text
Codex binary: /usr/bin/codex
CLI version: 0.147.0
source tag: rust-v0.147.0
source commit: be6e8eac029b183056b7e4402879f15d2c85f61b
model: gpt-5.6-sol
wire API: responses
auth: API key custom provider
fixture digest: 436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432
```

Pinned source and official OpenAI configuration documentation establish:

- provider/auth selection belongs in user-level Codex config; project-local
  config must not redirect provider/authentication;
- named profiles may set `model`, `model_provider`, and profile-scoped
  `features.remote_compaction_v2=false`;
- configured remote compaction requires the provider display `name` to be
  exactly `OpenAI` (or Azure semantics), while non-OpenAI custom names are
  remote-compaction unsupported;
- `model_catalog_json` replaces the startup catalog and must decode the full
  pinned `ModelsResponse` schema including model instructions;
- the pinned binary already bundles complete metadata/instructions for exact
  slug `gpt-5.6-sol` and `codex debug models --bundled` reads it without remote
  refresh;
- objective 009 proved the OpenAI-identity internal metadata is safely dropped
  by SLAIF before forwarding/persistence.

Primary references:

```text
https://developers.openai.com/codex/config-reference
https://developers.openai.com/codex/config-advanced
https://github.com/openai/codex/releases/tag/rust-v0.147.0
```

Do not infer later Codex/model compatibility and do not call a real provider.

## Product truth and support level

Objective 010 does **not** establish full gateway/provider E2E compatibility;
objective 011 owns that proof and bounded pilot readiness. Therefore the only
positive support level introduced here is:

```text
protocol_qualified
```

UI, CLI, docs, and metadata must state: exact protocol/profile locally
qualified, real provider-through-gateway E2E not yet run. Never display
`compatible`, `production ready`, or `release qualified` for this state.

## Route metadata contract

Define one strict top-level `model_routes.capabilities.codex_qualification`
object. For this objective, a declared object must contain exactly:

```json
{
  "support_level": "protocol_qualified",
  "profile_version": 1,
  "cli_version": "0.147.0",
  "model": "gpt-5.6-sol",
  "profile": "api-key-responses-v1",
  "catalog_source": "bundled",
  "fixture_sha256": "436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432",
  "evidence_date": "2026-08-18",
  "wire_api": "responses",
  "provider_display_name": "OpenAI",
  "remote_compaction": "v1",
  "remote_compaction_v2": false,
  "real_provider_e2e": false
}
```

Missing metadata means `not_declared`; malformed/unknown/non-exact metadata
means `invalid`, never qualified. No coercion, aliases, partial objects, future
versions, arbitrary reason text, or model-name inference.

A route is usable for this qualification only as part of one explicit pair:

1. enabled/visible/streaming exact `/v1/responses` route;
2. enabled exact `/v1/responses/compact` route for the same provider,
   requested model, and upstream model;
3. both exact-match requested/upstream model `gpt-5.6-sol`;
4. both carry identical exact qualification metadata, all five Codex boolean
   route gates, strict `codex_limits`, and explicit reciprocal compatible route
   UUIDs as required by objective 009;
5. the Responses route has stateless+streaming; compact route has compact;
6. provider config is enabled;
7. active pricing rows for both endpoints exist and carry complete normal,
   cached, reasoning, cache-write, FX, and `codex_accounting` metadata required
   by 009.

Return a safe deterministic readiness result: state, requested model, provider,
route IDs, exact pinned versions/profile, and enumerated low-cardinality reason
codes only. Never include provider keys, gateway keys, raw pricing metadata,
URLs with credentials/query/fragment, prompts, content, or arbitrary notes.

## Bundled model-catalog strategy and profile renderer

The supported route's requested model must be exact bundled slug
`gpt-5.6-sol`. The rendered profile deliberately omits `model_catalog_json` and
uses the pinned binary's complete bundled model instructions/metadata. Do not
create a partial replacement catalog, copy large model instructions into this
repository, or claim aliases are supported. A custom catalog/alias is a future
separately captured profile.

Add `slaif-gateway codex` read-only commands:

- `inspect` lists deterministic qualification/readiness results from local DB;
- `profile` requires an exactly ready model and a validated gateway base URL,
  then prints a mergeable TOML snippet (or safe JSON wrapper with `--json`).

The fixed rendered profile/provider names are `slaif` and must include:

```toml
[model_providers.slaif]
name = "OpenAI"
base_url = "https://gateway.example.org/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false

[profiles.slaif]
model = "gpt-5.6-sol"
model_provider = "slaif"

[profiles.slaif.features]
remote_compaction_v2 = false
```

Validate base URL: absolute `https` except numeric loopback `http`, no userinfo,
query, fragment, control characters, or secret-looking value; canonical path
must end exactly `/v1`. Escape TOML safely. The renderer must not read, accept,
store, or print an API key and must not modify `~/.codex`, repository `.codex`,
or any file. Users set only `OPENAI_API_KEY` to a gateway-issued key and run
`codex --profile slaif`.

Add one manual verifier that creates a private temporary `CODEX_HOME`, writes
only the generated credential-free snippet there, supplies a dummy key in the
child environment, and runs exact Codex 0.147.0 against numeric loopback. Prove
the named profile/model/provider load with no custom-catalog decode warning,
uses ordinary uncompressed Responses JSON, reaches only loopback, and persists/
prints no raw payload. It must not invoke Codex from pytest/CI/startup; pytest
tests only pure renderer/verifier helpers.

## Admin and key policy experience

### Route views

Add safe parsed qualification fields/reasons to route list/detail DTOs and
templates. Show a clear badge/summary:

- `Protocol-qualified: Codex 0.147.0 / gpt-5.6-sol / profile v1`, or
- `Not declared`, or
- `Invalid/not ready` plus enumerated safe reason codes.

Raw capabilities remain visible for audit, but no secret or raw pricing body is
added. Route create/edit continues using the existing confirmed/audited JSON
workflow; do not add an unaudited qualification mutation shortcut.

### Key creation preset

Add an explicit checkbox and confirmation to create one **Codex protocol pilot
key**. It is available only when local qualification/readiness validation finds
an exactly ready selected route pair. Server-side validation must require:

- standard key, not trusted calibration;
- no allow-all provider/model/endpoint switches;
- exactly one selected model `gpt-5.6-sol` and its one provider;
- exact endpoints `/v1/models`, `/v1/responses`, and
  `/v1/responses/compact`, with no extras;
- explicit confirmation and audit reason;
- existing positive finite request/token/cost limits (do not create an
  unbounded pilot key).

Set, through the existing `CreateGatewayKeyInput.responses_policy` and normal
KeyService/audit path only:

```json
{
  "version": 1,
  "allowed_capabilities": [
    "codex_request_envelope",
    "codex_client_tools",
    "codex_streaming_tool_events",
    "codex_encrypted_reasoning_replay",
    "codex_compaction"
  ],
  "allowed_local_tool_types": ["function", "custom"]
}
```

Use canonical capability order. Do not enable hosted/provider tools, MCP,
background, stored provider state, allow-all, or external-tool overrun. On any
invalid/stale route/pricing/selection, reject before key mutation and render a
safe fixed error/reasons. Preserve ordinary key creation unchanged.

Model selector labels should expose the protocol-qualified badge/reasons, so an
operator can deliberately select the correct route. The key result/detail shows
the existing safe Responses policy summary; no plaintext behavior changes.

## `/v1/models` compatibility

Do not add Codex metadata to the public OpenAI `GET /v1/models` schema. Its
objects remain exactly `id`, `object`, `created`, and `owned_by`, filtered by
authenticated key/provider/route visibility. Add regression tests proving
qualification metadata cannot leak and ordinary OpenAI clients receive the
same shape/order semantics.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/codex.py
app/slaif_gateway/cli/main.py
app/slaif_gateway/schemas/admin_catalog.py
app/slaif_gateway/services/admin_catalog_dashboard.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/web/templates/keys/_policy_selector.html
app/slaif_gateway/web/templates/keys/create.html
app/slaif_gateway/web/templates/routes/detail.html
app/slaif_gateway/web/templates/routes/list.html
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/security-model.md
oap/active
oap/orders/010-a-codex-model-catalog-profile-admin-capability.md
scripts/verify_codex_profile.py
tests/browser/test_admin_dashboard_smoke.py
tests/unit/test_admin_catalog_dashboard_service.py
tests/unit/test_admin_catalog_routes.py
tests/unit/test_admin_key_create_routes.py
tests/unit/test_admin_key_create_templates.py
tests/unit/test_admin_route_actions_routes.py
tests/unit/test_cli_codex.py
tests/unit/test_codex_qualification.py
tests/unit/test_model_catalog_service.py
tests/unit/test_v1_models_catalog.py
```

Final report-only commit adds only:

```text
oap/reports/010-a-codex-model-catalog-profile-admin-capability.md
```

If another exact implementation/test path is genuinely required, do not edit
it. Publish `BLOCKED` with the path/reason for a narrow 010 continuation. Do not
modify DB models/migrations, dependencies, provider adapters, runtime 009
policy/accounting/HMAC code, README, fixtures/capture, CI/deployment, project-
local `.codex`, prior OAP history, or unrelated artifacts.

## Focused verification and test economy

Run only:

- new qualification/CLI tests and directly affected admin/catalog/models unit
  files named above;
- pure template safety and one browser smoke file only if the normal local
  Playwright prerequisite already works; otherwise report local browser NOT RUN
  and rely on GitHub CI;
- focused OAP/documentation tests, scoped Ruff/compile, `git diff --check`,
  exact paths/topology, fixture digest;
- one final exact manual profile verifier against numeric loopback.

Do not run full unit, integration, PostgreSQL, E2E, browser matrix,
Docker/Compose, or HPC suites locally. No schema/data write requires local DB
integration in this objective. GitHub CI owns broad coverage. Never use real
provider keys/calls or real gateway keys.

The report must record exact commands/counts, safe profile verifier keys,
browser status, every broad suite NOT RUN, and all failures/skips honestly.

## Acceptance criteria

1. Strict route-pair/provider/pricing qualification yields only
   `protocol_qualified`, `not_declared`, or fail-closed invalid/not-ready safe
   reasons; no inference from model names or single flags.
2. CLI inspect/profile are deterministic, credential-free, bundled-catalog
   only, safe-URL validated, and never mutate user/repo Codex config.
3. Exact Codex 0.147.0 loads the rendered named profile with provider name
   `OpenAI`, bundled `gpt-5.6-sol`, profile-scoped V2 compaction disabled, no
   catalog decode warning, numeric-loopback-only request, and no raw persistence.
4. Admin route views and model selector show honest protocol qualification and
   safe reason codes. Invalid metadata/pricing never appears qualified.
5. Admin pilot-key checkbox is explicit/confirmed, validates the exact bounded
   provider/model/endpoints/limits/readiness, sets only the five local Codex
   gates through normal KeyService audit, and rejects before mutation otherwise.
6. Ordinary key creation and ordinary `/v1/models` response shape/filtering are
   unchanged; no Codex metadata or secret leaks into public models/admin/CLI.
7. Focused tests/docs/quality/privacy/path/fixture evidence and every report-head
   GitHub check pass; no broad local suite or real provider runs.
8. One new objective PR only; coding agent never merges/enables auto-merge;
   immutable report topology satisfies `SELF`.

## GitHub and report contract

Commit the unchanged 010-a order and `oap/active=010-a` with implementation,
push the required branch, create exactly one non-draft PR against `main` with
the exact title, inspect actual checks, and repair only in-scope failures.

Publish exactly one immutable report at
`oap/reports/010-a-codex-model-catalog-profile-admin-capability.md` with literal
implementation SHA, `Report publication commit: SELF`, exact metadata/readiness/
profile/admin/key/models/privacy evidence, manual verifier output, local/GitHub
checks, broad suites not run, documentation impact, and no-merge/no-auto-merge.
The final commit changes only that report and has the implementation head as
first parent. Verify remote report head, then signal exact `OK`. Never merge.

If the pinned profile cannot load without a replacement catalog, the admin key
preset cannot prove readiness before mutation, or any credential would need to
be written/read/printed, report `BLOCKED` rather than weaken the contract.
