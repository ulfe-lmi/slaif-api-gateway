# OAP Coding-Agent Report — 147-a

## Work order

- Identifier: 147-a
- Work-order file: `oap/orders/147-a-module-provider-foundation-and-fixed-request-billing.md`
- Result: PARTIAL — implementation is pushed, but required GitHub checks are blocked by stale migration-head assertions outside the allowed paths.
- PR: #282 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/282
- Base: `main` at `ddf6688b93cda905e0bc38673f6138afb2385a28`
- Branch: `oap/147-module-provider-foundation`
- Implementation head SHA: `f4adaf98dd448bbac18ff1b3da4b31a252f3b3b6`
- Commits before this report: `f4adaf98dd448bbac18ff1b3da4b31a252f3b3b6` (`feat: add module provider foundation and fixed request billing`)
- Report publication commit: SELF

## Scope delivered

- Added provider kind `module` and migration `0023_module_provider_foundation`.
- Added a minimal abstract `ProviderAdapter`-based native-module contract and a reviewed static registry/dispatch boundary. The registry is empty in this objective; unknown modules fail closed and configuration cannot select imports or classes.
- Preserved server-side provider credential loading from the configured environment variable. The client gateway Authorization token is not used as the module credential.
- Added fixed-request Chat Completions pricing for module routes, including exact zero EUR pricing, with existing EUR conversion.
- Added one-request/zero-token module reservations while preserving policy, request-limit, concurrency, rate-limit, revocation, expiry, and external-tool fence controls.
- Added successful normal Chat accounting with zero provider usage tokens and fixed request cost, including exact zero EUR, while retaining reservation and PostgreSQL ledger finalization ownership in the gateway.
- Added provider configuration/admin/CLI/template support and updated the three required contract documents.
- Did not add a facial adapter, facial registration, downstream call, streaming, Responses support, dynamic plugins, production provider data, secrets, or live provider qualification.

## Files changed

The implementation commit changed exactly these paths; all are in the activated order's allowed paths or are the activated OAP order/pointer:

- `app/slaif_gateway/api/admin.py`
- `app/slaif_gateway/cli/providers.py`
- `app/slaif_gateway/db/models.py`
- `app/slaif_gateway/modules/__init__.py`
- `app/slaif_gateway/modules/base.py`
- `app/slaif_gateway/providers/factory.py`
- `app/slaif_gateway/services/accounting.py`
- `app/slaif_gateway/services/chat_completion_gateway.py`
- `app/slaif_gateway/services/chat_completion_route_capabilities.py`
- `app/slaif_gateway/services/pricing.py`
- `app/slaif_gateway/services/provider_config_service.py`
- `app/slaif_gateway/services/quota_service.py`
- `app/slaif_gateway/web/templates/providers/create.html`
- `app/slaif_gateway/web/templates/providers/detail.html`
- `app/slaif_gateway/web/templates/providers/edit.html`
- `docs/accounting.md`
- `docs/openai-compatibility.md`
- `docs/provider-forwarding-contract.md`
- `migrations/versions/0023_module_provider_foundation.py`
- `oap/active`
- `oap/orders/147-a-module-provider-foundation-and-fixed-request-billing.md`
- `tests/integration/test_module_provider_foundation_postgres.py`
- `tests/unit/test_accounting_service_finalize.py`
- `tests/unit/test_alembic_provider_pricing.py`
- `tests/unit/test_module_provider.py`
- `tests/unit/test_pricing_service.py`
- `tests/unit/test_provider_config_service.py`
- `tests/unit/test_quota_service.py`

## Acceptance-criteria evidence

### Criterion 1 — module kind and migration

- Result: PASS locally; GitHub integration remains PARTIAL because of an unrelated stale head assertion.
- Evidence: `0023_module_provider_foundation.py` revises `0022_provider_governance`, extends the PostgreSQL kind check to `module`, and preserves the downgrade check. The focused PostgreSQL run accepted a module row and rejected `dynamic_import`. Local `alembic heads` reported `0023_module_provider_foundation`.

### Criterion 2 — configuration and URL boundaries

- Result: PASS in focused tests.
- Evidence: Provider service, admin form, CLI help, templates, module URL validation, insecure-HTTP confirmation/reason, and audit behavior are covered by the focused unit suite. Module URLs do not receive a hardcoded `/v1` requirement; userinfo, query, fragment, invalid ports, whitespace/control characters, and unsafe schemes remain rejected.

### Criterion 3 — static module dispatch

- Result: PASS in focused tests and static inspection.
- Evidence: The registry is source-defined and empty; no dynamic import or user-selected class path exists. An unregistered module raises `unsupported_module` without exposing the configured secret. A registered test adapter receives the server-side environment secret and operator URL only.

### Criterion 4 — fixed-request pricing

- Result: PASS in focused tests.
- Evidence: A module Chat pricing rule requires non-null non-negative `request_price`, ignores token component prices for billing, uses existing EUR conversion, and returns exact zero cost for a zero EUR rule.

### Criterion 5 — quota reservation

- Result: PASS locally.
- Evidence: Focused quota tests and the PostgreSQL module test recorded one reserved request, zero reserved tokens, and zero reserved EUR. Existing non-module reservation behavior remained covered by the focused suite; policy and hard-limit paths were not bypassed.

### Criterion 6 — successful accounting

- Result: PASS locally.
- Evidence: Focused accounting tests and the PostgreSQL module test finalized a representative provider response containing nonzero reported usage as zero prompt/completion/total tokens with fixed request billing and zero EUR. The existing gateway finalization path owns the ledger, counters, and reservation transition.

### Criterion 7 — credential and privacy boundary

- Result: PASS in focused tests and static inspection.
- Evidence: Provider credentials are resolved only through the configured environment variable; the client Authorization token is explicitly excluded from module dispatch. No raw credential, request content, response content, image, data URL, or external provider call was used by this objective. Static inspection found no dynamic import path in the module foundation.

### Criterion 8 — documentation and non-goals

- Result: PASS.
- Evidence: `docs/accounting.md`, `docs/openai-compatibility.md`, and `docs/provider-forwarding-contract.md` describe fixed-request/zero-price accounting, static registration, zero token usage in this billing mode, and the unsupported streaming/Responses/facial boundary.

## Local verification

- `.venv/bin/python -m pytest tests/unit/test_module_provider.py tests/unit/test_provider_factory.py tests/unit/test_provider_config_service.py tests/unit/test_pricing_service.py tests/unit/test_quota_service.py tests/unit/test_accounting_service_finalize.py tests/unit/test_chat_completion_route_capabilities.py tests/unit/test_alembic_provider_pricing.py tests/unit/test_cli_providers.py -q`: PASSED — 116 tests.
- `.venv/bin/python -m pytest tests/integration/test_module_provider_foundation_postgres.py tests/integration/test_accounting_finalization_postgres.py tests/integration/test_quota_accounting_invariants_postgres.py tests/integration/test_admin_provider_config_actions_postgres.py -q`: PASSED — 8 tests, using an isolated disposable PostgreSQL database. The database was dropped after verification.
- `.venv/bin/ruff check app tests`: PASSED.
- `.venv/bin/alembic heads`: PASSED — `0023_module_provider_foundation (head)`.
- `git diff --check`: PASSED.
- `python -m compileall -q app/slaif_gateway migrations/versions/0023_module_provider_foundation.py`: PASSED.
- Static dynamic-import/credential/content inspection over the module foundation and forwarding/accounting paths: PASSED; only the intentional comment that client Authorization is not passed was found.
- `.venv/bin/python -m pytest tests/unit -q`: FAILED locally with 24 failures. The failures included five stale migration-head assertions and unrelated production-settings/OpenRouter forwarding tests; this broad run did not authorize changes outside the order's allowed paths.

## GitHub CI / required checks

State observed for implementation head `f4adaf98dd448bbac18ff1b3da4b31a252f3b3b6` in CI run `32647316452` and analysis run `32647314889`:

- Analyze (python): SUCCESS.
- Analyze Python: SUCCESS.
- Analyze (javascript-typescript): SUCCESS.
- CodeQL: SUCCESS.
- Docker Compose smoke: SUCCESS.
- OpenAI-compatible E2E tests: SUCCESS.
- Playwright browser smoke: SUCCESS.
- Documentation hygiene: SUCCESS.
- Unit, lint, and migration head: FAILURE — 3393 passed, 5 failed, 1 skipped, 15 warnings. All five failures are stale assertions expecting `0022_provider_governance` in `tests/unit/test_alembic_accounting.py`, `tests/unit/test_alembic_email_jobs.py`, `tests/unit/test_alembic_external_tool_fence.py`, `tests/unit/test_alembic_key_prefix_default.py`, and `tests/unit/test_schema_status.py`. The job stopped before its Ruff, Alembic-head, and whitespace steps.
- PostgreSQL integration tests: FAILURE — 213 passed, 1 failed, 1 skipped, 35 warnings. The failure is `tests/integration/test_gateway_key_prefix_migration_postgres.py::test_migration_0005_normalizes_gateway_key_prefix_and_default`, which still expects `0022_provider_governance` after a successful upgrade to the new head.
- Required GitHub checks green for the implementation head at report drafting: no.
- PR review state: no approval decision; GitHub code-quality review left a comment. Merge state is `UNSTABLE`. Auto-merge is disabled.
- The report-only commit may trigger fresh checks. The strategic model must verify the `SELF` commit independently; this report will not be rewritten.

## Local setup / dependencies

- Created the ignored repository `.venv` and installed the package with development dependencies because the system Python is externally managed.
- Created a safe disposable PostgreSQL database with the narrow local PostgreSQL helper commands, used it only through `TEST_DATABASE_URL`, and dropped it after tests.
- No durable setup changes were committed. No production database, Redis, Docker deployment, upstream credential, email service, or external provider was accessed.

## Documentation

The three required documents were updated in the implementation commit. They state the static module foundation, configured credential/URL boundaries, fixed request billing, zero-price semantics, zero token accounting, and the explicit absence of facial, streaming, Responses, dynamic-plugin, and live-provider behavior.

## Safety and scope confirmations

- Unrelated files changed: NO. The implementation paths are within the order's allowed list; `oap/active` and the activated order were carried as orchestration evidence and not substantively edited by the coding agent.
- Production secrets accessed: NO.
- Production systems accessed: NO.
- Real upstream calls: NO.
- Real email sent: NO.
- Raw secrets or request/response/image content printed, persisted, or committed: NO.
- Required tests skipped/not run: YES — the order's focused checks ran. The full GitHub required check suite ran; its two failures are recorded above. No failure was represented as a pass.
- Scope deviation: NO. The stale assertion repair would require files explicitly outside the activated allowed paths and therefore was not made.
- Extra PR created for objective 147: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled: NO.
- Activated order and `oap/active` edited by coding agent: NO; the activated files were carried unchanged into the implementation commit.
- Report-publication commit changes only this report file: YES, to be verified before publication.

## Known limitations / blockers

- The PR cannot satisfy the required GitHub check gate until the six stale migration-head assertions are updated or the strategic model authorizes another compatible repair. That repair is outside this order's allowed paths, and the coding agent must not silently widen scope or weaken/remove the tests.
- The native module registry is intentionally empty. No facial-scoring adapter, endpoint rollout, API key, production row, downstream call, or live qualification exists.
- The report records the implementation-head CI state. Checks triggered by the report publication commit may differ and must be independently inspected by the strategic model.

## Recommended strategic follow-up

Authorize a bounded continuation order on PR #282 that permits updating the stale migration-head expectations in the named unit and integration tests, then rerun the complete required GitHub checks. Merge, abandon, or amend decisions remain strategic decisions.
