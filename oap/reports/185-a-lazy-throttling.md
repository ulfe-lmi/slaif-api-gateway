# OAP Execution Report — Objective 185-a: Bounded per-key lazy throttling

Report status: IMMUTABLE (finalized at the exact final implementation head
`31561af50f40cd86fd227085b36cf5816310b572`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first parent =
this implementation head; only this report path differs).

- Implementation head SHA: 31561af50f40cd86fd227085b36cf5816310b572
- Report publication commit: SELF

## 1. Work order and PR identity

- Work order: `oap/orders/185-a-lazy-throttling.md` (strategic-authored;
  committed unchanged by the activation commit); `oap/active` = `185-a`.
- PR: #323 `feat: add bounded per-key lazy throttling` — the unique 185 PR
  (CREATE_NEW_PR):
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/323.
- Branch: `oap/185-lazy-throttling`.
- Base: `main` at `8f706d308c7588677891de222be92922a5e5c5ec` (verified at
  activation; predecessor PR #322 merged before activation).
- Activation commit: `ef59ecafe1fef14e5b4938b55c6a71de5ff8ab12`; order and
  `oap/active` bytes unchanged since.
- Commit chain (1 activation + 8 implementation):
  - `ef59eca` — activation: strategic order + `oap/active` (bytes
    unchanged).
  - `24a1ec8` — R3 runtime seams: strict `LazyThrottlingPolicy`,
    `LazyThrottlingAdmission` helper (waiting lease/admission slot,
    bounded awaits, cancel-safe idempotent cleanup), wait/deadline/cap
    errors, config validation, Chat/Responses wiring.
  - `10e44fd` — R1/R2 admin key create/detail controls (schemas, dashboard
    service, templates, JS) + CI-compatibility corrections.
  - `2a209d7` — R4 pre-provider disconnect handling, bounded awaits,
    cancel-safe cleanup (unit level).
  - `8a82069` — V2/V4 integration: owned Redis/PG fixtures, waiting caps,
    HTTP wait→admit, Chat 429 negatives.
  - `1546cd8` — bounded transport disconnect probe + actual
    socket-disconnect integration proof.
  - `dd736d8` — V3/V4 lifecycle + Responses + admin durable/audit evidence.
  - `8ae4d29` — V5 browser proof, owner-inactive + audit-rollback
    controls, R7 docs.
  - `31561af` — verification-doc accuracy corrections + contended-wait
    pricing/FX preflight negatives (final implementation head).
- At publication the PR body was updated (metadata only, no new commit or
  head) to the final behavior description and validation summary.

## 2. What was implemented (R1–R7)

- R1: per-key opt-in policy — `reject` (default) or `wait` with positive
  finite `max_wait_seconds` (key default 30s) / `max_waiting_requests`
  (key default 2), operator ceilings (120s / 16), deployment-wide waiting
  cap (256), Redis waiting-lease TTL (300s). Strict parsing (unknown
  fields forbidden, integer digit strings); admin create/detail UI with
  strict stored-policy projection and same-transaction audit.
- R3: waiting occurs only at the existing Chat Completions and Responses
  Redis rate-limit seams (streaming and non-streaming, plus the Responses
  compaction path). The maximum wait is the ADMISSION budget for all
  pre-admission wait steps; once the wait loop ends (admission or
  deadline), final opaque-ID bookkeeping (waiting-lease/slot release)
  runs under its own separate per-ID 5-second bound — cleanup only, never
  extra eligibility — with the bounded Redis lease/slot TTLs as crash/
  outage backstop. While waiting, a key holds no quota reservation, no
  ledger row, no active concurrency slot, and no PostgreSQL connection;
  admission uses the existing atomic PostgreSQL reservation/finalization
  exactly once.
- R4: after a real wait, full revalidation before forwarding (key auth,
  owner active state, endpoint/request policy, lazy-policy equality,
  route re-resolution). Pre-provider disconnects are canceled before any
  provider call or accounting; 499 `client_disconnected` is internal only
  (no response is fabricated to a closed peer). Cleanup is idempotent and
  cancellation-safe at every await boundary (four task-cancel boundaries;
  timeout-origin distinction so a built-in `TimeoutError` is not misread
  as a deadline).
- R5: new OpenAI-shaped 429 codes `lazy_throttling_deadline_exceeded` and
  `lazy_throttling_waiting_capacity_full`; 409
  `policy_changed_while_waiting`; existing 429/503 mappings, codes, and
  error shapes unchanged; no `Retry-After` is sent.
- R7: documentation updates listed in section 7 plus the objective
  verification record and its index entry.

## 3. Exact test mapping — new (this objective) vs inherited

Newly executed (objective 185-a); the full record with per-case
descriptions is `docs/verification/lazy-throttling.md`:

- Integration — 14 cases in
  `tests/integration/test_lazy_throttling_postgres_redis.py`. The module
  acquires ONE fresh labeled loopback-bound tmpfs PostgreSQL 16 container
  and ONE fresh no-persistence Redis 7 container (exact-ID verified
  cleanup); all 14 cases share those instances and seed unique
  keys/owners/models per case:
  1. `test_two_instances_waiting_caps_and_admit_once`
  2. `test_global_waiting_cap_across_keys`
  3. `test_http_chat_waits_for_capacity_then_admits`
  4. `test_http_chat_default_mode_denies_immediately`
  5. `test_http_chat_wait_mode_deadline_429`
  6. `test_http_chat_waiting_capacity_full_429`
  7. `test_deadline_cancel_and_crash_expiry_release_leases`
  8. `test_http_chat_streaming_waits_for_capacity_then_admits`
  9. `test_http_chat_real_socket_disconnect_before_admission`
  10. `test_http_chat_hard_quota_refuses_immediately_without_waiting`
  11. `test_http_chat_revoked_while_waiting_refuses_403`
  12. `test_http_chat_owner_inactive_while_waiting_refuses_403`
  13. `test_http_responses_waits_for_capacity_then_admits`
  14. `test_admin_lazy_throttling_policy_durable_and_audited`
- Unit — 24 helper/route cases at the documented unit boundary (small
  lease/admission doubles and fake Redis client objects; no
  FakeRedis/Lua engine):
  - `tests/unit/test_lazy_throttling.py` — 17: admit-once; denial-then
    admit; token-never-fit impossibility (strict inequality; equality can
    fit); waiting-capacity full fast-fail; deadline exhaustion with lease
    release; lease TTL covering max wait plus margin; stalled
    revalidate/check bounds; built-in `TimeoutError` not misread as a
    deadline; Redis-unavailable propagation; disconnect during/after
    wait; the four task-cancel await boundaries (lease acquisition,
    admission call, post-admission probe, final lease release) with
    idempotent cleanup.
  - `tests/unit/test_lazy_throttling_routes.py` — 7: dynamic
    disconnect-probe wiring at the Chat and Responses call sites; Chat
    deadline 429 (helper + lease exercised, no provider/reserve); Chat
    disconnect cancellation (499, no provider/reserve/finalize); reject
    default immediate 429 (wait loop never runs); and two contended-wait
    preflight negatives where `capture_pricing_and_fx` raises the
    existing missing-pricing-rule / missing-FX errors: exact 400 codes
    (`pricing_rule_not_found`, `fx_rate_not_found`), wait helper never
    reached, zero waiting lease, zero provider calls, zero financial
    reservations.
- Browser — 3 cases in `tests/browser/test_admin_lazy_throttling.py`. The
  module reuses the integration module's qualified fixture (ONE owned
  labeled loopback-bound tmpfs PostgreSQL container shared by the 3 tests
  with unique data per test) and runs a real uvicorn app with the real
  login/HMAC/AES session and key-creation algorithms over explicit
  synthetic credentials and secret material:
  1. `test_admin_lazy_throttling_wait_create_update_and_reject` (JS-active
     create with NON-DEFAULT wait bounds, detail summary/prefill,
     authenticated update, return to reject, audit rows carry the actual
     admin actor ID)
  2. `test_admin_lazy_throttling_no_js_create_and_escaped_redisplay`
     (server-rendered wait inputs usable, NON-DEFAULT wait saved,
     malicious reason redisplayed escaped, stored policy unchanged)
  3. `test_admin_lazy_throttling_negatives_leave_policy_unchanged`
     (unauthorized 303, bad CSRF 400, missing reason 400, invalid bounds
     400 — all leave the stored policy unchanged)

Inherited (unchanged primitives, cited by exact test name; the 14 new
integration cases do not each re-exercise them):

- Fixed-window request/token counting, atomic limiter semantics, and the
  actual new-window reset control (real Redis):
  `tests/integration/test_redis_rate_limit_service.py::test_redis_rate_limit_service_with_real_redis`,
  with unit-level atomic-evaluation primitives
  `tests/unit/test_rate_limit_service.py::test_allows_requests_under_limit_with_one_atomic_eval`,
  `::test_rejects_over_request_limit`, `::test_rejects_over_token_limit`,
  `::test_rejects_and_releases_concurrency_limit`.
- Stream heartbeat/release primitive (unchanged; the new streaming case
  does not observe heartbeat ticks):
  `tests/unit/test_rate_limit_service.py::test_heartbeat_refreshes_existing_concurrency_slot`,
  `::test_expired_concurrency_slot_is_cleaned_after_ttl`.
- Missing pricing/FX in the NEW contended-wait preflight (objective
  185-a):
  `tests/unit/test_lazy_throttling_routes.py::test_chat_wait_mode_preflight_missing_pricing_fx_refuses_without_waiting`
  (both parameters); legacy normal-path pricing primitives (unchanged):
  `tests/unit/test_v1_chat_completions_pricing.py::test_missing_pricing_rule_returns_openai_error_before_501`,
  `::test_missing_fx_rate_returns_openai_error_before_501`.
- Active/held external-tool fence stays immediate (the immediate auth
  gate before any lazy parse):
  `tests/unit/test_auth_service.py::test_external_tool_fenced_key_raises_fence_active_error`
  (parametrized active/held); held-acquisition controls
  `tests/unit/test_external_tool_fence.py::test_acquire_other_request_id_while_fence_bound_is_rejected`,
  `::test_acquire_blocks_when_ordinary_pending_reservation_exists`; and
  `tests/unit/test_v1_responses_quota.py::test_hosted_pricing_and_max_tool_calls_fail_before_redis_fence_provider`.
- Redis outage fail-open/fail-closed (unchanged):
  `tests/unit/test_rate_limit_service.py::test_redis_unavailable_fails_closed_or_open`,
  `tests/unit/test_v1_chat_completions_rate_limits.py::test_redis_fail_closed_unavailable_returns_before_expensive_work`,
  `::test_redis_fail_open_allows_request`.
- OpenAI-shaped 429/503 error mapping (unchanged):
  `tests/unit/test_rate_limit_api_errors.py::test_rate_limit_exceeded_errors_map_to_openai_429`,
  `::test_redis_unavailable_maps_to_server_error`.
- Revoked/suspended key refusal (pre-wait primitive):
  `tests/unit/test_auth_service.py::test_revoked_key_raises_gateway_key_revoked_error`,
  `::test_suspended_key_raises_gateway_key_suspended_error`. The
  while-waiting revalidation variants are the new integration tests 11
  (revoked key while waiting) and 12 (OWNER deactivated while waiting —
  not a suspended-key variant).

## 4. Real versus mocked

- Real: owned PostgreSQL 16 (Docker; loopback-bound, tmpfs data, owner
  labeled, exact-ID verified cleanup) — migrations, key/policy/accounting
  rows, audit; owned Redis 7 (no persistence) — ZSET leases, atomic Lua
  limiter; HTTP via uvicorn + real sockets, including a real TCP client
  disconnect; native Chromium (JS and no-JS) running the real
  cryptographic/session algorithms (login, HMAC key hashing, one-time
  secret encryption) over SYNTHETIC credentials and secret material.
- Mocked: provider execution only (holding/echo adapters and canned SSE),
  and unit-level fakes confined to the documented unit boundary (small
  lease/admission doubles for helper controls; fake Redis client objects
  at the route unit boundary). Real Redis is used for all Lua and
  integration behavior. Service/unit doubles and the real browser crypto
  remain distinct claims.
- Not executed: broad local matrix (final-head GitHub CI is authoritative
  for the full suite), real provider/model calls, and real email — none
  are required by this objective.

## 5. Executed evidence summary (focused, local)

- Integration: 14/14 PASS (25.07s, exit 0).
- Browser: 3/3 PASS (17.38s, exit 0); strategic independent re-run 17.17s,
  0 skips, 0 RuntimeWarnings.
- Unit: 7/7 routes PASS (5.35s); focused unit slice (lazy + admin + key
  service + config) 233 PASS (32.25s); final-focused browser +
  integration 17 PASS (39.10s).
- Docs hygiene: `scripts/check_documentation.py` →
  `DOCUMENTATION_CHECK=OK` (93 files).
- Final-head GitHub CI at `31561af`: all ten checks SUCCESS (Unit/lint/
  migration head; PostgreSQL integration; OpenAI-compatible E2E;
  Playwright browser smoke; Docker Compose smoke; Documentation hygiene;
  CodeQL incl. Python and JS analyses).
- Strategic independent verifications (this objective): four new real
  PG/HTTP cases (10.73s); stream/socket/cleanup (10.66s); Chat HTTP happy
  path (8.41s); native browser all 3 (17.17s); owner-inactive + audit
  rollback (7.75s); AST audit confirming every test reference cited in
  the verification doc exists.

## 6. Scope and diff

47 files, +8750/−76 against base `8f706d3`:

- 20 app files: new `services/lazy_throttling.py` (policy model +
  admission helper); `rate_limit_policy.py` / `rate_limit_errors.py`;
  Chat and Responses gateways; `auth_service.py` (immediate active/held
  fence gate); `key_service.py`; `admin_key_dashboard.py`; `api/admin.py`
  and `api/dependencies.py` (session-closure fix, section 8c);
  `config.py`; `metrics.py`; `schemas/{keys,auth,admin_keys,rate_limits}.
  py`; templates `keys/{create,create_result,detail}.html`;
  `web/static/js/lazy-throttling.js`.
- 15 test files (4 new: helper, routes, integration, browser; 11
  extended with focused regressions, including the two authorized
  CI-compat paths in section 8a).
- 10 documentation files (section 7).
- 2 OAP files: the order and `oap/active` (committed unchanged by the
  activation commit).

No new dependencies, schema, migrations, financial services, CI platform,
or release/tag.

## 7. Documentation impact statement

Changed (10):

- `docs/configuration.md` — new settings and defaults (ceilings 120s/16,
  deployment cap 256, lease TTL 300s, key defaults 30s/2); maximum wait =
  admission budget + separate per-ID 5-second cleanup bound; client/proxy
  timeout guidance (allow validation + admission wait + inference +
  bounded cleanup; only a disconnect while waiting is canceled before the
  provider; once admitted the request completes under existing
  post-call accounting; a shorter timeout may end the connection before
  completion, including while already executing).
- `docs/cli-reference.md` — lazy throttling is dashboard-managed; not a
  CLI flag.
- `docs/database-schema.md` — new “Lazy throttling policy JSON” section
  (key metadata, strict projection).
- `docs/openai-compatibility.md` — new 429/409/499 codes and semantics;
  no `Retry-After` sent.
- `docs/provider-forwarding-contract.md` — waiting is admission-only;
  hard quota/security/fence/unknown pricing-FX/Redis-unavailable refusals
  are immediate and never converted into waits; admission budget +
  bounded cleanup.
- `docs/security-model.md` — while-waiting revalidation; disconnect/
  cancellation cleanup; admission budget + best-effort separately bounded
  bookkeeping; no durable queue, no FIFO promise, no replay.
- `docs/accounting.md` — zero reservation/ledger/slot/PG-connection while
  waiting; finalization exactly once per admitted request.
- `docs/runbooks/redis-outage.md` — waiting-lease TTL behavior during
  outage (crash backstop, fail-open/fail-closed unchanged).
- `docs/verification/lazy-throttling.md` — new objective verification
  record (exact new-versus-inherited mapping, real-vs-mocked).
- `docs/verification/README.md` — index entry for the new record (14
  integration / 24 helper-route unit / 3 browser cases).

## 8. Security, privacy, accounting, and honest limitations

- Waiting holds no financial or concurrency state: integration cases
  prove zero reservation/ledger mutation and zero app-pool checkouts
  during settled waits, and one correctly attributed finalization per
  request (per-request ledger rows with matching gateway request IDs).
- No plaintext gateway key, cookie, session, or CSRF value is logged or
  screenshotted by any test; audit rows carry old/new policy values and
  the actual admin actor ID, never the plaintext key; an injected
  audit-write failure proves same-transaction rollback of the metadata
  change and audit row.
- A disconnected client receives no fabricated response; 499
  `client_disconnected` is internal reporting only.
- No real provider/model calls and no real email in this objective;
  provider upstreams are mocked.
- No broad local matrix was run locally; final-head GitHub CI is
  authoritative for the full suite and was green at the implementation
  head.
- This is an RC-beta-grade capability; no production, security, or
  compliance certification is claimed.

## 9. Disclosed deviations (all bounded; none weaken gates)

(a) Two extra test paths authorized by
`workorders/185-a-ci-compatibility-scope-decision.md` (strategic):
  - `tests/unit/test_responses_codex_compaction.py` — fake
    `refreshed_context=None` seam (2 lines) so the test compiles against
    the new auth-context signature.
  - `tests/unit/test_oap_governance.py` — accepts the order's plain
    `PR mode: CREATE_NEW_PR` header as equivalent to the inline-code
    form; the activated order bytes and all semantic/negative gates are
    unchanged.
(b) `docs/verification/README.md` — the index entry was first added
  before `workorders/185-a-verification-index-scope-decision.md`; that
  decision subsequently forward-authorized exactly this one
  link/description (and no other historical entries). Disclosed here as a
  minor premature extra-path edit, now forward-authorized.
(c) `app/slaif_gateway/api/dependencies.py` — nested session-closure fix:
  `get_db_session_after_auth_header_check` previously iterated an inner
  `get_db_session_from_app_state` generator without explicitly awaiting
  its `aclose()`, so the outer `aclose()` could leave the inner cleanup
  scheduled to the GC finalizer; a probe observed a pool connection
  staying checked out after the request. The outer generator now holds
  the inner generator explicitly and `await inner.aclose()` in `finally`;
  RuntimeError conversion is unchanged. Proven by targeted regressions
  (15 dependency + 47 gateway unit tests) and final-head CI.
(d) `web/static/js/lazy-throttling.js` — display fix only: the author CSS
  `.form-grid { display: grid }` overrides the `hidden` attribute, so the
  JS hide/reveal also toggles `display`. The server still ignores wait
  fields in reject mode; no-JS behavior is unchanged.
(e) Typed closed-client outcome for pre-admission disconnects (within the
  order's permitted helper/error/gateway paths) so the middleware can end
  the request normally after an actual socket close; genuine asyncio task
  cancellation propagation and all four cancel-cleanup controls are
  unchanged.

## 10. Merge state and pending items (not yet done)

- PR #323 is OPEN at implementation head `31561af50f40cd86fd227085b36cf5816310b572`
  with all ten checks SUCCESS (verified at publication).
- Pending, and NOT claimed as done: final-SELF CI checks on this report
  commit; strategic independent review (report/topology/whole diff/all
  exact SELF checks); and the guarded merge by strategy as delegated merge
  authority. The coding agent never merges and never enables auto-merge.
