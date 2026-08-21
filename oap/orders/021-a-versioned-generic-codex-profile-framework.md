# OAP Work Order — 021-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Generalize SLAIF's single hard-coded Codex 0.147/OpenAI/GPT-5.6 qualification
into a server-defined, versioned profile registry capable of representing later
named generic-backend profiles. Preserve the existing qualified profile and its
rendered configuration exactly. Arbitrary admin/route JSON must never
self-declare qualification. This objective creates framework only; Qwen text and
vision profiles/live evidence belong to Objectives 022–023.

After one bounded read of `codex_qualification.py`, its CLI/admin consumers,
route metadata parser, current deterministic profile tests, and captured fixture
contract, implement. Do not repeat broad repository/manual/test discovery or run
broad local suites.

## Verified activation state

- Canonical `main` is
  `5c7bf45e3f1b7f5bd9fa45e4b07820bf801d945c`, merge of Objective 020 PR #246.
- Objectives 000–020 are merged. Generic backends now have mocked Chat/
  stateless-Responses conformance, guided setup, inline-only images, and
  PostgreSQL accounting/privacy evidence; no live model/Codex target is
  qualified.
- Existing Codex qualification is pinned to CLI 0.147.0, model
  `gpt-5.6-sol`, one exact OpenAI Responses/compact pair, fixed metadata,
  fixed fixture digest, five route/key gates, strict numeric limits, complete
  pricing/FX, and `real_provider_e2e=false`.
- Existing `render_codex_profile()` produces a credential-free SLAIF model-
  provider fragment and profile-v2 file; current callers/tests depend on its
  exact defaults.
- No Objective 021 branch/PR exists. Dependabot #224 is unrelated.
- No schema migration is needed: qualification metadata remains versioned route
  capability JSON.

## PR contract

- Create `oap/021-versioned-generic-codex-profile-framework` from current main.
- Create exactly one ready PR titled
  `[OAP 021] Add versioned Codex qualification profiles`, base `main`.
- Continuations amend it. Coding agent never merges or enables auto-merge.

## Allowed paths

Use the smallest necessary subset of:

```text
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/services/responses_route_capabilities.py
app/slaif_gateway/cli/codex.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/schemas/admin_catalog.py
app/slaif_gateway/web/templates/routes/detail.html
app/slaif_gateway/web/templates/keys/create.html
scripts/verify_codex_profile.py
tests/unit/test_codex_profile_registry.py
tests/unit/test_codex_qualification.py
tests/unit/test_cli_codex.py
tests/unit/test_admin_catalog_routes.py
tests/unit/test_admin_catalog_templates_safety.py
tests/unit/test_codex_gateway_e2e_verifier.py
tests/unit/test_documentation_contract_drift.py
README.md
AGENTS.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/openai-compatibility.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/security-model.md
oap/active
oap/orders/021-a-versioned-generic-codex-profile-framework.md
oap/reports/021-a-versioned-generic-codex-profile-framework.md
```

One exact adjacent profile/fixture test path is allowed if required and must be
reported. No migration or request-runtime widening is authorized.

## Required design

### 1. Immutable server-defined registry

Add a frozen typed profile definition and a read-only registry keyed by a safe
bounded profile ID. It must represent at least:

```text
profile_id
metadata_version
cli_version
public_model
upstream_model
wire_api
provider_kind and optional exact provider slug
required endpoint set
required route/key Responses gates
context/default-output/max-output limits
compaction mode (remote_v1 or client_local/none)
reasoning/replay/stream/local-tool feature claims
credential-free provider/profile TOML fields
optional model-catalog artifact and target filename
fixture SHA-256 and evidence date
mocked/live qualification booleans
```

- Register the existing profile as an exact built-in definition (choose a
  stable ID such as `openai-gpt-5.6-sol-codex-0.147-v1`). Populate it solely
  from the current authoritative constants/metadata; do not change a value,
  limit, digest, output, or qualification claim.
- Registry lookup returns immutable definitions and rejects unknown, duplicate,
  malformed, or partially defined profiles at import/test time.
- Do not register Qwen as qualified or ship a placeholder that can be selected
  as qualified in this objective.

### 2. Backward-compatible route metadata

- Preserve the current version-1 `codex_qualification` object and parser exactly
  for existing routes.
- Add a minimal version-2 declaration containing only exact server-owned
  identity, e.g. `{"version":2,"profile_id":"...","fixture_sha256":"..."}`.
  The registry—not route JSON—supplies all capabilities/limits/claims.
- Unknown profile, wrong digest/version/extra field/type, provider/model/
  endpoint mismatch, missing paired endpoint when required, gate/limit/pricing/
  FX mismatch, disabled provider/route, or route-selection ambiguity yields
  `not_ready`/`invalid` with bounded reason codes. It never falls back to model-
  name inference or version-1 defaults.
- Version-2 metadata cannot widen request policy. Runtime request gates continue
  to come from the existing explicit Responses capability booleans and limits.

### 3. Qualification service generalization

- Make inspection/profile selection operate from the resolved registry profile
  rather than module-global OpenAI constants while preserving current default
  methods/call signatures or adding backward-compatible optional profile ID.
- Required endpoint sets are profile-specific: the existing profile still
  requires its exact Responses/compact pair; future client-local-compaction
  profiles may require only Responses, but none is qualified now.
- Qualification result/admin/CLI safe DTO includes profile ID and metadata
  version while retaining existing badge/state/reason behavior for version 1.
- Pilot-key creation remains pinned to the existing OpenAI profile and its exact
  model/endpoints. Do not make it generic in this objective.

### 4. Deterministic credential-free artifacts

- Generalize profile rendering to accept a selected registered/qualified
  profile while preserving `render_codex_profile(base_url)` as the exact
  current-profile default.
- Artifacts may include:
  - base config merge fragment;
  - complete named profile-v2 TOML;
  - optional model-catalog JSON plus explicit target path/name.
- Use deterministic TOML/JSON ordering/newlines/escaping. No API key, LAN
  backend URL, provider secret env-var, prompt, output, tool payload, reasoning,
  or arbitrary route metadata may appear. The client base URL is the validated
  SLAIF gateway `/v1`, never the upstream backend.
- CLI `codex profile` gains an optional `--qualification-profile`; unknown or
  not-ready profile fails safely. Default output remains byte-for-byte current.
  Admin route detail shows safe profile ID/status and download/display artifacts
  only for a ready registered profile.

### 5. Sanitized fixture contract

- Add a pure validator/helper for future normalized structural fixtures. It may
  retain only field/event/tool type names, bounded IDs replaced by deterministic
  placeholders, ordering/cardinality, boolean/numeric limits, and digest.
- It must reject or remove prompt/output text, tool descriptions/schemas/
  arguments/results, reasoning/encrypted content, request/response bodies,
  URLs, headers, keys, cookies, authorization, environment values, workspace
  paths, and arbitrary metadata.
- Do not perform a Codex process or network capture in 021. Objectives 022–023
  will capture exact authorized fixtures using this contract.

## Non-goals

No Qwen/vLLM profile or claim, Codex 0.148 live/capture run, real provider/LAN,
new request/event/tool acceptance, Chat-to-Responses translation, arbitrary
admin profile creation, schema migration, provider discovery change, hosted
tool, remote image, production/release claim, or broad local suite.

## Acceptance and focused evidence

1. Existing version-1 OpenAI qualification states, safe DTOs, badges, pilot
   validation, profile TOML, verifier fixture digest, and tests remain
   byte/behavior compatible.
2. Version-2 known-profile positive and every unknown/drift/mismatch negative
   are deterministic and fail closed without runtime authority.
3. Renderer produces deterministic credential-free artifacts and never emits
   backend URLs/secrets/content; optional catalog support is proven with an
   unqualified synthetic test profile only, not a shipped qualified profile.
4. CLI/admin safely select/display registered ready profiles; default behavior
   is unchanged.
5. Fixture sanitizer privacy negatives prove prohibited content cannot enter
   a committed structural fixture.
6. Run only focused registry/qualification/CLI/admin/verifier/docs tests, scoped
   Ruff, compileall, Jinja parse if changed, Alembic head, and diff check. No
   full local suite; routine GitHub CI is broad evidence.

## Documentation and publication

Update current contracts to distinguish configured, mocked-conformant,
protocol-qualified, and live-qualified states; qualification remains exact
CLI/model/provider/profile evidence and never a generic OpenAI-compatible
claim. Preserve historical records and README branding.

Commit this exact order and `oap/active=021-a`, push implementation, create the
one PR, and publish one immutable
`oap/reports/021-a-versioned-generic-codex-profile-framework.md` report-only
final commit with literal implementation head and
`Report publication commit: SELF`. Verify remote head/check state, send exact
FIFO `OK`, and return to one control wait. Never merge.
