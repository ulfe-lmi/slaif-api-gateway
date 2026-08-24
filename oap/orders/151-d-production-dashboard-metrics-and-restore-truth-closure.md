# OAP Work Order — 151-d

PR mode: `AMEND_EXISTING_PR`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Current remote head: `e15fa8bbea8450fc3c39a49ae856c809f33466b1`
Title remains: `obj151: qualify production appliance boundary`

## Objective and reason

Close the independent-review defects that remain after the 151-c report. The
same PR must make the production dashboard landing route genuinely reachable,
inspect the authorized Prometheus payload rather than a static denial body,
and make the restore verifier's disposable-target and table-readability checks
strict enough to support its claims. Then rerun the complete production
qualification without redirect suppression or evidence substitution.

This is a continuation of numeric objective 151. Do not create another PR,
merge, enable auto-merge, call a real provider, or make a production-
certification claim.

## Verified starting state and rejection provenance

- Canonical remote `main` remains
  `ce0cf95685796477685a3aab6edacb39def6c27b`.
- PR #286 is OPEN and mergeable from
  `oap/151-production-appliance-closure`; no auto-merge is set.
- Remote PR head is the valid 151-c report-only commit
  `e15fa8bbea8450fc3c39a49ae856c809f33466b1`. Its sole parent is reported
  implementation head `bab4be5c99b5329870615f734744849923253214`, and it
  changes only
  `oap/reports/151-c-restore-and-interrupted-accounting-closure.md`.
- All required GitHub checks are successful on that report head. The report is
  still rejected as completion evidence because green checks do not repair the
  boundary defects below.
- The final 151-c run genuinely passed provider-double transport, accounting,
  process interruption/reconciliation, Redis failure/concurrency,
  persistence, backup/restore counts, key/quota lifecycle, subpage access,
  privacy canaries, and automatic cleanup. Preserve those repairs.
- Production NGINX has only `location /admin/`, while the FastAPI router's
  landing route and successful login redirect are exact `/admin`. NGINX
  canonicalizes `/admin` to `/admin/`; FastAPI canonicalizes `/admin/` back to
  `/admin`. On the qualification's remapped TLS port the first NGINX redirect
  drops the port and caused connection refusal; on normal port 443 the two
  canonicalizers can loop. The 151-c harness hid this by disabling redirects
  and accepting the login `303`, then going directly to `/admin/usage` and
  `/admin/audit`. That proves subpages, not the required login-to-dashboard
  production path.
- Production correctly denies an unallowlisted host request to the API
  diagnostic `/metrics` endpoint with `403`, and public NGINX does not proxy
  `/metrics`. The 151-c privacy phase accepted and scanned only the static 403
  denial body, yet its report claimed the metrics payload was scanned. The
  actual authorized Prometheus exposition was never read.
- `scripts/verify_restore.py` accepts any database name containing `test`,
  `dev`, or `local`; names such as `contest` therefore pass the destructive-
  target guard. It checks existence for all required tables but executes a
  read query only for `gateway_keys` and `usage_ledger`, so it does not prove
  every required table is queryable as claimed.
- CI correctly exposed stale migration-head fixtures and a quota fake after
  0024. The coding agent updated seven unit fixtures and one integration
  fixture outside 151-c's exact path list. The changes are mechanically
  appropriate and green, but this continuation must explicitly adopt, inspect,
  and report them rather than retroactively pretending the 151-c scope was
  obeyed.
- During 151-c diagnosis an inherited provider-key environment value was
  printed by an environment-enumeration command. Treat that credential as
  exposed and unusable. Never print, validate, call, or otherwise use any
  inherited provider credential. All test commands that could observe provider
  variables must explicitly unset them. Rotation/revocation is an external
  owner action and is not a product-completeness feature.

## Required implementation

### 1. Real production dashboard routing

- Repair `nginx/production.conf` so both the exact `/admin` landing route and
  `/admin/...` routes proxy to the API without NGINX/FastAPI slash
  canonicalization fighting. Keep the proxy narrowly scoped to the admin path;
  do not add a catch-all proxy or expose `/metrics`/`/readyz` publicly.
- Preserve HTTPS, secure cookie, CSRF, request-header, streaming, and public
  endpoint behavior. Do not weaken authentication or add a dashboard bypass.
- Remove the qualification client's no-redirect handler. A normal HTTPS client
  must GET the login form, POST valid credentials, follow the application's
  real redirect through NGINX to exact `/admin`, receive the actual dashboard
  landing page, retain a Secure session cookie, and then read usage and audit
  pages.
- Add a static contract test for exact `/admin` plus `/admin/` NGINX routing
  and a boundary assertion that the real composed login flow followed
  redirects. Merely accepting `303`, requesting subpages directly, or calling
  FastAPI without NGINX does not pass.

### 2. Authorized metrics and privacy truth

- Preserve the safe production default: the public NGINX path must not expose
  Prometheus metrics, and an unallowlisted request to the loopback diagnostic
  publish must remain denied.
- In the qualification-only Compose override, permit only container loopback
  (`127.0.0.1`) for metrics. Read `/metrics` from inside the API container so
  the request crosses the real production app endpoint as an authorized
  scraper without making metrics public.
- Require HTTP 200 and a real Prometheus exposition marker. Assert bounded
  accounting/request metric families exercised by the run are present. Scan
  the actual exposition body for every generated canary and secret alongside
  logs, dashboard bodies, provider state, and database metadata.
- A 403/404 denial body, a fabricated string, a unit-only renderer call, or a
  public metrics override is not authorized metrics evidence.

### 3. Restore-verifier safety and readability

- Tighten the database-name guard to an explicit documented disposable naming
  grammar. At minimum it must accept documented names such as `restore_test`
  and the qualification's `restore_local_<suffix>`, while rejecting substring
  accidents and production-shaped names such as `contest`, `production_test`,
  and `locality`.
- Continue to reject non-PostgreSQL schemes, missing names, and inherited
  unsafe targets without printing URLs or credentials.
- Prove every fixed required table exists in the intended schema and execute a
  read-only query against every one. Continue to emit only bounded counts for
  `gateway_keys` and `usage_ledger`; do not emit row content.
- Extend focused tests for accepted grammar, deceptive names, missing/wrong
  schema tables, query execution for all required tables, safe SQL shape, and
  no SQLite statement or swallowed database exception.

### 4. Migration and scope reconciliation

- Inspect and explicitly retain or correct the already-pushed migration-head
  fixture updates in:
  `tests/unit/test_alembic_accounting.py`,
  `tests/unit/test_alembic_email_jobs.py`,
  `tests/unit/test_alembic_external_tool_fence.py`,
  `tests/unit/test_alembic_key_prefix_default.py`,
  `tests/unit/test_alembic_provider_pricing.py`,
  `tests/unit/test_schema_status.py`,
  `tests/unit/test_quota_accounting_invariants.py`, and
  `tests/integration/test_gateway_key_prefix_migration_postgres.py`.
  They are now in scope; do not broaden into unrelated historical test rewrites.
- Add a focused 0024 migration contract test that proves the three columns are
  nullable, upgrade creates them once, downgrade removes them, and the
  revision chain remains singular. Also exercise upgrade to head, downgrade to
  0023, and upgrade back to head against a disposable PostgreSQL database.
- Preserve the application/accounting changes from 151-c unless a direct
  defect is demonstrated. Do not alter endpoint matrices, adapters, policy,
  pricing, or external-tool semantics.

### 5. Evidence, documentation, and immutable report

- Update the production qualification record to preserve 151-a/151-b/151-c
  history and state explicitly why the 151-c apparent pass was not accepted:
  redirect suppression hid `/admin`, metrics evidence was only a denial body,
  restore target/readability was weak, and some CI fixture edits exceeded the
  order's path list.
- Run one fresh final invocation without `--keep` after all implementation and
  test changes. Every existing phase must remain green, the dashboard phase
  must follow the real landing redirect, the privacy phase must scan the
  authorized metrics body, and exact cleanup must pass.
- Publish exactly one immutable
  `oap/reports/151-d-production-dashboard-metrics-and-restore-truth-closure.md`
  in a final report-only commit. Record exact implementation head, project ID,
  restore counts, dashboard redirect/landing evidence, public-denial plus
  authorized-metrics evidence, verifier negative cases, migration downgrade/
  re-upgrade, sanitized accounting rows, privacy, cleanup, changed paths, and
  final-head checks.
- The report publication commit must have the reported implementation head as
  its first parent, change only that report path, say `Report publication
  commit: SELF`, be pushed as PR #286's remote head, and precede exact `OK`.

## Exact allowed paths

```text
nginx/production.conf
scripts/production-qualification/run.py
scripts/production-qualification/qualification-compose.yml
scripts/verify_restore.py
tests/unit/test_production_compose_contract.py
tests/unit/test_verify_restore.py
tests/unit/test_alembic_quota_reservation_accounting_facts.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_external_tool_fence.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_schema_status.py
tests/unit/test_quota_accounting_invariants.py
tests/integration/test_gateway_key_prefix_migration_postgres.py
docs/backup-restore.md
docs/deployment-production.md
docs/deployment.md
docs/security-model.md
docs/verification/2026-08-24-production-appliance-qualification.md
oap/orders/151-d-production-dashboard-metrics-and-restore-truth-closure.md
oap/reports/151-d-production-dashboard-metrics-and-restore-truth-closure.md
oap/active
```

Use the narrowest subset. Existing 151-c changes outside this continuation
remain part of PR #286 but must not be edited unless listed above. Any newly
discovered product defect remains another objective-151 continuation.

## Anti-false-positive acceptance

- A normal redirect-following client traverses HTTPS NGINX login to a 200
  exact `/admin` landing page. Removing redirects, accepting the login 303 as
  success, direct subpage access, default-port assumptions, or a direct ASGI
  test does not pass.
- Public NGINX does not expose metrics; an unallowlisted diagnostic request is
  denied; an API-container loopback request returns the real Prometheus body.
  The body contains expected exercised metric families and no canary/secret.
- Restore verification rejects deceptive names before creating an engine and
  executes read-only SQL against all required tables in the intended schema.
  Existence-only checks and two-table readability do not pass.
- The 0024 migration has one head, nullable truthful legacy columns, a tested
  downgrade to 0023, and a tested re-upgrade to 0024 on disposable PostgreSQL.
- The final no-keep command exits zero and independent exact project/container/
  network/volume/runtime absence checks pass. Debug/kept runs, manual cleanup,
  stale logs, or evidence from a pre-fix commit do not pass.
- No command enumerates or prints provider credential values. No real provider
  transport occurs. Relevant local tests run with `OPENAI_API_KEY` and
  `OPENROUTER_API_KEY` explicitly unset.
- All required checks on the final report head are successful before strategic
  merge. The coding agent does not merge or enable auto-merge.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY python -m ruff check <all changed Python files and focused tests>
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused verifier, NGINX contract, migration, quota-fixture tests> -q
TEST_DATABASE_URL=<disposable objective-owned PostgreSQL URL> env -u OPENAI_API_KEY -u OPENROUTER_API_KEY python -m pytest <focused PostgreSQL reservation/reconciliation/migration tests> -q
DATABASE_URL=<disposable objective-owned PostgreSQL URL> env -u OPENAI_API_KEY -u OPENROUTER_API_KEY alembic upgrade head
DATABASE_URL=<same disposable URL> env -u OPENAI_API_KEY -u OPENROUTER_API_KEY alembic downgrade 0023_module_provider_foundation
DATABASE_URL=<same disposable URL> env -u OPENAI_API_KEY -u OPENROUTER_API_KEY alembic upgrade head
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY python scripts/verify_production_compose.py
sudo -n docker compose -f docker-compose.production.yml config --quiet
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY .venv/bin/python scripts/production-qualification/run.py
<independent exact project/container/network/volume/runtime absence checks>
```

Use only disposable local PostgreSQL/Redis/Compose state. Do not run broad
local suites merely for appearance; GitHub CI remains required at final head.

## Security, privacy, accounting, and production boundaries

- No real OpenAI/OpenRouter/native credential or request is authorized. No
  production, staging, shared, inherited, or remotely managed database,
  service, email destination, or deployment may be touched.
- Keep PostgreSQL authoritative. Preserve reservation/finalization,
  interrupted reconciliation, bounded overrun, Redis fail-closed and
  concurrency behavior, provider-key replacement, gateway-key lifecycle, and
  external-tool fence semantics already proven by 151-c.
- Preserve no-default-content-storage and safe audit/log/metric evidence. Do
  not log request bodies, prompts, completions, media, keys, passwords,
  cookies, provider bodies, raw errors, connection URLs, or secret values.
- This objective qualifies a disposable appliance path. It does not certify
  security, model accuracy, compliance, production readiness, invoice-grade
  billing, HA, support, or SLA.

## Non-goals

- No enterprise tenancy, SSO/SCIM, MFA, RBAC expansion, penetration test,
  certification, compliance work, retention automation, HA, release, or live
  deployment.
- No new endpoint, OpenAI field, provider, model, hosted tool, native module,
  plugin framework, generic module SDK, adapter generalization, or dashboard
  redesign.
- No real-provider or facial-scoring qualification; those remain separate
  post-MVP/evidence objectives.
- No credential rotation implementation. The exposed inherited credential
  requires external owner revocation/rotation and must never be reused here.

## Publication and response duties

- Commit and push bounded implementation changes to the existing PR branch.
- Keep PR #286 open; never merge or enable auto-merge.
- After all final-report-head checks are successful, publish the immutable
  report-only commit described above.
- Write exactly two bytes `OK` to the verified response FIFO only after the
  remote head/report topology and all requirements are true.
