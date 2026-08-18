# OAP Coding-Agent Report — 010-b

## Work order

- Identifier: `010-b`
- Work-order file:
  `oap/orders/010-b-correct-codex-profile-v2-layout.md`
- Work-order SHA-256:
  `2e7652ddda30aa247f67145410bb0ce1e090b20aa0c3485035b019d3b55e2d88`
- Numeric objective: `010`
- PR mode: `AMEND_EXISTING_PR`

## Status

IMPLEMENTED

## Executive summary

Objective 010-b completes the strict local Codex protocol-qualification,
profile-v2 rendering, read-only CLI, admin readiness, bounded pilot-key preset,
public-model privacy regression, documentation, and safe manual verification
required by the continuation order. It preserves the immutable 010-a BLOCKED
history and replaces only its obsolete legacy profile layout.

The generated user configuration is deliberately two separate credential-free
artifacts: a provider fragment for `$CODEX_HOME/config.toml` and a complete
named profile-v2 file at `$CODEX_HOME/slaif.config.toml`. Exact
`/usr/bin/codex` 0.147.0 applied that layout against a numeric-loopback mock,
selected bundled `gpt-5.6-sol`, used Responses with V1 compaction and no
request compression, completed one bounded request, and emitted no forbidden
legacy-profile or model-catalog warning.

The support claim remains only `protocol_qualified`. The qualification metadata
explicitly records `real_provider_e2e=false`; objective 011 remains the
real-provider-through-gateway boundary. No real provider, real gateway,
production system, hosted tool, MCP/connector, or external tool path was used.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Starting remote `main`:
  `250ee751cffb8cc7632aaa793385eaa498ed6d08`
- Starting objective-010 branch head / 010-a report commit:
  `36eed7c234b6fa69d8a89b4fafca37595e204b3b`
- Primary implementation commit:
  `f84996f9018d62af3cb731567b3677600b3f84bb`
- Implementation head SHA:
  `ee1ef823220ac5e058740e7dcd152316ab87f7c7`
- Implementation-head first parent:
  `f84996f9018d62af3cb731567b3677600b3f84bb`
- Implementation-head commit message:
  `[OAP 010-b] Stabilize Codex CI assertions`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `235`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/235`
- PR title: `[OAP 010] Manage Codex qualification and user profiles`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE` / `CLEAN`
- Base branch: `main`
- Head branch: `oap/010-codex-model-catalog-profile-admin-capability`
- Objective-010 PR count: exactly one, PR #235
- Created a new PR this turn: NO
- Amended the existing objective PR this turn: YES
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Exact profile-v2 output

The renderer returns and validates the following documents independently.

Base user-configuration fragment to merge into `$CODEX_HOME/config.toml`:

```toml
[model_providers.slaif]
name = "OpenAI"
base_url = "https://gateway.example.org/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
```

Complete gateway-owned `$CODEX_HOME/slaif.config.toml`:

```toml
model = "gpt-5.6-sol"
model_provider = "slaif"

[features]
remote_compaction_v2 = false
```

The default CLI display labels the first document as a merge fragment and the
second as a complete file; it does not present their combined display as one
TOML document. JSON output has fixed logical target names,
`base_config_toml`, `profile_config_toml`, profile/model/provider identifiers,
and `codex --profile slaif`. Neither form accepts or reads a credential, writes
a file, expands a user home path, or emits route/pricing internals.

The output contains no `profile = "slaif"`, `[profiles]`,
`[profiles.slaif]`, `[profiles.slaif.features]`, or `model_catalog_json`.
The base-URL validator requires canonical `/v1`, permits HTTPS or HTTP only on
numeric loopback, and rejects credentials, query, fragment, backslash,
percent-encoded ambiguity, control characters, noncanonical paths, and
secret-looking material before TOML rendering.

## Qualification and readiness evidence

`capabilities.codex_qualification` is accepted only as the exact 13-field
declaration below:

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

Missing metadata produces `not_declared`. Unknown, malformed, partial, stale,
or non-exact metadata is invalid/not ready with fixed low-cardinality reason
codes. Qualification is never inferred from a model name.

A positive result requires enabled exact reciprocal `/v1/responses` and
`/v1/responses/compact` routes with the same provider, requested model, and
upstream model; the five Codex gates; strict `codex_limits`; correct endpoint,
visibility, and streaming semantics; an enabled provider; complete active
pricing/accounting and required FX state; and both routes winning the ordinary
provider-constrained runtime ranking. A stale or shadowed pair therefore cannot
remain qualified. The deterministic DTO contains only state, stable route and
pair identifiers, model/provider/endpoint, enumerated reasons, pinned profile
facts, and the false real-E2E flag.

## CLI, admin, key, models, and privacy evidence

- `slaif-gateway codex inspect` is read-only and returns only deterministic safe
  qualification fields.
- `slaif-gateway codex profile --base-url ... [--json]` performs a fresh ready-
  pair check, then prints only the two credential-free logical artifacts.
- Admin route list/detail surfaces show the parsed qualification badge,
  reasons, and paired route while retaining raw capabilities for established
  audit behavior. The model selector distinguishes `Protocol-qualified`,
  `Invalid/not ready`, and concise `Not declared` states.
- The Codex protocol-pilot preset is explicit, confirmed, standard-key-only,
  and routed through the existing `CreateGatewayKeyInput`, `KeyService`, and
  audit path. It requires one exact provider/model, exactly `/v1/models`,
  `/v1/responses`, and `/v1/responses/compact`, no allow-all flags, positive
  finite request/token/EUR limits, a reason, and fresh route/pricing readiness
  before mutation.
- The pilot Responses policy grants exactly the five canonical Codex gates and
  local `function`/`custom` tool types. It does not grant hosted tools, MCP,
  background work, provider state, overrun, trusted calibration, or external
  execution.
- Ordinary key creation is preserved. Public authenticated `GET /v1/models`
  objects remain exactly `id`, `object`, `created`, and `owned_by`, with no
  qualification, route, pricing, URL, key, or secret metadata.
- No schema migration, runtime accounting change, HMAC/key-storage change,
  content-storage expansion, or real-provider call was added.

## Exact manual verifier evidence

Pinned client:

```text
/usr/bin/codex --version: codex-cli 0.147.0
/usr/bin/codex SHA-256: 134063e133f0b4244fa3b251acf973d4fe4b4aeeacbdc135211bf480f59f1477
source tag: rust-v0.147.0
source commit: be6e8eac029b183056b7e4402879f15d2c85f61b
```

Command:

```text
.venv/bin/python scripts/verify_codex_profile.py --base-url http://127.0.0.1:8765/v1
```

Safe output:

```text
RESULT=OK
CLI_VERSION=0.147.0
CLI_VERSION_MATCHED=true
PROFILE_V2_APPLIED=true
MODEL_MATCHED=true
PROVIDER_MATCHED=true
BUNDLED_CATALOG_USED=true
V1_COMPACTION_SELECTED=true
REQUEST_COUNT=1
CONTENT_ENCODING_ABSENT=true
LOOPBACK_ONLY=true
RAW_PAYLOADS_PERSISTED=false
```

Elapsed wall time was 1.18 seconds in the final timed run. The verifier used a
private temporary `CODEX_HOME`, 0700 directories, two 0600 generated config
files, a child-only fixed dummy `OPENAI_API_KEY`, dead external proxy settings,
and numeric-loopback `NO_PROXY`. The mock accepted exactly one ordinary
uncompressed JSON Responses request. Raw request data and bounded subprocess
output remained in memory only and were discarded; no prompt, completion, tool
content, dummy key, or raw body was printed or persisted.

## Changes and exact paths

The implementation commits change only these 28 order-allowed paths:

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
tests/unit/test_cli_codex.py
tests/unit/test_codex_qualification.py
tests/unit/test_model_catalog_service.py
tests/unit/test_v1_models_catalog.py
```

`oap/active` is exactly `010-b`; the matching order is unique. The 010-a order
and report remain byte-for-byte unchanged. The final report-publication commit
adds only `oap/reports/010-b-correct-codex-profile-v2-layout.md`.

## Local verification

- `.venv/bin/python -m pytest -q tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py tests/unit/test_admin_catalog_dashboard_service.py tests/unit/test_admin_catalog_routes.py tests/unit/test_admin_key_create_routes.py tests/unit/test_admin_key_create_templates.py tests/unit/test_admin_route_actions_routes.py tests/unit/test_model_catalog_service.py tests/unit/test_v1_models_catalog.py`:
  PASSED — 124 tests in 22.81 seconds; zero failures/errors/skips.
- `.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_documentation_contract_drift.py`:
  PASSED — 17 tests in 2.71 seconds; zero failures/errors/skips.
- `.venv/bin/ruff check app/slaif_gateway/api/admin.py tests/unit/test_cli_codex.py tests/unit/test_admin_key_create_templates.py tests/browser/test_admin_dashboard_smoke.py`:
  PASSED.
- `.venv/bin/python -m compileall -q app/slaif_gateway tests/unit scripts/verify_codex_profile.py`:
  PASSED in 0.76 seconds.
- `sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json`:
  PASSED —
  `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432`.
- Final manual numeric-loopback verifier: PASSED as recorded above.
- Exact allowed-path, branch, active-pointer, order/report topology, commit
  parentage, local/remote-head, and clean-worktree checks: PASSED.
- Product `git diff --check`: PASSED. When the unchanged strategic order was
  staged with the implementation, `git diff --cached --check` reported only
  its preexisting second blank line at EOF. The coding agent did not modify the
  immutable strategic bytes; the order digest above is exact. Product changes
  had no whitespace errors.
- Local Playwright browser smoke: NOT RUN. Existing local prerequisites were
  unavailable: `TEST_DATABASE_URL=missing`, `CHROMIUM=missing`. GitHub's exact
  browser smoke passed on the implementation head.
- Full local unit suite: NOT RUN — prohibited by focused test economy; GitHub
  CI owns broad routine coverage.
- Local integration/PostgreSQL suites: NOT RUN — prohibited; no migration or
  local database write was required.
- Local E2E, browser matrix, Docker/Compose, and HPC suites: NOT RUN —
  prohibited by the active order.
- Real upstream/provider/gateway smoke: NOT RUN — prohibited; objective 011
  owns that boundary.

One initial focused attempt used the system Python and stopped before test
collection because `structlog` was unavailable there. No test failed and no
repository state changed; all required runs then used the repository `.venv`.
A direct profile command without `DATABASE_URL` likewise exited at the normal
readiness-database configuration guard before rendering; unit coverage and the
manual verifier exercised the deterministic renderer in the intended isolated
contexts.

## GitHub CI / checks and focused repair

All ten checks completed successfully for implementation head
`ee1ef823220ac5e058740e7dcd152316ab87f7c7`, observed after exact 30-second
wait blocks:

- `Analyze (javascript-typescript)`: SUCCESS — 37s.
- `Analyze (python)`: SUCCESS — 1m36s.
- `Analyze Python`: SUCCESS — 1m14s.
- `CodeQL`: SUCCESS — 2s.
- `Docker Compose smoke`: SUCCESS — 56s.
- `Documentation hygiene`: SUCCESS — 5s.
- `OpenAI-compatible E2E tests`: SUCCESS — 1m15s.
- `Playwright browser smoke`: SUCCESS — 1m27s.
- `PostgreSQL integration tests`: SUCCESS — 2m20s.
- `Unit, lint, and migration head`: SUCCESS — 2m01s.
- All implementation-head checks green at report drafting: YES.
- Fresh report-head checks may run after SELF publication; the response FIFO
  remains withheld until the remote report head and its checks are verified.

The first implementation-head run exposed two in-scope test-contract issues,
not product qualification failures: Rich help rendering wrapped the literal
`--base-url` assertion, and the selector appended a real-E2E suffix to a
`not_declared` route. The GitHub CI log inspection workflow identified both.
Commit `ee1ef823220ac5e058740e7dcd152316ab87f7c7` tests Click command metadata
directly, keeps the undeclared label concise, and adds the corresponding unit
regression. The focused 11-test repair set passed locally, and both previously
failing GitHub jobs then passed. The GitHub CI-fix skill materially guided the
bounded log inspection and repair verification.

## Documentation impact

Updated `AGENTS.md`, `docs/codex-compatibility.md`,
`docs/compatibility-matrix.md`, `docs/configuration.md`,
`docs/database-schema.md`, and `docs/security-model.md` for the exact profile-v2
layout, strict metadata/readiness contract, admin/pilot behavior, public-model
privacy boundary, and honest `protocol_qualified` support level. The current
official OpenAI Codex configuration reference and advanced-configuration guide
confirmed the separate `$CODEX_HOME/slaif.config.toml` profile-v2 layer and
prevented reintroducing the rejected legacy profile table/selector:

- `https://developers.openai.com/codex/config-reference`
- `https://developers.openai.com/codex/config-advanced`

The OpenAI documentation skill materially determined the corrected two-file
configuration contract. Documentation does not claim real-provider E2E, full
compatibility, pilot completion, or production certification.

## Local setup / dependencies

- Packages/tools/services installed or configured: NONE.
- `sudo`-level setup performed: NONE.
- Durable local setup changes: NONE.
- Existing repository `.venv` and pinned `/usr/bin/codex` were used.
- No user/repository Codex configuration was read or modified by the verifier.

## Safety, privacy, and scope confirmations

- Unrelated files changed: NO.
- Earlier order/report bytes changed: NO.
- Production secrets accessed: NO.
- Production systems accessed: NO.
- Real provider/gateway or side-effecting external tool called: NO.
- Gateway/admin key actually created or mutated during verification: NO.
- User `~/.codex` or repository `.codex` modified: NO.
- Replacement/partial model catalog created: NO.
- Raw model catalog, request, response, prompt, completion, body, tool payload,
  API key, provider key, gateway key, or arbitrary pricing text printed,
  persisted, or committed: NO.
- Existing accounting, HMAC, schema, migrations, and content-storage boundaries
  preserved: YES.
- Required focused tests skipped: NO.
- Every broad/local or real-provider suite not run is listed explicitly above.
- Scope deviation or contract weakening: NO.
- Extra objective-010 PR created: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled by coding agent: NO.
- `.local-provider-catalog/` accessed, modified, staged, or committed: NO.
- Report-publication commit changes only this report: YES, verified before the
  FIFO response.

## Final safety statement

This turn amended only PR #235, preserved the immutable 010-a history, kept the
claim at local `protocol_qualified` with `real_provider_e2e=false`, and
performed no merge or auto-merge action. Coding-agent `OK` after remote SELF
and report-head verification means only that this execution turn, immutable
report, and claimed GitHub state are published; it does not mean the work is
accepted.
