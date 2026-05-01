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
not secret values. Admin provider config forms accept `api_key_env_var` names
only and reject provider-secret-looking values; they never accept, store, or
display provider key values.

In production, enabled built-in OpenAI/OpenRouter providers require configured,
non-placeholder upstream provider secrets. The server treats `OPENAI_API_KEY` as
a client-facing gateway-key variable, not as the upstream OpenAI provider secret;
likely provider-key values in `OPENAI_API_KEY` fail configuration validation
with a safe message that names `OPENAI_UPSTREAM_API_KEY` but never logs the
value. Production `/readyz` checks enabled DB provider config env-var references
and reports only env var names, never secret values.

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

Celery/Celery Beat can be configured to inspect reconciliation backlog
periodically. Scheduled reconciliation is disabled by default and scheduled
mutation remains opt-in: expired-reservation and provider-completed repair tasks
only execute when the matching auto-execute setting is enabled and dry-run mode
is disabled. Scheduled tasks call the same reconciliation service used by the
CLI, never call providers, and return/log only low-cardinality counts plus safe
IDs and statuses. They do not include plaintext gateway keys, token hashes,
encrypted payloads, nonces, provider keys, prompts, completions, or email bodies
in task payloads/results.

Optional reconciliation alert webhooks are disabled by default and are emitted
only from backlog inspection. Alerting is for operator visibility, not repair:
it does not mutate quota/accounting, does not call providers, and does not send
email. Payloads contain counts by default; when explicitly enabled they may also
include safe reservation or usage-ledger IDs. Webhook URLs may contain bearer
tokens or routing secrets and must be treated as secrets; logs and task results
must not include the full webhook URL.

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

Email delivery is not mathematically exactly-once because SMTP acceptance and
database finalization are separate systems. The gateway fails closed around that
boundary: before SMTP it persists a `sending` state, SMTP failure before
acceptance records a retryable `failed` status with the one-time secret still
pending, and SMTP success finalizes by consuming the one-time secret and marking
the delivery `sent`. If SMTP may have accepted the message but database
finalization fails, the row is left or marked `ambiguous`; automatic retry is
blocked and operators should rotate the key if receipt cannot be confirmed.

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
`/admin` dashboard, key list/detail pages under `/admin/keys`, owner,
institution, and cohort list/detail/create/edit pages, provider config pages, model route
pages, pricing pages, and FX list/detail/create/edit pages. The key pages
display safe key metadata only:
prefix, public key ID, hint, owner, status, computed validity state, quotas,
counters, allowed policy summaries, and rate-limit policy. Key detail pages
provide CSRF-protected POST actions to suspend, activate, and permanently revoke
gateway keys through the existing key service and audit behavior.
Owner, institution, and cohort pages display safe record metadata and key count
summaries and provide CSRF-protected create/edit forms for schema-backed record
metadata. These forms require a non-empty audit reason, write safe audit rows
through service-layer logic, reject secret-looking notes/metadata, do not create
keys inline, and do not modify historical usage ledger rows. Delete and
anonymization workflows are intentionally not implemented yet because
owner/institution/cohort records can be linked to historical usage snapshots.
Cohorts are standalone in the current schema; owners can reference institutions
but do not link directly to cohorts. Provider config pages display safe local metadata and provide
CSRF-protected create, edit, enable, and disable forms for provider metadata
only. They may display `api_key_env_var` names, but never provider secret values,
and state changes write safe audit rows through the provider config service.
Model route pages provide CSRF-protected create, edit, enable, and disable forms
for local routing metadata only. Route forms validate exact/prefix/glob match
types, provider config references, priority values, endpoints, and safe metadata;
they may display provider env var names for operator selection, but never
provider secret values. Route state changes write safe audit rows through the
model route service and do not change provider adapter behavior. Pricing pages
provide CSRF-protected create, edit, enable, and disable forms for local pricing
metadata only. Pricing forms parse decimal strings directly, validate
currencies, validity windows, provider references, and safe metadata, and write
safe audit rows through the pricing rule service. Pricing changes may affect
future quota reservation and accounting, but the dashboard does not change the
runtime pricing calculation semantics and does not accept provider secret
values. FX catalog pages provide CSRF-protected create and edit forms for local
FX metadata only. FX forms parse Decimal rates from strings, validate currency
pairs, positive rates, and validity windows, and write safe audit rows through
the FX rate service. FX import preview validates CSV/JSON without mutation, and
confirmed FX import execution re-parses and re-validates server-side, requires
explicit confirmation plus an audit reason, and creates rows only when every row
is a valid supported create. FX changes may affect future EUR conversion, quota
reservation, and accounting, but the dashboard does not change runtime FX lookup
semantics and does not call external FX services. The current FX schema has no
enabled state; active status is controlled by validity windows. Read-only usage, audit, and email delivery pages display
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

Admin login is protected by DB/audit-backed failed-attempt rate limiting. The
gateway counts recent failed `/admin/login` attempts by normalized email and
client IP, records failed attempts and temporary lockout events in `audit_log`,
and blocks password verification while the lockout is active. Failure and
lockout messages are generic, do not reveal whether an account exists, and do
not expose exact attempt counts. Redis is not required for this admin control.
Plaintext passwords are never stored, logged, or written to audit metadata.

Current v1 admin authorization treats all active admin users as full operators.
`role=admin` and `role=superadmin` can use the implemented dashboard/operator
actions; `superadmin` is metadata/future-proofing rather than an enforced RBAC
boundary. Inactive admin accounts cannot log in, and revoked or expired
server-side sessions cannot access admin routes. Operators should treat every
active admin account as highly privileged. Future RBAC, superadmin-only
permissions, and MFA may be added later, but they are not implemented in the
current admin surface.

Login and logout forms use CSRF tokens. Login CSRF tokens are signed and paired
with a temporary cookie. Authenticated form CSRF tokens are HMAC-hashed in the
server-side session row. Admin key, owner, institution, cohort, provider, route,
pricing, FX, usage, audit, and email delivery pages use authenticated GET
routes. Key creation, suspend, activate, revoke, validity-window update, hard
quota limit update, usage-counter reset, rotation, owner/institution/cohort
metadata changes, provider config, route, pricing, and FX metadata mutation forms require a valid authenticated session
plus the per-session CSRF token. The dashboard route import preview form
requires CSRF, validates CSV/JSON rows, verifies provider references against
provider config rows, rejects unknown fields and secret-looking
capabilities/metadata/source values, and does not write `model_routes`, audit
rows, or uploaded content. Route import execution also requires CSRF, explicit
confirmation, and a non-empty audit reason. It re-parses and re-validates the
submitted upload or pasted content server-side, does not trust preview HTML or
client-side classification, and writes model route rows only after all rows
validate as supported create rows. Invalid, duplicate, conflict, or
update-classified rows block the entire import with no mutation. Successful
creates are audited through the route service. Route import preview/execution
does not call providers, does not store raw uploaded content, and changes future
model resolution only after confirmed local route rows are created. The
dashboard pricing import preview form also
requires CSRF, validates CSV/JSON rows with Decimal money values parsed from
strings, rejects unknown fields and secret-looking source/metadata values, and
does not write `pricing_rules`, audit rows, or uploaded content. Dashboard
pricing import execution requires CSRF, explicit confirmation, and a non-empty
audit reason. It re-parses and re-validates the submitted upload or pasted
content server-side, does not trust preview HTML or client-side classification,
and writes pricing rows only after all rows validate as supported create rows.
Invalid, duplicate, overlapping, disabled, or update-classified rows block the
entire import with no mutation. Successful creates are audited through the
pricing service. Neither preview nor execution calls external pricing APIs or
providers, stores raw uploaded content, or accepts provider keys. The dashboard
FX import preview form requires CSRF, validates CSV/JSON rows with Decimal
rates parsed from strings, rejects unknown fields, invalid currency pairs,
same-currency pairs, invalid validity windows, non-positive rates, and
secret-looking source/note/metadata values, and does not write `fx_rates`, audit
rows, or uploaded content. Dashboard FX import execution requires CSRF, explicit
confirmation, and a non-empty audit reason. It re-parses and re-validates the
submitted upload or pasted content server-side, does not trust preview HTML or
client-side classification, and writes FX rows only after all rows validate as
supported create rows. Invalid, duplicate, conflict, or update-classified rows
block the entire import with no mutation. Successful creates are audited through
the FX service. FX import preview/execution does not call external FX APIs or
providers, does not accept provider keys, does not store raw uploaded content,
and changes future EUR conversion only after confirmed local FX rows are
created. Dashboard bulk key import preview requires an authenticated admin
session and CSRF token. It validates CSV/JSON key-creation rows, owner
references, optional cohort references, validity windows, hard quota fields,
allowlist policy fields, Redis rate-limit policy fields, email delivery modes,
upload size, row count, and secret-looking input. It is preview-only: no
plaintext keys are generated, no `gateway_keys`, `one_time_secrets`,
`email_deliveries`, or audit rows are written, no Celery tasks are enqueued, no
email is sent, and no providers are called. Dashboard usage and audit CSV exports require an authenticated admin
session, CSRF token, explicit confirmation, and a non-empty audit reason. Export
generation writes a safe audit row, respects the current dashboard filters,
enforces configured row limits, and neutralizes CSV formula injection. Exports
contain metadata only: prompts, completions, raw request/response bodies, email
bodies, plaintext gateway keys, provider key values, token hashes, encrypted
payloads, nonces, password hashes, session tokens, SMTP passwords, and HMAC
secrets are excluded or redacted. Export generation does not mutate usage or
audit rows and does not call providers or external services. Dashboard key creation
only selects existing owners/cohorts, calls the existing key service, and writes
the service audit row. Dashboard key creation and rotation support explicit
email-delivery modes:

- `none` renders a no-cache result page that shows the newly generated plaintext
  key exactly once.
- `pending` creates a pending `email_deliveries` row linked to the encrypted
  one-time secret and still shows the plaintext key exactly once.
- `send-now` sends through `EmailDeliveryService`, records `sending` before
  SMTP, consumes the one-time secret only after SMTP success, records delivery
  status, and suppresses browser plaintext display. Possible SMTP-accepted
  finalization failures become `ambiguous` and are not retried automatically.
- `enqueue` creates a pending delivery row, enqueues the Celery task with IDs
  only, and suppresses browser plaintext display.

Existing pending or failed key email deliveries can be sent now or enqueued from
the email delivery detail page only while the linked one-time secret is present,
pending, unexpired, unconsumed, and valid for key email delivery. These actions
require CSRF plus explicit confirmation, never accept plaintext key input, never
display plaintext keys in the browser, and use the same `EmailDeliveryService`
or ID-only Celery task path as the CLI. Consumed, expired, missing, or
wrong-purpose one-time secrets fail safely; the operator must rotate the key and
create a new delivery instead of resending an old plaintext key. Deliveries in
`sending` or `ambiguous` state also fail closed; operators should confirm receipt
out of band or rotate the key.

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

- Arbitrary old-key dashboard email resend actions are not implemented.
  Bulk key creation execution is not implemented; the dashboard currently
  provides preview/dry-run validation only.
  Standalone email-delivery mutation pages beyond the existing
  one-time-secret-backed send-now/enqueue actions are not implemented.
  Owner, institution, and cohort delete/anonymization workflows are not
  implemented yet. Usage and audit pages remain metadata-only except for
  audited CSV export controls.
  external FX refresh workflows are future work.
- Docker Compose packaging and an optional Nginx example are included for
  local/development service layout and reverse-proxy guidance. They are not a
  production certification; production operators must replace all secrets, run
  migrations explicitly, use HTTPS, and keep `/readyz` and `/metrics` internal
  or allowlisted.
- Native Anthropic API support is not implemented.
- Responses API and embeddings API are not implemented.
- Slack/PagerDuty-specific alert integrations are not implemented yet.
- This project has not completed a formal certification, compliance audit, or
  penetration test.
