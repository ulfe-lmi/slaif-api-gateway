# OAP 014-a — Exclusive external-tool quota fence reservation: immutable report

Implementation head SHA: 9ca9d62e8c3765cf2bf1610decc5cb511303fd04
Report publication commit: SELF
Objective order: oap/orders/014-a-external-tool-exclusive-fence-reservation.md
(oap/active = 014-a; both committed byte-exact, sha256 verified pre- and
post-commit)
PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/239
Base: main @ 72ac24d9820fef34bcf23021345c12ec8a57db34 (merge of PR #238)

## Scope implemented (014 = fence/reservation foundation only)

- Alembic migration 0015_external_tool_exclusive_fence (the single new
  head): five fence columns (state, reservation_id, request_id,
  acquired_at, expires_at) on gateway_keys with allowed-values,
  none-shape, and bound-shape CHECK constraints plus a
  (state, expires_at) index; quota_mode plus external_tool_capabilities
  / external_tool_destination_ids on quota_reservations with
  allowed-values, strict-mode-empty-facts, and fenced-mode-nonempty
  capabilities CHECK constraints; RESTRICT foreign key from
  gateway_keys.external_tool_fence_reservation_id to
  quota_reservations.id; backfill of existing rows to
  quota_mode='strict_bounded' with empty external facts and
  fence_state='none'.
- services/external_tool_fence.py (flush-only; callers own commit/
  rollback): acquire() locks the gateway_keys row (FOR UPDATE), enforces
  bound-state invariants (same request id + matching facts is
  idempotent; changed facts is conflict; different request id on a bound
  key is active-fence rejection; reused request id across existing
  reservations is conflict), checks remaining balance, then in one
  reservation row reserves the exact remaining cost/token balance plus
  one request, increments counters once, sets the fence active, and
  writes audit. resolve() clears only on terminal reservation + exactly
  one matching ledger + reconciled counters; held state is a no-op that
  keeps blocking. 014 never writes held.
- Active/held fence blocks bearer authentication with OpenAI-shaped 409
  (rate_limit_error / external_tool_fence_active), blocks ordinary
  quota admission (QuotaService guard), and blocks later acquires.
- Ordinary stale-reservation reconciliation can never auto-release a
  fenced reservation: the batch path skips candidates requiring
  external-tool review; the single-reservation path raises an invariant
  error for quota_mode='external_tool_fenced'. Expiry is an inspection
  threshold, never permission to release.
- Key lifecycle while fenced: policy/metadata mutation, reset, and
  rotation fail with GatewayKeyExternalToolFenceActiveError without
  mutation; emergency suspend/revoke does not settle accounting state.
- CLI: read-only slaif-gateway quota list-external-tool-fences
  --limit N --json (safe projection only: key id, fence state, request
  id, timestamps; no content, no secrets).
- Documentation updates (exact list in "Docs impact" below).

## Explicitly NOT implemented (015/016/017 remain)

No external/provider-hosted tool forwarding; no unknown-cost hold; no
provider call of any kind anywhere in this PR; no real email. The exact
overrun and one-winner concurrency promise remains conditional on later
provider activation. PostgreSQL key-row lock is the concurrency
authority; Redis absence does not affect correctness (no Redis read or
write exists in the fence path).

## Schema/backfill evidence

- Unit: tests/unit/test_alembic_external_tool_fence.py — 6/6 pass:
  migration file targets only fence foundation; exactly one head
  revision; upgrade adds only the five key fence columns (plus
  reservation-mode columns); downgrade drops only the new objects;
  GatewayKey and QuotaReservation models carry the exact fence
  contract (columns, checks, RESTRICT FK, relationship via string
  primaryjoin with remote()).
- Unit: all six prior alembic head-bump suites pass against the new
  single head (test_alembic_accounting, test_alembic_email_jobs,
  test_alembic_key_prefix_default, test_alembic_provider_pricing,
  test_alembic_external_tool_fence, test_schema_status).
- Real PostgreSQL (disposable slaif_oap014_test at 0015 head):
  test_backfilled_rows_get_fence_and_quota_mode_defaults — pre-existing
  row shapes backfill to fence_state='none', all four fence fact
  columns NULL, quota_mode='strict_bounded', empty external facts.
  test_fence_column_constraint_violations — bad fence state, broken
  none/bound shapes, and fenced-mode empty capabilities all raise
  IntegrityError; the bound key cannot be deleted while its bound
  reservation exists (RESTRICT FK).

## Full-balance arithmetic (exact remaining balance)

Limits cost 25 / tokens 100000 / requests 1000; used 1.25 / 100 / 2;
pre-existing reserved 0.50 / 50 / 1. Acquire reserves:
  cost    = 25 - 1.25 - 0.50 = 23.25
  tokens  = 100000 - 100 - 50 = 99850
  requests = 1 (the single allowed fence request)
Counters after acquisition:
  cost_reserved    = 0.50 + 23.25 = 23.75
  tokens_reserved  = 50 + 99850 = 99900
  requests_reserved = 1 + 1 = 2
  used counters unchanged (1.25 / 100 / 2)
Verified by test_acquire_reserves_exact_remaining_and_is_idempotent
(real PostgreSQL) and acquire_reserves_exact_full_remaining_balance
(unit). Exhaustion: with no positive remaining balance, acquire raises
ExternalToolFenceExhaustedError (acquire_rejects_when_no_positive
_remaining_balance).

## Race worker counts (independent PostgreSQL sessions/engines)

- 2-worker distinct-request-id race: exactly 1 winner (fence + one
  external_tool_fenced reservation + full-balance counters), 1 rejection
  (external_tool_fence_active).
- 16-worker distinct-request-id race: exactly 1 winner, 15 rejections,
  exactly 1 reservation in the database.
- 8-worker same-request-id concurrent retries: 1 non-idempotent
  acquisition + 7 idempotent results, exactly 1 reservation, single
  counter increment.
- 8 concurrent ordinary chat-completion reserve_for_chat_completion
  calls after a committed fence: all 8 rejected with the OpenAI-shaped
  external_tool_fence_active error; counters, reservation, and fence
  unchanged. Ordinary racing requests cannot bypass the committed
  fence.

## Idempotency / rollback / restart / expiry / resolution / mutation /
Redis / privacy evidence

- Idempotency: exact same request id + route facts replays return the
  existing reservation with idempotent=True and no counter re-
  increment; changed facts under the same request id raises
  ExternalToolFenceConflictError without mutating state.
- Rollback: every rejection path in the real-PostgreSQL file is
  exercised with an explicit session rollback followed by assertions
  that the key, fence, reservation, and counters are unchanged
  (no partial state survives a failed acquire/resolve).
- Restart: test_fence_survives_restart_and_resolves_from_finalized_
  evidence — a brand-new engine/session sees the committed fence and
  enforces it; resolution with the exact terminal reservation +
  matching finalized ledger evidence clears the fence and audits;
  mismatched/negative evidence never clears the fence
  (test_resolve_negative_evidence_never_clears_fence), including
  negative reserved-counter rejection without mutation.
- Expiry: held/active fenced reservations forced past expiry are never
  auto-released by ordinary stale reconciliation; the reservation stays
  pending, counters and fence are untouched
  (test_held_fence_blocks_and_never_auto_releases; batch skip counted).
- Mutation while fenced: policy/metadata update, limits reset, and
  rotation all raise GatewayKeyExternalToolFenceActiveError with no row
  mutation (test_key_service_policy_update,
  test_key_management_service_limits,
  test_key_management_service_rotation fence cases).
- Redis: no Redis read/write exists in the fence path; all evidence
  above was produced with no Redis dependency and none configured.
- Privacy: no prompt/body/tool/credential content is stored or exposed;
  stored external facts are capability/destination identifiers only;
  audit and CLI list-external-tool-fences expose the safe projection;
  unit tests assert the safe projection only
  (list_unresolved_fences_exposes_only_safe_projection_fields) and the
  documentation drift suite enforces the no-content/no-secret rules.

## Actual PostgreSQL commands and cleanup

Disposable database slaif_oap014_test (user ubuntu, Unix socket
/var/run/postgresql), never touching DATABASE_URL:
  - created and migrated to head (0015) by the fixture runs
    (scripts: alembic upgrade via migrated_postgres_url fixture);
  - read-only inspection queries (psql) of quota_reservations/
    gateway_keys used to diagnose a cross-run state-poisoning bug in
    the backfill test (a pending reservation with no counter
    movement; fixed by making that test delete its own
    ledger/reservation/key in a finally block; re-ran green);
  - cleanup: DROP DATABASE slaif_oap014_test after verification
    (executed in the final step, below the signal).
The three SLAIF worktrees and .local-provider-catalog/ were not
touched at any point.

## Focused verification (local, this run)

Environment: unset DATABASE_URL, RUN_UPSTREAM_TESTS, OPENAI_API_KEY,
OPENAI_UPSTREAM_API_KEY, OPENROUTER_API_KEY; ENABLE_EMAIL_DELIVERY=
false; TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/
slaif_oap014_test?host=/var/run/postgresql.

- Unit batch (17 files incl. all six alembic head-bump suites, fence
  service, auth/error mapping, quota service, reconciliation service,
  key management fakes/limits/rotation/policy, CLI quota reconciliation,
  documentation contract drift): 162/162 passed, exit 0, ~11.8 s.
- Real-PostgreSQL batch (5 files, no skips): external tool fence 9/9,
  external tool fence concurrency 4/4, gateway key prefix migration
  (0005 on the shared disposable DB) pass, quota accounting
  invariants pass, reconciliation tasks pass; 18/18 total, exit 0,
  ~7.7 s. Fence file re-run after the backfill-test fix: 9/9 again.
- ruff check on all 47 touched paths: all checks pass (CI gates ruff
  check; ruff format applied to the new files only, leaving
  pre-existing HEAD formatting drift in unrelated lines untouched).
- python -m compileall -q app/slaif_gateway: clean.
- alembic heads: exactly one head, 0015_external_tool_exclusive_fence.

## GitHub checks (PR #239)

All 10 required checks on implementation head
9ca9d62e8c3765cf2bf1610decc5cb511303fd04 (PR #239) passed:

| Check | Result |
| --- | --- |
| Unit, lint, and migration head | pass (1m46s) |
| PostgreSQL integration tests | pass (2m17s) |
| OpenAI-compatible E2E tests | pass (1m24s) |
| Playwright browser smoke | pass (2m20s) |
| Docker Compose smoke | pass (1m1s) |
| Documentation hygiene | pass (6s) |
| CodeQL | pass |
| CodeQL: Analyze Python | pass (1m17s) |
| CodeQL: Analyze (python) | pass (1m43s) |
| CodeQL: Analyze (javascript-typescript) | pass (1m19s) |

## Broad suites NOT run locally (by work-order test economy)

Full local unit/integration/E2E/browser/Docker/HPC suites, real
upstream provider tests (RUN_UPSTREAM_TESTS=0), Mailpit/real email:
not run. GitHub CI owns the broad routine coverage for this PR.

## No provider / no forwarding evidence

No provider adapter code was touched; the PR diff contains no
httpx/provider call sites; the fence service is flush-only against the
gateway's own database. All integration evidence used only the
disposable PostgreSQL database. No OpenAI/OpenRouter key was set in any
verification environment.

## Docs impact (exact files)

- AGENTS.md (014 fence foundation status line)
- docs/database-schema.md (fence columns/checks/index, quota_mode +
  external facts, fence-state semantics, reconciliation rules,
  non-storage line, re-scoped migration sentence)
- docs/accounting.md (fence reservation accounting; expiry is not
  release; suspend/revoke does not settle)
- docs/security-model.md (key-row lock authority; Redis non-authority;
  no content/secrets stored)
- docs/configuration.md (no new client-facing configuration; fence is
  key/route policy)
- docs/compatibility-matrix.md (fence blocking surfaces)
- docs/provider-forwarding-contract.md (external forwarding remains
  not implemented; 015/016/017 own it)
- docs/responses-compatibility.md (fence boundary for Responses)
- docs/runbooks/stale-reservation-reconciliation.md (new
  External-Tool Fenced Reservations section with the read-only CLI
  inspection command)
- docs/product-scope.md (fence foundation implemented; remainder
  deferred to 015-017)

## No merge / no auto-merge

The coding agent did not merge this PR and did not enable auto-merge.
Merge authority for OAP-managed PRs belongs to the strategic reviewer
and the human maintainer. This report is the single immutable report
commit; its first parent is the implementation head above and it
changes only this file.
