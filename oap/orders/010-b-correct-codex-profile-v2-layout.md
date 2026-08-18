# OAP Work Order — 010-b

## Objective

Amend objective-010 PR #235 and complete the model qualification, bundled-
catalog Codex profile, CLI/admin readiness, bounded pilot-key preset, public
models regression, documentation, and evidence originally required by 010-a.
Replace only the obsolete inline legacy profile layout with the exact Codex
0.147.0 profile-v2 two-file contract verified after 010-a; do not weaken or
discard any other 010-a requirement.

## GitHub objective state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #235,
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/235`.
- PR title: `[OAP 010] Manage Codex qualification and user profiles`.
- Base branch: `main`.
- Required existing head branch:
  `oap/010-codex-model-catalog-profile-admin-capability`.
- Remote PR head at activation:
  `36eed7c234b6fa69d8a89b4fafca37595e204b3b`, the immutable 010-a report
  publication commit.
- Its first parent is the 010-a implementation head
  `2dada60375bc341fd113e64cb2f5b7801aadcacd`.
- Remote `main` remains
  `250ee751cffb8cc7632aaa793385eaa498ed6d08`, the merge commit for PR #234.
- PR #235 is open and non-draft; auto-merge is disabled. Report-head CI was
  still running at activation, with no observed failure. Reconcile the actual
  current GitHub state before editing.
- This is `AMEND_EXISTING_PR`. Check out and update the existing branch. Never
  create a second objective-010 PR, change the base, merge, or enable
  auto-merge.

## Why 010-a was insufficient

010-a correctly stopped before product implementation because its mandatory
rendered snippet used legacy `[profiles.slaif]` and
`[profiles.slaif.features]` tables in `$CODEX_HOME/config.toml` while also
requiring `codex --profile slaif`. Codex CLI 0.147.0 rejects that exact
combination before provider/model loading.

The immutable 010-a report and independent strategic verification established:

- `--profile slaif` is profile v2 and loads
  `$CODEX_HOME/slaif.config.toml` as a layer over base
  `$CODEX_HOME/config.toml`;
- the base file may define `[model_providers.slaif]`;
- the profile-v2 file carries top-level `model`, `model_provider`, and
  `[features]` settings;
- a base `profile = "slaif"` selector or `[profiles.slaif]` table conflicts
  with `--profile slaif` and is rejected;
- the provider/auth selection remains user-level and project-local config
  remains unsuitable for redirecting it.

This continuation deliberately resolves that contract conflict. It does not
reinterpret the BLOCKED 010-a round as product completion, and it must preserve
the 010-a report unchanged.

## Authoritative pinned client and product truth

Retain the exact 010 qualification identity:

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

Use current official OpenAI Codex configuration documentation and pinned
0.147.0 source only for client semantics. Do not infer compatibility from a
later client/model. Full real-provider-through-gateway compatibility remains
objective 011; objective 010's only positive support level is still
`protocol_qualified`.

## Exact corrected profile-v2 contract

The renderer produces two credential-free logical artifacts. It prints them
only; it never writes either file, reads a credential, accepts a credential as
an argument, mutates Codex config, or expands `$CODEX_HOME` to a user-specific
path in output.

### Base user configuration fragment

Label this as a fragment to merge into `$CODEX_HOME/config.toml`:

```toml
[model_providers.slaif]
name = "OpenAI"
base_url = "https://gateway.example.org/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
```

### Named profile-v2 file

Label this as the complete gateway-owned content for
`$CODEX_HOME/slaif.config.toml`:

```toml
model = "gpt-5.6-sol"
model_provider = "slaif"

[features]
remote_compaction_v2 = false
```

Do not emit `profile = "slaif"`, `[profiles]`, `[profiles.slaif]`, or
`[profiles.slaif.features]` anywhere. Do not emit `model_catalog_json`; exact
bundled slug `gpt-5.6-sol` remains the only supported catalog strategy.

The default text form of `slaif-gateway codex profile` must make the two target
files and merge-versus-complete-file distinction unambiguous and must not
pretend that the combined display is one parseable TOML document. The `--json`
form must return a stable safe object with fixed logical target names,
`base_config_toml`, `profile_config_toml`, profile/model/provider identifiers,
and invocation `codex --profile slaif`; it must contain no credential, expanded
home path, arbitrary DB text, or raw route/pricing metadata. Internal renderer
helpers should return the two TOML documents separately so each can be parsed
and tested independently.

Continue to validate the gateway base URL exactly as 010-a requires: absolute
HTTPS except HTTP on numeric loopback, no userinfo/query/fragment/control or
secret-looking material, canonical path ending exactly `/v1`, and safe TOML
escaping. User instructions must say to merge the base fragment, place the
profile-v2 file, set the gateway-issued key only in `OPENAI_API_KEY`, and run
`codex --profile slaif`.

## Manual profile verifier correction

Create the 010-a manual verifier, but make its private temporary `CODEX_HOME`
contain exactly the generated credential-free two-file layout:

- `config.toml` receives the generated base provider fragment;
- `slaif.config.toml` receives the generated profile-v2 document;
- neither contains any key;
- a fixed dummy `OPENAI_API_KEY` exists only in the child environment;
- the URL is numeric loopback and the mock accepts only loopback;
- invoke exact `/usr/bin/codex` 0.147.0 with `--profile slaif` through a runtime
  command that actually applies the profile.

The final exact verifier must prove the named v2 profile, exact model/provider,
bundled catalog, V1 compaction selection, ordinary uncompressed Responses JSON,
and loopback request all load/work without a legacy-profile or custom-catalog
decode warning. It must print only low-cardinality booleans/counts/version and
must not persist or print raw request/response bodies, prompts, completions,
tool content, or the dummy value. It must not run from pytest, CI, startup, or
normal CLI execution. Pytest exercises only pure rendering/validation/verifier
helpers.

## Requirements carried forward from 010-a

Except for the explicit profile-v2 corrections above, implement 010-a in full:

1. Define strict exact `capabilities.codex_qualification` parsing with only the
   specified `protocol_qualified`, profile/version/client/model/fixture/catalog/
   wire/provider/compaction/E2E facts. Missing is `not_declared`; malformed,
   unknown, partial, or non-exact is invalid. Never infer from model names.
2. Validate the explicit enabled `/v1/responses` and
   `/v1/responses/compact` pair, reciprocal compatible UUIDs, exact same
   provider/requested/upstream model, all five Codex gates, strict
   `codex_limits`, route endpoint/visibility/streaming semantics, enabled
   provider, and complete active objective-009 pricing/accounting metadata.
3. Return only deterministic safe qualification/readiness fields and
   enumerated low-cardinality reason codes. Never expose credentials, prompts,
   content, arbitrary notes, raw pricing metadata, or unsafe URLs.
4. Add read-only `slaif-gateway codex inspect` and corrected two-file
   `slaif-gateway codex profile`, including deterministic JSON modes.
5. Add safe parsed qualification state/badge/reasons to admin route list/detail
   while retaining raw capabilities for existing audit behavior. Do not add an
   unaudited qualification mutation shortcut.
6. Add the explicit confirmed standard-key-only Codex protocol-pilot preset to
   admin key creation. Require exact one provider/model and exact endpoints
   `/v1/models`, `/v1/responses`, `/v1/responses/compact`, no allow-all flags,
   positive finite request/token/cost limits, exact current route/pricing
   readiness, audit reason, and confirmation before mutation.
7. Populate only the canonical five-capability Responses policy and local
   `function`/`custom` tool types specified by 010-a through existing
   `CreateGatewayKeyInput.responses_policy`, KeyService, and audit paths.
   Hosted tools, MCP, background work, provider state, overrun, allow-all, and
   trusted-calibration behavior remain excluded. Reject stale/invalid selection
   before any key mutation.
8. Preserve ordinary key creation. Preserve public `GET /v1/models` objects as
   exactly `id`, `object`, `created`, and `owned_by`, with existing authenticated
   visibility/order semantics and no qualification metadata leak.
9. Update all 010-a-required compatibility/configuration/security/schema/admin
   documentation honestly for profile v2 and `protocol_qualified`; do not claim
   real provider E2E, pilot readiness, full compatibility, or production
   readiness before objective 011.
10. Preserve objective-009 runtime policy, accounting, HMAC, privacy, schema,
    and migrations. Objective 010 adds no migration or real provider call.

All exact 010-a route metadata, readiness, policy JSON, safe URL, admin,
security/privacy, catalog, and `/v1/models` requirements remain authoritative
where not contradicted by this work order. Read 010-a and its immutable report
completely before implementation.

## Allowed paths

Implementation may change only the original 010-a allowed product/test/doc
paths plus this continuation selector/order:

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
oap/orders/010-b-correct-codex-profile-v2-layout.md
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

The final report-only commit adds only:

```text
oap/reports/010-b-correct-codex-profile-v2-layout.md
```

Preserve all earlier orders/reports byte-for-byte, including the BLOCKED 010-a
report. If another exact product/test path is genuinely required, do not edit
it; report `BLOCKED` with the path/reason for a narrow 010-c decision.

## Focused verification and test economy

Run only the new qualification/CLI tests and directly affected admin/catalog/
models unit files listed above; focused OAP/documentation tests; scoped Ruff/
compile; `git diff --check`; exact path/topology/fixture checks; and one final
manual numeric-loopback profile-v2 verifier. Run the one browser smoke file only
if its normal local prerequisite already works; otherwise report it NOT RUN and
rely on GitHub CI.

Do not run full local unit, integration, PostgreSQL, E2E, browser-matrix,
Docker/Compose, or HPC suites. No migration/data write requires local DB
integration. GitHub CI owns broad routine coverage. Never call a real provider,
real gateway, hosted/external tool, or production system. Record exact focused
commands/counts and all not-run suites honestly.

## Acceptance criteria

1. Both generated artifacts parse independently, contain the exact v2 layout,
   contain no legacy profile selectors/tables/catalog replacement/credential,
   and CLI output makes their separate target/merge semantics unmistakable.
2. Exact Codex 0.147.0 actually applies `$CODEX_HOME/slaif.config.toml` over the
   base provider layer and completes the harmless loopback verifier without
   legacy-profile/catalog warnings, non-loopback access, compression, or raw
   persistence/output.
3. Every non-conflicting 010-a acceptance criterion is satisfied: strict
   qualification/readiness; credential-free CLI; honest admin views; bounded
   confirmed pilot-key preset; unchanged ordinary key creation and public
   models; docs/privacy/scope/evidence.
4. The support claim remains only `protocol_qualified`; `real_provider_e2e`
   remains false and objective 011 remains the pilot/E2E boundary.
5. Focused local evidence and every required current report-head GitHub check
   pass. No broad local suite or real-provider run is used to manufacture that
   result.
6. Only PR #235 is amended; the coding agent neither merges nor enables
   auto-merge; the immutable 010-b report has valid `SELF` topology.

## GitHub and report contract

Commit the unchanged 010-b order and `oap/active=010-b` with the implementation
on the existing branch, push only that branch, and update PR #235's body from
the historical 010-a BLOCKED summary to the current implemented objective and
honest support boundary. Do not rewrite or delete 010-a commits/report.

Inspect actual GitHub checks and repair only in-scope failures. Publish exactly
one immutable report at
`oap/reports/010-b-correct-codex-profile-v2-layout.md` with literal
implementation SHA, `Report publication commit: SELF`, exact two-file output,
qualification/admin/key/models/privacy evidence, safe manual verifier output,
local and GitHub checks, all broad suites not run, documentation impact, and
no-merge/no-auto-merge confirmation. The final commit changes only that report
and has the implementation head as first parent. Verify the remote report head,
then signal exact `OK`. Never merge.

