# OAP Coding-Agent Report — 014-c

## Work order

- Identifier: 014-c
- Work-order file: `oap/orders/014-c-close-retry-lock-order-and-review-truth.md`
- Numeric objective: 014
- PR mode: AMENDED_EXISTING_PR

## Status

COMPLETE

## Executive summary

Closed the requested 014-b merge blockers on the existing PR #239:

- duplicate request capabilities now fail before database mutation and before
  the operator ceiling can be satisfied by deduplication;
- active retries require the exact active fence, a pending reservation owned by
  the same key, fenced mode, and all exact request/fence facts;
- held, terminal, missing, cross-key, and conflicting pointed reservations fail
  closed without retry mutation;
- active resolution now reads the key without a lock, locks the reservation
  first, locks the gateway key second, and revalidates all state after both
  locks;
- the two reported code-quality constructs were corrected;
- unrelated formatter churn in `db/models.py` and
  `db/repositories/quota.py` was removed relative to the 014-b
  implementation baseline while retaining all functional 014-b model,
  constraint, relationship, index, and repository changes.

No external forwarding or provider calls were enabled.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 239
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/239
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/014-external-tool-exclusive-fence-reservation`
- Starting remote SHA: `86400d4171654b4d2df891a8420dbbfc29b8dfcc`
- Implementation head SHA: `d663825ddecaeff258b5ad51b34108e22df4189d`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `d663825ddecaeff258b5ad51b34108e22df4189d`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO
- Auto-merge: disabled/null
- PR merge state before report publication: CLEAN

## Changes made

- `ExternalToolFenceService` rejects duplicate capabilities, enforces
  active/pending/same-key retry identity, performs unlocked retry reads, and
  uses reservation-before-key locking for resolution.
- Added unit and PostgreSQL negatives for duplicate capabilities, held and
  terminal retry state, and cross-key reservation pointers.
- Added deterministic unit call-order evidence and a real PostgreSQL independent
  session lock-wait proof.
- Corrected the unnecessary lambda and no-effect-looking awaited task.
- Restored pre-014-b formatting in the mature model/repository files while
  retaining their functional fence changes.
- Documented the retry and lifecycle lock-order contract in
  `docs/accounting.md` and `docs/security-model.md`.

## Acceptance-criteria evidence

### Duplicate and retry admission

- Duplicate request capabilities fail with
  `external_tool_fence_capability_duplicate` before key locking,
  reservation creation, counters, or audit.
- Valid canonical input retains sorted canonical behavior and the existing
  operator ceiling.
- Active retry requires state `active`, the pointed reservation, same-key
  ownership, status `pending`, fenced mode, and exact route/provider/
  capability/destination facts.
- Held state remains blocking, including same request ID.
- Terminal, missing, cross-key, wrong-mode, and conflicting pointed facts fail
  closed without creating or mutating a reservation.

### Lock order and concurrency

- Fresh acquisition retains key-first locking because no reservation exists.
- Active retry uses a non-locking reservation read after the key lock and does
  not call the reservation `FOR UPDATE` method.
- Resolution now follows:
  `key read -> reservation FOR UPDATE -> gateway key FOR UPDATE -> revalidation`.
- Unit evidence asserts `reservation, key` for active resolution.
- The real PostgreSQL test holds the reservation lock, proves resolve waits,
  proves an independent transaction can lock the key while resolve waits, then
  releases the reservation and proves bounded completion without clearing the
  pending fence.
- Existing dedicated PostgreSQL race coverage also proves ordinary pending
  reservation/fence admission races terminate and preserve one-reservation and
  counter invariants.

### Review truth and 014-b correction

The immutable 014-b report overclaimed duplicate request-capability rejection
and claimed no new findings remained. 014-c corrects both claims:

- duplicate capability rejection was absent in 014-b and is implemented here;
- the review query after this push found four historical threads:
  two resolved (one outdated and one current), one unresolved/current lambda
  finding, and one unresolved/outdated no-effect finding. The corresponding
  code constructs are corrected in this implementation; the thread states
  remain reported exactly as GitHub returned them.

### Formatting and scope

- Diff comparison from `f9168909bf14342d3a2f661bff92a112d5a9401f` to the new
  implementation head contains only functional hunks in
  `db/models.py` and `db/repositories/quota.py`.
- No migration was added or edited; Alembic remains at the single head
  `0015_external_tool_exclusive_fence`.

## Local verification

- `/tmp/slaif-api-gateway-014c-venv/bin/python -m pytest tests/unit/test_external_tool_fence.py -q`: PASSED — 81 passed.
- `DATABASE_URL=<same explicit disposable URL> TEST_DATABASE_URL=<same explicit disposable URL> /tmp/slaif-api-gateway-014c-venv/bin/alembic upgrade head`: PASSED — migrations through 0015.
- `DATABASE_URL=<same explicit disposable URL> TEST_DATABASE_URL=<same explicit disposable URL> /tmp/slaif-api-gateway-014c-venv/bin/python -m pytest tests/integration/test_external_tool_fence_postgres.py tests/integration/test_external_tool_fence_concurrency_postgres.py -q -ra`: PASSED — 19 passed, no skips; one Alembic deprecation warning.
- `/tmp/slaif-api-gateway-014c-venv/bin/ruff check app/slaif_gateway/db/models.py app/slaif_gateway/db/repositories/quota.py app/slaif_gateway/services/external_tool_fence.py tests/unit/test_external_tool_fence.py tests/integration/test_external_tool_fence_postgres.py tests/integration/test_external_tool_fence_concurrency_postgres.py`: PASSED.
- `/tmp/slaif-api-gateway-014c-venv/bin/python -m compileall -q app/slaif_gateway tests/unit/test_external_tool_fence.py tests/integration/test_external_tool_fence_postgres.py tests/integration/test_external_tool_fence_concurrency_postgres.py`: PASSED.
- `git diff --check`: PASSED.
- Full local unit, integration, E2E, browser, Docker, HPC, manual-Codex, and
  provider suites: NOT RUN — explicitly out of scope for this order.

## PostgreSQL setup and cleanup

- Used one explicit disposable database:
  `slaif_gateway_test_oap014c_20260820`.
- Created it owned by local user `ubuntu), used only through
  `TEST_DATABASE_URL` for pytest; Alembic additionally required
  `DATABASE_URL` and it was pointed to the same disposable URL only.
- Dropped the database with `dropdb --if-exists` via an EXIT trap after each
  final run; no disposable database remains.
- No production database or `DATABASE_URL` outside that disposable target was
  touched.

## GitHub CI / required checks

All ten checks passed for implementation head
`d663825ddecaeff258b5ad51b34108e22df4189d):

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
the SELF commit independently without rewriting this immutable report.

## Documentation

Documentation updated: `docs/accounting.md`, `docs/security-model.md`.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Provider calls: none.
- Real email: none.
- Prompts, responses, media, credentials, and prohibited content: none stored,
  logged, or committed.
- Redis used as quota authority: no.
- Required tests skipped/not run: no focused required tests were skipped; broad
  suites were intentionally not run by order.
- Scope deviation: no.
- Extra PR created for same numeric objective: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled: NO.
- Activated order and `oap/active` edited by coding agent: NO; both were
  committed byte-for-byte as supplied.
- Report-publication commit changes only this report file: yes.

## Known limitations / blockers

- The four historical GitHub review-thread states remain as reported above;
  one current thread is unresolved and one outdated thread is unresolved even
  though both corresponding code findings were corrected. No review state was
  fabricated or silently changed.
- External provider forwarding, provider-hosted tool execution, unknown-cost
  holds, and later reconciliation transitions remain out of scope for
  objective 014 and are still disabled.

## Recommended strategic follow-up

Independently verify the report-only SELF commit topology and the current
required checks, then decide whether PR #239 is accepted, needs another
continuation, or is ready for strategic merge. The coding agent does not merge.
