# OAP Report — 019-c

Implementation head SHA: ecbf315c5f73aaa199f4d26d53e11848e9f2c221
Report publication commit: SELF

## Scope

Amended PR #245 on `oap/019-openai-compatible-backend-wizard-discovery`.
This round makes the direct `OpenAICompatibleSetupService` contract fail
closed: when `public_model_ids` is supplied, its keys must exactly equal the
selected upstream-model set. The no-mapping default remains supported.

## Implementation and evidence

- Normalization rejects missing, extra discovered, extra unknown, and
  duplicate-public-ID mappings before discovery or mutation.
- Valid exact mappings remain accepted and are passed through the shared setup
  path; admin and CLI scalar mapping tests remain green.
- Added direct unit coverage for each required rejection boundary and valid
  exact mapping.
- Included the unchanged 019-c order and `oap/active=019-c` on PR #245.

## Local verification

Passed the exact scoped command:

```text
.venv/bin/ruff check app/slaif_gateway/services/openai_compatible_setup.py tests/unit/test_openai_compatible_setup.py tests/unit/test_cli_providers.py tests/unit/test_admin_provider_config_actions_routes.py
git diff --check
.venv/bin/python -m compileall -q app/slaif_gateway
.venv/bin/alembic heads
```

The Alembic head was:

```text
0015_external_tool_exclusive_fence (head)
```

Focused tests passed 43/43 with zero skips: 14 setup, 7 CLI, 14 admin-route,
and 8 OAP-governance tests. No PostgreSQL rerun was required by the order;
the service-only change did not alter PostgreSQL code or fixtures.

No real provider/network call, email delivery, production access, or secret
was used. The change contains no provider body, credentials, headers, or
arbitrary metadata handling.

## GitHub checks

All final PR checks passed on implementation head `ecbf315`:

- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL
- Docker Compose smoke
- Documentation hygiene
- OpenAI-compatible E2E tests
- Playwright browser smoke
- PostgreSQL integration tests
- Unit, lint, and migration head

## Documentation, privacy, and security

No documentation changes were required. Exact-set validation strengthens the
existing fail-closed public-ID boundary and preserves PostgreSQL as the
authoritative setup transaction store. No secrets or prohibited content were
printed, persisted, or committed.

## Merge status

PR #245 remains open. No merge, auto-merge, release, or direct push to `main`
was performed.
