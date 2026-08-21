# OAP 021-b execution report

Implementation head SHA: 444361422f38b7660e24425a16ddb4af57b7016f
Report publication commit: SELF

## Scope and PR state

Objective 021-b amended existing PR #247 on branch
`oap/021-versioned-generic-codex-profile-framework`, base `main`:
`https://github.com/ulfe-lmi/slaif-api-gateway/pull/247`.

The PR is open and unmerged. No merge or auto-merge was performed. The two
live review threads were code-quality findings for the unused
`_REQUIRED_FIELDS` declaration and redundant `compatible_ids` assignment.
Both were removed/fixed in this implementation and then resolved through the
GitHub review-thread API. A final thread query shows both resolved and no new
threads.

## Implementation evidence

Generic qualification now resolves all model ranking, provider kind/slug,
endpoint requirements, gates, limits, and result facts from the selected
profile. Version-1 behavior and the default renderer remain compatible. The
version-2 result carries profile ID, metadata version, CLI version, profile,
catalog source, wire API, provider kind/display identity, and live-provider
evidence from the resolved registry definition.

Provider readiness checks exact registered provider kind for version-2 routes
and exact provider slug when configured. A synthetic unregistered profile test
uses a non-OpenAI `openai_compatible` provider, a non-GPT model, a higher-
priority exact route against a lower-priority prefix decoy, one Responses
endpoint, and client-local compaction. It proves profile-derived ranking,
provider-kind failure, no compact-pair requirement, and safe result fields.
The synthetic definition is accepted only by the pure artifact renderer;
runtime/CLI selection rejects caller-supplied unregistered profile objects.

Registry construction validates safe IDs/names/versions, supported wire API,
provider kind, compaction mode, canonical unique endpoints/gates/tools, strict
booleans, coherent positive limits, SHA-256/date, immutable provider fields,
and optional catalog artifact/target pairs. Catalog JSON is canonical,
bounded, credential-free, and rejects URLs, secrets, prompt/output/tool/
reasoning content, traversal/absolute targets, and mutable mismatches.

Fixture sanitization now bounds total nodes, IDs, depth, and list cardinality;
maps first-seen opaque IDs to stable `ID_1`, `ID_2`, … placeholders; rejects
input digests; and rejects secret-looking/content-like values, URLs, headers,
credentials, environment/workspace paths, tool content, and arbitrary keys.

Admin route DTOs receive profile facts from the resolved qualification result,
not from independently trusting route JSON. Version-1 keeps the exact legacy
ready paragraph; version-2 uses escaped profile facts. Ready registered routes
can display and download the deterministic base/profile/catalog artifacts only
when a validated configured SLAIF gateway `/v1` URL is available. Non-ready,
unknown, or drifted routes return no artifact. Provider base URLs and upstream
credentials are not used as artifact gateway URLs.

## Focused verification

Exact focused command:

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py tests/unit/test_admin_catalog_routes.py tests/unit/test_admin_catalog_templates_safety.py tests/unit/test_codex_gateway_e2e_verifier.py tests/unit/test_documentation_contract_drift.py
```

Result: **145 passed**, 0 failed, 0 skipped. One existing Starlette/httpx
deprecation warning was emitted. The test set includes 16 registry, 62
qualification, 7 admin-route, 6 CLI, 1 template-safety, 38 verifier, and 15
documentation-contract tests.

Additional scoped checks:

```text
.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/services/admin_catalog_dashboard.py app/slaif_gateway/api/admin.py app/slaif_gateway/schemas/admin_catalog.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_admin_catalog_routes.py  # passed
python -m compileall -q app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/services/admin_catalog_dashboard.py app/slaif_gateway/api/admin.py app/slaif_gateway/schemas/admin_catalog.py  # passed
git diff --check  # passed
```

No local PostgreSQL setup or cleanup was required by this framework-only
focused order. CI independently ran and passed its PostgreSQL integration
job. No schema migration, request-runtime widening, real provider/LAN call,
Codex capture/live run, real email, production service, credential, prompt,
response, tool payload, reasoning content, or secret was used or committed.

## GitHub checks and publication

All ten checks passed for implementation head
`444361422f38b7660e24425a16ddb4af57b7016f`:

```text
Analyze (javascript-typescript)       pass
Analyze (python)                      pass
Analyze Python                        pass
CodeQL                                pass
Docker Compose smoke                  pass
Documentation hygiene                 pass
OpenAI-compatible E2E tests           pass
Playwright browser smoke              pass
PostgreSQL integration tests          pass
Unit, lint, and migration head        pass
```

Documentation now distinguishes registry-scoped configured, mocked-
conformant, protocol-qualified, and live-qualified states and documents the
synthetic-only profile/artifact boundary. No production, release, compliance,
or live-provider qualification claim follows. Strategic acceptance, merge,
release, and roadmap decisions remain outside the coding agent's authority.
