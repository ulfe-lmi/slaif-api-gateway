# OAP Report — 019-b

Implementation head SHA: 8802b2acff74508af29e7f96d00b6a0c1d25f854
Report publication commit: SELF

## Scope

Amended PR #245 on `oap/019-openai-compatible-backend-wizard-discovery`.
The round closes explicit local-zero pricing acknowledgement, scalar public
model-ID mappings, confirmed CLI setup, direct generic-provider admin evidence,
and PostgreSQL rollback evidence. No migration, public endpoint, provider
runtime, real network/provider, email, or production change was made.

## Implementation evidence

- `SetupRequest` now requires an explicit local-zero acknowledgement; explicit
  pricing validates finite non-negative Decimal values and rejects a
  contradictory acknowledgement.
- Admin discovery preview renders escaped editable
  `<provider>/<upstream_model>` defaults and submits repeated scalar
  `upstream=public` fields. Execution re-probes and validates fresh selected
  models before mutation.
- `providers setup-models` reuses `OpenAICompatibleSetupService`, requires
  `--confirm-execute`, pricing confirmation/equivalent values, and an audit
  reason. Its JSON is restricted to provider, safe model/row IDs and counts,
  preset, enabled state, and pricing mode.
- The active selector and unchanged 019-b order are included on this PR.

## Local verification

Passed scoped Ruff and diff checks:

```text
.venv/bin/ruff check app/slaif_gateway/services/openai_compatible_setup.py app/slaif_gateway/cli/providers.py app/slaif_gateway/api/admin.py tests/unit/test_openai_compatible_setup.py tests/unit/test_cli_providers.py tests/unit/test_admin_provider_config_actions_routes.py tests/integration/test_openai_compatible_setup_postgres.py
git diff --check
```

Passed 54 focused unit tests: 10 setup, 7 CLI, 14 admin route, 8 OAP
governance, and 15 documentation-contract-drift tests.

Passed the focused PostgreSQL setup test file: 2/2. It used a disposable
`slaif_test_019_b_*` database created with `createdb` and removed with
`dropdb`; the injected audit failure occurred after route and pricing writes,
and a fresh session verified route, pricing, and audit counts were unchanged.
The temporary provider configuration is explicitly deleted by the test.

Passed the combined setup/readiness regression slice: 7/7, using the same
safe disposable database naming and cleanup.

Passed template parsing, application `compileall`, and Alembic head checks:

```text
JINJA_PARSE=OK
0015_external_tool_exclusive_fence (head)
```

No real provider calls, LAN calls, email delivery, production access, or
secrets were used. No provider body, key, headers, arbitrary metadata, or
content is persisted or emitted by the new preview/CLI paths.

## GitHub checks

After the cleanup follow-up commit, every reported PR check passed:

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

An earlier PostgreSQL job on the initial implementation head failed because
the new evidence test left its temporary provider configuration behind. That
in-scope test-isolation defect was repaired in `8802b2a`; the replacement job
passed in 2m36s.

## Documentation, privacy, and security

No documentation expansion was required. The preview uses escaped template
values and bounded scalar fields rather than JSON or hidden provider bodies.
The CLI emits only the safe result DTO. PostgreSQL remains the transaction
authority; Redis and real upstream services are not involved.

## Merge status

PR #245 remains open. No merge, auto-merge, release, or direct push to `main`
was performed.
