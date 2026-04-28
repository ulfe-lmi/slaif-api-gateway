# Compatibility Matrix

This matrix summarizes implemented behavior for reviewers. It describes the current repository state, not a future roadmap promise.

| Feature / endpoint / field | Current support | Provider coverage | Notes | Test coverage |
| --- | --- | --- | --- | --- |
| `GET /v1/models` | Implemented | Local route/provider metadata | Returns enabled, visible routes allowed for the authenticated key | Unit and integration model catalog tests |
| `POST /v1/chat/completions` non-streaming | Implemented | OpenAI, OpenRouter | Full auth, policy, routing, pricing, PostgreSQL reservation, provider forwarding, accounting finalization | Unit, integration, mocked official-client E2E |
| `POST /v1/chat/completions` streaming | Implemented | OpenAI, OpenRouter | SSE streaming, final usage requested, missing usage emits stream error instead of successful `[DONE]`, durable finalization recovery | Unit, integration, ASGI disconnect, mocked official-client E2E |
| `/v1/responses` | Not implemented | None | Unsupported endpoint; no Responses API translation | Error handling only |
| `/v1/embeddings` | Not implemented | None | No embeddings forwarding/accounting path yet | Error handling only |
| Files/images/audio endpoints | Not implemented | None | No file/image/audio storage, pricing, or forwarding | Error handling only |
| Native Anthropic API | Not implemented | None | Anthropic-family model names may be routed through OpenRouter only | Route/OpenRouter coverage |
| `messages` | Preserved | OpenAI, OpenRouter | Required and validated as a list of objects with string `role`; not stored in ledger | Request policy and forwarding tests |
| `tools` / `tool_choice` | Preserved | OpenAI, OpenRouter | Forwarded as ordinary JSON fields | Provider and route forwarding tests |
| `response_format` | Preserved | OpenAI, OpenRouter | Forwarded as ordinary JSON field | Provider and route forwarding tests |
| `stream_options.include_usage` | Forced to `true` for streaming | OpenAI, OpenRouter | Other `stream_options` keys are preserved | Unit, integration, E2E streaming tests |
| `temperature` / `top_p` / `stop` | Preserved | OpenAI, OpenRouter | Forwarded as ordinary JSON fields | Request passthrough tests |
| `max_tokens` / `max_completion_tokens` | Validated/preserved or defaulted | OpenAI, OpenRouter | Conflicting values rejected; absent values inject `max_completion_tokens` | Request policy tests |
| `metadata` / `user` | Preserved upstream | OpenAI, OpenRouter | Not stored wholesale in usage ledger | Request passthrough tests |
| Unknown ordinary JSON fields | Preserved | OpenAI, OpenRouter | The gateway avoids silent dropping; explicit policy errors still apply | Request passthrough tests |
| OpenAI non-streaming | Implemented | OpenAI | Uses OpenAI provider key and JSON Accept | Provider adapter tests |
| OpenAI streaming | Implemented | OpenAI | SSE parse/forward, usage chunk parse, error event handling | Provider streaming tests |
| OpenRouter non-streaming | Implemented | OpenRouter | Parses usage, request IDs, and provider-reported cost metadata when present | Provider adapter tests |
| OpenRouter streaming | Implemented | OpenRouter | Parses SSE usage, cost metadata, request IDs, and error events | Provider streaming, integration, E2E tests |
| Provider errors | Implemented | OpenAI, OpenRouter | Client errors are safe; diagnostics are sanitized and bounded | Provider error and PostgreSQL diagnostic tests |
| Provider usage parsing | Implemented | OpenAI, OpenRouter | Supports `prompt_tokens`/`completion_tokens`/`total_tokens` and input/output aliases | Unit and integration accounting tests |
| Provider cost metadata | Partial | OpenRouter | Captures OpenRouter `usage.cost`/`cost_usd` as provider-reported native metadata; hard quota finalization still uses configured pricing/FX | Provider adapter and accounting tests |
| Gateway key HMAC storage | Implemented | Not provider-specific | PostgreSQL stores HMAC digest, not plaintext key | Crypto/key service tests |
| Client Authorization isolation | Implemented | OpenAI, OpenRouter | Client gateway key is replaced by provider key upstream | Provider header tests |
| Provider key isolation | Implemented | OpenAI, OpenRouter | Provider keys come from server-side env/config and are redacted from diagnostics/logs | Provider/header/redaction tests |
| PostgreSQL hard quota | Implemented | All forwarded chat requests | Reserve before forward; finalize or release after response/error | Unit and PostgreSQL integration tests |
| Redis operational rate limiting | Implemented when enabled | Chat Completions path | Request/token/concurrency throttles only; not the hard quota source of truth | Unit and Redis/PostgreSQL integration tests |
| Usage ledger without prompt/completion storage | Implemented | All accounting paths | Stores metadata, token counts, cost, status, diagnostics; not full content | Accounting, redaction, integration tests |
| Streaming finalization recovery | Implemented | OpenAI, OpenRouter | Provider-completed finalization failures are durable and operator-repairable | Unit and PostgreSQL integration tests |
| Stale reservation reconciliation | Implemented | Not provider-specific | Operator repair for expired pending reservations; refuses provider-completed recovery rows as zero-cost stale failures | Unit and PostgreSQL integration tests |
| Dashboard pages | Not implemented | None | Out of scope for current implementation | None |
| Email/Celery workers | Not implemented | None | CLI/admin one-time secret storage exists separately; sending workers are future work | None |
| Real upstream calls in normal tests | Not used | None | Upstream HTTP is mocked with RESPX | Test suite configuration |
