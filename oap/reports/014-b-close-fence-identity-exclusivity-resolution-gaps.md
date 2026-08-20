# OAP 014-b — Close fence identity/exclusivity/resolution gaps: immutable report

Implementation head SHA: 7f6b3bee551c3a70d9fe5606e3710d28f0fbea1d
Report publication commit: SELF
Objective order: oap/orders/014-b-close-fence-identity-exclusivity-resolution-gaps.md
(oap/active = 014-b; both committed byte-exact in the 014-b implementation
commit f32791bc3b5e0eaaede5ae3808778b03dddb350f, sha256 verified pre- and
post-commit; freshly recomputed below)
PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/239
Base: main @ 72ac24d9820fef34bcf23021345c12ec8a57db34 (merge of PR #238)

SHA256 (recomputed at report commit time, worktree == committed blob):
- oap/orders/014-b-close-fence-identity-exclusivity-resolution-gaps.md:
  2361a050aaf243c3fbb34cbfceec8b061de57f22efb3b2d272101eb208c65b64
- oap/active: bca680e19846cb4528a20b1588dd4e0936e0fa1884c3808833f1fa4b20fed341

## Scope implemented (014-b = fence identity/exclusivity/resolution repair on the 014-a foundation)

This continuation amended the same unreleased migration 0015 and the same
objective-014 PR #239; no new migration number, no second PR. It closed the
strategic-review gaps: changed provider/route facts can no longer be treated
as an exact retry; duck-typed admission decisions and malformed stored policy
are no longer accepted; an external fence and an already-reserved ordinary
request cannot coexist in either lock order; and a fence clears only on exact
terminal evidence with all reserved counters exactly zero.

### Slice 1 — exact route identity and PostgreSQL-enforced shapes

- Migration 0015 (unreleased; amended, not renumbered) adds to
  quota_reservations: external_tool_provider text null and
  external_tool_route_id uuid null references model_routes(id) on delete
  restrict. Fenced rows require both; strict_bounded rows keep both null.
- The two unnamed 014-a reservation checks were replaced by four named
  checks: quota_reservations_quota_mode_allowed_values,
  quota_reservations_external_tool_facts_array_shape,
  quota_reservations_strict_mode_empty_external_facts,
  quota_reservations_fenced_mode_bound_facts. PostgreSQL now enforces the
  JSON/array shape, the strict-empty rule, and the fenced-bound rule;
  service-layer validation remains responsible for canonical
  capability/destination values.
- gateway_keys.external_tool_fence_reservation_id is now a full unique
  index (ix_gateway_keys_external_tool_fence_reservation_id_unique;
  multiple NULLs allowed) in addition to RESTRICT, so one reservation can
  never be the durable pointer for two keys. Downgrade removes only
  objective-014 objects in dependency-safe order; existing rows still
  backfill to quota_mode='strict_bounded' with empty external facts and
  null route facts.
- QuotaReservation model, QuotaReservationsRepository.create_reservation
  (external_tool_provider / external_tool_route_id parameters), the
  authoritative schema doc, and the exact-head/migration tests were updated
  together; Alembic remains one head, 0015.

### Slice 2 — exact acquisition facts and fail-closed policy

- ExternalToolFenceService._validate_decision now requires the exact
  objective-012 ExternalToolAdmissionDecision type (isinstance on an
  object-typed parameter; the 014-a tautological isinstance(decision,
  object) duck check is gone) plus the full positive fenced contract:
  allowed is True, quota_mode == external_tool_fenced,
  type(effective_tool_call_cap) is int and > 0, the canonical allowed
  reason code, and all four exclusive obligations is True. Any violation
  raises a fixed invariant error before locking or mutation.
- Endpoint, requested model, provider, and route UUID are validated as
  bounded safe facts before locking/mutation.
- The stored key policy is parsed through parse_key_external_tool_policy
  with the canonical operator ceilings; missing, malformed, noncanonical,
  wrong-version, duplicate, over-ceiling, non-acknowledged
  (single_request_overrun_acknowledged), or non-fenced policy fails
  closed.
- Request capabilities/destination IDs are validated as canonical values
  without silently accepting malformed, duplicate, or over-ceiling facts.
- The fenced reservation persists the exact provider string and route
  UUID; the exact-retry comparison now covers key, request ID, endpoint,
  requested model, provider, route UUID, capabilities, destinations,
  fenced mode, and the linked fence facts. Changing provider alone or
  route UUID alone produces the fixed conflict and changes no counters,
  reservation, fence, or audit state.

### Slice 3 — real exclusivity and authoritative resolution

- An external fence and an already-admitted ordinary reservation cannot
  coexist regardless of which transaction takes the gateway-key row lock
  first (deterministic races below).
- Resolution now proves exact reservation/ledger ownership and fact
  agreement (key, request ID, endpoint, model, provider, route, mode) and
  requires every reserved counter on the key to be exactly zero before
  clearing. Clearing happens once (audit: external_tool_fence_acquired on
  acquire; terminal resolution audit on clear); re-resolution is a no-op.
  Mismatched or negative evidence, and any positive unreconciled reserved
  counters, never clear the fence. held state and expiry remain blocking;
  no auto-release.

### Slice 4 — deterministic concurrency evidence

- The four 014-a independent-engine race tests were threaded through the
  new route_id facts, and two new deterministic lock-order tests were
  added (full facts below).
- Both GitHub code-quality findings were closed: the unused
  _DEFAULT_FENCE_TTL constant was removed, and the unused remote
  import/relationship workaround was removed without weakening
  relationship correctness.

### 012 contract-isolation repair (CI repair continuation 7f6b3be)

At implementation head f32791b, PR #239 check "Unit, lint, and migration
head" failed 1/3095 unit tests:
tests/unit/test_documentation_contract_drift.py::
test_external_tool_contract_is_wired_only_to_policy_surfaces_not_runtime_or_migrations.
The 014-b implementation had imported
slaif_gateway.services.external_tool_policy_contract into
app/slaif_gateway/schemas/external_tool_fence.py (typed the dataclass
decision field with the 012 type). The objective-012 wiring contract
enforced by that test allows the policy-contract module to be imported
only by its whitelisted policy-surface consumers; the schemas module is
not on that whitelist. The repair (7f6b3be) removed that import and
reverted the inert dataclass annotation to Any with a docstring stating
the exact-type requirement; the exact objective-012 type is enforced
where acceptance actually happens — ExternalToolFenceService, which is an
objective-012 whitelisted consumer. No governance test was modified and no
precedence exception was invented: the 012 contract remains intact, the
order's acceptance criterion 2 (only the real positive 012 decision can
acquire) is satisfied by the service's exact-type check, and the repair
touched exactly one allowed path.

## Deterministic lock-order races (independent PostgreSQL sessions/engines)

tests/integration/test_external_tool_fence_concurrency_postgres.py, each
race using two independent engines (two real connections/sessions), the
locking side left uncommitted to hold the gateway-key row lock, a 0.2 s
assertion that the rival task had not completed while blocked, then the
lock-holder commit:

- Fence first (test_race_fence_lock_first_blocks_ordinary_reservation):
  the fence session acquires and holds the key-row lock uncommitted; the
  ordinary reserve_for_chat_completion task blocks on the same key; after
  the fence commit the ordinary reservation is rejected with
  QuotaFenceActiveError (OpenAI-shaped 409, error_code
  external_tool_fence_active). Post-state: fence active with pointer;
  reserved counters 25 / 100000 / 1; exactly one reservation.
- Ordinary first (test_race_ordinary_reservation_first_blocks_fence):
  the ordinary session locks the key, inserts a pending strict_bounded
  reservation (0.25 EUR / 50 tokens / 1 request, request id
  req-ordrace-*, with TTL), and increments reserved counters, all
  uncommitted; the fence acquire task blocks; after the ordinary commit
  the fence raises ExternalToolFenceOccupiedError with error_code
  external_tool_fence_pending_reservation (the pending-reservation check
  fires before the nonzero-counter check). Post-state: fence state
  none with null pointer; reserved counters exactly 0.25 / 50 / 1;
  exactly one reservation (the ordinary strict one); zero audit_log rows
  for entity_type='gateway_key' AND action='external_tool_fence_acquired'.
  Both tests dispose every engine in a finally block.

The 014-a independent-engine races were re-verified at this head with the
new route facts: 2-worker and 16-worker distinct-request-id races yield
exactly one winner (full-balance fence counters) and N-1
external_tool_fence_active rejections with exactly one reservation; 8
concurrent same-request-id retries yield 1 non-idempotent acquisition + 7
idempotent results with a single counter increment; 8 concurrent ordinary
reservations against a committed fence are all rejected.

## State-unchanged negative evidence

- Every rejection path (wrong object type; denied/non-fenced decision;
  missing positive call cap; noncanonical reason; any of the four
  obligations not True; missing/malformed/noncanonical/wrong-version/
  duplicate/over-ceiling/non-acknowledged/non-fenced stored policy;
  invalid endpoint/model/provider/route facts; malformed/duplicate/
  over-ceiling capabilities or destinations; conflict on changed retry
  facts including provider-only and route-only changes; occupied fence;
  exhausted balance) is exercised with an explicit session rollback
  followed by assertions that the key row, fence, reservations, counters,
  and audit are unchanged.
- Resolution: mismatched key/request/endpoint/model/provider/route/mode
  evidence, negative or absent ledger evidence, and any positive
  unreconciled reserved counters never clear the fence; only exact
  terminal evidence with all reserved counters exactly zero clears once,
  and re-resolution is an audited no-op.
- held state and expired fences remain blocked by ordinary reconciliation
  and by new acquires; no auto-release occurs.

## Focused verification (local, this run, at repair head 7f6b3be)

Environment: unset DATABASE_URL, TEST_DATABASE_URL (unit),
RUN_UPSTREAM_TESTS, OPENAI_API_KEY, OPENAI_UPSTREAM_API_KEY,
OPENROUTER_API_KEY; no Redis configured or used.

- Unit:
  .venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py
  tests/unit/test_external_tool_fence.py
  tests/unit/test_alembic_external_tool_fence.py
  -> 95 collected, 95 passed, 0 failed, 0 skipped. (The two dedicated fence
  unit files were 81/81 at the pre-repair head as well; the drift file is
  14 tests. The drift file is not one of the 16 modifiable paths; it was
  executed read-only because it was the concrete CI-failing symbol, and it
  was not modified.)
- PostgreSQL integration (disposable DB):
  TEST_DATABASE_URL='postgresql+asyncpg://ubuntu@/
  slaif_gateway_test_oap014b_20260820?host=/var/run/postgresql'
  .venv/bin/python -m pytest
  tests/integration/test_external_tool_fence_postgres.py
  tests/integration/test_external_tool_fence_concurrency_postgres.py
  -> 15 collected, 15 passed, 0 failed, 0 skipped.
- Scoped static checks: ruff check and ruff format --check pass on all
  six code/test files in scope; python -m compileall -q app/slaif_gateway
  clean; alembic heads reports exactly one head,
  0015_external_tool_exclusive_fence.

## Actual PostgreSQL commands and cleanup

Disposables only; DATABASE_URL was never read, pointed at, or modified:

- createdb slaif_gateway_test_oap014b_20260820 (first as postgres-owned,
  which failed with InsufficientPrivilegeError on the public schema for
  the ubuntu test user and was immediately dropped; recreated
  ubuntu-owned via peer auth).
- The integration fixtures ran alembic upgrade head (0015) inside that DB
  and the tests read/wrote only that DB.
- dropdb slaif_gateway_test_oap014b_20260820 after the run; absence
  verified via psql select count(*) from pg_database (0).
- psql was used only for the read-only ownership/absence queries above.
- The three SLAIF worktrees and .local-provider-catalog/ were not touched
  at any point this session.

## Broad suites NOT run locally (by work-order test economy)

Full local unit, integration, E2E, browser, Docker Compose, and
supercomputer-sharded (HPC) suites; real upstream provider tests
(RUN_UPSTREAM_TESTS never set); Mailpit/real email. GitHub CI owns the
broad routine coverage for this PR.

## Privacy / Redis / no-provider evidence

- No prompt text, request/response bodies, tool arguments or results, raw
  MCP values, URLs, credentials, or provider response content is stored or
  exposed; stored external facts are bounded capability/destination
  identifiers plus the provider string and route UUID only. The 014-b diff
  (implementation + repair commits) contains no secret-bearing content;
  audit and CLI projections remain safe.
- Redis: no Redis read or write exists in the fence path; no Redis
  dependency or configuration was present in any verification
  environment; correctness does not depend on it.
- Provider: no provider adapter, request handler, or dependency was
  changed; the diff contains no httpx/provider call sites; no
  OpenAI/OpenRouter key was set in any environment; no provider call of
  any kind occurred; no real email was sent.

## GitHub checks (PR #239)

- Implementation head f32791bc3b5e0eaaede5ae3808778b03dddb350f (run
  32311643983): 9 of 10 checks SUCCESS (Analyze (javascript-typescript),
  Analyze Python, Analyze (python), PostgreSQL integration tests,
  OpenAI-compatible E2E tests, Playwright browser smoke, Docker Compose
  smoke, Documentation hygiene, CodeQL). One FAILURE: "Unit, lint, and
  migration head" (job 96255659481, 1m43s) — 1 failed / 3094 passed / 11
  warnings in 71.59 s; the single failure was the objective-012
  contract-wiring drift test caused by the schemas-file import, repaired
  by this continuation.
- Repair head 7f6b3bee551c3a70d9fe5606e3710d28f0fbea1d (the
  implementation head above): all 10 required checks SUCCESS, including
  the previously failing "Unit, lint, and migration head" (Analyze
  (javascript-typescript), Analyze Python, Analyze (python),
  PostgreSQL integration tests, OpenAI-compatible E2E tests,
  Playwright browser smoke, Docker Compose smoke, Documentation
  hygiene, CodeQL).
- Report head (this commit, SELF): carries the identical code state as
  7f6b3be plus this report file; per acceptance criterion 7 its
  GitHub checks are watched after publication until all 10 are
  successful, with the final state recorded in the PR check record on
  the report head.

## GitHub code-quality bot-comment disposition

Both 014-a findings were closed in f32791b: the unused
_DEFAULT_FENCE_TTL constant was removed and the unused remote
import/relationship workaround was removed without weakening the
relationship's correctness. No new blocking bot findings remain open on
the repair head at publication time.

## Docs impact (exact files)

- docs/database-schema.md (unique pointer index line plus the named index
  ix_gateway_keys_external_tool_fence_reservation_id_unique;
  quota_reservations gains external_tool_provider text null and
  external_tool_route_id UUID null references model_routes(id) on delete
  restrict; the two 014-a checks are replaced by the four named checks
  above; three new rule bullets: strict rows carry null external facts,
  PostgreSQL enforces the named checks while the service layer owns
  canonical capability values, and the route FK is RESTRICT)
- docs/accounting.md (014-b extension of the objective-014 paragraph:
  provider/route persisted on the reservation; the exact-retry identity
  list; both lock orders; resolution requires exact evidence plus all
  reserved counters exactly zero)
- docs/security-model.md (route-identity binding; no coexistence in either
  lock order; zero-counter clear; audited)
- docs/provider-forwarding-contract.md (binding clause: the reservation
  carries the exact provider and route UUID, so later execution is
  unambiguous; forwarding itself remains not implemented)
- docs/product-scope.md (Current paragraph amended: identity binding,
  exclusivity in either lock order, zero-counter clear; still deny-only)

## Scope and allowed paths

This continuation modified only the 16 paths named by the order
(app/slaif_gateway/db/models.py, app/slaif_gateway/db/repositories/
quota.py, app/slaif_gateway/schemas/external_tool_fence.py,
app/slaif_gateway/services/external_tool_fence.py, docs/accounting.md,
docs/database-schema.md, docs/product-scope.md,
docs/provider-forwarding-contract.md, docs/security-model.md,
migrations/versions/0015_external_tool_exclusive_fence.py, oap/active,
oap/orders/014-b-close-fence-identity-exclusivity-resolution-gaps.md,
tests/integration/test_external_tool_fence_concurrency_postgres.py,
tests/integration/test_external_tool_fence_postgres.py,
tests/unit/test_alembic_external_tool_fence.py,
tests/unit/test_external_tool_fence.py). f32791b committed all 16
(including the byte-exact order and oap/active); the 7f6b3be repair
committed exactly one of them (the schemas file); this report commit
changes only this report file. Zero paths outside the list were touched.
The immutable 014-a order and report are unmodified; the objective-012
policy-contract implementation, provider adapters, request handlers,
dependencies, and CI are unmodified.

## No merge / no auto-merge

The coding agent did not merge this PR and did not enable auto-merge
(autoMergeRequest is null at every check). Merge authority for OAP-
managed PRs belongs to the strategic reviewer and the human maintainer.
This report is the single immutable report commit for 014-b; its first
parent is the implementation head above and it changes only this file.

## Honest status

This remains the fence/reservation foundation: objectives 015 and 016 own
unknown-cost holds and provider execution (and forwarding), and no RC2,
release, production, security, or compliance claim follows from this
objective.
