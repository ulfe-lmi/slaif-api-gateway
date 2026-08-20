# OAP Coding-Agent Report — 014-d

## Work order

- Identifier: 014-d
- Work-order file: `oap/orders/014-d-refresh-locked-state-and-close-review-gap.md`
- Numeric objective: 014
- PR mode: AMENDED_EXISTING_PR

## Status

COMPLETE

## Executive summary

Amended the sole objective-014 PR #239 to make reservation-first resolution
revalidation fresh under SQLAlchemy's identity map and to close the remaining
review/report-truth gap.

- `GatewayKeysRepository.get_gateway_key_for_update()` now uses
  `execution_options(populate_existing=True)` on its `FOR UPDATE` select.
- The PostgreSQL resolve-wait test now changes the key from `active` to
  `held` in an independent session while resolve waits on the reservation;
  resolve freshly observes `held`, returns the required no-op, and does not
  clear or audit resolution.
- Added a real independent-session `QuotaService.release_reservation` versus
  `ExternalToolFenceService.resolve` race with a bounded timeout.
- Replaced the remaining `lambda: object()` with `object`.
- No schema, migration, product, quota-service, provider, forwarding, or
  documentation files were changed.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 239
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/239
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/014-external-tool-exclusive-fence-reservation`
- Starting remote SHA: `b9402546a76017e226e29fbc9638d8bd99d029f2`
- Implementation head SHA: `17408dc7a5df9de9f7eb8bb0ac16cff0d3d368d0`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  `17408dc7a5df9de9f7eb8bb0ac16cff0d3d368d0`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO
- Auto-merge: disabled/null
- PR merge state before report publication: CLEAN

## Acceptance-criteria evidence

### Fresh locked key state

The existing administrative lookup now builds a `SELECT ... FOR UPDATE`
statement with `execution_options(populate_existing=True)`. This preserves
the method signature and row-lock behavior while refreshing an object already
present in the SQLAlchemy session identity map.

The regression test holds the reservation lock, starts resolve after its
unlocked key read, commits `active -> held` through an independent key
transaction, releases the reservation lock, and proves resolve returns
`fence_state="held", resolved=False`. The final row remains held with the
same reservation pointer; no resolution audit is written. This test is
designed to fail against the stale locked lookup.

### Actual release/resolve lifecycle race

The independent-session race ran both real lifecycle services with a
five-second bounded timeout. The release path completed with reservation
status `released`; resolve returned the expected invariant outcome
(`external_tool_fence_reservation_not_terminal` or
`external_tool_fence_ledger_count`, depending on lock winner).

Final evidence:

- one reservation only;
- reservation status `released`;
- cost/token/request reserved counters all exactly zero;
- fence remained `active`;
- no ledger was invented;
- audit actions contained exactly one
  `external_tool_fence_acquired` and no resolution audit;
- no provider or other side effect occurred;
- no PostgreSQL deadlock or timeout occurred.

### Review and report truth

The immutable 014-c report incorrectly stated that the lambda construct had
been corrected. 014-d corrects that record without editing 014-c.

The single review-thread query after this implementation returned:

- unused global: resolved, outdated;
- unused import: resolved, current;
- unnecessary lambda: unresolved, outdated;
- no-effect statement: resolved, outdated.

No GitHub resolution state was fabricated.

## Local verification

- `/tmp/slaif-api-gateway-014c-venv/bin/python -m pytest tests/unit/test_external_tool_fence.py -q`: PASSED — 81 passed.
- `DATABASE_URL=<same explicit disposable URL> TEST_DATABASE_URL=<same explicit disposable URL> /tmp/slaif-api-gateway-014c-venv/bin/alembic upgrade head`: PASSED — migrations through 0015.
- `DATABASE_URL=<same explicit disposable URL> TEST_DATABASE_URL=<same explicit disposable URL> /tmp/slaif-api-gateway-014c-venv/bin/python -m pytest tests/integration/test_external_tool_fence_postgres.py tests/integration/test_external_tool_fence_concurrency_postgres.py -q -ra`: PASSED — 20 passed, no skips; one Alembic deprecation warning.
- `/tmp/slaif-api-gateway-014c-venv/bin/ruff check app/slaif_gateway/db/repositories/keys.py app/slaif_gateway/services/external_tool_fence.py tests/unit/test_external_tool_fence.py tests/integration/test_external_tool_fence_postgres.py tests/integration/test_external_tool_fence_concurrency_postgres.py`: PASSED.
- `/tmp/slaif-api-gateway-014c-venv/bin/python -m compileall -q app/slaif_gateway tests/unit/test_external_tool_fence.py tests/integration/test_external_tool_fence_postgres.py tests/integration/test_external_tool_fence_concurrency_postgres.py`: PASSED.
- `git diff --check`: PASSED.
- Full local unit, integration, E2E, browser, Docker, HPC, manual-Codex, and
  provider suites: NOT RUN — explicitly out of scope.

## PostgreSQL setup and cleanup

- Used one explicit disposable database:
  `slaif_gateway_test_oap014d_20260820`.
- It was created owned by local user `ubuntu`.
- `TEST_DATABASE_URL` targeted only that database for pytest; Alembic also
  required `DATABASE_URL`, which was pointed to the same disposable URL only.
- The database was dropped with `dropdb --if-exists` through an EXIT trap;
  no disposable database remains.
- No production database, provider credential, email service, Redis authority,
  or upstream call was used.

## GitHub CI / required checks

All ten checks passed for implementation head
`17408dc7a5df9de9f7eb8bb0ac16cff0d3d368d0`:

- Analyze (javascript-typescript): SUCCESS
- Analyze (python): SUCCESS
- Analyze Python: SUCCESS
- CodeQL: SUCCESS
- Docker Compose smoke: SUCCESS
- Documentation hygiene: SUCCESS
- OpenAI-compatible E2E tests: SUCCESS
- Playwright browser smoke: SUCCESS
- PostgreSQL integration tests: SUCCESS
- Unit, lint, and migration head: SUCCESS

The report-only commit may trigger fresh checks; the strategic model must verify
the SELF commit independently without rewriting this report.

## Documentation

Documentation intentionally deferred: the order allowed only the repository,
service, test, selector, and order paths; existing accounting/security
documentation already describes the reservation-first lifecycle contract.
Follow-up documentation changes, if desired, require a separately authorized
scope.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Provider calls: none.
- Real email: none.
- Prompts, responses, media, credentials, and prohibited content: none stored,
  logged, or committed.
- Required focused tests skipped: no.
- Scope deviation: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled: NO.
- Activated order and `oap/active` edited by coding agent: NO; committed
  byte-for-byte as supplied.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- One historical GitHub lambda thread remains unresolved but is outdated;
  the underlying construct is corrected in this implementation.
- Provider-hosted execution and later external-tool hold/reconciliation
  transitions remain outside objective 014.

## Recommended strategic follow-up

Independently verify the report-only SELF commit topology and current checks,
then decide whether PR #239 is ready for strategic merge. The coding agent does
not merge.
