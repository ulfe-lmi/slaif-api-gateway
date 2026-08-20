# OAP 017-f execution report

Implementation head SHA: 0ce4061dd3eb7490ea58afe94d53e2f1ca7fec74
Report publication commit: SELF

## Scope

This round amended existing PR #242 on
`oap/017-external-tool-security-accounting-e2e`. It changed only the existing
PostgreSQL integration test helper/tests plus the activated `oap/active=017-f`
and order. No production code, documentation, migration, new PR, merge, or
auto-merge action was performed.

## Required post-reconciliation evidence

- `test_gateway_created_hold_finalize_actual_reconciles_once` now creates a
  fresh successful mocked provider client after `finalize-actual`. The fitting
  ordinary request and hosted web-search request both return HTTP 429. The
  provider controller records zero calls; two follow-up Redis releases are
  observed. The single prior reservation/ledger remains the only linked
  ledger, fence is `none`, all reserved counters are zero, used cost/tokens
  remain above limits, and no duplicate hold/reconciliation audit is added.
- `test_gateway_created_hold_release_no_charge_reconciles_once` now creates a
  fresh successful mocked provider client after `release-no-charge`. The
  fitting hosted request returns HTTP 200 and invokes the provider exactly once;
  one follow-up Redis release is observed. PostgreSQL contains the one prior
  reconciled ledger plus exactly one new successful ledger, with fence and
  reserved counters cleared. The prior hold-created and reconciliation audit
  actions each remain singular; no duplicate hold/reconciliation mutation is
  created.
- Existing pre-reconciliation ordinary/hosted blocking assertions remain in
  both tests. Provider, query, error, and response canaries were asserted
  absent from responses and durable state.

## Verification

- PostgreSQL command: `TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/slaif_oap_017f_test_1787266541 pytest tests/integration/test_responses_external_tool_postgres.py -q -ra`; 16 collected and passed, zero skips.
- The disposable PostgreSQL database was created with
  `sudo -n -u postgres createdb -O ubuntu` and dropped with
  `sudo -n -u postgres dropdb --if-exists`; drop status was 0.
- Scoped Ruff, compileall, and `git diff --check` passed for the changed test
  file. The changed-path check contained only the authorized integration test,
  `oap/active`, and the activated order.
- No local E2E or broad suite was run; no E2E file changed. GitHub provided the
  routine broad checks.

## Safety and privacy

No real provider calls, production systems, real email, or secrets were used.
All provider/query/error canaries were checked absent from HTTP responses,
ledger representations, and audit-related assertions. PostgreSQL remained the
authoritative accounting store; Redis was observed only for release behavior.

## GitHub state

All ten fresh implementation-head checks passed: Unit/lint/migration,
PostgreSQL integration, OpenAI-compatible E2E, Playwright browser smoke, Docker
Compose smoke, documentation hygiene, and four CodeQL checks. PR #242 remains
open on the existing branch with base `main`, auto-merge disabled, and no merge
performed.
