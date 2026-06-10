# RC2 Feature Scope

This is the canonical RC2 scope-lock document for `slaif-api-gateway`.

## Scope-Lock Rules

1. A passing full verification harness means **verification-clean for implemented scope**, not **feature-full RC2**.
2. RC2 is not feature-full until every `RC2_REQUIRED_MISSING` row in this document is implemented and verified.
3. Hosted tools, MCP/connectors, file search, web search, code interpreter, image generation, video, moderations, batch, vector stores, and Responses background/cancel are not RC2 targets.
4. Standalone `/v1/audio/*`, Realtime audio, and `POST /v1/embeddings` are RC2 targets.
5. Chat request-body audio input and non-streaming audio output are already implemented, but they do **not** satisfy the standalone `/v1/audio/*` or Realtime audio targets.

## Classification Labels

- `RC2_REQUIRED_IMPLEMENTED`
- `RC2_REQUIRED_MISSING`
- `RC2_EXPLICITLY_DEFERRED`
- `RC2_UNSUPPORTED_BY_POLICY`
- `NEEDS_MAINTAINER_DECISION`

## Classification Summary

| Classification | Row count |
| --- | ---: |
| `RC2_REQUIRED_IMPLEMENTED` | 22 |
| `RC2_REQUIRED_MISSING` | 5 |
| `RC2_EXPLICITLY_DEFERRED` | 12 |
| `RC2_UNSUPPORTED_BY_POLICY` | 1 |
| `NEEDS_MAINTAINER_DECISION` | 6 |

## RC2 Scope Matrix

| Row | Current SLAIF status | Test coverage status | Accounting/pricing status | Provider-forwarding status | Privacy/storage status | RC2 classification | Reason | Next PR name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `GET /v1/models` | Implemented | Unit, integration, mocked official-client E2E | No generation quota reservation; no normal generation ledger row | Local metadata only; no upstream call | Safe local metadata only | `RC2_REQUIRED_IMPLEMENTED` | Part of the current required `/v1` surface | — |
| `POST /v1/chat/completions` | Implemented | Unit, integration, mocked official-client E2E | Reservation/finalization implemented; PostgreSQL authoritative | Canonical OpenAI/OpenRouter forwarding implemented | Prompts/completions not stored | `RC2_REQUIRED_IMPLEMENTED` | Core RC2 Chat surface is already implemented | — |
| Chat text streaming | Implemented | Unit, provider-stream, integration, mocked official-client E2E | Normal streaming generation accounting | Canonical SSE forwarding implemented | Streamed chunks not stored | `RC2_REQUIRED_IMPLEMENTED` | Required implemented Chat scope | — |
| Chat streaming live-burn | Implemented | Unit, provider-stream, accounting, integration coverage | Live-burn plus safe interruption accounting implemented | Stream termination and finalization ordering implemented | Safe counters/reasons only; no chunk storage | `RC2_REQUIRED_IMPLEMENTED` | Required hardening is merged | — |
| Chat image input | Implemented behind capability | Unit, forwarding, accounting, E2E coverage | Normal Chat reservation/finalization | Canonical request reconstruction | No image payload storage/logging | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Chat scope | — |
| Chat file input | Implemented behind capability | Unit, forwarding, accounting, E2E coverage | Normal Chat reservation/finalization | Canonical request reconstruction | No file payload storage/logging | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Chat scope | — |
| Chat audio input | Implemented behind capability | Unit, forwarding, accounting, E2E coverage | Normal Chat reservation/finalization | Canonical request reconstruction | No audio payload storage/logging | `RC2_REQUIRED_IMPLEMENTED` | RC2 explicitly includes Chat request-body audio input | — |
| Chat non-streaming audio output | Implemented behind capability | Unit, forwarding, accounting, E2E coverage | Normal Chat reservation/finalization; provider usage authoritative when available | Canonical request reconstruction; non-streaming only | Generated audio not stored/logged | `RC2_REQUIRED_IMPLEMENTED` | RC2 explicitly includes Chat non-streaming audio output | — |
| Chat streaming audio output | Fail-closed | Unit/policy coverage | No streaming audio accounting path exposed | Rejected before unsupported provider forwarding | No audio payload storage/logging | `RC2_UNSUPPORTED_BY_POLICY` | RC2 requires explicit fail-closed behavior until audio-aware streaming accounting exists | — |
| Chat local function tools | Implemented in documented local/client-side scope | Unit, integration, E2E coverage | Normal Chat accounting | Canonical forwarding implemented | No tool payload storage/logging | `RC2_REQUIRED_IMPLEMENTED` | Included in the current implemented Chat scope | — |
| Chat local custom tools | Implemented in documented non-streaming local/client-side scope | Unit, integration, E2E coverage | Normal Chat accounting | Canonical forwarding implemented | No tool payload storage/logging | `RC2_REQUIRED_IMPLEMENTED` | Included in the current implemented Chat scope | — |
| `POST /v1/responses` | Implemented for bounded non-hosted/non-MCP subset | Unit, integration, mocked official-client E2E | Reservation/finalization implemented | Canonical OpenAI/OpenRouter forwarding implemented for supported subset | No prompt/response body storage | `RC2_REQUIRED_IMPLEMENTED` | Required current Responses subset | — |
| Responses typed text streaming | Implemented for stateless text subset | Unit, provider-stream, mocked official-client E2E | Streaming finalization from completed event | Typed SSE forwarding implemented | Streamed chunks not stored | `RC2_REQUIRED_IMPLEMENTED` | Required current Responses subset | — |
| Responses streaming live-burn | Implemented for stateless text subset | Unit, provider-stream, accounting, mocked route tests | Live-burn plus safe interruption accounting implemented | Supported typed event forwarding only | Safe counters/reasons only; no chunk storage | `RC2_REQUIRED_IMPLEMENTED` | Required hardening is merged | — |
| Responses stored response lifecycle | Implemented for supported non-streaming stored create and owned lifecycle | Unit, repository, mocked official-client E2E | Stored create uses normal generation accounting; lifecycle calls do not | Canonical forwarding plus ownership checks | Safe reference metadata only | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| `GET /v1/responses/{response_id}` | Implemented with ownership checks | Unit, mocked official-client E2E | No generation quota reservation; no normal generation ledger row | Owned-reference proxy only | Safe reference metadata only | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| `DELETE /v1/responses/{response_id}` | Implemented with ownership checks | Unit, mocked official-client E2E | No generation quota reservation; no normal generation ledger row | Owned-reference proxy only | Safe reference metadata only | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| `GET /v1/responses/{response_id}/input_items` | Implemented with ownership checks | Unit, mocked official-client E2E | No generation quota reservation; no normal generation ledger row | Owned-reference proxy only | No input-item content storage | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| `POST /v1/responses/input_tokens` | Implemented | Unit, mocked official-client E2E | Provider-reported count only; no generation reservation | Canonical forwarding implemented | No input content storage | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| `POST /v1/responses/compact` | Implemented for bounded subset | Unit, mocked official-client E2E | Endpoint-specific reservation/finalization implemented | Canonical forwarding implemented | No compact content storage | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| Responses previous_response_id | Implemented for owned non-streaming references only | Unit, mocked official-client E2E | Normal non-streaming generation accounting | Forwarded only after owned-reference resolution | Safe reference metadata only | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| Conversations create/retrieve/update/delete | Implemented for owned provider references | Unit, repository, mocked official-client E2E | Control-plane/resource calls only; no normal generation ledger row | Canonical forwarding implemented | Safe reference metadata only; no item/metadata value storage | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| Conversation items create/list/retrieve/delete | Implemented for owned provider references | Unit, mocked official-client E2E | Control-plane/resource calls only; no normal generation ledger row | Canonical forwarding implemented | No item content storage | `RC2_REQUIRED_IMPLEMENTED` | Part of current implemented Responses scope | — |
| `POST /v1/audio/speech` | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No audio payload storage | `RC2_REQUIRED_MISSING` | Maintainer clarified standalone audio endpoints are RC2 targets | `feature/audio-endpoints-foundation` |
| `POST /v1/audio/transcriptions` | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No audio payload storage | `RC2_REQUIRED_MISSING` | Maintainer clarified standalone audio endpoints are RC2 targets | `feature/audio-endpoints-foundation` |
| `POST /v1/audio/translations` | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No audio payload storage | `RC2_REQUIRED_MISSING` | Maintainer clarified standalone audio endpoints are RC2 targets | `feature/audio-endpoints-foundation` |
| Realtime audio | Not implemented | No runtime coverage; unsupported/http-absent surface only | No session accounting design yet | No transport/forwarding path yet | No audio payload storage | `RC2_REQUIRED_MISSING` | Maintainer clarified Realtime audio is an RC2 target | `feature/realtime-audio-foundation` |
| `POST /v1/embeddings` | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No embedding payload storage | `RC2_REQUIRED_MISSING` | Maintainer clarified embeddings are an RC2 target | `feature/embeddings-endpoint-foundation` |
| Hosted/provider-side tools | Unsupported/fail-closed | Unit/policy coverage | No billing/accounting path exposed | Rejected before provider forwarding | No hosted-tool payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| MCP/connectors | Unsupported/fail-closed | Unit/policy coverage | No billing/accounting path exposed | Rejected before provider forwarding | No connector payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| File search | Unsupported/fail-closed | Unit/policy coverage | No billing/accounting path exposed | Rejected before provider forwarding | No search payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Web search | Unsupported/fail-closed | Unit/policy coverage | No billing/accounting path exposed | Rejected before provider forwarding | No search payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Code interpreter | Unsupported/fail-closed | Unit/policy coverage | No billing/accounting path exposed | Rejected before provider forwarding | No tool payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Image generation | Unsupported/fail-closed | Unsupported-route/policy coverage | No pricing/accounting path exposed | No supported provider forwarding | No media payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Video | Unsupported/fail-closed | Policy/docs coverage | No pricing/accounting path exposed | No supported provider forwarding | No media payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Moderations | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No moderation payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Batch | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No batch payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Vector stores | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No vector-store payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| Responses `background=true` | Unsupported/fail-closed | Unit/policy coverage | No async/background accounting path exposed | Rejected before provider forwarding | No background payload storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| `POST /v1/responses/{response_id}/cancel` | Not implemented | Unsupported-route/error-shape coverage only | No cancel accounting path yet | No provider forwarding path yet | No response body storage | `RC2_EXPLICITLY_DEFERRED` | Explicitly not an RC2 target | — |
| `/v1/files` list/create/retrieve/delete/content | Not implemented | Unsupported-route/error-shape coverage only | No ownership/pricing/accounting contract | No provider forwarding path yet | No file payload storage | `NEEDS_MAINTAINER_DECISION` | Maintainer asked for explicit decision unless separately documented | — |
| `/v1/uploads` and upload parts | Not implemented | Unsupported-route/error-shape coverage only | No ownership/pricing/accounting contract | No provider forwarding path yet | No upload payload storage | `NEEDS_MAINTAINER_DECISION` | Maintainer asked for explicit decision unless separately documented | — |
| Legacy `POST /v1/completions` | Not implemented | Unsupported-route/error-shape coverage only | No pricing/accounting path yet | No provider forwarding path yet | No prompt/completion storage | `NEEDS_MAINTAINER_DECISION` | Maintainer asked for explicit decision unless separately documented | — |
| Responses audio | Unsupported/fail-closed | Unit/policy coverage | No audio pricing/accounting path exposed | Rejected before provider forwarding | No audio payload storage | `NEEDS_MAINTAINER_DECISION` | Maintainer asked for explicit decision unless Realtime/audio work narrows the bridge | — |
| Responses multimodal output | Unsupported/fail-closed | Unit/policy coverage | No multimodal output pricing/accounting path exposed | Rejected before provider forwarding | No media payload storage | `NEEDS_MAINTAINER_DECISION` | Maintainer asked for explicit decision if distinct from current input-to-text support | — |
| Other public OpenAI-compatible endpoint families not listed above | Not implemented unless separately documented | Unsupported-route/error-shape coverage only where applicable | No pricing/accounting path yet | No provider forwarding path yet | No payload storage | `NEEDS_MAINTAINER_DECISION` | Maintainer requested explicit decision for anything overclaimed outside the listed RC2 target | — |

## Required RC2 Implementation Sequence

1. `feature/audio-endpoints-foundation`
   - implement `POST /v1/audio/speech`
   - implement `POST /v1/audio/transcriptions`
   - implement `POST /v1/audio/translations`
   - no Realtime yet
   - no `/v1/files` lifecycle
   - no audio payload storage
   - normal quota/pricing/accounting
   - OpenAI/OpenRouter support only where provider adapter support is safe

2. `feature/embeddings-endpoint-foundation`
   - implement `POST /v1/embeddings`
   - add route/model capability
   - add pricing/accounting for input tokens/vector generation
   - add official OpenAI Python client E2E coverage

3. `feature/realtime-audio-foundation`
   - design Realtime audio transport/session model
   - make explicit WebSocket/WebRTC decision
   - define authentication/quota/accounting behavior
   - keep no prompt/audio payload storage
   - design live session cost and disconnect accounting
   - expect at least one design PR before implementation

4. `feature/rc2-final-verification`
   - run the full 128-worker harness only after all `RC2_REQUIRED_MISSING` rows are implemented
