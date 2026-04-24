# Database Schema for `slaif-api-gateway`

Authoritative schema design for the SLAIF OpenAI-compatible API gateway.

This document should be committed at:

```text
docs/database-schema.md
```

Codex/agents should implement this design using:

```text
PostgreSQL 16+
SQLAlchemy 2.x async
asyncpg
Alembic migrations
```

The schema is designed for an open-source, Dockerized API gateway that exposes an OpenAI-compatible `/v1` API, authenticates gateway-issued API keys, enforces hard per-key quotas, routes requests to OpenAI/OpenRouter, accounts for token/cost usage, supports email delivery of keys, and provides an admin dashboard plus CLI.

---

## 1. Design goals

The database must support:

1. Gateway-issued API keys with owner metadata.
2. No plaintext storage of user API keys.
3. Hard per-key token, request, and cost quotas.
4. Atomic reservation/finalization accounting to prevent quota races.
5. OpenAI-compatible user experience using only:

   ```bash
   OPENAI_API_KEY
   OPENAI_BASE_URL
   ```

6. Provider routing to OpenAI and OpenRouter.
7. Explicit model pricing and fail-closed behavior for unknown pricing.
8. Email delivery of newly generated or rotated keys without permanently storing plaintext keys.
9. Admin dashboard authentication, sessions, CSRF support, and auditability.
10. Immutable or effectively append-only usage reporting.
11. Privacy-aware logging: no prompt/response payloads by default.
12. Open-source maintainability.

---

## 2. Important corrections from the first draft

The earlier draft was directionally correct, but this version fixes several important omissions:

1. **Asynchronous key email delivery needs special handling.**
   If a plaintext key is sent to a Celery worker, it may be stored in Redis. This schema adds `one_time_secrets` for short-lived encrypted delivery secrets.

2. **Provider API keys must not be stored in plaintext in PostgreSQL.**
   This schema adds `provider_configs`, which stores provider metadata and environment variable names, not provider secrets.

3. **Cost accounting needs currency handling.**
   User limits are in EUR, while upstream pricing/cost data may be in another currency. This schema adds `fx_rates` and stores both native and EUR cost fields where needed.

4. **Quota reset and reporting need more metadata.**
   `gateway_keys` includes reset metadata. Historical usage remains in `usage_ledger`.

5. **Rate limits need persistent policy fields.**
   Runtime counters live in Redis, but per-key policy belongs in PostgreSQL.

6. **Admin browser sessions should be revocable.**
   This schema adds `admin_sessions` instead of relying only on opaque client-side cookies.

7. **Model routing needs explicit match type.**
   Exact, prefix, and glob-like routes are not the same. `model_routes` includes `match_type` and `priority`.

8. **Streaming and interrupted requests need explicit accounting status.**
   `usage_ledger.accounting_status` distinguishes finalized, estimated, failed, and interrupted accounting.

9. **Usage reports need historical snapshots.**
   `usage_ledger` stores owner/institution/cohort snapshots so reports remain meaningful even if owner metadata changes later.

10. **Anthropic support is not assumed natively.**
    Anthropic-family models may be supported through OpenRouter's OpenAI-compatible API. Native Anthropic support would require a separate adapter and additional tests.

---

## 3. Global schema rules

### 3.1 PostgreSQL extensions

Enable these extensions in the first Alembic migration:

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
```

Use `pgcrypto` for UUID generation if desired, and `citext` for case-insensitive email fields.

### 3.2 Types and conventions

Use:

```text
UUID primary keys
`timestamptz` for all timestamps
`bigint` for token and request counters
`numeric(18,9)` for money/cost values
`citext` for email fields
`jsonb` for structured metadata
text fields with CHECK constraints for enums
```

Do not use floats for money.

### 3.3 Timestamp fields

Most mutable tables should include:

```text
created_at timestamptz not null
updated_at timestamptz not null
```

Append-only/event tables need only `created_at` unless they have a finalization lifecycle.

### 3.4 Secret handling

Never store plaintext gateway API keys.

Gateway keys:

```text
plaintext token shown once or emailed once
public key id stored
HMAC-SHA-256 token hash stored
plaintext discarded
```

Provider keys:

```text
OPENAI_UPSTREAM_API_KEY
OPENROUTER_API_KEY
SMTP_PASSWORD
TOKEN_HMAC_SECRET
ONE_TIME_SECRET_ENCRYPTION_KEY
```

must be supplied through environment variables or Docker secrets, not plaintext DB rows.

### 3.5 Request/response privacy

By default, do not store prompts, completions, uploaded files, tool outputs, or full upstream response bodies.

Store only:

```text
token counts
costs
models
providers
latency
HTTP status
redacted error metadata
raw usage metadata, if safe
```

If future prompt logging is added, it must be explicitly opt-in and documented separately.

---

## 4. Key format and lookup model

Generated gateway keys should be compatible with clients that expect an OpenAI-style bearer token. A recommended format is:

```text
sk-slaif-<public_key_id>.<secret>
```

Example:

```text
sk-slaif-k_8Yx4pQ2s.d5f...large-random-secret...
```

The exact format can vary, but it must include a public lookup identifier so the server does not need to scan all key hashes.

Request validation flow:

```text
1. Read Authorization: Bearer <token>.
2. Parse public_key_id from token.
3. Load gateway_keys row by public_key_id.
4. Compute HMAC-SHA-256(server pepper, full token).
5. Compare with token_hash using constant-time comparison.
6. Check status, validity window, endpoint/model policy, rate limit, and quota.
```

---

## 5. Tables

## 5.1 `institutions`

Organizations associated with key owners.

Examples:

```text
University of Ljubljana, Faculty of Electrical Engineering
SLAIF
Partner university
Company participant
```

Columns:

```text
id UUID primary key
name text not null
country text null
notes text null
created_at timestamptz not null
updated_at timestamptz not null
```

Constraints/indexes:

```text
unique(lower(name))
```

Implementation note:

SQLAlchemy/Alembic may implement `unique(lower(name))` using a functional unique index.

---

## 5.2 `owners`

People who receive gateway keys.

Columns:

```text
id UUID primary key
name text not null
surname text not null
email citext not null
institution_id UUID null references institutions(id) on delete set null
external_id text null
notes text null
is_active boolean not null default true
anonymized_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
```

Constraints/indexes:

```text
unique(email)
index(institution_id)
index(is_active)
```

Notes:

- `external_id` may be used for university IDs, workshop registration IDs, or future identity provider IDs.
- If GDPR/data minimization requires anonymization, preserve usage ledger rows but anonymize owner fields.

---

## 5.3 `cohorts`

Workshop, course, training event, or project group.

Examples:

```text
SLAIF WP6 Workshop Ljubljana 2026-05
UL FE Internal Pilot 2026
SLAIF Summer School 2026
```

Columns:

```text
id UUID primary key
name text not null
description text null
starts_at timestamptz null
ends_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
```

Constraints/indexes:

```text
unique(name)
index(starts_at, ends_at)
```

---

## 5.4 `admin_users`

Dashboard and CLI administrators.

Columns:

```text
id UUID primary key
email citext not null
display_name text not null
password_hash text not null
role text not null default 'admin'
is_active boolean not null default true
last_login_at timestamptz null
created_at timestamptz not null
updated_at timestamptz not null
```

Allowed `role` values:

```text
viewer
operator
admin
superadmin
```

Constraints/indexes:

```text
unique(email)
check(role in ('viewer', 'operator', 'admin', 'superadmin'))
index(is_active)
```

Security rules:

```text
password_hash must use Argon2id
never store plaintext passwords
never log password hashes
```

Suggested role semantics:

```text
viewer      read-only dashboard access
operator    can create/export reports and inspect usage
admin       can create/revoke/extend keys and manage cohorts
superadmin  can manage admins, pricing, routes, and provider config
```

---

## 5.5 `admin_sessions`

Server-side admin login sessions, useful for revocation and CSRF protection.

Columns:

```text
id UUID primary key
admin_user_id UUID not null references admin_users(id) on delete cascade
session_token_hash text not null
csrf_token_hash text not null
ip_address inet null
user_agent text null
expires_at timestamptz not null
revoked_at timestamptz null
created_at timestamptz not null
last_seen_at timestamptz null
```

Constraints/indexes:

```text
unique(session_token_hash)
index(admin_user_id)
index(expires_at)
index(revoked_at)
```

Rules:

- Store only hashes of session and CSRF tokens.
- Admin logout should set `revoked_at`.
- Expired sessions should be cleaned by scheduled jobs.

---

## 5.6 `gateway_keys`

Central table for user-facing API keys.

Columns:

```text
id UUID primary key
public_key_id text not null
key_prefix text not null default 'sk-slaif'
key_hint text null
token_hash text not null
hash_algorithm text not null default 'hmac-sha256'
hmac_key_version integer not null default 1

owner_id UUID not null references owners(id) on delete restrict
cohort_id UUID null references cohorts(id) on delete set null

status text not null default 'active'
valid_from timestamptz not null
valid_until timestamptz not null

cost_limit_eur numeric(18,9) null
token_limit_total bigint null
request_limit_total bigint null

cost_used_eur numeric(18,9) not null default 0
tokens_used_total bigint not null default 0
requests_used_total bigint not null default 0

cost_reserved_eur numeric(18,9) not null default 0
tokens_reserved_total bigint not null default 0
requests_reserved_total bigint not null default 0

rate_limit_requests_per_minute integer null
rate_limit_tokens_per_minute bigint null
max_concurrent_requests integer null

allow_all_models boolean not null default false
allowed_models jsonb not null default '[]'
allow_all_endpoints boolean not null default false
allowed_endpoints jsonb not null default '[]'

metadata jsonb not null default '{}'

last_used_at timestamptz null
last_quota_reset_at timestamptz null
quota_reset_count integer not null default 0

created_at timestamptz not null
updated_at timestamptz not null
revoked_at timestamptz null
revoked_reason text null
```

Allowed `status` values:

```text
active
suspended
revoked
```

Do not store `expired` as a status. Expiration is derived from `valid_until`.

Constraints/indexes:

```text
unique(public_key_id)
unique(token_hash)
index(owner_id)
index(cohort_id)
index(status)
index(valid_until)
check(status in ('active', 'suspended', 'revoked'))
check(cost_used_eur >= 0)
check(cost_reserved_eur >= 0)
check(tokens_used_total >= 0)
check(tokens_reserved_total >= 0)
check(requests_used_total >= 0)
check(requests_reserved_total >= 0)
check(valid_until > valid_from)
```

Policy semantics:

```text
cost_limit_eur null       means no cost limit; avoid this for training keys
token_limit_total null    means no token limit; avoid this for training keys
request_limit_total null  means no request limit
allow_all_models false + empty allowed_models means no models allowed
allow_all_endpoints false + empty allowed_endpoints means no endpoints allowed
```

Recommended default for training keys:

```text
allow_all_models = false
allowed_models = ['gpt-4.1-mini', 'gpt-4o-mini', ...]
allow_all_endpoints = false
allowed_endpoints = ['/v1/chat/completions', '/v1/models']
cost_limit_eur not null
token_limit_total not null
```

Quota rule:

Before forwarding a request, update reservation counters in the same PostgreSQL transaction that checks limits. Use row locking or atomic conditional updates.

---

## 5.7 `quota_reservations`

Temporary reservations created before upstream forwarding and finalized/released after response handling.

Columns:

```text
id UUID primary key
gateway_key_id UUID not null references gateway_keys(id) on delete restrict
request_id text not null
endpoint text not null
requested_model text null
reserved_cost_eur numeric(18,9) not null default 0
reserved_tokens bigint not null default 0
reserved_requests bigint not null default 1
status text not null default 'pending'
created_at timestamptz not null
expires_at timestamptz not null
finalized_at timestamptz null
released_at timestamptz null
```

Allowed `status` values:

```text
pending
finalized
released
expired
```

Constraints/indexes:

```text
unique(request_id)
index(gateway_key_id)
index(status, expires_at)
check(status in ('pending', 'finalized', 'released', 'expired'))
check(reserved_cost_eur >= 0)
check(reserved_tokens >= 0)
check(reserved_requests >= 0)
```

Rules:

- Every quota-affecting request should create one reservation.
- Stale `pending` reservations must be released by a scheduled cleanup job.
- Finalization must adjust `gateway_keys.*_reserved_*` and `gateway_keys.*_used_*` counters atomically.

---

## 5.8 `usage_ledger`

Accounting record for each proxied request.

Rows may be inserted as `pending` and then finalized once upstream response/usage data arrives. After finalization, they should be treated as append-only except for administrative correction workflows that must be audited.

Columns:

```text
id UUID primary key
request_id text not null
client_request_id text null
idempotency_key text null
quota_reservation_id UUID null references quota_reservations(id) on delete set null

gateway_key_id UUID not null references gateway_keys(id) on delete restrict
owner_id UUID null references owners(id) on delete set null
institution_id UUID null references institutions(id) on delete set null
cohort_id UUID null references cohorts(id) on delete set null

owner_email_snapshot citext null
owner_name_snapshot text null
owner_surname_snapshot text null
institution_name_snapshot text null
cohort_name_snapshot text null

endpoint text not null
http_method text not null default 'POST'
provider text not null
requested_model text null
resolved_model text null
upstream_request_id text null

streaming boolean not null default false
success boolean null
accounting_status text not null default 'pending'
http_status integer null
error_type text null
error_message text null

prompt_tokens bigint not null default 0
completion_tokens bigint not null default 0
input_tokens bigint not null default 0
output_tokens bigint not null default 0
cached_tokens bigint not null default 0
reasoning_tokens bigint not null default 0
total_tokens bigint not null default 0

estimated_cost_eur numeric(18,9) null
actual_cost_eur numeric(18,9) null
actual_cost_native numeric(18,9) null
native_currency text null

usage_raw jsonb not null default '{}'
response_metadata jsonb not null default '{}'

started_at timestamptz not null
finished_at timestamptz null
latency_ms integer null
created_at timestamptz not null
```

Allowed `accounting_status` values:

```text
pending
finalized
estimated
failed
interrupted
released
```

Constraints/indexes:

```text
unique(request_id)
index(gateway_key_id, created_at)
index(owner_id, created_at)
index(institution_id, created_at)
index(cohort_id, created_at)
index(provider, resolved_model)
index(endpoint, created_at)
index(accounting_status, created_at)
check(accounting_status in ('pending', 'finalized', 'estimated', 'failed', 'interrupted', 'released'))
check(prompt_tokens >= 0)
check(completion_tokens >= 0)
check(input_tokens >= 0)
check(output_tokens >= 0)
check(cached_tokens >= 0)
check(reasoning_tokens >= 0)
check(total_tokens >= 0)
check(estimated_cost_eur is null or estimated_cost_eur >= 0)
check(actual_cost_eur is null or actual_cost_eur >= 0)
```

Rules:

- Do not store prompts or completions in this table.
- `usage_raw` may store provider usage fields only, not message content.
- `response_metadata` must be redacted.
- For interrupted streams where final usage is unavailable, mark `accounting_status='interrupted'` or `estimated` and finalize according to the reservation policy.

---

## 5.9 `provider_configs`

Configuration metadata for upstream providers.

This table must not store provider API keys.

Columns:

```text
id UUID primary key
provider text not null
display_name text not null
kind text not null
base_url text not null
api_key_env_var text not null
enabled boolean not null default true
timeout_seconds integer not null default 300
max_retries integer not null default 2
notes text null
created_at timestamptz not null
updated_at timestamptz not null
```

Allowed `kind` values:

```text
openai_compatible
```

Initial providers:

```text
provider='openai'
base_url='https://api.openai.com/v1'
api_key_env_var='OPENAI_UPSTREAM_API_KEY'

provider='openrouter'
base_url='https://openrouter.ai/api/v1'
api_key_env_var='OPENROUTER_API_KEY'
```

Constraints/indexes:

```text
unique(provider)
index(enabled)
check(kind in ('openai_compatible'))
```

Rules:

- Secrets are read from environment variables or Docker secrets.
- The admin dashboard may show `api_key_env_var`, but never the secret value.

---

## 5.10 `model_routes`

Maps user-requested model names to provider/upstream model names.

Columns:

```text
id UUID primary key
requested_model text not null
match_type text not null default 'exact'
endpoint text not null default '/v1/chat/completions'
provider text not null
upstream_model text not null
priority integer not null default 100
enabled boolean not null default true
visible_in_models boolean not null default true
supports_streaming boolean not null default true
capabilities jsonb not null default '{}'
notes text null
created_at timestamptz not null
updated_at timestamptz not null
```

Allowed `match_type` values:

```text
exact
prefix
glob
```

Examples:

```text
requested_model='gpt-4.1-mini'
match_type='exact'
provider='openai'
upstream_model='gpt-4.1-mini'

requested_model='openai/'
match_type='prefix'
provider='openrouter'
upstream_model='{requested_model}'

requested_model='anthropic/*'
match_type='glob'
provider='openrouter'
upstream_model='{requested_model}'
```

Constraints/indexes:

```text
index(requested_model, enabled)
index(provider, enabled)
index(endpoint, enabled)
index(priority)
check(match_type in ('exact', 'prefix', 'glob'))
```

Rules:

- Lowest `priority` wins when multiple routes match.
- Anthropic-family model names should route through OpenRouter unless a native Anthropic adapter is explicitly added later.
- `/v1/models` should expose only enabled and visible routes allowed for the requesting key.

---

## 5.11 `pricing_rules`

Approved pricing table used for cost estimation and final accounting.

Columns:

```text
id UUID primary key
provider text not null
upstream_model text not null
endpoint text not null default '/v1/chat/completions'
currency text not null default 'USD'

input_price_per_1m numeric(18,9) null
cached_input_price_per_1m numeric(18,9) null
output_price_per_1m numeric(18,9) null
reasoning_price_per_1m numeric(18,9) null
request_price numeric(18,9) null

pricing_metadata jsonb not null default '{}'
valid_from timestamptz not null
valid_until timestamptz null
enabled boolean not null default true
source_url text null
notes text null
created_at timestamptz not null
updated_at timestamptz not null
```

Constraints/indexes:

```text
unique(provider, upstream_model, endpoint, valid_from)
index(provider, upstream_model, endpoint, enabled)
index(valid_from, valid_until)
check(input_price_per_1m is null or input_price_per_1m >= 0)
check(cached_input_price_per_1m is null or cached_input_price_per_1m >= 0)
check(output_price_per_1m is null or output_price_per_1m >= 0)
check(reasoning_price_per_1m is null or reasoning_price_per_1m >= 0)
check(request_price is null or request_price >= 0)
```

Rules:

- Unknown pricing must fail closed.
- Do not forward requests for models without an enabled pricing rule unless an admin explicitly marks the route as free or exempt.
- If upstream returns cost directly, still store the native currency and converted EUR value in `usage_ledger`.
- Use `pricing_metadata` for provider-specific dimensions that are not yet first-class fields.

---

## 5.12 `fx_rates`

Currency conversion table for converting native upstream costs to EUR limits.

Columns:

```text
id UUID primary key
base_currency text not null
quote_currency text not null
rate numeric(18,9) not null
valid_from timestamptz not null
valid_until timestamptz null
source text null
created_at timestamptz not null
```

Example:

```text
base_currency='USD'
quote_currency='EUR'
rate=0.920000000
```

Constraints/indexes:

```text
unique(base_currency, quote_currency, valid_from)
index(base_currency, quote_currency, valid_from, valid_until)
check(rate > 0)
```

Rules:

- The gateway's hard user-facing cost limits are in EUR.
- If pricing is stored in USD, the service must convert to EUR before reservation and finalization.
- A manually configured FX rate is acceptable for MVP; automated rate updates can be added later.

---

## 5.13 `one_time_secrets`

Short-lived encrypted secrets used for workflows that temporarily need recoverable plaintext, especially email delivery of newly generated or rotated gateway keys.

This table exists because permanently storing plaintext keys is forbidden, but asynchronous email delivery through Celery otherwise risks putting plaintext keys into Redis job payloads.

Columns:

```text
id UUID primary key
purpose text not null
owner_id UUID null references owners(id) on delete set null
gateway_key_id UUID null references gateway_keys(id) on delete cascade
encrypted_payload text not null
nonce text not null
encryption_key_version integer not null default 1
expires_at timestamptz not null
consumed_at timestamptz null
created_at timestamptz not null
```

Allowed `purpose` values:

```text
gateway_key_email
gateway_key_rotation_email
```

Constraints/indexes:

```text
index(gateway_key_id)
index(expires_at)
index(consumed_at)
check(purpose in ('gateway_key_email', 'gateway_key_rotation_email'))
```

Rules:

- Encrypt with AES-256-GCM or equivalent authenticated encryption.
- The encryption master key must come from an environment variable or Docker secret.
- Plaintext may exist only in process memory.
- Celery jobs should reference `one_time_secrets.id`, not contain plaintext keys.
- After successful email delivery, mark `consumed_at` and optionally delete the row after a retention window.
- Expired unconsumed secrets must be deleted or marked unusable by a scheduled cleanup job.

---

## 5.14 `email_deliveries`

Tracks outbound key emails and other administrative emails.

Columns:

```text
id UUID primary key
owner_id UUID null references owners(id) on delete set null
gateway_key_id UUID null references gateway_keys(id) on delete set null
one_time_secret_id UUID null references one_time_secrets(id) on delete set null
recipient_email citext not null
subject text not null
template_name text not null
status text not null default 'pending'
provider_message_id text null
error_message text null
created_at timestamptz not null
sent_at timestamptz null
failed_at timestamptz null
```

Allowed `status` values:

```text
pending
sent
failed
cancelled
```

Constraints/indexes:

```text
index(owner_id)
index(gateway_key_id)
index(one_time_secret_id)
index(status, created_at)
check(status in ('pending', 'sent', 'failed', 'cancelled'))
```

Rules:

- Never store plaintext keys in `email_deliveries`.
- Store only status, recipient, template, and delivery metadata.

---

## 5.15 `audit_log`

Security-relevant administrative action log.

Columns:

```text
id UUID primary key
admin_user_id UUID null references admin_users(id) on delete set null
action text not null
entity_type text not null
entity_id UUID null
old_values jsonb null
new_values jsonb null
ip_address inet null
user_agent text null
request_id text null
note text null
created_at timestamptz not null
```

Indexes:

```text
index(admin_user_id, created_at)
index(entity_type, entity_id)
index(action, created_at)
index(request_id)
```

Examples of `action`:

```text
create_key
bulk_create_keys
email_key
revoke_key
suspend_key
activate_key
extend_key
reset_quota
rotate_key
change_owner
change_pricing
change_route
create_admin
change_admin_role
disable_admin
export_usage
login
logout
failed_login
```

Rules:

- Audit values must be redacted.
- Never place plaintext keys, passwords, provider keys, session tokens, or CSRF tokens in audit rows.
- CLI actions should also create audit entries where possible.

---

## 5.16 `background_jobs`

Optional but recommended table for tracking Celery jobs visible from the admin dashboard.

Columns:

```text
id UUID primary key
celery_task_id text null
job_type text not null
status text not null default 'queued'
created_by_admin_user_id UUID null references admin_users(id) on delete set null
payload_summary jsonb not null default '{}'
result_summary jsonb not null default '{}'
error_message text null
created_at timestamptz not null
started_at timestamptz null
finished_at timestamptz null
```

Allowed `status` values:

```text
queued
running
succeeded
failed
cancelled
```

Indexes:

```text
index(celery_task_id)
index(job_type, created_at)
index(status, created_at)
index(created_by_admin_user_id, created_at)
```

Rules:

- `payload_summary` must be redacted.
- Do not store plaintext secrets in job payload summaries.

---

## 6. Quota reservation algorithm

Before forwarding an upstream request:

```text
1. Parse and authenticate gateway key.
2. Resolve endpoint and requested model.
3. Resolve provider route.
4. Resolve pricing rule.
5. Estimate worst-case tokens and cost.
6. Start DB transaction.
7. Lock gateway_keys row or use atomic conditional UPDATE.
8. Verify:
   - key active
   - within valid_from/valid_until
   - endpoint allowed
   - model allowed
   - used + reserved + estimate <= limit
9. Insert quota_reservations row.
10. Increment gateway_keys reserved counters.
11. Commit.
12. Forward upstream.
```

After upstream response:

```text
1. Extract provider usage fields.
2. Calculate actual token/cost usage.
3. Convert native cost to EUR if needed.
4. Start DB transaction.
5. Lock gateway_keys row and reservation row.
6. Decrement reserved counters.
7. Increment used counters by actual usage.
8. Mark reservation finalized/released/expired.
9. Insert or finalize usage_ledger row.
10. Commit.
```

If upstream fails before usage is known:

```text
release reservation
write usage_ledger with success=false
```

If stream is interrupted and usage is unavailable:

```text
finalize using policy-defined estimate or reserved amount
mark accounting_status='interrupted' or 'estimated'
```

The system must never allow concurrent requests to overspend the same key.

---

## 7. Rate limiting

PostgreSQL stores rate-limit policy fields in `gateway_keys`:

```text
rate_limit_requests_per_minute
rate_limit_tokens_per_minute
max_concurrent_requests
```

Redis stores runtime counters, for example:

```text
rate:req:<public_key_id>:<minute>
rate:tok:<public_key_id>:<minute>
concurrency:<public_key_id>
```

PostgreSQL remains the source of truth. Redis is only fast operational state.

---

## 8. Initial seed data

Initial migrations or seed scripts should create:

1. Provider configs for `openai` and `openrouter`.
2. Basic model routes for supported OpenAI models.
3. Optional OpenRouter route patterns.
4. Pricing rules for explicitly supported models.
5. First admin user through CLI, not a hardcoded migration.

Do not seed secrets.

---

## 9. Implementation notes for SQLAlchemy/Alembic

1. Use SQLAlchemy 2.x typed models where practical.
2. Use async sessions for application code.
3. Use Alembic migrations for all schema changes.
4. Avoid inventing schema changes in application code without updating this document.
5. Use explicit indexes for all dashboard filters and accounting queries.
6. Use database constraints for statuses and nonnegative counters.
7. Use transactions for quota reservation/finalization.
8. Avoid cascade deletion of usage/accounting records.
9. Prefer `on delete restrict` for keys and accounting-critical references.
10. Ensure all secret-like fields are redacted from logs and reprs.

---

## 10. Tables summary

Required core tables:

```text
institutions
owners
cohorts
admin_users
admin_sessions
gateway_keys
quota_reservations
usage_ledger
provider_configs
model_routes
pricing_rules
fx_rates
one_time_secrets
email_deliveries
audit_log
```

Recommended operational table:

```text
background_jobs
```

---

## 11. What is intentionally not stored in the database

Do not store:

```text
OpenAI upstream API key
OpenRouter API key
SMTP password
TOKEN_HMAC_SECRET
ONE_TIME_SECRET_ENCRYPTION_KEY
plaintext gateway API keys
admin plaintext passwords
session plaintext tokens
CSRF plaintext tokens
full prompt payloads
full completion payloads
uploaded file contents
```

These belong in environment variables, Docker secrets, ephemeral process memory, object storage with separate policy, or nowhere at all.

---

## 12. Minimal MVP subset

If implementation needs to start smaller, the minimum viable schema is:

```text
institutions
owners
cohorts
admin_users
admin_sessions
gateway_keys
quota_reservations
usage_ledger
provider_configs
model_routes
pricing_rules
fx_rates
one_time_secrets
email_deliveries
audit_log
```

`background_jobs` can be added after the first admin dashboard version, but it is recommended if the dashboard will expose long-running imports/exports.

---

## 13. Agent implementation rule

When implementing this schema:

```text
Do not silently simplify away quota_reservations, one_time_secrets, audit_log,
provider_configs, or pricing_rules. Those tables address concrete correctness,
security, and accounting risks.
```

Any simplification must be documented as a deliberate MVP decision in both:

```text
docs/database-schema.md
AGENTS.md
```
