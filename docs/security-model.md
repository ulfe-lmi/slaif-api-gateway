# Security Model

This document summarizes the implemented security architecture. It is not a
formal certification, compliance audit, or penetration-test report.

## Goals

- Reduce damage from gateway bearer key leakage.
- Keep upstream provider keys isolated from clients.
- Enforce hard quota and account for usage before and after provider calls.
- Avoid storing prompts and completions by default.
- Avoid placing plaintext gateway keys in PostgreSQL, audit rows, logs,
  email-delivery metadata, or Celery/Redis payloads.

## Gateway Key Lifecycle

The gateway generates OpenAI-looking bearer keys with a configurable prefix,
such as `sk-slaif-`. The `public_key_id` portion is non-secret and supports fast
lookup.

The full plaintext key is shown, written, or delivered only during creation or
rotation. PostgreSQL stores an HMAC-SHA-256 digest of the full key using the
configured server-side HMAC secret version. Key verification recomputes the HMAC
for the stored version and compares it without storing plaintext.

`ACTIVE_HMAC_KEY_VERSION` selects the version used for newly generated keys.
Existing keys continue to require the HMAC secret version stored on the key row.
If a key is lost, rotate it; do not resend an old plaintext key.

## Provider Key Isolation

Provider secrets live in environment variables or deployment secrets. The
`provider_configs` table stores provider metadata and environment variable names,
not secret values.

Client `Authorization` headers contain gateway-issued keys and are never
forwarded upstream. Provider adapters construct a new upstream `Authorization`
header from the server-side provider secret and use an outbound header allowlist.

## Quota And Accounting

PostgreSQL is the hard quota source of truth. Redis rate limiting is operational
throttling only.

For supported `/v1/chat/completions` requests, the gateway authenticates the key,
checks policy, estimates input/output/cost, reserves PostgreSQL quota before
forwarding, forwards the request, then finalizes or releases the reservation
after provider response/error handling.

The usage ledger records metadata, token counts, cost, provider/model status,
and safe diagnostics. It does not store prompt text, completion text, uploaded
files, tool payloads, or raw provider bodies by default.

Manual reconciliation exists for expired pending reservations and
provider-completed streaming finalization failures. Provider-completed repair
uses stored safe usage/cost metadata and does not call providers.

## Streaming Security And Accounting

Streaming requests force `stream_options.include_usage=true` upstream so final
usage can be captured. Successful streaming requires final provider usage before
the gateway emits a successful `[DONE]`.

If final usage is missing, the gateway emits a safe stream error, records the
request as incomplete/failed according to current accounting policy, and does not
emit a normal successful `[DONE]`. If final usage was received but finalization
fails after content reached the client, a durable recovery state is left for
operator reconciliation.

Prompt and completion content are not stored by default.

## Redis Rate Limiting

When enabled, Redis enforces request, estimated-token, and active-concurrency
limits. Active concurrency uses request-specific slots with heartbeat refresh
for long streams and TTL cleanup for crash recovery.

`RATE_LIMIT_FAIL_CLOSED` controls Redis failure behavior. When unset, production
fails closed and development/test fails open. Redis remains fast operational
state; it is not the hard quota source of truth.

## Email And Celery

Asynchronous key delivery uses encrypted `one_time_secrets` rows. Celery task
payloads contain IDs only, such as `one_time_secret_id` and `email_delivery_id`.
They never contain plaintext gateway keys.

Plaintext keys may appear transiently inside the email delivery process because
email is the intended one-time delivery channel. They are not stored in
`email_deliveries`, audit rows, logs, PostgreSQL key rows, or Celery/Redis
payloads. Send-now and enqueue CLI modes suppress plaintext key output because
email/Celery is the selected secret delivery channel.

## Redaction And Logging

Structured logging redacts configured/custom gateway key prefixes, bearer keys,
provider keys, cookies, passwords, CSRF/session tokens, token hashes, encrypted
payloads, nonces, and nested sensitive metadata across common key naming styles.

Metrics and logs must not contain real secrets. `/metrics` and `/readyz` should
be internal or allowlisted in production. Production startup warnings make risky
exposure overrides visible but do not replace network controls.

## CLI Safety

Text-mode key create/rotate commands may show the newly generated plaintext key
once for operator workflows. JSON output is secret-safe by default: operators
must explicitly use `--show-plaintext` or `--secret-output-file` when capturing
the one-time secret outside email delivery.

`--secret-output-file` writes to a new file with restrictive `0600`
permissions. Send-now and enqueue email delivery modes reject additional
plaintext destinations by default. Destructive reserved-counter resets require
explicit confirmation.

## Admin Web Sessions And CSRF

The admin web foundation exposes `/admin/login`, `/admin/logout`, a placeholder
`/admin` dashboard, key list/detail pages under `/admin/keys`, read-only owner,
institution, and cohort list/detail pages, and read-only provider, route,
pricing, and FX list/detail pages. The key pages display safe key metadata only:
prefix, public key ID, hint, owner, status, computed validity state, quotas,
counters, allowed policy summaries, and rate-limit policy. Key detail pages
provide CSRF-protected POST actions to suspend, activate, and permanently revoke
gateway keys through the existing key service and audit behavior.
Owner, institution, and cohort pages display safe record metadata and key count
summaries. Catalog pages display safe local provider, route, pricing, and FX
metadata. Provider config pages may display `api_key_env_var` names, but never
provider secret values. Read-only usage, audit, and email delivery pages display
safe activity metadata only. Usage pages do not display prompts, completions, or
raw request/response bodies. Email delivery pages do not display email bodies
because key-delivery email bodies may contain plaintext gateway keys. Audit
metadata is sanitized/redacted before display. These pages do not display
plaintext gateway keys, token hashes, encrypted one-time-secret payloads,
nonces, provider key values, password hashes, admin session tokens, or
prompt/completion content.

Admin passwords are verified with Argon2id password hashes. Successful login
creates a server-side `admin_sessions` row. PostgreSQL stores HMAC-hashed
session and CSRF tokens only; plaintext session tokens are sent only as secure
browser cookies and are not logged or rendered in templates.

Admin session cookies are `HttpOnly`, `SameSite=Lax` by default, and `Secure`
by default in production. Session validation rejects missing, revoked, expired,
or inactive-admin sessions. Logout revokes the server-side session row and
clears the browser cookie.

Login and logout forms use CSRF tokens. Login CSRF tokens are signed and paired
with a temporary cookie. Authenticated form CSRF tokens are HMAC-hashed in the
server-side session row. Admin key, owner, institution, cohort, provider, route,
pricing, FX, usage, audit, and email delivery pages use authenticated GET
routes. Key creation, suspend, activate, revoke, validity-window update, hard
quota limit update, usage-counter reset, and rotation forms require a valid
authenticated session plus the per-session CSRF token. Dashboard key creation
only selects existing owners/cohorts, calls the existing key service, and writes
the service audit row. Dashboard key creation and rotation support explicit
email-delivery modes:

- `none` renders a no-cache result page that shows the newly generated plaintext
  key exactly once.
- `pending` creates a pending `email_deliveries` row linked to the encrypted
  one-time secret and still shows the plaintext key exactly once.
- `send-now` sends through `EmailDeliveryService`, consumes the one-time secret
  only after SMTP success, records delivery status, and suppresses browser
  plaintext display.
- `enqueue` creates a pending delivery row, enqueues the Celery task with IDs
  only, and suppresses browser plaintext display.

Revoke and rotation also require an explicit confirmation field and
dashboard-side audit reason before the key service is called. Validity, hard
quota, usage-counter, and rotation changes call the existing key service and
write audit rows through the same service-layer behavior as the CLI. Dashboard
rotation never displays or resends the old plaintext key, and lost replacement
keys must be rotated again. Dashboard creation and rotation plaintext keys are
not stored in PostgreSQL key rows, audit rows, logs, cookies, server-side
sessions, URLs, email delivery rows, or Celery payloads. The service stores the
key HMAC and encrypted one-time-secret material only. Send-now and enqueue use
email/Celery as the selected secret delivery channel and therefore suppress
browser plaintext display. Celery task payloads contain IDs only, never
plaintext keys, email bodies, encrypted payloads, or nonces. Hard quota
limit updates affect PostgreSQL-backed lifetime cost, token, and request limits;
they do not reset used/reserved counters and are distinct from Redis operational
rate-limit policy. Usage-counter reset does not delete usage ledger rows, and
reserved-counter reset requires a second explicit confirmation because it is an
admin repair action for stale in-flight reservations. These key detail actions
never recover or send old plaintext keys.

## Current Limitations

- Standalone dashboard email resend/retry actions are not implemented yet.
  Owner, institution, cohort, provider,
  routing, pricing, FX, usage, audit, and email-delivery mutation pages are not
  implemented yet.
- Docker/Nginx deployment packaging is not implemented yet.
- Native Anthropic API support is not implemented.
- Responses API and embeddings API are not implemented.
- Scheduled reconciliation/alerting is not implemented yet.
- This project has not completed a formal certification, compliance audit, or
  penetration test.
