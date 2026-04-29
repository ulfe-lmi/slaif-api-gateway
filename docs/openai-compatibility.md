# OpenAI Compatibility

This gateway is OpenAI-compatible for the endpoint set implemented in this repository. It is not a full OpenAI platform clone.

Clients use standard OpenAI client configuration only:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

The key in `OPENAI_API_KEY` is a gateway-issued key. It is not an upstream OpenAI or OpenRouter provider key. The server-side upstream OpenAI secret must use `OPENAI_UPSTREAM_API_KEY`; production validation rejects likely upstream provider keys placed in server `OPENAI_API_KEY`. The gateway authenticates the gateway key, applies policy and quota, resolves a provider route, and substitutes the real provider key server-side before forwarding.

## Endpoint Support

| Endpoint | Status | Auth | Quota/accounting | Streaming | Test coverage |
| --- | --- | --- | --- | --- | --- |
| `GET /v1/models` | Implemented | Required | No usage charge; model visibility is filtered by key policy and enabled routes | Not applicable | Unit and integration coverage for model catalog visibility |
| `POST /v1/chat/completions` | Implemented | Required | PostgreSQL quota reservation before provider call; usage ledger finalization after provider response | Non-streaming and SSE streaming | Unit, integration, and mocked official OpenAI Python client E2E coverage |
| `POST /v1/responses` | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| `POST /v1/embeddings` | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Files endpoints | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Images endpoints | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Audio endpoints | Not implemented | Not applicable | Not implemented | Not implemented | Unsupported route/error behavior only |
| Native Anthropic API | Not implemented | Not applicable | Not implemented | Not implemented | Anthropic-family model names are covered only through OpenRouter routes |

Unsupported `/v1` routes return OpenAI-shaped errors through the FastAPI error handlers. The gateway does not claim 100% OpenAI platform compatibility outside the rows marked implemented.

## Model Catalog Visibility

`GET /v1/models` returns an OpenAI-shaped list containing only enabled, visible route metadata allowed for the authenticated gateway key. The endpoint does not call upstream providers and does not create usage or quota records.

Model access follows the same key policy used by chat authorization:

- `allow_all_models=true` exposes otherwise enabled and visible model routes.
- `allow_all_models=false` with a non-empty `allowed_models` list exposes only those allowed model IDs when they are otherwise enabled and visible.
- `allow_all_models=false` with an empty `allowed_models` list returns `{"object": "list", "data": []}`.

This avoids exposing local model catalog entries to keys that cannot use any model.

## Chat Completions Request Fields

`ChatCompletionRequest` requires:

- `model`
- `messages`

The schema preserves extra JSON-compatible fields instead of silently dropping them. The gateway currently preserves ordinary OpenAI Chat Completions fields including:

- `model`
- `messages`
- `temperature`
- `top_p`
- `stop`
- `tools`
- `tool_choice`
- `response_format`
- `seed`
- `user`
- `logprobs`
- `top_logprobs`
- `presence_penalty`
- `frequency_penalty`
- `n` when omitted or exactly `1`
- `stream`
- `stream_options`
- `metadata`
- `reasoning_effort`
- `modalities`
- `parallel_tool_calls`
- `service_tier`
- `max_tokens`
- `max_completion_tokens`

Unknown ordinary JSON-compatible fields are also preserved unless a gateway policy explicitly rejects them. Current request policy rejects malformed `messages`, invalid output-token controls, input estimates over the configured hard input cap, non-object `stream_options` when `stream=true`, and Chat Completions `n` values other than integer `1`.

`n > 1` is intentionally rejected for now. Multi-choice Chat Completions can produce multiple choices and require choice-aware quota reservation, cost estimation, and final usage validation. The gateway does not silently clamp or drop `n`; future support requires multiplying reservation and cost policy by the requested choice count and validating provider final-usage semantics.

## Gateway-Mutated Fields

| Field | Behavior | Reason |
| --- | --- | --- |
| `model` | Replaced upstream with the resolved route `upstream_model` | Allows aliases and provider-specific model names while keeping client-facing model IDs stable |
| `max_completion_tokens` | Injected from `DEFAULT_MAX_OUTPUT_TOKENS` when both output-token fields are absent | Hard quota requires a bounded maximum output |
| `max_tokens` / `max_completion_tokens` | Rejected when both are present with different values; rejected when non-positive or over `HARD_MAX_OUTPUT_TOKENS` | Avoid ambiguous quota estimation and enforce hard output caps |
| `stream_options.include_usage` | Forced to `true` for streaming requests, preserving other `stream_options` keys | Streaming accounting requires final provider usage metadata |
| Gateway-internal fields | Not sent upstream | Internal accounting, routing, and quota metadata never belongs in the provider body |

Non-streaming requests do not get `stream_options` injected unless the client supplied it. Streaming requests always forward `stream=true` and `stream_options.include_usage=true`.

## Request Pipeline

For `POST /v1/chat/completions`, the implemented order is:

1. Authenticate the gateway key from `Authorization: Bearer ...`.
2. Check endpoint allow-list policy.
3. Validate request shape with the permissive Chat Completions schema.
4. Apply request policy and token caps.
5. Apply Redis operational rate limits when enabled.
6. Resolve the model route and provider.
7. Look up pricing and FX data.
8. Reserve PostgreSQL hard quota.
9. Forward to OpenAI or OpenRouter.
10. Parse provider usage.
11. Finalize or release accounting.
12. Record metrics and safe usage ledger metadata.

Redis rate limiting is temporary operational throttling only. PostgreSQL remains authoritative for hard quota and usage accounting.

## Streaming Compatibility

Streaming Chat Completions use Server-Sent Events and are compatible with the official OpenAI Python client `stream=True` path in mocked E2E tests.

Implemented streaming behavior:

- The gateway returns `text/event-stream`.
- Provider SSE data chunks are forwarded as they arrive.
- Upstream streaming requests use `Accept: text/event-stream`.
- The gateway forces `stream_options.include_usage=true`.
- Final provider usage is required for successful streaming accounting finalization.
- The provider `[DONE]` event is held until finalization succeeds.
- If final usage is missing, the gateway records a failed/incomplete accounting event, releases the reservation according to current policy, does not charge actual cost, emits a safe SSE error event, and does not emit a normal successful `[DONE]`.
- If the provider completed with usage but finalization fails after content was already delivered, the gateway leaves a durable provider-completed recovery row marked for reconciliation and does not treat the request as a zero-cost provider failure.
- Streaming Redis concurrency slots are heartbeated while the stream remains open and released in the generator cleanup path.

Client disconnect handling is best-effort through generator cancellation cleanup. The code records a provider failure for detected cancellation, releases the quota reservation, and releases rate-limit concurrency when Redis rate limits are enabled. A real ASGI server test closes a stream early and verifies this cleanup path.

Successful streaming is covered by mocked official OpenAI Python client E2E tests. The missing-final-usage error path is covered by unit and PostgreSQL integration tests; an additional official-client assertion for the exact exception shape can be added later if needed.

## Error Compatibility

Errors from `/v1` routes are OpenAI-shaped:

```json
{
  "error": {
    "message": "...",
    "type": "invalid_request_error",
    "param": null,
    "code": "..."
  }
}
```

Provider errors are normalized to safe OpenAI-shaped client errors. Raw provider response bodies are not returned to clients and are not stored. When available, bounded sanitized provider diagnostics are stored for operators in failure ledger metadata.

Unsupported endpoints and unsupported provider adapter endpoints are explicit errors; they are not silently proxied.

## What Is Not Implemented

- Responses API.
- Embeddings API.
- Files, images, audio, or batch endpoints.
- Native Anthropic API.
- New provider types beyond OpenAI and OpenRouter.
- Bulk/import dashboard workflows, owner/institution/cohort mutation pages,
  usage/audit mutation pages, and MFA remain outside the current admin surface.
  Docker/Nginx packaging is deployment documentation and service layout only; it
  does not change `/v1` compatibility. The implemented dashboard and key-email
  delivery workflows are summarized in `docs/compatibility-matrix.md` and
  `docs/security-model.md`.
- Automatic key-email sending by default. Key email delivery is explicit through
  create/rotate email modes, CLI commands, or the one-time-secret-backed email
  delivery detail actions.
- Real upstream smoke tests in the normal test suite.
