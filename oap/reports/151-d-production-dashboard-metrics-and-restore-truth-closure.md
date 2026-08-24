# OAP report — 151-d production dashboard, metrics, and restore truth closure

Report publication commit: SELF

Date: 2026-08-24 (Europe/Ljubljana)

Status: **QUALIFICATION PASS — objective boundary closed; no production-certification claim**

Objective 151-d continued PR #286 and repaired the independent-review defects
left by the historical 151-c report. This report is the single immutable
151-d report. It records a disposable RC-beta appliance qualification only; it
does not certify production readiness, security, compliance, SLA performance,
provider-invoice accuracy, or any real upstream deployment.

## Git and OAP evidence

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR: `#286`, branch `oap/151-production-appliance-closure`, still open
- Base recorded by the activated order: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
- Implementation head: `a6d5d8c3da381827e5b7fc0fd0e019f314aad4b0`
- Implementation head parent: `e15fa8bbea8450fc3c39a49ae856c809f33466b1`
- Activated order: `oap/orders/151-d-production-dashboard-metrics-and-restore-truth-closure.md`
- Active pointer: `oap/active` contains exactly `151-d\n`
- The report publication commit is required to be the first child of the
  implementation head, changes only this report path, and is pushed as the
  remote PR head before the OAP response signal.

The already-pushed 151-c migration-head fixture repairs were explicitly
inspected and retained in scope: `tests/unit/test_alembic_accounting.py`,
`tests/unit/test_alembic_email_jobs.py`,
`tests/unit/test_alembic_external_tool_fence.py`,
`tests/unit/test_alembic_key_prefix_default.py`,
`tests/unit/test_alembic_provider_pricing.py`,
`tests/unit/test_schema_status.py`,
`tests/unit/test_quota_accounting_invariants.py`, and
`tests/integration/test_gateway_key_prefix_migration_postgres.py`.

## Fresh no-keep qualification

Exact command, with inherited provider/database test variables removed:

```text
env -u APP_ENV -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS \
  -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY \
  ENABLE_EMAIL_DELIVERY=false \
  .venv/bin/python scripts/production-qualification/run.py
```

- Result: `RESULT=OK`
- Compose project: `slaif-151-3981570-28080`
- Cleanup: containers, networks, volumes, and runtime all absent; no
  residual project networks or volumes
- Email delivery: disabled
- Provider: isolated qualification double only

All 16 phases passed:

| Phase | Seconds | Result |
| --- | ---: | --- |
| prepare | 0.14 | OK |
| tls | 0.49 | OK |
| compose | 29.21 | OK |
| operator-configuration | 30.46 | OK |
| async-worker-and-scheduler-liveness | 6.04 | OK |
| chat-and-responses | 2.13 | OK |
| provider-failures-and-disconnects | 3.02 | OK |
| redis-and-timeout-controls | 9.74 | OK |
| redis-concurrency | 8.44 | OK |
| api-termination-and-cli-reconciliation | 16.17 | OK |
| persistence | 40.70 | OK |
| backup-restore | 12.74 | OK |
| privacy-input-boundaries | 0.68 | OK |
| quota-and-key-controls | 7.96 | OK |
| admin-dashboard-session | 0.29 | OK |
| privacy | 36.41 | OK |

### Dashboard boundary

The qualification client used ordinary `urllib` redirect handling through the
HTTPS Nginx port; the prior no-redirect handler was removed. The login form
was fetched at `/admin/login`, valid credentials were posted, the real login
redirect was followed, and the final response was HTTP 200 at the exact
`/admin` path with the dashboard marker. The session cookie was retained and
verified Secure. The same authenticated client then received HTTP 200 at the
exact `/admin/usage` and `/admin/audit` paths with their expected page markers.
No direct ASGI call, intermediate `303` acceptance, or direct-subpage-only
success condition was used.

`nginx/production.conf` now has a narrow exact `location = /admin` proxy and
the `/admin/` subtree proxy. No catch-all admin bypass was added, and the
public `/readyz` and `/metrics` surfaces remain unexposed by Nginx.

### Metrics and privacy truth

- Host access to the API diagnostic `/metrics` endpoint without the allowlist
  was required to return HTTP 403.
- Public HTTPS Nginx access to `/metrics` was required to remain denied (the
  configuration has no `/metrics` location; the bounded qualification check
  accepts only an HTTP 403/404 denial).
- The qualification-only Compose override set
  `METRICS_REQUIRE_AUTH=true` and `METRICS_ALLOWED_IPS=127.0.0.1`.
- A real request from inside the API container to
  `http://127.0.0.1:8000/metrics` returned HTTP 200 and the actual Prometheus
  exposition body. It contained the exercised families
  `gateway_http_requests_total`, `gateway_provider_requests_total`,
  `gateway_tokens_total`, and `gateway_cost_eur_total`.
- The actual exposition body, not a denial body or fabricated marker, was
  scanned together with logs, dashboard bodies, provider state, and database
  metadata for every generated canary and generated secret. No generated
  value was found.

### Restore and migration truth

The strict verifier accepts only the documented disposable PostgreSQL naming
grammar: `restore_test`, `restore_local_<lowercase-alphanumeric-suffix>`,
`test_slaif_gateway`, `slaif_gateway_test`, and `slaif_test`. Focused negative
cases rejected `contest`, `production_test`, `locality`, missing suffixes, and
non-PostgreSQL schemes before engine creation. It requires every fixed table
(`institutions`, `owners`, `gateway_keys`, `usage_ledger`, `audit_log`) in the
`public` schema, executes a read-only query against each, and emits only
bounded counts for `gateway_keys` and `usage_ledger`.

Against disposable database `restore_local_151d20260824`, migrations were
run to head, downgraded to `0023_module_provider_foundation`, and upgraded to
head again. Migration `0024_quota_reservation_accounting_facts` exposed
`provider`, `resolved_model`, and `streaming` as nullable columns after the
re-upgrade. The PostgreSQL restore verifier returned:

```text
RESULT=OK required_tables=institutions,owners,gateway_keys,usage_ledger,audit_log row_counts=gateway_keys:0,usage_ledger:0
```

The focused PostgreSQL migration integration test passed on a separate
disposable `restore_local_151dintegration` database, which was then dropped.

### Accounting, privacy, and cleanup

The qualification restore snapshot and restored database matched exactly:

```text
gateway_keys=2
usage_ledger=15
```

The interrupted streamed request reconciled with immutable route facts
`provider=qualification-double`, `resolved_model=qualification-model`, and
`streaming=true`; reservation counters were cleared and reconciliation audit
metadata was present. Normal, failed, expired, quota-denied, and finalized
accounting paths remained green. No prompts, completions, gateway keys,
provider keys, passwords, cookies, raw provider bodies, or canaries were
printed or persisted by the qualification evidence.

## Verification evidence

- `git diff --check`: passed
- Ruff on all changed Python files and focused tests: passed
- Focused verifier, Nginx, migration, migration-head fixture, and quota tests:
  47 passed
- Focused PostgreSQL gateway-key migration integration test: 1 passed on an
  isolated disposable database
- PostgreSQL `0024` upgrade/downgrade/re-upgrade: passed
- `scripts/verify_production_compose.py`: `RESULT=OK static=true compose=false`
- `docker compose -f docker-compose.production.yml config --quiet`: passed
- Fresh no-keep qualification: all 16 phases passed with exact cleanup

Changed implementation/order paths in the implementation commit were limited
to the activated order's allowlist: the production Nginx route, qualification
Compose override and runner, restore verifier, the named migration/fixture
tests, the focused `0024` contract test, the named deployment/security/
verification documents, `oap/active`, and the activated order itself.

## Safety boundaries

- No real OpenAI or OpenRouter transport was used.
- The exposed inherited provider credential was not enumerated, validated,
  printed, or reused; relevant commands explicitly unset provider variables.
- No production, staging, shared, or remotely managed database was touched.
- The PostgreSQL databases used for migration/integration evidence were
  explicitly named disposable targets and were dropped afterward.
- No real email was sent.
- No merge, release, deployment, auto-merge, or production-certification
  action was taken.

## Final-head checks

After this report-only commit is pushed, the required PR checks must be
independently verified successful at its final remote head before the exact
`OK` response is written. The required set is: Unit, lint, and migration head;
PostgreSQL integration tests; OpenAI-compatible E2E tests; Playwright browser
smoke; Docker Compose smoke; Documentation hygiene; Analyze Python; Analyze
JavaScript/TypeScript (the two CodeQL language checks). No check failure or
pending state is accepted as completion evidence.
