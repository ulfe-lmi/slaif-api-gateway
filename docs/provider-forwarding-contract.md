# Provider Forwarding Contract

This document describes exactly how implemented `/v1/chat/completions` requests are forwarded to upstream providers. It is intended for code reviewers and operators verifying implementation claims.

## Provider Adapters

| Provider | Adapter | Upstream API shape | Implemented endpoint |
| --- | --- | --- | --- |
| OpenAI | `OpenAIProviderAdapter` | OpenAI Chat Completions | `POST /chat/completions` |
| OpenRouter | `OpenRouterProviderAdapter` | OpenRouter OpenAI-compatible Chat Completions | `POST /chat/completions` |

Anthropic-family, Google, Meta, Mistral, Qwen, and other non-OpenAI model names are supported only when a route sends them to OpenRouter's OpenAI-compatible interface. There is no native Anthropic adapter in this implementation.

Model route rows are local metadata used by the existing route resolver. They
may be managed from the admin dashboard, but that dashboard workflow does not
change the forwarding contract or provider adapter semantics described below.
Pricing rows are local metadata used by the existing pricing and FX estimate
path before forwarding. They may also be managed from the admin dashboard, but
that workflow does not change the Python pricing calculation or provider
forwarding semantics described below.
FX rows are local metadata used by the same estimate path for EUR conversion.
They may be created and edited from the admin dashboard, but that workflow does
not change the Python FX lookup, pricing calculation, or provider forwarding
semantics described below.

## OpenAI Upstream Forwarding

| Area | Contract |
| --- | --- |
| Base URL | Route provider config `base_url` when configured; otherwise `https://api.openai.com/v1` |
| Upstream endpoint | `POST /chat/completions` |
| Provider auth | `Authorization: Bearer <OPENAI_UPSTREAM_API_KEY>` or route-configured `api_key_env_var` value |
| Client auth | Client `Authorization` is never forwarded |
| Non-streaming Accept | `application/json` |
| Streaming Accept | `text/event-stream` |
| Content-Type | `application/json` |
| Body preservation | Ordinary OpenAI Chat Completions fields are preserved |
| Body mutation | `model` is replaced with the resolved `upstream_model`; default output token control may be injected; streaming forces usage options |
| Successful non-streaming response | Provider JSON body is returned to the client after accounting finalization succeeds |
| Successful streaming response | Provider SSE events are forwarded; `[DONE]` is sent only after final accounting succeeds |
| Usage/accounting | Provider `usage` is parsed; local pricing and FX data compute actual EUR cost |
| Provider errors | Client receives a safe OpenAI-shaped error; raw provider body is not returned or stored; sanitized diagnostics may be stored |

## OpenRouter Upstream Forwarding

| Area | Contract |
| --- | --- |
| Base URL | Route provider config `base_url` when configured; otherwise `https://openrouter.ai/api/v1` |
| Upstream endpoint | `POST /chat/completions` |
| Provider auth | `Authorization: Bearer <OPENROUTER_API_KEY>` or route-configured `api_key_env_var` value |
| Client auth | Client `Authorization` is never forwarded |
| Non-streaming Accept | `application/json` |
| Streaming Accept | `text/event-stream` |
| Content-Type | `application/json` |
| Model routing | Routes may use OpenRouter namespaced models such as `openai/...`, `anthropic/...`, `google/...`, or aliases that resolve to those names |
| Body preservation | Ordinary OpenAI-compatible fields are preserved |
| Body mutation | `model` is replaced with the resolved `upstream_model`; default output token control may be injected; streaming forces usage options |
| Successful non-streaming response | Provider JSON body is returned to the client after accounting finalization succeeds |
| Successful streaming response | Provider SSE events are forwarded; `[DONE]` is sent only after final accounting succeeds |
| Usage/accounting | Token usage is parsed; OpenRouter `usage.cost` or `usage.cost_usd` is captured as provider-reported native cost metadata when supplied; gateway cost finalization still uses the configured pricing/FX estimate path |
| Provider errors | OpenRouter JSON and streaming error events produce safe diagnostics; raw provider bodies are not returned or stored |

Known limitations:

- The gateway does not fetch live OpenRouter billing or pricing.
- Native provider-specific APIs behind OpenRouter are not exposed.
- Provider-specific request fields are forwarded only as ordinary JSON body fields; provider-specific headers are not generally forwarded.

## Header Contract

| Header | Client to gateway | Gateway to provider | Gateway to client | Behavior |
| --- | --- | --- | --- | --- |
| `Authorization` | Required as gateway Bearer token | Replaced with provider Bearer token | Not echoed | Client gateway key never leaves the gateway |
| `Content-Type` | Accepted for JSON requests | Sent as `application/json` | Provider response dependent | Provider request bodies are JSON |
| `Accept` | May be sent by client | Forced to `application/json` or `text/event-stream` based on request mode | Provider response dependent | Streaming requests use SSE Accept upstream |
| `X-Request-ID` | Safe incoming value may be accepted by middleware | Forwarded as the gateway request ID | Response includes gateway request ID | Used for tracing without exposing secrets |
| `Cookie` | Not used for `/v1` auth | Never forwarded | Not forwarded from provider except allowlisted safe headers | Blocks browser/session leakage |
| `Set-Cookie` | Not applicable | Not sent | Not exposed from provider | Blocks provider/admin session leakage |
| CSRF/session/admin headers | Not used for `/v1` auth | Never forwarded | Not exposed | Internal/admin headers stay internal |
| Provider request ID headers | Not sent by client | Not generated except gateway `X-Request-ID` | Safe provider request IDs may be retained in metadata/headers | Useful for diagnostics when provider returns them |

Outbound provider header construction uses a small allowlist. Header names containing authorization, cookie, CSRF, session, password, token, secret, admin, gateway, API key, or set-cookie fragments are blocked.

## Body Mutation Contract

| Field | Behavior | Reason |
| --- | --- | --- |
| `model` | Mutated upstream | Replaced with route `upstream_model` for aliases and provider-specific naming |
| `messages` | Preserved | Required Chat Completions input; used only for validation and token estimation, not stored |
| `max_tokens` | Preserved when valid | OpenAI Chat Completions output control |
| `max_completion_tokens` | Preserved when valid or injected if no output-token field exists | Bounded output is required for quota reservation |
| `stream` | Preserved; streaming path selected only when `true` | Controls JSON vs SSE response |
| `stream_options` | Preserved, but `include_usage` forced to `true` for streaming | Required for reliable streaming accounting |
| `tools` / `tool_choice` | Preserved | Ordinary OpenAI Chat Completions fields |
| `response_format` | Preserved | Ordinary OpenAI Chat Completions field |
| `metadata` | Preserved to provider; not stored wholesale in ledger | Ordinary OpenAI Chat Completions field |
| `user` | Preserved | Ordinary OpenAI Chat Completions field |
| `temperature` / `top_p` | Preserved | Ordinary OpenAI Chat Completions fields |
| Unknown ordinary JSON fields | Preserved | Avoid silently dropping OpenAI SDK/provider-compatible fields |
| Gateway-internal data | Rejected/not present in provider body | Routing, quota, rate-limit, and accounting state must not be sent upstream |

The gateway does not intentionally store prompt, completion, full request body, full response body, tool payload, or streamed chunk content in `usage_ledger`.

## Accounting Contract

For `POST /v1/chat/completions`:

1. Authentication and endpoint policy run before provider work.
2. Request policy validates shape, estimates input tokens, and bounds maximum output.
3. Redis operational rate limiting runs when enabled.
4. Route resolution selects provider and upstream model.
5. Pricing/FX lookup estimates maximum cost.
6. PostgreSQL hard quota reservation is committed before the provider call.
7. Provider forwarding happens after reservation. The provider call is not made while holding the quota row lock.
8. Successful provider responses are finalized using provider usage.
9. Failed provider responses release the pending reservation and create a failed usage ledger row when a reservation exists.
10. Successful accounting increments used counters, clears reserved counters, finalizes the reservation, writes/finalizes a ledger row, and records token/cost metrics.

### Streaming Accounting

Streaming has an extra finalization rule because content may already have reached the client:

- Provider chunks are forwarded as they arrive.
- Final provider usage is required for success.
- If usage is missing, the reservation is released, a failed/incomplete event is recorded with zero actual cost, a safe SSE error event is emitted, and normal successful `[DONE]` is not emitted.
- If usage is present, the gateway writes a durable provider-completed record before final counter mutation.
- If finalization succeeds, that record is marked finalized and `[DONE]` is emitted.
- If finalization fails, the record is marked with `needs_reconciliation=true` and `recovery_state=provider_completed_finalization_failed`; `[DONE]` is not emitted.
- Operator reconciliation can later finalize these provider-completed rows using stored usage/cost metadata without calling providers.

### Reconciliation

Manual quota reconciliation supports:

- Expired pending reservation repair for crash/stale cases.
- Provider-completed finalization-failure repair for streaming requests that already received final usage.

Provider-completed finalization failures are not treated as zero-cost provider failures. The repair path uses stored safe usage/cost metadata and does not call upstream providers.

## Safety Boundaries

- Provider API keys come from server settings or provider config environment variable names; they are not accepted from clients.
- Client gateway keys, provider keys, token hashes, cookies, sessions, and Authorization headers are not stored in ledger metadata.
- Raw provider response bodies are not returned to clients or stored.
- Provider diagnostics are bounded and sanitized.
- Normal tests mock upstream OpenAI/OpenRouter with RESPX and do not require real provider keys.
