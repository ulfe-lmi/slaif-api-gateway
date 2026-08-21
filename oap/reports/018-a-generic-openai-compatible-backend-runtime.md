# OAP execution report — 018-a

## Result

Objective 018-a created PR #244:

<https://github.com/ulfe-lmi/slaif-api-gateway/pull/244>

Implementation head SHA: 4616033e873824c5230428499028208047be7256
Report publication commit: SELF

The PR remains open and ready for review, with auto-merge disabled. No merge,
release, production access, migration, real provider call, or real email was
performed.

## Implementation delivered

- Added the safe `provider_kind` route field and populated it from provider
  configuration without changing provider slugs used by routing, diagnostics,
  accounting, or audit metadata.
- Added a thin generic `openai_compatible` adapter that reuses the canonical
  OpenAI wire implementation while retaining the configured provider slug.
  Built-in `openai` and `openrouter` selection remains unchanged.
- Added server-side environment-name validation, rejection of the client key
  environment name, exact `/v1` URL validation for generic backends, valid-port
  checking, no-redirect behavior through the existing HTTPX defaults, and
  fail-closed missing/invalid configuration handling.
- Added explicit confirmation and non-empty audit-reason gates for generic HTTP
  LAN backends in the service, CLI, and admin create/edit flows. Templates warn
  that bearer credentials and content traverse LAN HTTP unencrypted.
- Added focused factory/service tests and documentation distinguishing built-in
  adapters from operator-defined runtime foundation. No migration was added.

## Verification

Exact focused command passed:

```text
.venv/bin/python -m pytest -q tests/unit/test_provider_factory.py tests/unit/test_openai_provider_adapter.py tests/unit/test_openai_provider_streaming.py tests/unit/test_provider_config_service.py tests/unit/test_route_resolution_service.py tests/unit/test_cli_providers.py tests/unit/test_admin_provider_config_actions_routes.py tests/unit/test_admin_catalog_templates_safety.py
76 passed, 0 failed, 0 skipped
```

The targeted governance and source-safety repair command passed 12 tests:

```text
.venv/bin/python -m pytest -q tests/unit/test_oap_governance.py tests/unit/test_cli_routing_pricing_safety.py
12 passed, 0 failed, 0 skipped
```

Scoped Ruff, compileall, `git diff --check`, and `.venv/bin/python -m alembic
heads` passed. Alembic reported the single head
`0015_external_tool_exclusive_fence`.

The first CI run passed 3,172 tests and exposed two bounded governance/source
safety failures; both were repaired in the implementation follow-up commit.
The final GitHub unit/lint/migration check passed. No test failure remains.

No local PostgreSQL setup was required. GitHub PostgreSQL integration used its
CI-managed disposable database lifecycle and passed; no `DATABASE_URL` or
production database was touched. No local test was skipped. No real upstream
provider, email, MCP, or external service call was made, and no credentials or
secrets were printed or committed.

## GitHub checks

All ten required checks passed on implementation head
`4616033e873824c5230428499028208047be7256`:

- Unit, lint, and migration head
- PostgreSQL integration tests
- OpenAI-compatible E2E tests
- Playwright browser smoke
- Docker Compose smoke
- Documentation hygiene
- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL

## Scope, privacy, and handoff

Only the activated 018-a order was executed. The implementation does not
discover, call, or inspect human Qwen/vLLM services; tests use mocks and local
metadata. Provider secret values remain server-side and are never accepted in
CLI/admin JSON, HTML, errors, audit values, logs, or outbound client headers.
The generic runtime does not gain OpenAI hosted web-search authority or
OpenRouter provider-reported cost semantics.

The implementation commit was pushed before this report. This final report
commit has the implementation head as its first parent and changes only this
new report file. No repository mutation or push will occur after publication.
No merge or auto-merge action was performed.
