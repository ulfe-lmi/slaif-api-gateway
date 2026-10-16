# OAP Work Order — 185-a

## Objective and human authorization

Implement bounded opt-in lazy throttling per INDIVIDUAL API KEY. The human
approved on2026-10-15 the explained interface and recommendation: admin key
creation/detail controls, immediate rejection default, wait before provider
execution, finite wait/queue limits, Chat Completions and Responses including
streaming. User-wide preferences/aggregate counters are a separate extension.
Goal: implement the delayed response as agreed. This means delayed admission,
not storing or pacing completed provider output. Keep this one coherent PR.

## Verified state, identity and prerequisite

PR mode: CREATE_NEW_PR
Canonical repository: ulfe-lmi/slaif-api-gateway
Base: main at8f706d308c7588677891de222be92922a5e5c5ec
Branch: oap/185-lazy-throttling
Title: feat: add bounded per-key lazy throttling

Predecessor184 PR322 MERGED2026-10-14T05:31:44Z. All ten actual main check
runs SUCCESS. Accepted SELFf9836a37255270668c51623e87fcd78e5598bb6a/report-only
parent6b376054ee410c3378adbdf6faee08ee6b4e0ffc; prior active184-a terminal.
Prior report SHA2569143b51caa7c4e5ddfead566a6005ead941ca2e897e7a56c2a21013a993e333e.
Only unrelated Dependabot319 open; no185 PR at preparation. Active main
ruleset23580289 deletion/non-fast-forward, bypassactors[]; release remains
v0.1.0-rc.1. Local checkout on prior SELF with only CODEX-SESSIONS.md/codex.sh
untracked: preserve these, .codex/, .local-provider-catalog/, unrelated
worktrees and all prior immutable OAP orders/reports. Agent owns Git execution;
strategy has not switched/reset/cleaned/stashed anything to publish this order.
185-a creates exactly one new PR. Same-number continuations amend that PR.
Coding agent never merges or enables auto-merge.

## Required reading and setup

Read applicable AGENTS.md and OAP-COMMUNICATION-coding-agent.md completely;
strategic compact OAP and ARCHITECTURE-for-agents.md, inert workorders/185-a-
lazy-throttling.md; relevant live docs/database-schema.md, docs/accounting.md,
docs/openai-compatibility.md, docs/provider-forwarding-contract.md,
docs/security-model.md, docs/configuration.md and admin mutation contracts.
Read source/test seams before designing. No full root architecture/archive or
catalog loads absent a concrete unresolved detail. Reconcile live GitHub/main,
open PRs, current checks/rules/release and matching OAP before Git execution.

Existing dev venv /tmp/slaif-181c-strategic-venv (Python3.12). Docker qualified
at unix:///var/run/docker.sock. Use NEW owned synthetic PostgreSQL and Redis
containers, loopback random ports, labels and exact-ID cleanup; PostgreSQL
tmpfs, Redis no persistence. Never destructive DATABASE_URL/.env/shared-port
setup; supply owned TEST_DATABASE_URL/TEST_REDIS_URL. Existing browser runtime
may be reused at /tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu
with command-scoped LD_LIBRARY_PATH if needed; inspect existing tooling first.
Routine owned test setup/dependencies allowed. No system-wide Docker/daemon/
network configuration or broad package upgrades. No actual provider/model call,
public-source GET, protected auth/config read, production data, release/tag/deploy.

## Exact permitted paths (only changes required by this objective)

- app/slaif_gateway/config.py, metrics.py
- app/slaif_gateway/schemas/rate_limits.py, keys.py, auth.py, admin_keys.py
- app/slaif_gateway/services/rate_limit_policy.py, rate_limit_service.py,
  rate_limit_errors.py, lazy_throttling.py (new bounded shared helper allowed)
- app/slaif_gateway/services/key_service.py, auth_service.py,
  admin_key_dashboard.py, key_policy_validation.py
- app/slaif_gateway/db/repositories/keys.py
- app/slaif_gateway/api/admin.py, dependencies.py, rate_limit_errors.py
- app/slaif_gateway/services/chat_completion_gateway.py, responses_gateway.py
- app/slaif_gateway/web/templates/keys/create.html, detail.html,
  create_result.html, _lazy_throttling.html (new reusable partial allowed)
- app/slaif_gateway/web/static/js/lazy-throttling.js (small progressive UI only)
- tests/unit/test_rate_limit*.py, test_lazy_throttling.py (new),
  test_key_rate_limit_policy_cli.py, test_key_service_create.py,
  test_key_service_policy_update.py, test_key_service_safety.py,
  test_key_policy_validation.py, test_auth_service.py,
  test_admin_key_create_routes.py, test_admin_key_create_templates.py,
  test_admin_key_actions_routes.py, test_admin_key_actions_templates.py,
  test_admin_keys_dashboard_service.py, test_admin_keys_templates_safety.py,
  test_config.py, test_v1_chat_completions_rate_limits.py,
  test_v1_chat_completions_streaming_rate_limits.py, test_v1_responses_quota.py,
  test_lazy_throttling_routes.py (new)
- tests/integration/test_redis_rate_limit_service.py,
  test_v1_rate_limits_redis.py,
  test_v1_streaming_rate_limit_concurrency_postgres_redis.py,
  test_admin_key_create_postgres.py, test_admin_key_actions_postgres.py,
  test_lazy_throttling_postgres_redis.py (new)
- tests/browser/test_admin_dashboard_smoke.py,
  test_admin_lazy_throttling.py (new)
- docs/configuration.md, cli-reference.md, security-model.md,
  database-schema.md, openai-compatibility.md, provider-forwarding-contract.md,
  accounting.md, runbooks/redis-outage.md,
  verification/lazy-throttling.md (new)
- .env.example (document only non-secret operational waiting caps if added)
- Activated oap/orders/185-a-lazy-throttling.md and oap/active UNCHANGED;
  own new oap/reports/185-a-lazy-throttling.md only in report-only SELF.

No models/migration/dependency/workflow/other endpoint/financial-executor change
is pre-authorized. Reuse PostgreSQL gateway_keys metadata_json for validated
small policy if feasible. If an exact additional path is actually necessary,
request a bounded prospective scope decision before editing it; do not expand
supporting machinery by inference. Paths in the first groups are relative to
their named directory (e.g.schemas/keys.py and services/key_service.py).

## Product contract and acceptance requirements

R1. Policy and defaults. Individual keys have reject(default) or wait mode,
maximum wait seconds and maximum waiting requests. Legacy/missing policy keeps
immediate rejection. Use existing key metadata/service/repository/audit paths;
strict validated typed configuration, no arbitrary metadata/client-header opt-in.
Concrete initial form defaults wait30s and2waiting/key, reject selected. Positive
finite configurable settings with hard operator ceilings (initial maxwait120s,
max16waiting/key) and deployment-wide waiting cap(default256) are sufficient;
no new management platform. Zero/negative/boolean/NaN/infinity/unknown values
refuse; disabled UI fields must not accidentally re-enable or erase other policy.
Malformed stored waiting policy cannot silently grant wait or bypass a limit.
Changing ordinary rate limits must preserve the delayed policy unless explicitly
changed. Rotation preserve-rate-policy option preserves/reset delayed fields
consistently; absent policy on existing template/bulk paths remains reject.

R2. Administrative interface. Extend existing key CREATE Rate Limits section:
When a rate limit is reached: Reject immediately / Wait for capacity (lazy
throttling); reveal maximum waiting time and maxwaiting/key for wait. Work with
JS disabled (progressive enhancement, server validation and escaped redisplay).
On key DETAIL add actual authenticated, authorized, CSRF-protected update form,
required audit reason, readable current values and summary (mode/seconds/count/
Chat Completions and Responses). Persist through existing KeyService in same
transaction as audit with safe old/new values, no plaintext key/secret in DTOs.
Help text: waiting precedes provider execution; queue/full/deadline yields429;
hard quotas/security remain immediate; streaming starts after admission.
No user-level controls. Admin cannot exceed configured operator ceilings.
If ENABLE_REDIS_RATE_LIMITS is off, show clearly that operational throttling is
inactive; enabling lazy metadata must not imply actual enforcement or cause
unrelated key policy changes. No standalone new dashboard/SPA/live queue UI.

R3. Shared bounded admission. Apply only at existing Chat Completions and
Responses Redis rate-limit seams, including supported streaming/nonstreaming
and existing Responses compaction path. Default path unchanged. On temporary
request/token/concurrency denial in enabled wait mode: keep original HTTP
request open, wait asynchronously and retry the existing atomic Redis limiter
until admitted, cancelled, no longer authorized or maxwait exhausted. Preserve
existing fixed-window counting and active-slot heartbeat/release semantics;
not a new smooth-pacing algorithm. Calculate useful bounded retry times (the
existing denied request/token hint is always fullwindow, not time to boundary;
concurrency TTL is not earliest actual completion). No blind fixed60s sleep,
spin loop, busy polling or simultaneous uncontrolled admission at reset.
Permit progress when an active request finishes before its TTL. Redis remains
the atomic admission authority across worker instances; waiting itself must
not increment request/token counters or reserve an ACTIVE concurrency slot.

Use a small shared Redis waiting lease/counter bound per-key AND deployment,
not only a process-local counter. Acquire atomically, fail429 when cap reached;
release on every exit and recover crashed-worker leases with bounded expiry.
Only opaque request/key IDs and timestamps in operational state, NEVER body,
messages/media/tools/Authorization/prompts/outputs. In-memory original body is
transient request handling only. Do not introduce durable/FIFO jobs, DB queue,
Celery task, disk spooling, Redis body storage or distributed scheduler. Strict
FIFO is not promised; document possible reordering under contention.

R4. Lifecycle/security. No provider call, monetary quota reservation, quota-row
lock, DB session/connection held, or content persistence during waiting. Close
short read sessions before suspension. Re-authenticate key/owner/status/expiry/
fence and revalidate current endpoint/model/provider/tool/request policies and
re-resolve current route after a real wait before forwarding; do not reuse a
stale pre-wait authorization or policy result to admit. Use existing services
and short sessions, not a new authority system. A key revoked/suspended/expired
or policy tightened while waiting cannot execute under its former permissions.
If lazy mode disabled or limits reduced while pending, respect current policy;
never reset original deadline on a policy update. Cancel and clean up promptly
on disconnect or task cancellation BEFORE provider work; no automatic replay
or retry of an already forwarded request. No early fake200/SSE headers or
buffering/dribbling of provider response. Request length/body caps still apply.
No event-loop blocking and no waiting on unrelated hard errors.

R5. Hard rejection and accounting. Hard quota/security/hosted-tool fence/hold,
unknown pricing/FX, malformed requests and Redis unavailable are NOT temporary
429 candidates for waiting. Detect existing hard refusals using current
non-mutating checks where necessary (no duplicate financial implementation);
no spending/reservation for a request still waiting. A request whose estimated
tokens exceed its complete token-rate window capacity cannot ever fit and must
fail immediately rather than wait until timeout. Final admission still uses
existing PostgreSQL atomic quota reservation/finalization and live pricing/FX;
no quota bypass, changed monetary math, double reservation/charge or duplicate
provider invocation. Redis failure retains existing configured fail-open versus
fail-closed policy (503 for unavailable fail-closed; no infinite queue/fallback
that widens it). PG hosted exclusive fence/unknown-cost hold remain immediate
hard controls, never queued retries. Cancellation before admission leaves no
financial application, usage charge, active slot or waiting lease behind.

R6. Bounded diagnostics. Preserve OpenAI error envelope. Deadline and waiting
cap failures use honest429/safe machine codes, optional truthful Retry-After;
Redis failure503 unchanged. Metrics may add bounded-label delayed-admission,
wait-duration and timeout/full/cancel counts, not per-key/request/body labels.
No provider-key/client-content logs, background transcripts or request storage.

R7. Documentation. Document exact enabled endpoints, operator/master Redis
setting, key controls/defaults/ceilings, fixed-window semantics, waiting caps,
client/proxy timeout tradeoff, no FIFO/durability promise, disconnect/restart/
Redis behavior and accounting unchanged. Update affected live contracts in same
PR. Do not claim all endpoints, per-user limits, provider429 retries, invoice
accuracy, strict no-overrun or production/release readiness.

## Required focused verification and negative evidence

Implement first; exercise real boundaries, not a large fake-shim framework.
No complete local suite: focused tests plus routine final-head GitHub CI.

V1. Focused policy/service tests: legacy/defaultreject; validwait/defaults;
all validation/ceilings/invalid stored policy; create/update/audit/rotation
round-trip and preserve unrelated metadata; unknown client fields cannot optin.
V2. REAL owned Redis, >=2 separate service instances sharing state: capacity
later frees then admits once; per-key and global waiting caps under contention;
request/window reset vs token-fit impossibility; waiting does not increment
active or request/token state; deadline/cancellation/crash-expiry cleanup;
actual admitted concurrency never overlimit; separate keys independent.
V3. Actual HTTP Chat/Responses normal AND streaming using mock provider: waits
before upstream, normal result after capacity, exactly one invocation, default
immediate429, full/deadline429. Include actual server client disconnect before
admission (ASGI test cancellation alone is not disconnect proof). Preserve
existing stream heartbeat/release/accounting and unsupported endpoints.
V4. REAL owned PostgreSQL+Redis integration: admin policy create/update durable
and safe old/new audit; waiting has zero quota-reservation/ledger mutation and
no held connection/transaction; after admission exactly one normal reservation/
finalization; expiry/revoke/suspend/tighten model/endpoint/tool policy during
wait prevents old-policy forwarding. Existing hardquota and externalfence/hold
refusals remain immediate; invalid price/FX not converted to wait; no actual
provider credentials/calls. Prove cleanup after Redis outage and cancellation.
Use a representative pair of runtime HTTP paths plus focused common-helper
cases to avoid duplicating every negative on every endpoint.
V5. Actual browser key create/detail/update/summary, positive saved wait and
return to reject, no-JS usability/escaped error redisplay, CSRF/unauthorized/
missingreason/invalid bounds negatives. Reuse existing browser/admin fixtures;
do not add a separate platform or system runtime installation.
V6. Run focused Ruff/docs hygiene; use actual final-head GitHub unit/lint/
migration/PG/E2E/browser/Compose/docs/CodeQL checks. Report executed vs skipped
versus inherited proof distinctly; green CI is necessary but not sufficient.

## Boundaries and non-goals

No user/owner aggregate policy; no application of waiting to admin login,
audio/embeddings/realtime/models or endpoints without the current limiter.
No provider rate-limit retry, deferred billed requests, strict ordering, durable
queue/resume after restart, global model/provider scheduler, response buffering,
byte pacing, per-token stream slowdown or external-tool allowance expansion.
No new schema/migration/financial services/dependencies/CI platform, broad
cleanup, release/tag/deployment, production import or protected credentials.
Do not rewrite existing orders/reports/message.txt or inherited incident history.

## Publication/report duties

Commit/push strategic-authored order and exact active185-a unchanged from shared
filesystem; create unique185 PR early, record actual URL/head. Provide concise
implementation checkpoints in pane; strategy reviews while you execute. Report
actual failures, corrections, deviations and unexecuted evidence honestly. No
publication until actual required evidence is complete or explicit PARTIAL/
BLOCKED with concrete obstacle; never reinterpret a required skip as pass.

Atomic immutable report: oap/reports/185-a-lazy-throttling.md. Include workorder,
uniquePR/base/branch, actual implementation commits and full literal
Implementation head SHA: <40hex>; Report publication commit: SELF; exact tests,
real Redis/PG/browser/mock/actual distinction, scope/diff, docs, security/privacy/
accounting evidence and limitations. Include repository-required documentation-
impact statement. Publish once, report-only SELF first parent implementation;
push and verify exact remote PR SELF. Do not report merge/final-SELF CI as done
before it occurs. Never merge or enable auto-merge. Send exactly two-byte OK
on verified response FIFO once, close descriptor and return to the sole
wait-control-and-wake.sh helper on pane%9. Do not read strategic responseFIFO,
send strategiccontrolOK, or spawn competing FIFO readers. Strategy independently
reviews report/topology/whole diff/all exact SELF checks then merges guarded.
