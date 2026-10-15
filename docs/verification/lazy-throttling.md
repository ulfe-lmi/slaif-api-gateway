# Lazy (waiting) Throttling Verification

> **Status:** Current objective 185-a verification record
> **Boundary:** Focused real-boundary evidence plus final-head GitHub CI; no broad local matrix is claimed

## Scope verified in this objective

- Per-key lazy throttling policy: `reject` (default) or `wait` with positive
  finite `max_wait_seconds` / `max_waiting_requests`, operator ceilings
  (defaults 120s / 16 per key), deployment-wide waiting cap (default 256),
  and Redis waiting-lease TTL (default 300s).
- Enabled only at the existing Chat Completions and Responses Redis
  rate-limit seams (streaming and non-streaming, plus the existing Responses
  compaction path). All other endpoints and policy surfaces are unchanged.
- Waiting holds no quota reservation, ledger row, active concurrency slot, or
  PostgreSQL connection; admission uses the existing atomic PostgreSQL
  reservation/finalization exactly once.
- Revalidation after a real wait: key auth, owner active state, endpoint and
  request policy, lazy-policy equality, and route re-resolution.
- Disconnection/cancellation cleanup at every await boundary; crashed-waiter
  lease expiry.

## Newly executed evidence (objective 185-a)

### Integration: real owned PostgreSQL + real owned Redis

`tests/integration/test_lazy_throttling_postgres_redis.py` — 14 tests, each
running against a fresh labeled loopback-bound tmpfs PostgreSQL 16 container
and a fresh no-persistence Redis 7 container (exact-ID verified cleanup):

1. `test_two_instances_waiting_caps_and_admit_once` — two separate service
   instances sharing one real Redis: per-key waiting cap, cross-instance
   visibility, admit-once after the slot frees, and no request/token state
   increments while waiting.
2. `test_global_waiting_cap_across_keys` — the deployment-wide waiting cap
   under contention across distinct keys.
3. `test_http_chat_waits_for_capacity_then_admits_once` — actual HTTP Chat
   wait-then-admit with real PG snapshots: zero reservation/ledger mutation
   while waiting, zero app pool connections checked out during the settled
   wait, and one correctly attributed finalization (per-request ledger rows)
   after admission.
4. `test_http_chat_default_mode_denies_immediately` — default `reject` keys
   get an immediate 429 with no waiting lease.
5. `test_http_chat_wait_mode_deadline_429` — the configured maximum wait
   expires with 429 `lazy_throttling_deadline_exceeded` and lease release.
6. `test_http_chat_waiting_capacity_full_429` — per-key cap reached returns
   429 `lazy_throttling_waiting_capacity_full` before any lease.
7. `test_deadline_cancel_and_crash_expiry_release_leases` — deadline,
   external cancel, and crashed-waiter TTL expiry all release waiting leases.
8. `test_http_chat_streaming_waits_for_capacity_then_admits` — streaming
   variant: SSE starts only after admission; stream heartbeat/release and
   accounting preserved.
9. `test_http_chat_real_socket_disconnect_before_admission` — actual TCP
   client disconnect before admission: cancellation, no provider call, no
   reservation/ledger, waiting lease released.
10. `test_http_chat_hard_quota_refuses_immediately_without_waiting` — an
    exhausted hard quota refuses immediately (no queue, no waiting lease, no
    new financial state) while a holder is admitted.
11. `test_http_chat_revoked_while_waiting_refuses_403` — key revoked while
    waiting: 403 `gateway_key_revoked` at revalidation; holder finalizes
    normally; no provider call or accounting for the refused waiter.
12. `test_http_chat_owner_inactive_while_waiting_refuses_403` — owner
    deactivated while waiting: 403 `owner_not_active` at revalidation with
    the same no-provider/no-accounting guarantees.
13. `test_http_responses_waits_for_capacity_then_admits` — actual HTTP
    Responses wait-then-admit with the same zero-mutation-while-waiting and
    one-finalization-per-request proof.
14. `test_admin_lazy_throttling_policy_durable_and_audited` — create/update
    durability in key metadata, strict projection, audit old/new values with
    no plaintext key, ordinary rate-limit updates preserving the policy, and
    an injected audit-write failure proving the metadata change and audit row
    roll back in the same transaction.

### Unit: helper and route wiring (mock Redis, no network)

- `tests/unit/test_lazy_throttling.py` — 17 tests: admit-once, denial-then
  admit, token-never-fit impossibility (strict inequality; equality can fit),
  waiting-capacity full fast-fail, deadline exhaustion with lease release,
  lease TTL covering max wait plus margin, stalled revalidate/check bounds,
  built-in `TimeoutError` not misread as a deadline, Redis-unavailable
  propagation, disconnect during/after wait, and the four task-cancel await
  boundaries (lease acquisition, admission call, post-admission probe, final
  lease release) with idempotent cleanup.
- `tests/unit/test_lazy_throttling_routes.py` — 5 tests: Chat and Responses
  route wiring (wait admission invoked, deadline/cap error mapping, reject
  default), using fake services at the documented unit boundary only.
- Admin/service/template unit regressions in `tests/unit/`
  (`test_admin_key_create_routes.py`, `test_admin_key_create_templates.py`,
  `test_admin_key_actions_routes.py`, `test_admin_key_actions_templates.py`,
  `test_admin_keys_dashboard_service.py`, `test_admin_keys_templates_safety.py`,
  `test_key_service_create.py`, `test_key_service_policy_update.py`,
  `test_key_service_safety.py`, `test_key_policy_validation.py`,
  `test_config.py`, `test_v1_chat_completions_rate_limits.py`,
  `test_v1_chat_completions_streaming_rate_limits.py`,
  `test_v1_responses_quota.py`, `test_auth_service.py`,
  `test_rate_limit_*.py`): form parsing/validation against ceilings, strict
  stored-policy projection, same-transaction audit, CSRF/unauthorized
  behavior, and unchanged 429/503 OpenAI error mappings.

### Browser: real Chromium, owned PostgreSQL, real app

`tests/browser/test_admin_lazy_throttling.py` — 3 tests against a fresh owned
PostgreSQL container and a real uvicorn app with explicit synthetic HMAC /
one-time-encryption / session secrets:

1. `test_admin_lazy_throttling_wait_create_update_and_reject` — JS-active
   create with NON-DEFAULT wait bounds (group hidden for reject, revealed for
   wait), detail summary and prefilled form, authenticated detail update,
   return to reject, and the audit rows for the logged-in web saves carrying
   the actual admin actor ID.
2. `test_admin_lazy_throttling_no_js_create_and_escaped_redisplay` —
   no-JS: server-rendered wait inputs usable, NON-DEFAULT wait saved, and an
   invalid-bounds attempt with a malicious reason redisplayed escaped with
   the stored policy unchanged.
3. `test_admin_lazy_throttling_negatives_leave_policy_unchanged` —
   unauthorized (303 to login), bad CSRF (400), missing reason (400
   redisplay), and invalid bounds (400 redisplay) all leave the stored policy
   unchanged.

No plaintext key, cookie, session, or CSRF value is logged or screenshotted
by any of these tests.

## Inherited evidence (unchanged primitives, cited by exact test name)

The 14 new integration cases do not each re-exercise every inherited
primitive; the following unchanged tests supply that proof:

- Fixed-window request/token counting and atomic limiter semantics:
  `tests/unit/test_rate_limit_service.py::test_allows_requests_under_limit_with_one_atomic_eval`,
  `::test_rejects_over_request_limit`, `::test_rejects_over_token_limit`,
  `::test_rejects_and_releases_concurrency_limit`.
- Token-never-fit impossibility (new, objective 185-a):
  `tests/unit/test_lazy_throttling.py::test_token_impossibility_refuses_before_any_lease`
  and `::test_token_impossibility_equality_can_fit`.
- Missing pricing/FX never converted to a wait:
  `tests/unit/test_v1_chat_completions_pricing.py::test_missing_pricing_rule_returns_openai_error_before_501`,
  `::test_missing_fx_rate_returns_openai_error_before_501`.
- Active/held external-tool fence stays immediate:
  `tests/unit/test_external_tool_fence.py::test_acquire_reserves_exact_full_remaining_balance`,
  `::test_acquire_blocks_when_ordinary_pending_reservation_exists`, and
  `tests/unit/test_v1_responses_quota.py::test_hosted_pricing_and_max_tool_calls_fail_before_redis_fence_provider`.
- Redis outage fail-open/fail-closed unchanged:
  `tests/unit/test_rate_limit_service.py::test_redis_unavailable_fails_closed_or_open`,
  `tests/unit/test_v1_chat_completions_rate_limits.py::test_redis_fail_closed_unavailable_returns_before_expensive_work`,
  `::test_redis_fail_open_allows_request`.
- OpenAI-shaped 429/503 error mapping:
  `tests/unit/test_rate_limit_api_errors.py::test_rate_limit_exceeded_errors_map_to_openai_429`,
  `::test_redis_unavailable_maps_to_server_error`.
- Revoked/suspended key refusal (pre-wait primitive):
  `tests/unit/test_auth_service.py::test_revoked_key_raises_gateway_key_revoked_error`,
  `::test_suspended_key_raises_gateway_key_suspended_error`; the while-waiting
  revalidation variants are the new integration tests 11 and 12 above.

## Real versus mocked

- Real: owned PostgreSQL (migrations, key/policy/accounting rows, audit),
  owned Redis (ZSET leases, atomic limiter), HTTP (uvicorn + real sockets,
  including a real client disconnect), Chromium (admin forms, JS and no-JS).
- Mocked: provider upstreams (holding/echo adapters and canned SSE), admin
  session/HMAC/one-time-encryption material (explicit synthetic values), and
  unit-level fakes confined to the documented unit boundary (fake Redis
  client objects for helper controls; real Redis is used for all Lua and
  integration behavior).
- Not executed: broad local matrix (final-head GitHub CI is authoritative for
  the full suite), real provider/model calls, and real email — none are
  required by this objective.
