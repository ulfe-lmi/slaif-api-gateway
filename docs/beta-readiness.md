# RC-Beta Readiness Report

Date: 2026-05-01

Status: RC-beta readiness candidate after verification fixes.

Current `main` baseline after the RC-beta CI/docs PR #120 merge:
`dbc98374c47be4537cc5087bd008a36b76fc8f17`

Recommendation: RC-beta ready for the implemented and documented scope.

This report is not a production certification, compliance attestation, or
penetration-test report. It records a release-candidate beta verification pass
for the current implemented scope.

## Implemented API Scope

- `GET /healthz` and `GET /readyz`.
- Authenticated `GET /v1/models` using local route/provider metadata.
- `POST /v1/chat/completions` non-streaming and SSE streaming through OpenAI
  and OpenRouter adapters.
- OpenAI-shaped errors for unsupported `/v1` routes and policy failures.
- `n` omitted or `n=1` is supported; `n > 1` is rejected before provider
  forwarding, rate limiting, pricing, quota reservation, or ledger mutation.
- Streaming requests force `stream_options.include_usage=true`; missing final
  usage emits a safe stream error and does not emit a misleading success.
- Provider authorization is substituted server-side; client `Authorization`
  headers are not forwarded upstream.

## Implemented Dashboard Scope

- Admin login/logout, server-side sessions, login CSRF, form CSRF, and
  DB/audit-backed login lockout.
- Key list/detail/create, rotation, suspend/activate/revoke, validity updates,
  hard quota updates, usage-counter reset, and explicit create/rotate email
  delivery modes.
- Bulk key CSV/JSON preview and confirmed execution, including `none`,
  `pending`, and `enqueue` modes. Bulk `send-now` remains unsupported and
  rejects before mutation.
- Owner, institution, and cohort list/detail/create/edit metadata forms.
- Provider config, route, pricing, and FX metadata pages, including supported
  import preview/execution workflows.
- Usage and audit read-only pages with audited CSV metadata export controls.
- Email delivery list/detail plus one-time-secret-backed send-now/enqueue
  actions for eligible pending or failed delivery rows.

All admin mutations are POST-only, require an authenticated admin session and
CSRF, and high-risk/mutating workflows require explicit confirmation and/or a
non-empty audit reason according to the action.

## Implemented CLI And Deployment Scope

- Typer CLI commands cover admin bootstrap/reset, institution/cohort/owner
  records, key lifecycle operations, provider/route/pricing/FX metadata,
  usage reporting/export, reconciliation, email testing/pending delivery, and
  database migration helpers.
- Docker Compose packages API, worker, scheduler, PostgreSQL, Redis, and
  Mailpit. Migrations remain explicit operator actions.
- Nginx configuration is present for reverse proxy guidance with streaming-safe
  proxy settings and metrics denied by default.

## Verification Summary

- Unit tests: `1134 passed, 6 warnings`.
- Ruff: passed.
- Alembic heads: single head, `0006_email_delivery_attempt_state`.
- `git diff --check`: passed before edits and rerun for this PR.
- PostgreSQL integration tests: `105 passed, 34 warnings`.
- E2E official OpenAI client tests: `6 passed, 6 warnings`.
- Playwright browser smoke: `1 passed, 1 warning`.
- Docker Compose config: passed.
- Docker build and service smoke: passed using `sudo -n docker`.
- Container migration smoke: `slaif-gateway db upgrade` completed through
  Alembic head.
- Container health/readiness smoke: `/healthz` and `/readyz` returned ok.
- Nginx syntax validation: passed with `nginx:stable nginx -t`.

The RC-beta CI/docs follow-up adds GitHub Actions coverage for unit/lint,
PostgreSQL integration, E2E, Playwright browser smoke, Docker Compose smoke,
Nginx syntax validation, documentation hygiene, CodeQL, and Dependabot.

## Review 5.0 Closure

The Review 5.0 remediation matrix now records every Review 5.0 finding as
addressed or hardened:

- `n > 1` Chat Completions ambiguity: addressed by fail-closed rejection.
- `/v1/models` empty allow-list mismatch: addressed.
- Admin login brute-force/rate-limit protection: addressed.
- Production provider-secret validation drift: addressed.
- Admin role semantics: addressed and documented.
- Email delivery exactly-once semantics: hardened and documented without
  overclaiming mathematically exactly-once delivery.
- `docs/openai-compatibility.md` admin/email drift: addressed.

No Review 5.0 remediation item remains open for the RC-beta scope.

## Security And Safety Notes

- PostgreSQL remains authoritative for hard quota reservation/finalization.
- Redis rate limiting is operational throttling only and is optional/configured.
- Provider calls happen after quota reservation and outside the quota row-lock
  transaction.
- Usage ledger metadata does not store prompts or completions by default.
- Provider keys are referenced by environment variable names and are not stored
  or displayed by dashboard metadata forms.
- One-time plaintext gateway keys are only shown on explicit no-cache
  create/rotate/bulk result pages where documented.
- Bulk enqueue mode queues Celery tasks with IDs only and suppresses browser
  plaintext display.
- CSV exports neutralize formula-looking cells and exclude prompts,
  completions, raw request/response bodies, email bodies, and secret material.

## Known Limitations

- Bulk key synchronous `send-now` execution is not implemented.
- Native Anthropic API is not implemented; Anthropic-family models are supported
  only through OpenRouter's OpenAI-compatible interface when routed that way.
- Responses API is not implemented in RC1. RC2 is planned to focus on limited
  stateless `POST /v1/responses` support with explicit key/template policy,
  allowed tool controls, pricing catalog support, and bounded-overrun cost
  estimates. See `responses-compatibility.md`.
- Embeddings API is not implemented.
- MFA is not implemented.
- Full RBAC is not implemented; every active admin is currently a full operator
  and `superadmin` is metadata/future-proofing.
- Real upstream smoke tests are disabled by default and require explicit
  operator opt-in and real provider credentials.
- External FX refresh workflows are not implemented.
- Owner/institution/cohort delete and anonymization workflows are not
  implemented.
- Arbitrary old plaintext key resend is intentionally not implemented.
- There is no formal security certification, formal penetration test, SOC/ISO
  attestation, or compliance certification.
- Production deployment still requires operator-managed secrets, HTTPS/Nginx
  hardening, backups, monitoring, alert routing, and operational runbooks.

## Non-Goals For This RC-Beta

- No synchronous bulk `send-now`.
- No native Anthropic adapter.
- No Responses, embeddings, files, image, or audio API support in RC1.
- No MFA or full RBAC.
- No production certification or compliance claim.
- No real provider calls or external email during verification.

## Remaining Pre-GA Items

- Add MFA and role-gated permissions if required for the deployment context.
- Add formal security review or penetration testing before production claims.
- Implement Responses API as a separate scoped RC2 project under
  `responses-compatibility.md`; decide separately whether to implement bulk key
  send-now, embeddings, and native provider adapters.
- Build production runbooks for backups, monitoring, alerting, secret rotation,
  and incident response.
- Keep CI green and review dependency/security updates before each tag.

Final verdict: RC-beta ready: yes, for the implemented and documented scope.

Tag-specific release notes for the recommended first RC-beta tag are in
[`releases/v0.1.0-rc.1.md`](releases/v0.1.0-rc.1.md).
