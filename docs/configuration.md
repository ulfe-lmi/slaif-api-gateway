# Configuration

This gateway is configured with environment variables. Secrets should come from
environment variables, a deployment secret manager, or Docker secrets. The root
`.env.example` file is a safe Docker Compose-oriented template only; it must not
contain real credentials.

Migrations are explicit operator actions. The application and `/readyz` do not
run migrations on startup.

## Required Production Secrets

Production requires strong, non-placeholder values for:

- `TOKEN_HMAC_SECRET_V1`, or the version matching `ACTIVE_HMAC_KEY_VERSION`
- `ADMIN_SESSION_SECRET`
- `ONE_TIME_SECRET_ENCRYPTION_KEY`
- `OPENAI_UPSTREAM_API_KEY` and/or `OPENROUTER_API_KEY` when those providers are enabled
- `SMTP_PASSWORD` when the configured SMTP server requires authentication

`ONE_TIME_SECRET_ENCRYPTION_KEY` must be base64url-encoded 32-byte key material.
Rotate any provider or SMTP secret that is accidentally committed, logged, or
shared.

## Client Vs Upstream Provider Keys

Training users configure the standard OpenAI client variables:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

`OPENAI_API_KEY` is a gateway-issued key from this service. It is not the real
OpenAI provider secret.

The server uses `OPENAI_UPSTREAM_API_KEY` for the actual OpenAI provider key.
Do not set the gateway's upstream provider secret as `OPENAI_API_KEY` in the
server environment. OpenRouter uses `OPENROUTER_API_KEY`.

When `APP_ENV=production`, enabled built-in providers require configured
non-placeholder upstream secrets. `OPENAI_API_KEY` is validated as a client-side
variable name boundary: values that look like real upstream provider keys fail
startup with a safe error directing operators to `OPENAI_UPSTREAM_API_KEY`.
Gateway-looking or placeholder `OPENAI_API_KEY` values are not copied into
provider settings.

## App And Gateway Keys

- `APP_ENV` controls environment-sensitive defaults such as production readiness
  details and metrics protection.
- `APP_BASE_URL` is the local app base URL.
- `PUBLIC_BASE_URL` is the user-facing OpenAI-compatible base URL and should
  usually include `/v1`.
- `GATEWAY_KEY_PREFIX` controls newly generated gateway key prefixes.
- `GATEWAY_KEY_ACCEPTED_PREFIXES` controls accepted prefixes and must include the
  active generation prefix.
- `ACTIVE_HMAC_KEY_VERSION` selects which versioned HMAC secret new keys use.
- `TOKEN_HMAC_SECRET_V1` stores the server-side HMAC pepper for version 1.
- `TOKEN_HMAC_SECRET` is a legacy/non-production fallback for version 1 only.

## Database Configuration

- `DATABASE_URL` is the SQLAlchemy async PostgreSQL URL.
- `DATABASE_POOL_SIZE`, `DATABASE_MAX_OVERFLOW`,
  `DATABASE_POOL_TIMEOUT_SECONDS`, and `DATABASE_POOL_RECYCLE_SECONDS` configure
  SQLAlchemy async engine pooling.
- `DATABASE_POOL_PRE_PING` is enabled by default so stale pooled connections are
  checked before use.
- `DATABASE_CONNECT_TIMEOUT_SECONDS` is passed to asyncpg connection setup.
- `DATABASE_STATEMENT_TIMEOUT_MS` is optional; when set, each asyncpg connection
  receives a PostgreSQL `statement_timeout` server setting.

CLI DB commands and service workflows create explicit settings/sessionmaker
instances. Engines are not created at import time.

The checked-in `.env.example` uses the Docker Compose hostname `postgres` inside
containers and publishes the container's PostgreSQL port on host port `15432` by
default through `POSTGRES_HOST_PORT`. For host-local development outside Compose,
use a localhost URL such as
`postgresql+asyncpg://slaif:slaif@localhost:15432/slaif_gateway`, or set
`POSTGRES_HOST_PORT` to match your local port plan.

## Redis And Rate Limiting

Redis is used for operational throttling and Celery broker state. PostgreSQL
remains the hard quota and accounting source of truth.

- `REDIS_URL` configures Redis access.
- `ENABLE_REDIS_RATE_LIMITS` enables request, estimated-token, and concurrency
  throttles for supported `/v1` traffic.
- `REDIS_CONNECT_TIMEOUT_SECONDS` and `REDIS_SOCKET_TIMEOUT_SECONDS` bound Redis
  operations.
- `DEFAULT_RATE_LIMIT_REQUESTS_PER_MINUTE`,
  `DEFAULT_RATE_LIMIT_TOKENS_PER_MINUTE`, and
  `DEFAULT_RATE_LIMIT_CONCURRENT_REQUESTS` provide global defaults when key
  metadata does not override them.
- `RATE_LIMIT_FAIL_CLOSED` controls Redis failure behavior. When unset,
  production fails closed and development/test fails open.
- `RATE_LIMIT_CONCURRENCY_TTL_SECONDS`,
  `RATE_LIMIT_CONCURRENCY_HEARTBEAT_SECONDS`, and
  `RATE_LIMIT_CONCURRENCY_TTL_GRACE_SECONDS` control active concurrency slot
  cleanup and stream heartbeats.

The checked-in `.env.example` uses the Docker Compose hostname `redis` inside
containers and publishes the container's Redis port on host port `16379` by
default through `REDIS_HOST_PORT`. For host-local development outside Compose,
use a localhost URL such as `redis://localhost:16379/0`, or set
`REDIS_HOST_PORT` to match your local port plan.

## Provider Configuration

- `OPENAI_UPSTREAM_API_KEY` supplies the OpenAI provider key.
- `OPENROUTER_API_KEY` supplies the OpenRouter provider key.
- `ENABLE_OPENAI_PROVIDER` and `ENABLE_OPENROUTER_PROVIDER` toggle provider
  availability at configuration level.

In production, an enabled built-in provider cannot start with a missing,
placeholder, whitespace-containing, or implausibly short provider secret.
Validation messages name only the environment variable, never the configured
value.

The `provider_configs` table stores provider metadata and environment variable
names such as `OPENAI_UPSTREAM_API_KEY`; it does not store provider secret
values. Admin dashboard provider config forms create, edit, enable, and disable
metadata rows by referencing environment variable names only; they do not accept
actual provider key values. Model routes, pricing, and FX rates are configured
through CLI/database metadata and the implemented admin metadata forms; those
forms do not accept provider key values or call upstream providers.

## Request Caps

- `DEFAULT_MAX_OUTPUT_TOKENS` is injected when a supported request omits output
  token controls.
- `HARD_MAX_OUTPUT_TOKENS` rejects requests above the configured maximum output.
- `HARD_MAX_INPUT_TOKENS` rejects requests whose estimated input is too large.

These caps protect hard quota reservation by bounding worst-case usage before
upstream forwarding.

## Metrics, Readiness, And Logging

- `/healthz` is process liveness and can be public-ish.
- `/readyz` checks database/schema readiness and Redis readiness only when
  Redis-backed features are enabled. In production it also checks enabled
  provider config rows for present `api_key_env_var` names and returns
  `provider_secrets=missing` with HTTP 503 when any referenced env var is absent.
  Keep it internal or allowlisted in production.
- `/metrics` exposes Prometheus metrics. Keep it internal or allowlisted in
  production.
- `ENABLE_METRICS=false` disables metrics.
- `METRICS_REQUIRE_AUTH`, `METRICS_PUBLIC_IN_PRODUCTION`, and
  `METRICS_ALLOWED_IPS` control production metrics exposure.
- `READYZ_INCLUDE_DETAILS` controls whether exact readiness details such as
  Alembic revisions and missing provider-secret env var names are included.
- `REQUEST_ID_HEADER`, `LOG_LEVEL`, and `STRUCTURED_LOGS` control request IDs
  and logging output.

Production startup logs warn when risky explicit overrides make `/metrics`
public or `/readyz` more detailed than the safe default. These warnings are not a
substitute for internal networking, reverse proxy allowlists, or an admin/auth
layer.

Structured logs redact gateway keys, provider keys, passwords, cookies, session
tokens, token hashes, encrypted payloads, nonces, and other sensitive fields.

## Admin Web

- `ENABLE_ADMIN_DASHBOARD` enables the server-rendered admin web foundation.
- `ADMIN_SESSION_SECRET` signs/HMACs admin session and CSRF tokens.
- `ADMIN_SESSION_COOKIE_NAME` controls the browser session cookie name.
- `ADMIN_SESSION_COOKIE_SECURE` can override cookie `Secure`; when unset it is
  enabled in production and disabled in development/test.
- `ADMIN_SESSION_COOKIE_HTTPONLY` defaults to true.
- `ADMIN_SESSION_COOKIE_SAMESITE` defaults to `lax`.
- `ADMIN_SESSION_TTL_SECONDS` controls server-side admin session lifetime.
- `ADMIN_LOGIN_CSRF_COOKIE_NAME` controls the temporary login CSRF cookie name.
- `ADMIN_CSRF_TTL_SECONDS` controls login CSRF token lifetime.
- `ADMIN_LOGIN_RATE_LIMIT_ENABLED` controls DB/audit-backed failed-attempt
  lockout for `/admin/login`.
- `ADMIN_LOGIN_MAX_FAILED_ATTEMPTS` defaults to `5`.
- `ADMIN_LOGIN_WINDOW_SECONDS` defaults to `900`.
- `ADMIN_LOGIN_LOCKOUT_SECONDS` defaults to `900`.

The current web surface includes `/admin/login`, `/admin/logout`, a placeholder
`/admin` dashboard, key list/detail pages under `/admin/keys`, owner,
institution, and cohort list/detail/create/edit pages, provider config list/detail/create/edit
pages under `/admin/providers`, model route list/detail/create/edit pages under
`/admin/routes`, pricing list/detail/create/edit pages under `/admin/pricing`,
FX list/detail/create/edit pages under `/admin/fx`, and read-only usage, audit,
and email delivery list/detail pages. The key pages
show safe metadata only: public key ID, prefix, hint, owner, status, validity,
quota counters, policy summaries, and rate-limit policy. `/admin/keys/create`
creates one key for an existing owner/cohort. Key creation and key rotation
support explicit email-delivery modes: `none`, `pending`, `send-now`, and
`enqueue`. `none` renders a no-cache result page that shows the plaintext
gateway key exactly once. `pending` creates a pending `email_deliveries` row
linked to the encrypted one-time secret and still shows the plaintext once.
`send-now` sends through the configured SMTP delivery service and suppresses
browser plaintext display. `enqueue` queues the Celery key delivery task with IDs
only and suppresses browser plaintext display. Existing pending/failed key email
deliveries can be sent now or enqueued from the email delivery detail page only
when a valid unconsumed one-time secret is still available. Those actions require
CSRF plus explicit confirmation, never accept plaintext key input, and enqueue
IDs only. Email delivery persists an in-progress state before SMTP. SMTP failure
before acceptance leaves the secret retryable, but possible SMTP acceptance
followed by database finalization failure is marked `ambiguous` and is not
automatically retried; rotate the key if receipt cannot be confirmed. Key detail pages include
CSRF-protected POST actions to suspend, activate, and permanently revoke keys,
update validity windows, update PostgreSQL-backed hard quota limits, reset usage
counters, and rotate keys through the existing key service and audit behavior.
Usage reset preserves usage ledger rows; reserved-counter reset requires an
additional admin repair confirmation. Hard quota limit updates are distinct from
Redis operational rate-limit policy. Owner, institution, and
cohort pages show safe record metadata and key count summaries, and their
create/edit forms require CSRF plus a non-empty audit reason. Institution forms
manage only `name`, `country`, and `notes`; cohort forms manage only `name`,
`description`, `starts_at`, and `ends_at`; owner forms manage only
`name`, `surname`, `email`, optional `institution_id`, `external_id`, `notes`,
and `is_active`. Cohorts are standalone in the current schema and are not linked
directly to institutions; owners can reference institutions but not cohorts.
The forms reject secret-looking notes/metadata, write safe audit rows through
service-layer logic, do not create keys inline, and do not modify historical
usage snapshots. Provider pages
allow CSRF-protected metadata create/edit/enable/disable actions and may show
`api_key_env_var` names, but never provider key values. Route, pricing, and FX
catalog pages no longer share the same mutation status: model route pages allow
CSRF-protected create/edit/enable/disable actions for local route rows, pricing
pages allow CSRF-protected create/edit/enable/disable actions for local pricing
rows, and FX pages allow CSRF-protected create/edit actions for local FX rows.
Route rows affect future `/v1` model
resolution through the existing resolver; pricing rows affect future local cost
estimates, quota reservation, and accounting through the existing pricing
service. FX rows affect future local EUR conversion through the existing FX
lookup path, and unknown FX conversion still fails closed for cost-limited keys.
The current FX schema has no enabled state; validity windows control whether an
FX row is active. Route and pricing forms reference provider config rows and env
var names but never provider key values. FX forms do not accept provider key
values and do not call external FX APIs. The FX import preview page validates
CSV/JSON FX metadata without writing rows; confirmed FX import execution
re-validates server-side, requires explicit confirmation plus an audit reason,
and creates rows only after every row validates. Usage and audit pages include
CSRF-protected CSV metadata exports for the current filters. Exports require
explicit confirmation and a non-empty audit reason, write safe export audit rows,
enforce configured row caps, and mitigate CSV formula injection. Exported usage
and audit CSVs exclude prompts, completions, raw request/response bodies, email
bodies, plaintext key material, token hashes, one-time-secret material, provider
key values, password hashes, and session tokens. Usage, audit, and email
delivery pages show safe local metadata only and do not call providers or
external services.

Arbitrary old-key dashboard email resend actions, bulk key creation forms,
external FX refresh workflows, standalone
email-delivery mutation pages beyond the existing send-now/enqueue actions,
owner/institution/cohort delete or anonymization workflows, and usage/audit
dashboard mutation workflows beyond audited CSV exports are not implemented yet. Admin
sessions are stored server-side in PostgreSQL with only
HMAC-hashed session and CSRF tokens. State-changing admin forms use CSRF
protection. Failed admin login attempts and temporary lockout events are tracked
through PostgreSQL audit rows by normalized email and client IP; Redis is not
required for this admin protection. Login failure and lockout messages remain
generic and do not reveal whether an account exists or how many attempts remain.

Current v1 admin role semantics are intentionally simple: every active admin
user is a full operator. The `admin_users.role` field, including `admin` and
`superadmin`, is metadata/future-proofing and is not currently an authorization
boundary for dashboard or admin CLI actions. Inactive admin accounts cannot log
in, and revoked or expired admin sessions cannot access admin routes. Operators
should protect every active admin account as highly privileged until future RBAC
or MFA hardening is implemented and documented.

## Email, Celery, And SMTP

- `ENABLE_EMAIL_DELIVERY` enables SMTP key delivery workflows.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`,
  `SMTP_USE_TLS`, `SMTP_STARTTLS`, and `SMTP_TIMEOUT_SECONDS` configure SMTP.
- `EMAIL_KEY_SECRET_MAX_AGE_SECONDS` controls encrypted one-time key delivery
  secret lifetime.
- `CELERY_BROKER_URL` configures the Celery broker; when unset, Celery can use
  `REDIS_URL`.
- `CELERY_RESULT_BACKEND` is optional and can remain empty.

Use Mailpit or another fake/local SMTP service for development and tests. Celery
task payloads contain IDs only, never plaintext gateway keys. Lost keys cannot
be resent; rotate and send a replacement key. In-progress or ambiguous delivery
rows are not retried automatically, preventing duplicate key emails after
possible SMTP acceptance.

The checked-in `.env.example` uses the Docker Compose hostname `mailpit` and
port `1025`. From the host, the Compose Mailpit SMTP port is published as
`localhost:1025` and the web UI is available at `http://localhost:8025` by
default. Override `MAILPIT_SMTP_HOST_PORT` or `MAILPIT_WEB_HOST_PORT` if those
ports are already in use.

## Scheduled Reconciliation

Scheduled reconciliation is a Celery/Celery Beat foundation for existing
operator reconciliation workflows:

- `ENABLE_SCHEDULED_RECONCILIATION=false` disables all Beat entries by default.
- `RECONCILIATION_DRY_RUN=true` keeps scheduled reconciliation in reporting mode
  unless explicitly changed.
- `RECONCILIATION_INTERVAL_SECONDS` controls the Beat interval when scheduling
  is enabled.
- `RECONCILIATION_EXPIRED_RESERVATION_LIMIT` and
  `RECONCILIATION_PROVIDER_COMPLETED_LIMIT` cap batch size.
- `RECONCILIATION_EXPIRED_RESERVATION_OLDER_THAN_SECONDS` and
  `RECONCILIATION_PROVIDER_COMPLETED_OLDER_THAN_SECONDS` can ignore very recent
  candidates.
- `RECONCILIATION_AUTO_EXECUTE_EXPIRED_RESERVATIONS=false` and
  `RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=false` keep mutation disabled
  by default.
- `ENABLE_RECONCILIATION_ALERTS=false` disables external alert delivery by
  default.
- `RECONCILIATION_ALERT_WEBHOOK_URL` configures an optional generic JSON
  webhook. Treat this URL as a secret if it contains tokens. When alerts are
  enabled, the URL must use `http` or `https`; production deployments should use
  `https`.
- `RECONCILIATION_ALERT_WEBHOOK_TIMEOUT_SECONDS=10` bounds the outbound webhook
  request.
- `RECONCILIATION_ALERT_MIN_EXPIRED_RESERVATIONS=1` and
  `RECONCILIATION_ALERT_MIN_PROVIDER_COMPLETED=1` set the backlog thresholds for
  sending an alert.
- `RECONCILIATION_ALERT_INCLUDE_IDS=false` keeps alert payloads counts-only by
  default. When enabled, payloads include only safe reservation/usage-ledger IDs,
  never keys, provider secrets, prompts, completions, encrypted payloads, nonces,
  or email bodies.
- `PRICING_IMPORT_MAX_BYTES=1048576` caps dashboard pricing import preview and
  execution uploads/pasted content.
- `PRICING_IMPORT_MAX_ROWS=1000` caps dashboard pricing import preview and
  execution row counts.
- `ROUTE_IMPORT_MAX_BYTES=1048576` caps dashboard route import preview and
  execution uploads/pasted content.
- `ROUTE_IMPORT_MAX_ROWS=1000` caps dashboard route import preview and
  execution row counts.
- `FX_IMPORT_MAX_BYTES=1048576` caps dashboard FX import preview and
  execution uploads/pasted content.
- `FX_IMPORT_MAX_ROWS=1000` caps dashboard FX import preview and execution row
  counts.
- `KEY_IMPORT_MAX_BYTES=1048576` caps dashboard bulk key import preview and
  execution uploads/pasted content.
- `KEY_IMPORT_MAX_ROWS=1000` caps dashboard bulk key import preview and
  execution row counts.

With only `ENABLE_SCHEDULED_RECONCILIATION=true`, Celery Beat schedules backlog
inspection/reporting. Automatic repair of expired pending reservations or
provider-completed finalization-failed rows requires the matching auto-execute
flag and `RECONCILIATION_DRY_RUN=false`. The scheduled tasks reuse
`ReservationReconciliationService`, do not call providers, and do not expose
plaintext gateway keys, provider keys, token hashes, encrypted payloads, nonces,
prompts, completions, or email bodies in task payloads/results. Manual CLI
reconciliation remains available and is still the operator review path for
unexpected accounting failures.

Dashboard pricing import preview is CSRF-protected and dry-run only. It accepts
CSV or JSON content, validates every row, parses money values from strings, and
rejects unknown fields or secret-looking source/metadata values. It does not
write `pricing_rules`, does not create audit rows, and does not call external
pricing or provider APIs.

Dashboard bulk key import preview is CSRF-protected and dry-run only. It accepts
CSV or JSON key-creation rows and validates owner references, optional cohort
references, validity windows, hard quota values, allowlist policy fields, Redis
rate-limit policy fields, email delivery modes, upload size, and row count. It
rejects unknown fields, gateway-key-looking input, provider-key-looking input,
and secret-looking notes/metadata/policy values. Preview does not generate
plaintext keys, does not write `gateway_keys`, `one_time_secrets`,
`email_deliveries`, or audit rows, does not enqueue Celery tasks, does not send
email, and does not call providers. Dashboard bulk key import execution uses the
same parser and validation rules, requires CSRF, explicit import confirmation,
one-time plaintext display confirmation, and a non-empty audit reason, and only
creates keys after all rows validate. Execution supports `none` and `pending`
email modes. `send-now` and `enqueue` remain future work for bulk execution.
Plaintext keys are shown once on a no-cache result page for supported modes and
are not stored in PostgreSQL, audit rows, cookies, sessions, URLs, email
delivery rows, logs, or Celery payloads.

Dashboard pricing import execution is also CSRF-protected and uses the same
parser/validation rules as preview. Execution requires explicit confirmation
and a non-empty audit reason, then re-parses the submitted upload or pasted
content server-side instead of trusting preview HTML or client-side
classification. The current dashboard execution workflow is all-or-nothing and
create-only: if any row is invalid, duplicated, overlapping, disabled, or would
require an update/replace decision, no rows are written. Successful creates go
through the pricing service and write safe audit rows.

Dashboard FX import preview is CSRF-protected and dry-run only. It accepts CSV
or JSON content, validates every row, parses rate values from Decimal strings,
normalizes three-letter currency pairs, and rejects unknown fields, same-currency
pairs, invalid validity windows, non-positive rates, and secret-looking
source/note/metadata values. It does not write `fx_rates`, does not create audit
rows, does not call external FX APIs or providers, and does not change FX lookup
runtime behavior.

Dashboard FX import execution is also CSRF-protected and uses the same
parser/validation rules as preview. Execution requires explicit confirmation
and a non-empty audit reason, then re-parses the submitted upload or pasted
content server-side instead of trusting preview HTML or client-side
classification. The current dashboard execution workflow is all-or-nothing and
create-only: if any row is invalid, duplicated, conflicting, or would require an
update/replace decision, no rows are written. Successful creates go through the
FX service and write safe audit rows. Confirmed FX imports affect future EUR
conversion through the existing FX lookup path.

Dashboard route import preview is CSRF-protected and dry-run only. It accepts
CSV or JSON content, validates every row, verifies provider references against
provider config rows, and rejects unknown fields, invalid match types, invalid
endpoints, negative priorities, and secret-looking capabilities/metadata/source
values. It does not write `model_routes`, does not create audit rows, does not
call providers, and does not change route resolution runtime behavior.

Dashboard route import execution is also CSRF-protected and uses the same
parser/validation rules as preview. Execution requires explicit confirmation
and a non-empty audit reason, then re-parses the submitted upload or pasted
content server-side instead of trusting preview HTML or client-side
classification. The current dashboard execution workflow is all-or-nothing and
create-only: if any row is invalid, duplicated, conflicting, or would require an
update/replace decision, no rows are written. Successful creates go through the
route service and write safe audit rows. Confirmed imports can affect future
model resolution through the existing resolver; route resolution runtime
semantics are otherwise unchanged.

Dashboard usage and audit CSV exports are capped by:

- `ADMIN_USAGE_EXPORT_MAX_ROWS` defaults to `10000`.
- `ADMIN_AUDIT_EXPORT_MAX_ROWS` defaults to `10000`.

Both values must be positive integers. The optional form-level export limit must
also be positive and cannot exceed the configured cap.

Optional reconciliation alerts are operator-visibility only. They are generated
from the inspection task, do not call providers, do not send email, and do not
change quota/accounting state. The first supported sink is a generic JSON
webhook; Slack, PagerDuty, and other product-specific integrations can be wired
through an operator-managed bridge.

## Production Notes

- Never commit `.env`.
- Never commit real provider keys, gateway keys, SMTP passwords, HMAC secrets,
  session secrets, or one-time-secret encryption keys.
- Rotate provider keys immediately if leaked.
- Rotate HMAC secrets carefully; removing an old version invalidates keys that
  were created with that version.
- Docker Compose packaging is provided for local/development service layout.
  API, worker, and scheduler containers do not run migrations automatically; use
  `slaif-gateway db upgrade` as an explicit operator step.
- Use HTTPS and a reverse proxy in production. The checked-in Nginx example
  keeps `/readyz` private-network allowlisted and denies `/metrics` by default;
  review and tighten those controls for the target network.
- Configure SSE streaming without proxy buffering.

## Optional Browser Test Configuration

Playwright admin dashboard smoke tests are opt-in. Normal unit, integration, and
OpenAI-compatible E2E tests do not require browser installation. To run the
browser smoke suite, install Chromium explicitly and provide a safe PostgreSQL
test database through `TEST_DATABASE_URL`:

```bash
python -m playwright install chromium
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/browser -m playwright
```

The suite starts a local FastAPI server and uses safe dummy data only. It does
not use `DATABASE_URL` for destructive setup, call real OpenAI/OpenRouter
providers, or send real email.
