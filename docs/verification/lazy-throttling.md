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
  reservation/finalization exactly once. The key's maximum wait is the
  admission budget for all pre-admission wait steps; once the wait loop ends
  (admission or deadline), final opaque-ID bookkeeping (lease and slot
  release) runs under its own separate per-ID 5-second bound (cleanup only,
  never extra eligibility), with the bounded Redis lease/slot TTLs as the
  crash/outage backstop.
- Revalidation after a real wait: key auth, owner active state, endpoint and
  request policy, lazy-policy equality, and route re-resolution.
- Disconnection/cancellation cleanup at every await boundary; crashed-waiter
  lease expiry.

## Newly executed evidence (objective 185-a)

### Integration: real owned PostgreSQL + real owned Redis

`tests/integration/test_lazy_throttling_postgres_redis.py` — 14 tests. The
module acquires ONE fresh labeled loopback-bound tmpfs PostgreSQL 16
container and ONE fresh no-persistence Redis 7 container (exact-ID verified
cleanup); all 14 cases share those instances and seed unique
keys/owners/models per case:

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
   variant: SSE starts only after admission. This new case is short and is
   admission/release/accounting evidence only; it does not wait for or
   observe heartbeat ticks (the unchanged heartbeat primitive is cited in
   the inherited section below).
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

- `tests/unit/test_lazy_throttling.py` — 17 tests using small
  lease/admission doubles (not a FakeRedis/Lua engine): admit-once, denial-then
  admit, token-never-fit impossibility (strict inequality; equality can fit),
  waiting-capacity full fast-fail, deadline exhaustion with lease release,
  lease TTL covering max wait plus margin, stalled revalidate/check bounds,
  built-in `TimeoutError` not misread as a deadline, Redis-unavailable
  propagation, disconnect during/after wait, and the four task-cancel await
  boundaries (lease acquisition, admission call, post-admission probe, final
  lease release) with idempotent cleanup.
- `tests/unit/test_lazy_throttling_routes.py` — 7 cases: dynamic
  disconnect-probe wiring at the Chat and Responses call sites; Chat
  deadline 429 (helper + lease exercised, no provider/reserve); Chat
  disconnect cancellation (499, no provider/reserve/finalize); reject
  default immediate 429 (wait loop never runs); and two contended-wait
  preflight negatives where `capture_pricing_and_fx` raises the existing
  missing-pricing-rule / missing-FX errors: exact 400 codes
  (`pricing_rule_not_found`, `fx_rate_not_found`), wait helper never
  reached, zero waiting lease, zero provider calls, zero financial
  reservations. All run at the documented unit boundary with fake services;
  the actual waiting-cap mapping is proven by the integration cap cases
  above, not by this unit file.
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

`tests/browser/test_admin_lazy_throttling.py` — 3 tests. The module
reuses the integration module's qualified fixture: ONE fresh owned labeled
loopback-bound tmpfs PostgreSQL container for the module (the 3 tests share
it with unique data per test), plus a real uvicorn app running the real
login/HMAC/AES session and key-creation algorithms over explicit synthetic
credentials and secret material (not mocked login/HMAC/encryption
implementations):

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

- Fixed-window request/token counting, atomic limiter semantics, and the
  actual new-window reset control (real Redis):
  `tests/integration/test_redis_rate_limit_service.py::test_redis_rate_limit_service_with_real_redis`,
  with unit-level atomic-evaluation primitives in
  `tests/unit/test_rate_limit_service.py::test_allows_requests_under_limit_with_one_atomic_eval`,
  `::test_rejects_over_request_limit`, `::test_rejects_over_token_limit`,
  `::test_rejects_and_releases_concurrency_limit`.
- Stream heartbeat/release primitive (unchanged; the new streaming case does
  not observe heartbeat ticks):
  `tests/unit/test_rate_limit_service.py::test_heartbeat_refreshes_existing_concurrency_slot`,
  `::test_expired_concurrency_slot_is_cleaned_after_ttl`.
- Token-never-fit impossibility (new, objective 185-a):
  `tests/unit/test_lazy_throttling.py::test_token_impossibility_refuses_before_any_lease`
  and `::test_token_impossibility_equality_can_fit`.
- Missing pricing/FX in the NEW contended-wait preflight (objective 185-a):
  `tests/unit/test_lazy_throttling_routes.py::test_chat_wait_mode_preflight_missing_pricing_fx_refuses_without_waiting`
  (both parameters): immediate 400 hard refusal before the wait loop, zero
  waiting lease, zero provider calls, zero financial reservations. The
  legacy normal-path pricing primitives (unchanged) are
  `tests/unit/test_v1_chat_completions_pricing.py::test_missing_pricing_rule_returns_openai_error_before_501`,
  `::test_missing_fx_rate_returns_openai_error_before_501`; they verify the
  ordinary default-pricing/conversion path, not the new wait preflight.
- Active/held external-tool fence stays immediate (the immediate auth
  gate before any lazy parse):
  `tests/unit/test_auth_service.py::test_external_tool_fenced_key_raises_fence_active_error`
  (parametrized active/held), held-acquisition controls
  `tests/unit/test_external_tool_fence.py::test_acquire_other_request_id_while_fence_bound_is_rejected`
  and `::test_acquire_blocks_when_ordinary_pending_reservation_exists`, and
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
  `::test_suspended_key_raises_gateway_key_suspended_error`. The
  while-waiting revalidation variants are the new integration tests 11
  (revoked key while waiting) and 12 (OWNER deactivated while waiting — not
  a suspended-key variant).

## Real versus mocked

- Real: owned PostgreSQL (migrations, key/policy/accounting rows, audit),
  owned Redis (ZSET leases, atomic limiter), HTTP (uvicorn + real sockets,
  including a real client disconnect), Chromium (admin forms, JS and no-JS).
  The native browser app runs the real cryptographic/session algorithms
  (login, HMAC key hashing, one-time-secret encryption) over SYNTHETIC
  credentials and secret material; those implementations are not mocked.
- Mocked: provider execution (holding/echo adapters and canned SSE), and
  unit-level fakes confined to the documented unit boundary (small
  lease/admission doubles for helper controls; fake Redis client objects at
  the route unit boundary). Real Redis is used for all Lua and integration
  behavior. Service/unit doubles and the real browser crypto remain distinct
  claims.
- Not executed: broad local matrix (final-head GitHub CI is authoritative for
  the full suite), real provider/model calls, and real email — none are
  required by this objective.
