# OAP Work Order — 201-a

PR mode: CREATE_NEW_PR
Objective: 201 — inspect recorded request failures by request ID
Branch: oap/201-content-free-request-diagnostics
Base: main at 7cf8a7dbf02c8a5934ff25d3b28ad88b66f81afa
PR title: Diagnose request failures by ID without storing request content

## Purpose and verified state

Implement MISSING_CLI_FUNCTIONALITY.md §8.2 / DoD 10 under the approved full CLI feature round. Ordinary continuation is authorized. Objectives 202–205 remain inert; all eleven final installed-executable outcomes still require Objective 205. This order creates exactly one PR for 201. The coding agent never merges or self-activates.

Verified before activation on 2026-10-29 UTC: Objective 200 is TERMINAL. PR #356 merged at 2026-10-29T00:53:04Z as `7cf8a7dbf02c8a5934ff25d3b28ad88b66f81afa`; parents `4c265bc3c9668a66bb1643915d442fb8c411ff11` + accepted final SELF `fc43d451923f7e86f0f490a4442fcc80480de82b`; tree `e8909c44dd5cf4e084f61d0827cf82950d151b88` equals the accepted head. ALL 10 final-head checks and ALL 9 actual-main checks / THREE workflows (including dynamic Code Quality) succeeded. Both review threads are resolved. Root receipts: `200-guarded-merge.json`, `200-actual-main-checks-final.json`, `200-objective-complete.json`. Timings and the 200 acceptance row are reconciled. Full installed-CLI transcript remains 205, not claimed complete.

Live `main` still equals that merge; only unrelated Dependabot PR #319 is open. No 201 PR/order/report exists yet. Main ruleset 23580289 is active, default branch main, only release v0.1.0-rc.1; no release authority is granted. Existing local coding branch remains `oap/200-replay-reference-maintenance` at final E SELF with the SAME tree as main; root did not switch/reset/stash/clean/stage/commit Git state. Before publication, tracked tree was clean and only protected untracked CODEX-SESSIONS.md/codex.sh remained; hashes unchanged. The coding agent owns synchronization/new-branch execution and publishing unchanged strategic order/active bytes.

Fresh preactivation source review verifies ten existing runtime files byte-equal to the inspected baseline, records the actual function `apply_codex_route_limits`, current 0025 single migration head / 32 tables, and eight necessary existing head-literal dependencies including the guarded prefix-migration integration test. Root source receipt `201-preactivation-source-revalidation.json` and earlier inert diagnostics checkpoints are evidence, not new authority. This order now explicitly authorizes the ONE justified diagnostics table/migration, the four bounded default-OFF settings and the precise paths below; no generic observability/capture framework. New default settings are operator startup settings, not new key grants.

Verified fixed FIFOs and the sole coding control reader PID 3926843 / pane %9 before signal. Root will send exactly one control OK only after this complete shared order and exact active `201-a` exist. Existing pane/profile/model/effort remain unchanged. No other numeric objective runs concurrently.

Current source provides server-generated `gateway_request_id` and client-facing `request_id`, a shared ASGI scope-state channel, structured taxonomy rejection facts, and normal-auth provenance. UsageLedger requires a key and UsageProfile requires a ledger, so neither can represent failed authentication or pre-admission failures honestly. Existing logs have no bounded, portable, restart-safe CLI index. The smallest justified durable store is ONE small PostgreSQL operational-diagnostics table, expressly permitted by brief §8.2 when necessary, with a migration and schema documentation. Do not use audit logs, accounting rows, full capture files, a job system, or a new logging platform as substitutes.

## Operator workflow and facts

Provide `slaif-gateway diagnostics request show --request-id ID --json`, through a typed shared service. Support both recorded client request IDs and server gateway diagnostic IDs. Client IDs are nonunique and can equal another request's gateway ID. Provide an explicit namespace option (`any` by default, plus `gateway` and `client`) or equivalently clear resolution; never infer identity from a prefix or silently choose an arbitrary match. Bound ambiguous matches at 100, report ambiguity/count/overflow honestly, and offer gateway IDs for disambiguation. A lookup ID never establishes authentication authority.

A retained failure record must distinguish HTTP status from stream outcome. Include server diagnostic ID/time; a static endpoint template and method; known safe public error code/parameter and the shared classifier's reason/positions/counts/limits; authenticated key UUID ONLY after successful normal authentication; actual configured/resolved route UUID and safe public catalog identity when available; existing operator-declared deployment revision/provenance when safe and available (reuse existing settings, unknown when absent); actual input estimate/output allowance/relevant ceilings; and safe replay counts where genuinely known. Missing facts stay absent/unavailable. Do not guess from IP, model, timestamp, byte lengths, a nearby ledger, or current configuration.

Cover endpoint/model/capability denial, unsupported function tools, context-window rejection, replay rejection, and an unsupported streaming event after HTTP 200. Cover unattributable authentication failures and historical requests whose facts were never retained. Existing replay errors deliberately conflate several unavailable-reference causes: report the actual fixed error and known counts; do not invent an expired-versus-missing count or add wider replay/HMAC lookups to manufacture one.

Return stable typed outcomes such as found, ambiguous, not_found, and unavailable. Explain absence/retention/recording-disabled limits without claiming why a particular unrecorded historical request is absent. CLI lookup may read retained records even when recording is disabled; expose recording status separately. No provider inference or full-request capture is needed for lookup. A small metadata-only `diagnostics status` and expired-record `cleanup` command are allowed for operation and verification; do not add a UI or a general administration framework.

## Privacy and unchanged decisions

This facility stores content-free FAILURE metadata, not successful request history, bodies, prompts, instructions, descriptions, schemas, arguments/results, media URLs, reasoning, provider messages, replay/provider item/call IDs, HMACs, credentials, headers, queries, or raw path variables. It complements the existing explicitly armed full incoming-request capture facility; it must not replace it, arm it, or weaken its masking and complete-body requirements.

Use the existing scope facts and classifier result, not another validator. Existing capture maps contain free-form `error_message`, `error_param`, validation locations, and decoder text; a length cap does not make those content-free. Project only a finite typed vocabulary, safe known path components/indices, bounded numeric facts, and known public codes. Unsafe or unknown free-form values become explicitly unavailable. Never persist a whole exception, capture map, request state, policy result, or provider payload. In particular, `policy_result.effective_body` contains content and must never be dumped into diagnostics.

`api/dependencies.py::_observe_normal_auth_provenance` sets `auth_provenance=normal_auth` only after the normal authentication service succeeds. The capture observer can also have `read_only_capture_probe` provenance; that is NOT successful API authentication and must never supply authenticated diagnostic identity. Keep the two origins distinct.

Client IDs are untrusted. A complete incoming authentication secret can appear as an ID or another metadata value. Reuse the existing redaction/known-secret helpers where appropriate, including custom gateway prefixes and incoming bearer/cookie/session/proxy credentials; omit/mask such aliases with fixed safe reasons. Do not read or expose server-side provider credential values. Never use raw client model/wildcard suffixes as configured model identity; use the actual configured route UUID/pattern/literal where safe. Use static route templates, not URL/path/query values. Mask known authentication aliases in any new log paths as well. If the existing request-ID log binding needs a narrow alias-redaction correction, retain wire Request-ID behavior and authentication decisions.

All observation is best effort. Preserve response acceptance, validation/classification, normalization, auth, key/route/tool grants, provider forwarding, quota reservation/finalization, holds/fences, concurrency release, replay law, and cancellation. No permission or compatibility change is authorized.

## Storage and bounded operation — explicit decisions

Add only `request_diagnostics` and migration `0026_request_diagnostics` after the current single head `0025_catalog_refresh_applications`. No changes to existing accounting/identity tables. Store bounded typed columns and/or a strictly projected facts object; enforce an 8 KiB maximum serialized record payload and bounded scalar lengths. Unknown fields are rejected by the typed service boundary. Use a stable unique server diagnostic ID; client IDs are a separate nonunique lookup field.

Settings (document all names/defaults and restart requirements):

- `REQUEST_DIAGNOSTICS_ENABLED=False`.
- `REQUEST_DIAGNOSTICS_RETENTION_SECONDS=604800`, range 1..2592000.
- `REQUEST_DIAGNOSTICS_MAX_RECORDS=10000`, range 1..100000.
- `REQUEST_DIAGNOSTICS_WRITE_TIMEOUT_MS=100`, range 10..1000.

Configuration is startup configuration; changing it requires restarting the API workers. Defaults do not persist new diagnostic records. Disabling recording must not prevent reading/cleaning retained records. CLI status must distinguish disabled recording, an unavailable store, and an empty retained dataset.

Use an independent, bounded, best-effort transaction, never the request's accounting transaction. A failed insert, timeout, unavailable schema/database, capacity contention, or cleanup error must not change the original HTTP/SSE result, admission, accounting, or cancellation. Do not suppress CancelledError. No unbounded background tasks, queue, retry loop, or scheduler. Enforce the configured maximum count under concurrent writers, not an unsafe count-then-insert race. A small nonblocking transactional lock plus bounded expiry/oldest eviction is sufficient; do not create a general storage-slot or job framework. Document consistent settings across workers and the actual policy when the writer drops a record.

Filter expired records from lookup. Physically prune on writes and via an explicit bounded cleanup operation; document that idle storage needs cleanup and do not claim a background expiry daemon. Cleanup affects this table only. No arbitrary SQL, record editing, secret recovery, or audit-log retention changes.

## Narrow integration points

Use ASGI scope state across BaseHTTPMiddleware task boundaries. Prefer one observer write after the final HTTP/stream outcome, with pure best-effort fact hooks at the existing decisions; do not parse or buffer response/request bodies to derive diagnostics.

The actual route-limit function is `services/responses_request_policy.py::apply_codex_route_limits` (some inert notes called it “validate”; live source is authoritative). It knows actual estimates/output/context before raising. Carry those typed facts without repeating token estimation or changing the limit decision. Preserve the existing additional-tools classifier result and positions. If private error attributes are needed to carry facts through `app/slaif_gateway/api/policy_errors.py`, do not add them to the public error JSON.

`services/responses_gateway.py::_streaming_responses_response` has the nested `_events::_failure` builder. Record the actual failure outcome at that existing boundary, and cancellation facts where feasible, without changing event order, holds, finalization, or cleanup. HTTP 200 alone must never produce a success diagnostic for a failed stream. Use the actual resolved route/policy data already available, not a request-body reconstruction.

## Exact allowed paths

New product files:

- `app/slaif_gateway/schemas/request_diagnostics.py`
- `app/slaif_gateway/services/request_diagnostics.py`
- `app/slaif_gateway/db/repositories/request_diagnostics.py`
- `app/slaif_gateway/api/request_diagnostics.py`
- `app/slaif_gateway/cli/diagnostics.py`
- `migrations/versions/0026_request_diagnostics.py`

Existing product files, limited to this feature:

- `app/slaif_gateway/db/models.py`: append the one model only.
- `app/slaif_gateway/config.py`, `.env.example`: the four settings/validation only.
- `app/slaif_gateway/main.py`: install the observer only.
- `app/slaif_gateway/cli/main.py`: register the CLI group only.
- `app/slaif_gateway/api/errors.py`, `app/slaif_gateway/api/policy_errors.py`, `app/slaif_gateway/api/dependencies.py`, `app/slaif_gateway/api/middleware.py`: private typed facts/provenance and the narrowly needed ID alias protection; preserve wire behavior.
- `app/slaif_gateway/services/responses_request_policy.py`, `app/slaif_gateway/services/responses_gateway.py`: the narrow observation hooks described above; no decision/permission/accounting refactor.
- `app/slaif_gateway/logging.py`: only if needed for the narrow incoming-authentication-alias log binding protection.

New tests: `tests/unit/test_request_diagnostics.py`, `tests/unit/test_cli_diagnostics.py`, `tests/unit/test_request_diagnostics_middleware.py`, `tests/unit/test_alembic_request_diagnostics.py`; `tests/integration/test_request_diagnostics_postgres.py`, `tests/integration/test_request_diagnostics_api_postgres.py`. Keep owned-fixture helpers in these new test files; reuse/copy existing safe patterns, not a new shared fixture framework.

Existing tests: ONLY necessary current-head literal updates in `tests/unit/test_alembic_email_jobs.py`, `tests/unit/test_schema_status.py`, `tests/unit/test_alembic_quota_reservation_accounting_facts.py`, `tests/unit/test_alembic_provider_pricing.py`, `tests/unit/test_alembic_key_prefix_default.py`, `tests/unit/test_alembic_external_tool_fence.py`, `tests/unit/test_alembic_accounting.py`, and `tests/integration/test_gateway_key_prefix_migration_postgres.py`. Preserve all behavioral assertions and the prefix-migration test's existing database-name safety allowlist. If running that integration check locally, create an owned database whose name satisfies the existing guard; never relax it. Existing consumer tests may be RUN unchanged; if another source/test path is demonstrably required, report the exact need before editing.

Docs: `docs/database-schema.md` (one new table, head/count/catalog: 32→33), `docs/configuration.md`, `docs/cli-reference.md`, `docs/cli-field-administration.md`, `docs/observability.md`, `docs/security-model.md`, `docs/verification/2026-10-29-cli-request-diagnostics.md` and `docs/verification/README.md`. Keep the existing honest SLO-foundation limitations. Check accounting/compatibility/forwarding/product contracts; no change to their behavior is authorized. Old OAP reports/orders and all unrelated local/strategic files stay unchanged.

No UI, client/server module/profile changes, provider adapter changes, new dependencies/workflows, replay/ledger/accounting/hold/fence/rate implementation changes, full-capture changes, email/batch/owner features, global event bus, generic logging framework, or 202+ work. Needed extra path → report before editing; do not silently expand.

## Acceptance and focused verification

Demonstrate real CLI lookup through the shared service and real synthetic HTTP/stream failures, not only mocked callback assertions. Use an owned PostgreSQL database for persistence, migrations, retention/cap concurrency, and unchanged admission/accounting evidence. At minimum:

1. Failed/pre-auth requests have no authenticated key UUID or fabricated ledger. Normal successful auth plus later policy rejection has the correct UUID. A read-only capture-probe UUID never becomes normal-auth identity.
2. Endpoint denial, unsupported function tools, context rejection with actual numeric decision facts, replay unavailable/expired fixture, and HTTP-200 unsupported-stream-event cases are recorded and retrievable by CLI. State the real missing/expired distinction limit honestly.
3. Both ID namespaces, repeated client IDs, cross-namespace collision, ambiguity/overflow, not_found, unavailable database/schema, disabled recording, readable retained history while disabled, and absent historical facts work predictably.
4. Full request/prompt/tool/media/secret canaries and known authentication aliases never reach any new row, CLI output, or log path. Include unknown-field names, malformed input, a raw model wildcard suffix, bearer/custom-prefix/cookie/session/proxy secrets, and capture-probe provenance. Capture remains default off and unarmed.
5. Actual concurrent PostgreSQL writers cannot exceed the configured record cap. Expiration, eviction, cleanup, unique diagnostic ID/repeat safety, byte/type limits, migration up/down/single head, and docs/model parity are verified.
6. Compare actual HTTP/SSE outcomes and relevant PostgreSQL reservation/ledger/key/hold state with recording disabled, enabled, and an injected failing/timing-out writer. Preserve cancellation and streaming finalization. Distinguish real PostgreSQL from mocked provider/rate infrastructure and synthetic clients; do not claim a live backend test.

Run the focused new suites; unchanged relevant error/request-ID/capture, Responses policy/stream-failure, and replay consumer checks; narrow migration-head tests; governance/inventory/drift; Ruff, docs checker, diff check. Do not run a complete local matrix without a concrete CI failure or explicit phase gate. Derive per-file counts from JUnit, state failures/errors/skips and overlaps, and credit root versus agent evidence correctly. Final-head CI remains the broad mandatory gate.

## Setup and publication

Use the existing Python 3.12 `/tmp/slaif192-coding-venv`; unset ambient DATABASE_URL/TEST_DATABASE_URL. Only a freshly created unique-owned PostgreSQL 16, fixed Unix Docker socket, loopback binding, tmpfs, identity inspected BEFORE migration, and exact-ID/owner-label cleanup is authorized. No foreign database/container/worktree cleanup, apt/HPC, production DB/SSH/credentials, real provider/model/client/SMTP/Redis calls, deployment, tag, or release. Mock provider/rate services when needed and label the evidence precisely.

Use the same existing right pane `%9`, profile `early-beta`, model/effort/settings unchanged. No helper models/subagents or relaunch. Root owns order/active bytes; agent owns Git execution. Preserve CODEX-SESSIONS.md/codex.sh, ignored settings/catalogs, and other worktrees.

Commit/push this unchanged strategic order and exact active `201-a` with the implementation on the new branch; create ONE PR to main. Document schema/upgrade/enablement/restart/retention/cleanup, all limits and missing-history behavior. Final report includes the literal implementation SHA and `Report publication commit: SELF`, exact paths/tests/layers/limitations, and the required `Documentation updated: <files>` line. Publish a report-only SELF whose first parent is the implementation and whose only diff is the new report; verify it is the unique remote PR head and order/active bytes match BEFORE sending exactly two response bytes OK once. Then launch exactly ONE control waiter. Never merge/auto-merge/self-activate. Root independently reviews source/privacy/security/accounting/docs/checks/reviews, guard-merges, and verifies actual merged-main workflows/timing before 202. No full-goal or release completion claim.
