# Review Remediation Matrix

This matrix summarizes major findings from the external quality/security-oriented reviews. It is a remediation tracker, not a formal security certification, compliance attestation, or penetration-test report.

Status values are intentionally conservative:

- **Fixed**: implemented and covered by tests or docs in the cited PRs.
- **Addressed**: substantially handled, with possible follow-up hardening still useful.
- **Partially addressed**: improved, but not complete.
- **Planned**: still open future work.
- **Superseded**: finding is no longer current because later design or scope changed.

| Review | Finding | Severity | Status | Fixed / Addressed in PR(s) | Verification | Notes |
|---|---|---:|---|---|---|---|
| 4.0 | `main.py` / route orchestration too large | Medium | Partially addressed | #54, #57, #61, #68 | Unit, integration, and E2E checks around chat orchestration | Chat handling moved into service orchestration and gained coverage, but continued simplification is still useful as features grow. |
| 4.0 | DB transaction around provider call / transaction boundaries | High | Addressed | #45, #46, #54 | PostgreSQL quota/accounting integration tests | Provider calls are outside hard quota row-locking; PostgreSQL remains authoritative for reservation/finalization. |
| 4.0 | DB engine/session lifespan | High | Fixed | #45, #70 | `tests/unit/test_db_lifespan.py`, DB session config tests | Lifespan creates/disposes shared engine/sessionmaker; pool/timeout/pre-ping settings are configurable. |
| 4.0 | `/readyz` realism and schema currentness | High | Fixed | #50, #70 | `tests/unit/test_readyz_schema.py`, `tests/integration/test_readyz_postgres.py` | `/readyz` checks database reachability and Alembic current/head state without running migrations; production details are coarse by default. |
| 4.0 | Endpoint allow-list enforcement | High | Fixed | #54, #57, #59, #60 | `/v1` policy and forwarding tests | Implemented endpoint policy and OpenAI-shaped unsupported-route behavior for the current endpoint set. |
| 4.0 | Provider-config-driven adapters | Medium | Addressed | #54, #57, #67 | Provider adapter and route-resolution tests | OpenAI/OpenRouter adapters use provider config, route metadata, server-side provider key substitution, and documented forwarding contracts. |
| 4.0 | Quota counter invariant checks | High | Fixed | #46 | Unit and PostgreSQL quota tests | Reserved/used counters and underflow guards are tested. |
| 4.0 | High-contention PostgreSQL quota test | High | Fixed | #46, #53 | PostgreSQL-backed integration verification | Concurrency/reservation behavior is covered against PostgreSQL, not only mocks. |
| 4.0, 4.1 | OpenAI request passthrough | High | Fixed | #59, #60 | Chat request passthrough, provider adapter, and E2E tests | Ordinary Chat Completions fields are preserved unless explicitly rejected; unknown ordinary JSON fields are not silently dropped in covered tests. |
| 4.0, 4.1 | `stream_options.include_usage` enforcement | High | Fixed | #59, #60 | OpenAI/OpenRouter streaming adapter tests | Streaming upstream requests force `stream_options.include_usage=true` while preserving existing stream options. |
| 4.1, 4.2 | Streaming completed-without-usage client semantics | High | Fixed | #68 | Unit, integration, and E2E streaming checks | Missing final usage emits a safe stream error and does not emit a misleading successful `[DONE]`. |
| 4.0, 4.1 | Durable provider-completed finalization recovery | Critical | Fixed | #61 | Streaming finalization recovery unit and PostgreSQL tests | Provider-completed streaming requests with final usage create durable recovery state before finalization. |
| 4.1, 4.2 | Provider-completed reconciliation execution | High | Fixed | #65 | Service, CLI, and PostgreSQL reconciliation tests | Operators can list and reconcile provider-completed finalization-failed rows using stored usage/cost metadata. |
| 4.0, 4.1 | Redis active concurrency for long streams | High | Fixed | #62 | Redis integration and streaming rate-limit tests | Active concurrency uses request-ID slots, heartbeat refresh, idempotent release, and conservative TTL cleanup. |
| 4.1 | Redis release/heartbeat failure metrics | Medium | Addressed | #62 | Rate-limit metrics/unit tests | Release and heartbeat failure metrics/logging were added with low-cardinality labels. |
| 4.0, 4.1 | CLI JSON plaintext-key hardening | High | Fixed | #64 | CLI unit and PostgreSQL tests | JSON create/rotate requires `--show-plaintext` or `--secret-output-file`; secret files use `0600`; reserved-counter reset requires confirmation. |
| 4.0, 4.1 | Redaction for custom prefixes and nested metadata | High | Fixed | #63 | Redaction, logging, accounting, and audit tests | Configured/custom prefixes, generic gateway-key fallback, and nested sensitive metadata variants are sanitized. |
| 4.0, 4.1 | Provider diagnostics | Medium | Fixed | #66 | Provider error, provider metrics, and PostgreSQL diagnostics tests | Diagnostics are sanitized, bounded, and stored only as safe metadata. Raw provider bodies are not exposed or stored. |
| 4.0, 4.1, 4.2 | Finalized EUR cost metrics | Medium | Addressed | #66 | Provider metrics tests; verify in GitHub history for exact assertions | Successful accounting finalization records finalized EUR cost metrics. Review 4.2 still recommended direct cost-metric assertion hardening as follow-up. |
| 4.0, 4.1 | OpenRouter-specific edge coverage | Medium | Addressed | #66 | OpenRouter adapter/streaming/E2E tests | Coverage includes error bodies/events, usage chunks, request IDs, model substitution, and gateway/provider key isolation. |
| 4.1, 4.2 | DB pool/timeout/pre-ping settings | Medium | Fixed | #70 | Config and DB session unit tests | Pool size, overflow, timeout, recycle, pre-ping, connect timeout, and optional PostgreSQL statement timeout are configurable. |
| 4.1, 4.2 | Production `/readyz` and `/metrics` exposure controls | Medium | Fixed | #70 | Readyz production-detail and metrics endpoint tests | `/readyz` hides schema revision details in production by default; `/metrics` is denied in production unless explicitly allowed. |
| 4.2 | Documentation contract / provider forwarding contract | Medium | Fixed | #67, #69 | Documentation-only PR checks | Compatibility, provider forwarding, matrix, and documentation-governance docs now define implementation-contract update rules. |
| 4.2 | `n > 1` Chat Completions accounting policy | High | Addressed | This PR | Policy/API/provider/E2E tests | Gateway rejects `n > 1` before rate limiting, routing, pricing, quota reservation, or provider forwarding until multi-choice accounting is implemented. |
| 4.2 | Scheduled reconciliation or alerting | Medium | Planned | Not implemented | Follow-up required | Manual operator repair exists, but background jobs/alerts are intentionally out of scope until Celery/scheduler work. |
| 4.2 | Dashboard pages | Medium | Planned | Not implemented | Not applicable | Admin dashboard is listed as not implemented in README. |
| 4.2 | Email sending / Celery workers | Medium | Addressed | #74, #75 | Unit and PostgreSQL integration tests | Explicit CLI-controlled email delivery and Celery task foundations exist for newly generated/rotated keys. Automatic/dashboard email workflows remain out of scope. |
| 4.2 | Docker deployment files | Medium | Planned | Not implemented | Not applicable | Deployment docs/files are intentionally pending; no Docker deployment files are included by this remediation tracker. |

## Review 5.0 findings

Review 5.0 grades the project as B+ / serious pre-production infrastructure for the implemented scope, but not yet production-release-ready.

| Finding | Severity | Status | Planned / fixed in PR(s) | Verification | Notes |
|---|---:|---|---|---|---|
| `n > 1` Chat Completions accounting ambiguity | P0/P1 | Addressed | Fixed in this PR by rejecting `n > 1` until multi-choice accounting is implemented. | Policy/API/provider/E2E tests. | Multi-choice accounting remains unimplemented; this fix fails closed instead of under-reserving. |
| `/v1/models` empty `allowed_models` policy mismatch | P1 | Addressed | Fixed in this PR by returning an empty OpenAI-shaped model list when `allow_all_models=false` and `allowed_models` is empty. | Model catalog tests, `/v1/models` route tests, route-resolution consistency test, and mocked official-client E2E model-list test. | This aligns catalog visibility with chat authorization without changing route matching or provider forwarding semantics. |
| Admin login brute-force/rate-limit protection | P1 | Addressed | Fixed in this PR by adding DB/audit-backed failed-attempt lockout by normalized email/IP for `/admin/login`. | Admin auth unit/integration tests. | Redis is not required; failed attempts and lockout events are audited, and browser messages remain generic. |
| Production provider-secret validation drift | P1/P2 | Addressed | Fixed in this PR by requiring non-placeholder upstream secrets for enabled production providers, rejecting likely server-side `OPENAI_API_KEY` misuse, and checking enabled DB provider config env-var references in production readiness. | Config, startup warning, provider factory, readiness, and PostgreSQL readiness tests. | Provider-secret isolation is preserved; readiness reports env var names only when details are enabled and never secret values. |
| Admin role semantics unclear | P2 | Open | Planned fix: either document all active admins are full operators for now, or enforce role checks. | Docs/config tests or RBAC tests depending on chosen policy. | Current dashboard actions assume operator-level admin capability. |
| Email delivery exactly-once semantics | P2 | Open | Planned fix: harden SMTP-success/DB-commit failure path with outbox/attempt state or documented operational policy. | Email delivery service tests simulating SMTP success followed by DB failure. | One-time-secret payload design is sound, but delivery outcome atomicity needs clearer handling. |
| `docs/openai-compatibility.md` admin/email status drift | P2 | Open | Planned fix: update the “not implemented” section so it reflects admin/email dashboard workflows now implemented. | Docs diff. | Current main still contains stale wording around automatic/dashboard email workflows; verify exact intended wording before fixing. |
