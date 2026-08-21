# OAP execution report — 018-b

## Result

Continuation `018-b` amended the sole Objective 018 PR #244:

<https://github.com/ulfe-lmi/slaif-api-gateway/pull/244>

Implementation head SHA: 48de32fe13f6aacdb0e23425dc113de66e4d822a
Report publication commit: SELF

The PR remains open, ready for review, and auto-merge disabled. No merge,
release, production access, migration, real provider call, or real email was
performed.

## Repairs delivered

- Restored built-in OpenRouter `/api/v1` admin create/edit acceptance while
  retaining exact `/v1` enforcement for operator-defined generic providers.
  Service and admin URL validation now agree on provider-aware behavior.
- Made generic adapters require their exact configured secret and never fall
  back to `Settings.OPENAI_UPSTREAM_API_KEY`. Missing-secret failures retain
  the generic provider slug and do not disclose the built-in secret.
- Added canonical lowercase ASCII provider-slug validation and bounded length
  at provider-config create/update. Existing rows are not silently rewritten
  and no migration was added.
- Added explicit `follow_redirects=False` to runtime-created OpenAI-compatible
  HTTPX clients and a mocked 3xx/no-second-origin test.
- Added direct route metadata propagation, service audit acknowledgement
  evidence, CLI/admin HTTP confirmation tests, OpenRouter regression coverage,
  and safe environment-name-only rendering assertions.
- Updated README, AGENTS, configuration, schema, deployment, compatibility,
  and security contracts to distinguish built-ins from the generic runtime
  foundation and its non-claims.

## Verification

The required focused union passed:

```text
.venv/bin/python -m pytest -q tests/unit/test_provider_factory.py tests/unit/test_openai_provider_adapter.py tests/unit/test_provider_config_service.py tests/unit/test_route_resolution_service.py tests/unit/test_cli_providers.py tests/unit/test_admin_provider_config_actions_routes.py tests/unit/test_admin_catalog_templates_safety.py tests/unit/test_documentation_contract_drift.py
89 passed, 0 failed, 0 skipped
```

The supplemental governance run passed 8/8, and the combined local focused
run passed 97/97. Ruff, compileall, `git diff --check`, and
`.venv/bin/python -m alembic heads` passed. Alembic reported the single head
`0015_external_tool_exclusive_fence`.

The first CI implementation run passed 3,179 tests and exposed one governance
order-header failure. The order header was normalized to the repository’s
canonical form in the final implementation commit; the subsequent GitHub
unit/lint/migration check passed. No local PostgreSQL setup was required.
GitHub PostgreSQL integration used its CI-managed disposable database
lifecycle and passed; no `DATABASE_URL` or production database was touched.

## GitHub checks

All ten required checks passed on implementation head
`48de32fe13f6aacdb0e23425dc113de66e4d822a`:

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

Only the activated `018-b` order was executed. The implementation did not
inspect or call any human Qwen/vLLM service or configuration; upstream tests
used mocks only. Provider secret values remain server-side and are never
accepted in CLI/admin JSON, HTML, errors, audit values, logs, or client
headers. Generic HTTP warnings document unencrypted bearer/content traversal
and operator-owned firewall/reverse-proxy responsibility. Generic adapters do
not inherit hosted OpenAI tools or OpenRouter provider-reported cost authority.

The implementation commits were pushed before this report. The final report
commit has the implementation head as its first parent and changes only this
new report file. No repository mutation or push will occur after publication.
No merge or auto-merge action was performed.
