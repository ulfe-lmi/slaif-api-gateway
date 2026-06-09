# Configuration

For first-time local setup, see [`quickstart.md`](quickstart.md). For RC-beta
release scope and the verification checklist, see [`rc-beta.md`](rc-beta.md)
and [`beta-readiness.md`](beta-readiness.md).

This gateway is configured with environment variables. Secrets should come from
environment variables, a deployment secret manager, or Docker secrets. The root
`.env.example` file is a safe Docker Compose-oriented template only; it must not
contain real credentials. A copied `.env` file is clear-text local runtime
configuration and must not be committed.

Migrations are explicit operator actions. The application and `/readyz` do not
run migrations on startup.

The checked-in `.env.example` is intentionally local-development friendly:
Redis rate limiting is enabled, logs are DEBUG level, and log output is readable
instead of structured JSON. This makes first-time Docker setup and local
diagnosis easier. Production deployments should usually set:

```env
LOG_LEVEL=INFO
STRUCTURED_LOGS=true
GUNICORN_LOG_LEVEL=info
CELERY_LOG_LEVEL=INFO
```

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

## Generating Local Runtime Secrets

For local setup or initial self-hosted bootstrap, use the CLI to generate one
server runtime secret at a time:

```bash
slaif-gateway secrets generate hmac --version 1
slaif-gateway secrets generate admin-session
slaif-gateway secrets generate one-time
```

Without `--write`, each command prints only the generated value to stdout. To
update a local env file safely, copy `.env.example` first and write each target
variable explicitly:

```bash
cp .env.example .env
slaif-gateway secrets generate hmac --version 1 --env-file .env --write
slaif-gateway secrets generate admin-session --env-file .env --write
slaif-gateway secrets generate one-time --env-file .env --write
slaif-gateway secrets validate-env --env-file .env
```

Targets:

- `secrets generate hmac --version 1` writes `TOKEN_HMAC_SECRET_V1`.
- `secrets generate admin-session` writes `ADMIN_SESSION_SECRET`.
- `secrets generate one-time` writes `ONE_TIME_SECRET_ENCRYPTION_KEY`.
- `secrets validate-env` checks that the active HMAC secret, admin session
  secret, and one-time encryption key are configured without printing values.

`--write` intentionally writes generated runtime secrets into the local
clear-text dotenv file for bootstrap convenience. It preserves comments and
unrelated env lines, replaces blank or placeholder values, and appends the
variable if it is missing. It refuses `.env.example` and refuses to replace an
existing non-placeholder value unless `--force` is supplied.
`--force` prints only safe rotation warnings: replacing an HMAC secret can
invalidate keys signed with that version, replacing `ADMIN_SESSION_SECRET` logs
admins out, and replacing `ONE_TIME_SECRET_ENCRYPTION_KEY` can make pending
encrypted one-time deliveries undecryptable.

The `.env` file remains local operator configuration and must not be committed.
On shared systems, run `chmod 600 .env` so other local users cannot read it. The
generator is not a complete secret-management system; production deployments
should use deployment secret managers, Docker secrets, or equivalent controls
where appropriate.

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

Gateway-key request policy separates models from endpoints:

- allowed models are route-backed model IDs such as `gpt-4o-mini`;
- allowed endpoints are implemented `/v1` paths such as `/v1/models` and
  `/v1/chat/completions`;
- `/v1/responses` is implemented for the bounded Responses text-output subset,
  including non-streaming stored create when explicitly enabled, and still
  requires explicit route capability and pricing metadata;
- legacy `/v1/completions` is rejected until implemented.

Admins can edit this policy from a key detail page with **Update Request
Policy**. The same validation is used by service and CLI workflows: endpoint
values must be implemented `/v1` paths, explicit model values must not be
endpoint paths, and explicit models must match existing enabled routes.

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
default through `REDIS_HOST_PORT`. It enables Redis rate limiting for local
Docker with conservative request and concurrency defaults. Blank
`DEFAULT_RATE_LIMIT_*` values mean no global throttle for that dimension unless
the gateway key has its own rate-limit policy; token-rate defaults are therefore
left unset until an operator chooses them. For host-local development outside
Compose, use a localhost URL such as `redis://localhost:16379/0`, or set
`REDIS_HOST_PORT` to match your local port plan.

Verify the runtime setting without printing secrets:

```bash
docker compose exec -T api python - <<'PY'
from slaif_gateway.config import get_settings
s = get_settings()
print("ENABLE_REDIS_RATE_LIMITS:", s.ENABLE_REDIS_RATE_LIMITS)
print("REDIS_URL set:", bool(s.REDIS_URL))
PY
```

Choose `RATE_LIMIT_FAIL_CLOSED` deliberately in production. Redis rate limits
are operational throttles; PostgreSQL quota and accounting remain authoritative.

## Chat Completions Streaming Live-Burn Settings

Streaming live-burn margin settings apply only to
`POST /v1/chat/completions` with `stream=true`. Responses live-burn monitoring
remains future work.

Per-key metadata defaults to enabled monitoring with zero margins:

```json
{
  "chat_streaming_live_burn": {
    "version": 1,
    "enabled": true,
    "cost_margin_eur": "0.000000000",
    "token_margin": 0
  }
}
```

Admins can configure this per key from the key creation page, the key detail
page's separate Chat streaming live-burn update form, or the matching CLI flags
and `keys set-chat-streaming-live-burn` command. Those operator surfaces share
service-layer validation, require an audit reason for updates, and preserve
unrelated key metadata such as Redis rate-limit policy. When monitoring is
disabled, the dashboard greys and disables only the Chat live-burn margin
fields; hard quota and Redis rate-limit fields remain independent.

Positive margins stop streams early before the quota boundary, zero margins
stop near the estimated boundary, and negative margins allow bounded estimated
overrun. If monitoring is disabled for a key, stored margins are preserved but
ignored at runtime. Cost and token thresholds are enforced independently.

| Setting | Default | Purpose |
| --- | ---: | --- |
| `CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER` | `1.15` | Multiplier applied to provisional visible-output token estimates. |
| `CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR` | `1000000` | Absolute bound for per-key positive or negative cost margins. |
| `CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN` | `1000000000` | Absolute bound for per-key positive or negative token margins. |

Live estimates are provisional only and are not invoice-grade billing truth.
PostgreSQL remains authoritative for hard quota/accounting, Redis or in-memory
live state remains temporary operational state, and final provider usage/cost
remains authoritative when available. The estimator counts streamed generated
Chat Completions text deltas and discards them; prompts, completions, streamed
chunks, tool arguments, media payloads, raw request bodies, and raw response
bodies must not be stored or logged.

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

## OpenAI Assisted Catalog Proposals

The admin-only proposal generator uses a separate discovery key:

- `OPENAI_ADMIN_DISCOVERY_API_KEY` is the default environment variable read by
  `slaif-gateway openai-assisted pricing-proposal` and
  `slaif-gateway openai-assisted route-proposal`, and by the authenticated
  admin dashboard pages under `/admin/openai-assisted`.
- `OPENAI_ASSISTED_CATALOG_MODEL` defaults the proposal model when `--model` is
  omitted or when the dashboard form keeps the default. Operators can override
  it per CLI command with `--model` or per dashboard proposal form.

This key is only read when an operator explicitly runs the proposal CLI command
with `--acknowledge-llm-proposal-risk` or submits the dashboard proposal form
after checking the required acknowledgement. It is not used by gateway user
traffic, is not read from provider config rows, is never displayed in the
dashboard, and must not be named `OPENAI_API_KEY`. `OPENAI_API_KEY` remains the
OpenAI-compatible client variable for gateway-issued user keys.

The proposal commands and dashboard pages call OpenAI Responses with web search
restricted to official OpenAI domains where possible, ask for strict JSON,
validate the JSON locally, and render TSV proposal content. They do not mutate
`pricing_rules` or `model_routes`; import remains a separate
preview/confirm/audit workflow through the existing pricing and route import
pages. The dashboard result page is no-cache and can post a generated TSV
directly into the existing import preview route when it fits the configured
pricing or route import byte limit. That bridge is preview-only; execution still
requires the existing confirmation checkbox plus audit reason and server-side
re-validation. The result page must not store generated TSV in PostgreSQL,
cookies, audit rows, or server-side sessions, and it must not store raw model
responses, raw webpage text, prompts, completions, cookies, sessions, CSRF
tokens, provider keys, encrypted payloads, nonces, or raw request/response
bodies. Dashboard proposal generation is synchronous in the current
implementation and uses the service HTTP timeout; use the CLI if an operator
wants to run proposal generation outside a browser request.
Generated OpenAI pricing rows are operator-reviewed local accounting
assumptions, not authoritative provider pricing or invoice-grade guarantees.
Request, token, output, model, and rate limits remain important controls even
when local cost limits are configured.

## OpenAI Completions Catalog Bootstrap

For the implemented OpenAI-compatible Completions flow, operators should seed
local OpenAI Chat Completions metadata with:

```bash
slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

Setting `OPENAI_UPSTREAM_API_KEY` only makes the upstream provider secret
available. It does not create provider, route, or pricing rows. `/v1/models`
does not query OpenAI live; it lists local enabled, visible routes filtered by
the gateway key policy. With no local routes, `/v1/models` returns
`{"object":"list","data":[]}`. With no pricing row, cost-limited requests fail
closed.

The command creates or verifies:

- provider metadata for `provider=openai`, storing only the
  `OPENAI_UPSTREAM_API_KEY` env var name by default;
- exact visible routes for curated `/v1/chat/completions` model IDs;
- local pricing rows from an operator-controlled CSV.

For first-time local wiring checks only, operators may use explicit placeholder
mode:

```bash
slaif-gateway bootstrap openai-completions-catalog \
  --pricing-mode placeholder \
  --confirm-placeholder-pricing \
  --apply
```

The required pricing CSV columns are:

```text
provider,model,endpoint,currency,input_price_per_1m,output_price_per_1m
```

`--pricing-mode require-file` is the default and fails closed if any selected
catalog model is missing a pricing row. `--pricing-mode placeholder` requires
`--confirm-placeholder-pricing`, creates rows marked as placeholder assumptions,
and is for smoke tests only. Placeholder prices are not real pricing and must
not be used for production accounting.

`--include-legacy-models` adds older chat models from the curated catalog.
`--include-legacy-completions` is rejected because `POST /v1/completions` is not
implemented yet. Responses API configuration is separate and out of scope for
this bootstrap command.

## Request Caps

- `DEFAULT_MAX_OUTPUT_TOKENS` is injected when a supported request omits output
  token controls.
- `HARD_MAX_OUTPUT_TOKENS` rejects requests above the configured maximum output.
- `HARD_MAX_INPUT_TOKENS` rejects requests whose estimated input is too large.
  For Chat Completions, this estimate includes message content plus
  conservative serialized-size estimates for provider-forwarded non-message
  object/list fields such as `tools`, `functions`, and `response_format` JSON
  schemas.

These caps protect hard quota reservation by bounding worst-case usage before
upstream forwarding.

Chat Completions also has explicit per-field validation before Redis rate
limiting, route resolution, pricing lookup, quota reservation, or provider
forwarding. Defaults:

| Setting | Default | Applies to |
| --- | ---: | --- |
| `CHAT_MAX_CHOICES_PER_REQUEST` | `4` | Maximum `n` choices for one Chat Completions request when the route enables multiple choices |
| `CHAT_MAX_MESSAGES_PER_REQUEST` | `128` | Number of `messages` entries |
| `CHAT_MAX_MESSAGE_CONTENT_BYTES` | `262144` | One message's string/text-part content |
| `CHAT_MAX_TEXT_PARTS_PER_MESSAGE` | `64` | Text parts in one message |
| `CHAT_MAX_IMAGES_PER_REQUEST` | `8` | Image content parts in one request |
| `CHAT_MAX_IMAGES_PER_MESSAGE` | `4` | Image content parts in one message |
| `CHAT_MAX_IMAGE_URL_BYTES` | `4096` | One remote image URL |
| `CHAT_MAX_IMAGE_DATA_URL_BYTES` | `10485760` | One base64 image data URL |
| `CHAT_ALLOW_IMAGE_DATA_URLS` | `true` | Whether `data:image/...;base64,...` image URLs are accepted when route capability allows image input |
| `CHAT_ALLOW_REMOTE_IMAGE_URLS` | `true` | Whether `http`/`https` image URLs are accepted when route capability allows image input |
| `CHAT_MAX_FILES_PER_REQUEST` | `4` | Inline file content parts in one request |
| `CHAT_MAX_FILES_PER_MESSAGE` | `2` | Inline file content parts in one message |
| `CHAT_MAX_FILE_DATA_BYTES` | `10485760` | One `file.file_data` string, including any data-URL wrapper |
| `CHAT_MAX_FILE_NAME_BYTES` | `255` | One inline file `filename` |
| `CHAT_ALLOW_FILE_DATA_URLS` | `false` | Whether `data:<mime>;base64,...` file data URLs are accepted; raw base64 is accepted by default |
| `CHAT_ALLOW_FILE_IDS` | `false` | Reserved for a future Files API ownership policy; file IDs are rejected in this release |
| `CHAT_ALLOWED_FILE_MIME_TYPES` | `application/pdf,text/plain,text/markdown,text/csv,application/json` | Data-URL MIME allowlist for inline file inputs |
| `CHAT_ALLOWED_FILE_EXTENSIONS` | `.pdf,.txt,.md,.csv,.json` | Filename extension allowlist for inline file inputs |
| `CHAT_MAX_AUDIO_INPUTS_PER_REQUEST` | `4` | Audio input content parts in one request |
| `CHAT_MAX_AUDIO_INPUTS_PER_MESSAGE` | `2` | Audio input content parts in one message |
| `CHAT_MAX_AUDIO_INPUT_DATA_BYTES` | `10485760` | One `input_audio.data` base64 string |
| `CHAT_ALLOWED_AUDIO_INPUT_FORMATS` | `wav,mp3` | Allowed `input_audio.format` values |
| `CHAT_ALLOW_AUDIO_INPUT_DATA_URLS` | `false` | Reserved for future policy; audio input data URLs are not accepted by default |
| `CHAT_ALLOWED_AUDIO_OUTPUT_FORMATS` | `wav,mp3,flac,opus,pcm16` | Allowed non-streaming Chat Completions audio-output formats |
| `CHAT_ALLOWED_AUDIO_OUTPUT_VOICES` | `alloy,ash,ballad,coral,echo,fable,nova,onyx,sage,shimmer,marin,cedar` | Allowed built-in Chat Completions audio-output voices |
| `CHAT_ALLOW_CUSTOM_AUDIO_OUTPUT_VOICES` | `false` | Reserved for future policy; custom audio-output voices are rejected by default |
| `CHAT_ALLOW_STREAMING_AUDIO_OUTPUT` | `false` | Streaming Chat Completions audio output remains unsupported by default |
| `CHAT_ALLOW_AUDIO_OUTPUT_WITH_N_CHOICES` | `false` | `n > 1` with Chat Completions audio output remains unsupported by default |
| `CHAT_MAX_TOOLS_PER_REQUEST` | `64` | `tools` entries |
| `CHAT_MAX_CUSTOM_TOOLS_PER_REQUEST` | `16` | Custom local tools in one request |
| `CHAT_MAX_FUNCTIONS_PER_REQUEST` | `64` | Legacy `functions` entries |
| `CHAT_MAX_SINGLE_TOOL_SCHEMA_BYTES` | `65536` | One function-tool or function-choice schema payload |
| `CHAT_MAX_TOTAL_TOOL_SCHEMA_BYTES` | `262144` | Total local function-tool schema payloads |
| `CHAT_MAX_CUSTOM_TOOL_FORMAT_BYTES` | `65536` | One serialized custom-tool `format` object |
| `CHAT_MAX_CUSTOM_TOOL_GRAMMAR_BYTES` | `32768` | One raw custom-tool grammar definition |
| `CHAT_MAX_RESPONSE_FORMAT_SCHEMA_BYTES` | `65536` | `response_format.json_schema` |
| `CHAT_MAX_METADATA_BYTES` | `16384` | Serialized `metadata` object |
| `CHAT_MAX_METADATA_KEYS` | `32` | `metadata` key count |
| `CHAT_MAX_METADATA_KEY_BYTES` | `128` | One metadata key |
| `CHAT_MAX_STOP_SEQUENCES` | `4` | Stop sequence count |
| `CHAT_MAX_STOP_SEQUENCE_BYTES` | `1024` | One stop sequence |
| `CHAT_MAX_USER_FIELD_BYTES` | `1024` | `user` field |
| `CHAT_MAX_PREDICTION_BYTES` | `65536` | Serialized `prediction` object |
| `CHAT_MAX_STREAM_OPTIONS_BYTES` | `8192` | Serialized `stream_options` object |
| `CHAT_MAX_LOGIT_BIAS_BYTES` | `16384` | Serialized `logit_bias` object |
| `CHAT_MAX_TOOL_NAME_BYTES` | `128` | Function tool/choice name |
| `CHAT_MAX_TOOL_DESCRIPTION_BYTES` | `4096` | Function description |
| `CHAT_MAX_CUSTOM_TOOL_NAME_BYTES` | `128` | Custom tool/choice name |
| `CHAT_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES` | `4096` | Custom tool description |

Image input to text output is enabled only when the resolved route explicitly
sets `chat_image_inputs=true`. Inline file input to text output is enabled only
when the route sets `chat_file_inputs=true`. Audio input to text output is
enabled only when the route sets `chat_audio_inputs=true`. Non-streaming audio
output is enabled only when the route sets `chat_audio_outputs=true` and the
active pricing row provides `pricing_metadata.audio_output_price_per_1m`. The
image/file/audio caps above bound request shape before provider forwarding.
SLAIF does not fetch remote image URLs, fetch file or audio URLs, upload files
upstream, transcribe audio locally, transcode audio, decode media payloads,
store/log image, file, audio, transcript, request, or response payloads, or
infer final image/file/audio billing from URL/base64 byte size, transcript
length, audio format, voice, or duration; final accounting continues to use
provider usage/cost. File IDs, file URLs, audio URLs, audio data URLs, streaming
audio output, custom audio-output voices, previous-audio references, and `n > 1`
with audio output remain unsupported.

Scalar Chat Completions controls are validated explicitly: `temperature`
must be between `0` and `2`, `top_p` between `0` and `1`, presence/frequency
penalties between `-2` and `2`, `top_logprobs` between `0` and `20` and only
with `logprobs=true`, `logit_bias` values between `-100` and `100`,
`reasoning_effort` one of `minimal`, `low`, `medium`, or `high`, `service_tier`
omitted or `auto`, and `n` a positive integer up to
`CHAT_MAX_CHOICES_PER_REQUEST`. `n > 1` also requires the resolved route to set
`chat_multiple_choices=true`. Output-token caps remain per choice; quota and
cost reservation multiply possible output by `n`, while input estimation is not
multiplied.

## Trusted Calibration Keys

Trusted calibration keys are real gateway keys for trusted organizers/admins.
They are short-lived, request-limited, and use normal authentication, routing,
provider-secret isolation, PostgreSQL accounting, usage ledger, usage
profiling, and audit behavior. Their discovery policy may pass routed Chat
Completions hosted-capability markers only when the resolved route metadata
explicitly allows that capability, so an admin can later derive strict
participant policies/templates from observed usage. They are not participant
keys and do not enable `/v1/responses` or `/v1/completions`.

- `CALIBRATION_KEYS_ENABLED` defaults to `true` for development/test
  convenience. Operators should treat production calibration keys as privileged
  and issue them only to trusted organizers.
- `TRUSTED_CALIBRATION_MAX_REQUESTS` defaults to `10` and bounds the required
  `request_limit_total` for trusted calibration key creation.
- `TRUSTED_CALIBRATION_MAX_VALID_DAYS` defaults to `7`.
- `TRUSTED_CALIBRATION_ALLOW_UNKNOWN_HOSTED_TOOLS` defaults to `true` so
  discovery can observe provider-side tool type names. Normal keys still reject
  unknown tool types.
- `TRUSTED_CALIBRATION_ALLOW_EXTERNAL_AUTHORITY` defaults to `false`.
  External MCP/connectors, provider-side authorization fields, connector IDs,
  server URLs, and approval flows remain denied by default.

CLI creation requires `--trusted-calibration`,
`--confirm-trusted-calibration`, a non-empty `--reason`, a small
`--request-limit-total`, and a short validity window. The admin key creation
page exposes the same trusted-calibration mode with an explicit warning and
confirmation checkbox, then calls the same key service. Bulk key import does not
create trusted calibration keys.

Admins can summarize observed trusted-calibration usage with
`slaif-gateway calibration summarize` or from the trusted key detail page. That
preview uses a source key, optional time window, and multiplier to propose
strict participant policy values. Preview is read-only: no templates,
participant keys, key policy changes, routes, or pricing rows are created or
updated. After review, admins can create a durable key template from the
proposal with `slaif-gateway templates create-from-calibration` or the
dashboard. That writes only template/revision rows and safe audit metadata; it
does not create participant keys or mutate existing gateway keys. Admins can
then create exactly one normal key from a selected immutable revision with
`slaif-gateway keys create-from-template` or the template detail page. Bulk
template-based participant key creation remains future work.

## Responses API Configuration

The current Responses API foundation is text-output only. It supports
string input or bounded input item arrays, route-enabled user-message
`input_image` URL/data URL parts for image input to text output,
route-enabled user-message `input_file` URL/data URL parts for file input to
text output, non-streaming JSON, typed SSE text streaming, and non-streaming
structured `text.format` JSON object/schema output when route capability
metadata allows it. It also supports non-streaming local/client-side function
tools when route capability metadata allows them, and non-streaming
local/client-side custom tools when route capability metadata allows them.
Non-streaming stored create, non-streaming `previous_response_id`, input-item
listing, and non-streaming `conversation` use in `POST /v1/responses` are
available only when route capability metadata allows them and local ownership
checks pass. `POST /v1/conversations`, `GET /v1/conversations/{id}`, and
`DELETE /v1/conversations/{id}` are metadata/control proxy calls that require
explicit endpoint permission and safe local conversation-reference metadata;
they do not reserve generation quota or create normal generation usage ledger
rows. `POST /v1/responses/compact` is a separate bounded non-streaming
text-focused endpoint with explicit
`/v1/responses/compact` endpoint permission, route capability, pricing, and
provider usage finalization. Ordinary create reuses
`DEFAULT_MAX_OUTPUT_TOKENS` and `HARD_MAX_OUTPUT_TOKENS` for
`max_output_tokens`, and adds bounded request-shape caps:

- `RESPONSES_MAX_INPUT_TEXT_BYTES=262144`
- `RESPONSES_MAX_INPUT_ITEMS=128`
- `RESPONSES_MAX_INPUT_ITEM_TEXT_BYTES=262144`
- `RESPONSES_MAX_TOTAL_INPUT_TEXT_BYTES=1048576`
- `RESPONSES_MAX_TEXT_CONTENT_PARTS_PER_ITEM=64`
- `RESPONSES_MAX_INSTRUCTIONS_BYTES=65536`
- `RESPONSES_MAX_METADATA_BYTES=16384`
- `RESPONSES_MAX_METADATA_KEYS=32`
- `RESPONSES_MAX_STREAM_OPTIONS_BYTES=8192`
- `RESPONSES_MAX_TEXT_FORMAT_BYTES=65536`
- `RESPONSES_MAX_JSON_SCHEMA_BYTES=65536`
- `RESPONSES_MAX_TEXT_FORMAT_NAME_BYTES=64`
- `RESPONSES_MAX_TEXT_FORMAT_DESCRIPTION_BYTES=4096`
- `RESPONSES_MAX_TOOLS_PER_REQUEST=64`
- `RESPONSES_MAX_FUNCTION_TOOLS_PER_REQUEST=64`
- `RESPONSES_MAX_CUSTOM_TOOLS_PER_REQUEST=64`
- `RESPONSES_MAX_FUNCTION_TOOL_NAME_BYTES=128`
- `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=4096`
- `RESPONSES_MAX_SINGLE_FUNCTION_TOOL_SCHEMA_BYTES=65536`
- `RESPONSES_MAX_TOTAL_FUNCTION_TOOL_SCHEMA_BYTES=262144`
- `RESPONSES_MAX_FUNCTION_CALL_OUTPUT_BYTES=262144`
- `RESPONSES_MAX_CUSTOM_TOOL_NAME_BYTES=128`
- `RESPONSES_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES=4096`
- `RESPONSES_MAX_CUSTOM_TOOL_FORMAT_DEFINITION_BYTES=65536`
- `RESPONSES_MAX_TOTAL_CUSTOM_TOOL_FORMAT_BYTES=262144`
- `RESPONSES_MAX_CUSTOM_TOOL_CALL_OUTPUT_BYTES=262144`
- `RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST=16`
- `RESPONSES_MAX_IMAGE_URL_BYTES=4096`
- `RESPONSES_MAX_IMAGE_DATA_URL_BYTES=20971520`
- `RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES=41943040`
- `RESPONSES_ALLOWED_IMAGE_MIME_TYPES=image/png,image/jpeg,image/webp,image/gif`
- `RESPONSES_MAX_FILE_PARTS_PER_REQUEST=8`
- `RESPONSES_MAX_FILE_URL_BYTES=4096`
- `RESPONSES_MAX_FILE_DATA_URL_BYTES=26214400`
- `RESPONSES_MAX_TOTAL_FILE_DATA_URL_BYTES=52428800`
- `RESPONSES_MAX_FILE_NAME_BYTES=255`
- `RESPONSES_MAX_PREVIOUS_RESPONSE_ID_BYTES=256`
- `RESPONSES_MAX_CONVERSATION_ID_BYTES=256`
- `RESPONSES_ALLOWED_FILE_MIME_TYPES=application/pdf,text/plain,text/markdown,text/csv,application/json,text/html,text/xml,application/xml`
- `RESPONSES_ALLOWED_FILE_EXTENSIONS=.pdf,.txt,.md,.csv,.json,.html,.xml`
- `RESPONSES_COMPACT_DEFAULT_MAX_OUTPUT_TOKENS=12000`
- `RESPONSES_COMPACT_HARD_MAX_OUTPUT_TOKENS=24000`

These are validation caps, not feature toggles. Responses still requires a key
with `/v1/responses` in its endpoint policy, a resolved route with explicit
Responses text/stateless capability metadata, and an active `/v1/responses`
pricing row.

Responses compact settings control admission-time output reservation for
`POST /v1/responses/compact`. They are not feature toggles and do not enable
compact without explicit key permission, a `/v1/responses/compact` route and
pricing row, and `capabilities.responses.compact=true`. Compact input/output
and encrypted compaction content remain outside logs and durable metadata.

Responses custom-tool settings cap local/client-side custom tool names,
descriptions, grammar definitions, total custom format bytes, and string-only
`custom_tool_call_output` follow-up input. They do not enable hosted tools,
MCP/connectors, provider-side storage, tool execution, multimodal tool
outputs, or streaming custom tools.

Responses image settings cap user-message `input_image.image_url` values.
Remote `http`/`https` URLs are forwarded only after shape/credential/fragment
validation; image data URLs are MIME/base64 checked and capped. They do not
enable `input_image.file_id`, `/v1/files`, audio input/output, image
generation, hosted tools, stateful Responses, or server-side URL fetching.

Responses file settings cap user-message `input_file.file_url`,
`filename`, and `file_data` values. File URLs must be fully qualified HTTPS
URLs without embedded credentials or fragments and with allowed extensions.
Inline file data must use configured base64 data URL MIME types and a safe
basename filename. These settings do not enable `input_file.file_id`,
provider-side file upload/lifecycle, file search/retrieval tools, server-side
fetching, parsing, OCR, indexing, audio input/output, or Office/spreadsheet
formats outside the configured allowlist.

## Planned Responses Tool Configuration

Hosted/provider-side Responses tool settings remain future work unless a future
PR adds matching code, tests, and `.env.example` entries. Local function-tool
request caps listed above are active validation caps, but they do not enable
hosted tools, MCP/connectors, web search, file search, code interpreter,
computer use, image generation, tool search, storage, or background mode.

Possible future setting names:

- `ENABLE_RESPONSES_API=false`
- `RESPONSES_DEFAULT_ENABLED_FOR_KEYS=false`
- `RESPONSES_MAX_TOOL_CALLS_DEFAULT`
- `RESPONSES_ALLOWED_TOOLS_DEFAULT`
- `RESPONSES_MAX_SINGLE_REQUEST_COST_EUR_DEFAULT`
- `PRICING_CATALOG_FETCH_ENABLED=false`
- `OPENROUTER_PRICE_REFRESH_ENABLED=false`

The intended behavior is documented in
[`responses-compatibility.md`](responses-compatibility.md),
[`key-templates.md`](key-templates.md), and
[`pricing-catalog.md`](pricing-catalog.md). Unimplemented settings are not added
to `.env.example` so operators do not mistake roadmap names for active runtime
controls.

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
  and application logging output. Application settings default to `INFO` and
  structured JSON, while the checked-in local Docker `.env.example` overrides
  them to DEBUG and readable console logs for first-time diagnosis.
- `GUNICORN_LOG_LEVEL` and `CELERY_LOG_LEVEL` are Docker/Compose process-level
  controls for the API process manager and Celery worker/scheduler. They are
  intentionally shell/Compose settings rather than application `Settings`
  fields.

Production startup logs warn when risky explicit overrides make `/metrics`
public or `/readyz` more detailed than the safe default. These warnings are not a
substitute for internal networking, reverse proxy allowlists, or an admin/auth
layer.

Structured logs redact gateway keys, provider keys, passwords, cookies, session
tokens, token hashes, encrypted payloads, nonces, and other sensitive fields.
Admin failure pages show a safe diagnostic/reference ID, but never stack traces
or raw exception text. Operators can search server logs for that ID.

For local diagnostics, prefer:

```bash
LOG_LEVEL=DEBUG
STRUCTURED_LOGS=false
GUNICORN_LOG_LEVEL=debug
CELERY_LOG_LEVEL=DEBUG
```

Inspect logs with:

```bash
docker compose logs -f api
docker compose logs -f worker scheduler
docker compose logs api | rg '<diagnostic-id>'
```

Logs remain redacted, but they are still operator-side operational records and
must not be treated as a secret store or exposed through the dashboard.

## CLI Diagnostics

`LOG_LEVEL` is the persistent application logging switch for web/API, worker,
scheduler, and CLI processes that read the environment. For one-off CLI
diagnostics, use the global CLI options instead of editing `.env`:

```bash
slaif-gateway --verbose version
slaif-gateway --log-level DEBUG keys list
```

`--verbose` is equivalent to a per-command CLI `LOG_LEVEL=DEBUG` override.
`--log-level` accepts `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.
Supplying both options is rejected to avoid ambiguous diagnostics. CLI
diagnostic logs use the same redaction pipeline as the web app and are written
to stderr, so JSON command output on stdout remains machine-readable.

CLI verbosity does not change running web/API, Gunicorn, worker, or scheduler
processes. To diagnose admin pages or `/v1` requests, set `LOG_LEVEL` for the
API process and use the Docker/Compose process-level controls described above.

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
external services. Chat Completions streaming live-burn telemetry is reported
from existing PostgreSQL usage ledger metadata: usage list/detail pages show
safe stopped-status and estimate fields, usage CSV exports include safe
`chat_live_burn_*` columns, and `slaif-gateway usage live-burn-summary` prints
aggregate counts and sums. These reports do not store or render streamed
chunks, prompts, completions, tool arguments, raw bodies, secrets, or raw
live-burn metadata JSON.

Arbitrary old-key dashboard email resend actions, bulk key send-now execution,
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
CSV, JSON, or TSV content, validates every row, parses money values from strings, and
rejects unknown fields or secret-looking source/notes/metadata values. It does not
write `pricing_rules`, does not create audit rows, and does not call external
pricing or provider APIs.

Dashboard bulk key import preview is CSRF-protected and dry-run only. It accepts
CSV or JSON key-creation rows and validates owner references, optional cohort
references, validity windows, hard quota values, allowlist policy fields, Redis
rate-limit policy fields, Chat Completions streaming live-burn policy fields,
email delivery modes, upload size, and row count. It
rejects unknown fields, gateway-key-looking input, provider-key-looking input,
and secret-looking notes/metadata/policy values. Preview does not generate
plaintext keys, does not write `gateway_keys`, `one_time_secrets`,
`email_deliveries`, or audit rows, does not enqueue Celery tasks, does not send
email, and does not call providers. Dashboard bulk key import execution uses the
same parser and validation rules, requires CSRF, explicit import confirmation,
one-time plaintext display confirmation when browser plaintext will be shown,
and a non-empty audit reason, and only creates keys after all rows validate.
Execution supports `none`, `pending`, and `enqueue` email modes. Bulk `send-now`
remains future work and rejects before mutation. Plaintext keys are shown once
on a no-cache result page for `none` and `pending` rows, are suppressed for
`enqueue` rows, and are not stored in PostgreSQL, audit rows, cookies, sessions,
URLs, email delivery rows, logs, or Celery payloads. Bulk `enqueue` creates
one-time secrets and pending email delivery rows, then queues Celery tasks with
IDs only; SMTP is not called in the admin HTTP request.

Optional bulk import fields
`chat_streaming_live_burn_enabled`,
`chat_streaming_live_burn_cost_margin_eur`, and
`chat_streaming_live_burn_token_margin` use the same validation and persisted
metadata shape as the Admin/CLI per-key Chat policy. Omitted fields default to
enabled with zero margins. Disabled monitoring preserves supplied margins in
metadata but ignores them at runtime.

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
CSV, JSON, or TSV content, validates every row, verifies provider references against
provider config rows, and rejects unknown fields, invalid match types, invalid
endpoints, negative priorities, and secret-looking capabilities/metadata/source
or notes values. It does not write `model_routes`, does not create audit rows, does not
call providers, and does not change route resolution runtime behavior.

Dashboard route import execution is also CSRF-protected and uses the same
parser/validation rules as preview. Execution requires explicit confirmation
and a non-empty audit reason, then re-parses the submitted upload or pasted
content server-side instead of trusting preview HTML or client-side
classification. The current dashboard execution workflow is all-or-nothing and
create-only: if any row is invalid, duplicated, conflicting, or would require an
update/replace decision, no rows are written. Successful creates go through the
route service, receive explicit Chat Completions capability metadata when the
route is for `/v1/chat/completions`, and write safe audit rows. Confirmed
imports can affect future model resolution through the existing resolver; route
resolution runtime semantics are otherwise unchanged. Capability metadata is
separate from endpoint/model/provider allowlists and does not enable hosted
tools, multimodal/audio/file inputs, non-default service tiers, or multiple
choices unless the route explicitly enables the dedicated capability.

Dashboard usage and audit CSV exports are capped by:

- `ADMIN_USAGE_EXPORT_MAX_ROWS` defaults to `10000`.
- `ADMIN_AUDIT_EXPORT_MAX_ROWS` defaults to `10000`.

Both values must be positive integers. The optional form-level export limit must
also be positive and cannot exceed the configured cap.

`slaif-gateway usage live-burn-summary` is a read-only Chat Completions
streaming report over usage ledger metadata. It supports the same safe usage
filters as the usage summary command and has `--json` output. Prometheus
runtime live-burn counters remain future work; no additional configuration is
required for this reporting slice.

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

## Parallel Test Workflow

Serial pytest commands remain supported. For faster local and CI unit runs,
install development dependencies and use the explicit pytest-xdist wrapper:

```bash
python -m pip install -e ".[dev]"
scripts/test-unit-parallel.sh
```

The unit wrapper computes the default worker count as `min(20, visible CPU
cores)` with a minimum of one worker. Override the worker count or distribution
strategy when needed:

```bash
PYTEST_XDIST_WORKERS=1 scripts/test-unit-parallel.sh
PYTEST_XDIST_WORKERS=20 scripts/test-unit-parallel.sh
PYTEST_XDIST_ARGS="--dist loadscope" scripts/test-unit-parallel.sh
```

`make test-unit-parallel` calls the same wrapper. `scripts/test-parallel-safe.sh`
and `make test-parallel-safe` run unit tests in parallel, then run integration,
E2E, and Playwright browser suites serially. The database and browser suites stay
serial by default because they share PostgreSQL, Redis, and browser resources
unless a future per-worker isolation workflow proves parallel execution safe.
Skipped browser tests still do not count as browser coverage. DB-backed tests
must use `TEST_DATABASE_URL`; the parallel wrappers do not create, drop, or
mutate databases and must not use `DATABASE_URL` for destructive setup.
See [`docs/testing-parallelism.md`](testing-parallelism.md) for the current
parallel-safety analysis and the per-worker database isolation plan.

## GitHub CI Configuration

The checked-in GitHub Actions workflows install the package with `.[dev]`, run
unit tests through `scripts/test-unit-parallel.sh`, run lint/Alembic checks, and
run PostgreSQL-backed integration, OpenAI-compatible E2E, Playwright browser, and
Docker Compose smoke jobs without real provider keys. CI database jobs use
`TEST_DATABASE_URL`, not `DATABASE_URL`, and Redis-backed tests use
`TEST_REDIS_URL`.

The Docker smoke job copies `.env.example` to `.env` and uses only development
placeholders. It does not call providers or send real external email.
