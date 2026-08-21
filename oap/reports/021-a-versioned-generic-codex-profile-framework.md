# OAP 021-a execution report

Implementation head SHA: d1954057a0487e06026d1c91508462ecb18d1945
Report publication commit: SELF

## Scope and PR state

Objective 021-a created PR #247:
`https://github.com/ulfe-lmi/slaif-api-gateway/pull/247`.

The PR is open and unmerged, based on `main`, with branch
`oap/021-versioned-generic-codex-profile-framework`. No merge or auto-merge
was performed. The implementation head includes the exact activated order and
`oap/active=021-a`; this report is the only intended follow-up commit.

The change adds an immutable server-defined profile registry and preserves the
existing version-1 qualification object/parser, current profile constants,
pilot-key restrictions, default renderer bytes, and verifier behavior. The
built-in registry entry is `openai-gpt-5.6-sol-codex-0.147-v1`, with metadata
version 2, CLI `0.147.0`, model `gpt-5.6-sol`, OpenAI Responses/compact,
1,050,000 context, 32,768 default output, 128,000 maximum output, remote V1
compaction, the existing fixture digest/date, mocked qualification true, and
live qualification false. No Qwen or other future target is registered.

Version-2 route metadata is restricted to the exact server-owned identity
tuple `{version, profile_id, fixture_sha256}`. Registry lookup and import
validation reject unknown, malformed, duplicate, mixed, drifted, or unsafe
definitions. Qualification uses registry identity/capabilities/limits and
explicit route gates; it does not infer authority from model names or
arbitrary route JSON. Unknown profile, digest/version/field drift, provider,
model, endpoint, paired-route, selection, gate, limit, provider, pricing, FX,
and disabled-state failures remain bounded not-ready/invalid outcomes.

The renderer accepts a selected registered ready profile while
`render_codex_profile(base_url)` retains the existing byte-compatible default.
CLI selection is optional and fail-closed. Admin route DTOs/templates expose
only validated profile identity/version. The fixture helper retains only
bounded structural event/field/tool types, deterministic ID placeholders,
ordering/cardinality, booleans/numbers, and a deterministic digest; prompt,
output, tool content, bodies, URLs, headers, keys, cookies, environment,
workspace paths, and arbitrary metadata are rejected.

## Focused verification

Exact command:

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py tests/unit/test_admin_catalog_routes.py tests/unit/test_admin_catalog_templates_safety.py tests/unit/test_codex_gateway_e2e_verifier.py tests/unit/test_documentation_contract_drift.py
```

Result: **138 passed**, 0 failed, 0 skipped. One existing Starlette/httpx
deprecation warning was emitted. The selected files cover registry positive
and negative declarations, fixture privacy, version-1 compatibility,
version-2 qualification, CLI safe output and selection, admin route/template
safety, verifier safety boundaries, and documentation contract drift.

Additional scoped checks:

```text
.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/cli/codex.py app/slaif_gateway/schemas/admin_catalog.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py  # passed
python -m compileall -q app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/cli/codex.py app/slaif_gateway/schemas/admin_catalog.py  # passed
git diff --check  # passed
```

No PostgreSQL setup or cleanup was required by this framework-only focused
unit/admin/verifier order, and no local integration database was created. CI's
PostgreSQL integration job passed independently. No migration was added.

## GitHub checks

All ten checks passed for implementation head
`d1954057a0487e06026d1c91508462ecb18d1945`:

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

Routine broad CI coverage passed. No real Codex process, real upstream
provider, LAN backend, production service, real email, secret, credential,
prompt, response, tool payload, reasoning content, or prohibited fixture data
was used or committed. The implementation does not widen request/event/tool
runtime acceptance or claim live-provider, production, release, or compliance
qualification.

Documentation impact is limited to the Codex compatibility contract and
compatibility matrix, which now distinguish configured, mocked-conformant,
protocol-qualified, and live-qualified evidence and document the registry
boundary. Strategic acceptance, merge, release, and roadmap decisions remain
outside the coding agent's authority.
