# Streaming Live-Burn Margin Milestone

**Project:** SLAIF API Gateway
**Status:** Chat Completions streaming implemented; Responses live-burn remains future work
**Implementation order:** Chat Completions first, Responses second
**Primary intent:** reduce streaming quota-overrun risk by interrupting active streams when live output estimates cross a per-key margin
**Non-goal:** replacing final provider-usage accounting or turning chunk estimates into invoice-grade billing truth

---

## 1. Executive summary

SLAIF's hard accounting model is reserve-then-finalize:

1. authenticate the gateway key;
2. validate endpoint, model, provider, route, request shape, and capabilities;
3. apply gateway input/output caps;
4. estimate maximum possible request usage/cost;
5. reserve hard quota in PostgreSQL before the provider call;
6. forward the canonical provider request;
7. stream or return provider output;
8. finalize from provider-reported usage/cost;
9. record safe usage/accounting/audit metadata without storing prompts, completions, raw request bodies, raw response bodies, streamed chunks, media payloads, tool payloads, gateway secrets, or provider secrets.

This milestone adds a second, softer control:

> **Streaming live-burn margin** is a per-key operational policy that estimates visible streamed output while a stream is active and stops the stream early when estimated live burn crosses either the key's configured cost margin or configured output-token margin.

This is not final billing. It is not a replacement for PostgreSQL hard quota. It is not Redis-only quota. It is a live operational brake that reduces the chance that a long stream pushes a key far past its budget before final provider usage arrives.

Final accounting remains provider-truth:

```text
provider final usage/cost wins when available
live burn estimates are provisional
missing provider usage remains incomplete/reconciliable, not normal success
```

Implemented Chat Completions policy:

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

Sign convention:

```text
positive margin = restrictive; stop before the key reaches quota
zero margin     = boundary; stop around the estimated quota boundary
negative margin = permissive; allow bounded estimated overrun, so the key may finish negative
```

---

## 2. Why this deserves milestone status

Streaming creates a timing gap:

```text
content can reach the user before final provider usage/cost arrives
```

SLAIF already treats streaming accounting strictly: successful streaming must obtain final provider usage where possible, missing usage is not normal success, provider-completed/finalization-failed streams need durable recovery state, and PostgreSQL remains the hard quota source of truth.

However, a stream that starts legally can continue generating output until provider completion, client disconnect, provider error, timeout, or configured output cap. That can be too loose for workshop/classroom deployments with small participant quotas.

Streaming live-burn margin gives operators a practical per-key risk control:

```text
strict workshop key:
  enabled=true
  positive margin
  stream stops before expected zero balance

normal participant key:
  enabled=true
  zero margin
  stream stops near estimated quota boundary

trusted/admin/calibration key:
  enabled=true
  negative margin
  stream may finish with bounded negative balance

uninterrupted trusted workflow:
  enabled=false
  no live stream interruption from this feature
```

The milestone belongs in development governance because future agents must not confuse this with final accounting, Redis hard quota, provider billing truth, or content logging.

---

## 3. Definitions

### 3.1 Hard quota

Durable authoritative quota stored in PostgreSQL.

Examples:

```text
cost_limit_eur
token_limit_total
request_limit_total
used_cost_eur
used_tokens
reserved_cost_eur
reserved_tokens
usage ledger rows
quota reservation state
reconciliation state
```

Hard quota is authoritative. Redis and live-burn counters are not.

### 3.2 Reservation

The pre-provider-call quota hold. A cost-bearing request must not call the provider until quota has been reserved successfully.

Reservation is based on the effective request after policy and caps have been applied.

### 3.3 Final provider usage

The usage/cost metadata from the provider that finalizes actual accounting.

For OpenAI-style routes, SLAIF may compute cost from provider usage and local pricing. For OpenRouter-style routes, provider-reported cost may be preferred where the current accounting contract allows it. In all cases, final provider usage/cost is authoritative for successful finalization.

### 3.4 Streaming live-burn estimate

A provisional estimate calculated during an active stream.

Implemented Chat Completions surface:

```text
Chat Completions:
  choices[].delta.content
  choices[].delta.tool_calls[].function.name
  choices[].delta.tool_calls[].function.arguments
```

Future Responses surface:

```text
Responses:
  response.output_text.delta
```

The estimate is used to decide whether to interrupt an active Chat Completions
stream. It is not invoice-grade billing truth.

### 3.5 Streaming live-burn margin

The per-key margin used to compute live interruption thresholds.

Implemented Chat Completions metadata key:

```text
chat_streaming_live_burn
```

Recommended operator label:

```text
Streaming live-burn margin
```

Recommended help text:

```text
Positive margin stops streams early before the key reaches quota.
Zero margin stops near the estimated quota boundary.
Negative margin allows bounded estimated overrun, so the key may finish with a negative balance.
Final provider usage remains authoritative.
```

---

## 4. Sign convention and cutoff formula

The margin is subtracted from the remaining budget to obtain the live cutoff:

```text
live_cost_cutoff = remaining_cost_eur - cost_margin_eur
live_token_cutoff = remaining_tokens - token_margin
```

Stop when either dimension is crossed:

```text
stop if estimated_request_cost_so_far >= live_cost_cutoff
stop if estimated_request_tokens_so_far >= live_token_cutoff
```

Whichever threshold is hit first stops the stream.

### 4.1 Money examples

Assume:

```text
remaining_cost_eur = 1.00
```

| `cost_margin_eur` | Cutoff | Interpretation |
|---:|---:|---|
| `+0.20` | `0.80` | Restrictive. Stop early; aim to leave about €0.20 unspent. |
| `0.00` | `1.00` | Boundary. Stop near estimated zero balance. |
| `-0.20` | `1.20` | Permissive. Allow estimated overrun; key may finish near -€0.20. |

### 4.2 Token examples

Assume:

```text
remaining_output_tokens = 10_000
```

| `token_margin` | Cutoff | Interpretation |
|---:|---:|---|
| `+2_000` | `8_000` | Restrictive. Stop early; aim to leave about 2k output tokens. |
| `0` | `10_000` | Boundary. Stop near estimated token quota boundary. |
| `-2_000` | `12_000` | Permissive. Allow estimated overrun; key may finish near -2k tokens. |

### 4.3 Disabled monitoring

If monitoring is disabled:

```text
chat_streaming_live_burn.enabled = false
```

then:

```text
chat_streaming_live_burn.cost_margin_eur is ignored
chat_streaming_live_burn.token_margin is ignored
```

The request remains subject to ordinary policy validation, quota reservation, output caps, provider completion, final provider-usage accounting, and reconciliation rules.

---

## 5. Per-key policy model

### 5.1 Per-key only in the first version

The first implementation is one Chat Completions streaming policy per gateway
key.

Do not split margins by:

```text
model
provider
endpoint
route
tool type
modality
cohort
institution
```

The actual estimate can still use the resolved provider/model/pricing for the current request. The policy itself remains per-key.

### 5.2 Effective defaults

Every key has effective defaults for Chat Completions streaming:

```text
enabled = true
cost_margin_eur = 0
token_margin = 0
```

Missing metadata has the same effect as the default policy. The effective policy
is visible to operators in the admin key pages and CLI output.

### 5.3 Implemented metadata shape

The Chat Completions implementation persists safe key metadata:

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

The metadata must not contain prompts, completions, streamed text, tool arguments, tool outputs, media payloads, raw request bodies, raw response bodies, provider keys, gateway plaintext keys, token hashes, encrypted payloads, nonces, session tokens, CSRF tokens, password hashes, or email bodies.

### 5.4 Suggested first-class schema fields

If implemented as first-class columns, the conceptual fields are:

```text
gateway key streaming live-burn enabled flag
gateway key streaming live-burn cost margin in EUR
gateway key streaming live-burn output token margin
```

Exact database field names, constraints, defaults, and migrations must be defined in the authoritative database schema documentation before or in the same PR as implementation.

### 5.5 Key-template policy

Template-specific live-burn policy is future work. Keys created through current
template workflows receive the normal default Chat Completions streaming
live-burn policy unless their creation path explicitly sets a per-key override.

Possible future safe template summary:

```json
{
  "chat_streaming_live_burn": {
    "version": 1,
    "enabled": true,
    "cost_margin_eur": "0.100000000",
    "token_margin": 500
  }
}
```

Template rules:

- Existing keys must not be silently mutated when a template changes.
- Revisions remain immutable snapshots.
- Keys created from a template may copy the safe policy summary to the created key.
- Bulk key creation from templates remains a separate workflow unless explicitly implemented.
- Template policy must not store raw content or secrets.

---

## 6. Interaction with hard reservation

Live-burn monitoring must not replace admission-time reservation.

Required sequence:

```text
1. authenticate gateway key
2. validate endpoint/model/provider/request/capability policy
3. apply gateway input/output caps
4. estimate maximum request cost/tokens
5. reserve PostgreSQL hard quota
6. start provider streaming request
7. estimate visible output burn as stream deltas arrive
8. stop stream if live-burn threshold is crossed
9. finalize from provider usage if provider usage arrives
10. otherwise record interrupted/incomplete/reconciliable state according to accounting policy
```

Concurrency rule:

```text
do not double-count this stream's own reservation
do include other active reservations
```

The effective remaining budget used for live-burn thresholds must be derived from current PostgreSQL quota/reservation state. Concurrent streams must not each believe they own the same remaining budget.

Conceptual expression:

```text
cost_budget_for_this_request =
  key.cost_limit_eur
  - key.cost_used_eur
  - max(key.cost_reserved_eur - current_reservation.cost_reserved_eur, 0)

token_budget_for_this_request =
  key.token_limit_total
  - key.tokens_used_total
  - max(key.tokens_reserved_total - current_reservation.tokens_reserved_total, 0)
```

The Chat Completions implementation follows this formula after a successful
PostgreSQL quota reservation.

---

## 7. Estimation model

### 7.1 First supported estimation surface

The Chat Completions implementation estimates visible generated output deltas:

```text
Chat Completions:
  choices[].delta.content
  choices[].delta.tool_calls[].function.name
  choices[].delta.tool_calls[].function.arguments
```

Do not initially estimate live burn for:

```text
streaming audio output
image generation
file output
hosted tools
MCP/connectors
provider-side tool execution
hidden reasoning tokens
non-visible provider work
```

### 7.2 Token estimate

Chunk boundaries are not token boundaries. The estimate must be conservative.

Conceptual formula:

```text
estimated_output_tokens =
    ceil(max(local_text_token_estimate, utf8_bytes_seen / 3) * safety_multiplier)
```

Implemented setting:

```text
CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER=1.15
```

If the project has an existing dependency-free token estimator, reuse it. If not, a byte/character heuristic is acceptable for the first implementation, provided the documentation states clearly that the estimate is provisional.

### 7.3 Cost estimate

For a resolved route with known output pricing:

```text
estimated_output_cost = estimated_output_tokens * output_price_per_token
```

For reasoning-heavy models, visible deltas can undercount total provider usage because hidden reasoning tokens may be billed. Operators who want strong no-overrun behavior should use positive margins and route/model policies that reserve enough for reasoning tokens.

For OpenRouter-style provider-reported-cost flows, live cost estimation may still use local pricing metadata because it is provisional. Final accounting remains governed by provider usage/cost rules.

### 7.4 Money and tokens are independent

The stream stops when either threshold is crossed:

```text
estimated cost crosses cost cutoff
OR
estimated output tokens cross token cutoff
```

If a key has no relevant limit, that dimension is inactive:

```text
no cost limit -> no cost live-burn stop
no token limit -> no token live-burn stop
no cost or token limit -> live-burn monitoring can observe but has no stop threshold
```

---

## 8. Stream interruption behavior

### 8.1 Goal

When a threshold is crossed, SLAIF should stop the upstream provider stream if possible.

The gateway should not merely stop sending to the client while the upstream provider continues generating.

### 8.2 Chat Completions SSE behavior

Emit a safe OpenAI-shaped SSE error payload:

```text
data: {"error":{"type":"insufficient_quota","code":"streaming_live_burn_limit_exceeded","message":"The streaming response was stopped because estimated usage crossed the key's streaming live-burn margin."}}
```

Then close the stream.

Do not emit normal successful:

```text
data: [DONE]
```

unless usage-backed finalization genuinely reaches the existing success path.

### 8.3 Responses SSE behavior

Responses live-burn interruption is not implemented yet. A future Responses PR
must emit a safe Responses-compatible error event:

```text
event: error
data: {"error":{"type":"insufficient_quota","code":"streaming_live_burn_limit_exceeded","message":"The streaming response was stopped because estimated usage crossed the key's streaming live-burn margin."}}
```

Then close the stream.

Do not emit normal successful:

```text
response.completed
data: [DONE]
```

unless usage-backed finalization genuinely reaches the existing success path.

### 8.4 Safe error code

Recommended stable code:

```text
streaming_live_burn_limit_exceeded
```

Recommended safe reason values:

```text
cost
tokens
both
```

Do not include exact prompt/completion content, raw request bodies, raw response bodies, provider secrets, gateway secrets, tool payloads, or media payloads in errors.

---

## 9. Final accounting after live-burn interruption

### 9.1 If provider final usage arrives

If final usage arrives:

```text
provider usage/cost wins
finalize from provider usage/cost
record safe live-burn trigger metadata
```

### 9.2 If provider final usage is missing

If final usage is missing after an intentional Chat Completions live-burn abort:

```text
do not finalize as normal success
do not emit normal successful terminal marker
record interrupted estimated accounting
store only safe estimate counters and metadata
```

The Chat Completions implementation debits an estimated interrupted usage event
when the gateway intentionally stops the provider stream before final usage
arrives. This avoids a zero-cost abuse path. The estimate is marked
`accounting_status="estimated"`, `success=false`, and
`estimate_is_invoice_grade=false`; it is not invoice-grade billing truth.

### 9.3 Safe metadata

Safe metadata may include:

```json
{
  "streaming_live_burn_enabled": true,
  "streaming_live_burn_triggered": true,
  "streaming_live_burn_stop_reason": "cost",
  "estimated_tokens_at_stop": 1234,
  "estimated_cost_eur_at_stop": "0.123400000",
  "cost_margin_eur": "0.000000000",
  "token_margin": 0,
  "final_provider_usage_available": false,
  "estimate_is_invoice_grade": false
}
```

Never store:

```text
streamed text
chunk text
prompt text
completion text
raw request body
raw response body
tool arguments
tool outputs
media payloads
provider keys
gateway plaintext keys
Authorization headers
cookies
CSRF/session tokens
password hashes
encrypted payloads
nonces
```

---

## 10. Redis and metrics

### 10.1 Redis role

Redis may store temporary live-burn visibility/counter data.

Redis must not become hard quota truth.

Possible temporary keys:

```text
stream:<request_id>:estimated_output_tokens
stream:<request_id>:estimated_cost_eur
stream:<request_id>:chunks_seen
stream:<request_id>:live_burn_state
```

Rules:

- TTL-bound.
- Deleted on cleanup when possible.
- No raw content.
- No secrets.
- Failure to write Redis live-burn metrics must not corrupt PostgreSQL hard quota.
- Redis outage must not create a Redis-only hard quota path.

### 10.2 Metrics

Suggested Prometheus metrics:

```text
gateway_streaming_live_burn_interruptions_total{endpoint,provider,model,reason}
gateway_streaming_live_burn_estimate_error_total{endpoint}
gateway_streaming_live_burn_monitoring_enabled_requests_total{endpoint}
gateway_streaming_live_burn_monitoring_disabled_requests_total{endpoint}
```

Metric labels must remain low-cardinality.

Do not label by:

```text
gateway key
prompt
completion
request ID
raw URL
raw model alias if high cardinality
user-provided content
```

---

## 11. Configuration model

Implemented Chat Completions settings:

```env
CHAT_STREAMING_LIVE_BURN_ESTIMATE_MULTIPLIER=1.15
CHAT_STREAMING_LIVE_BURN_MAX_ABS_COST_MARGIN_EUR=1000000
CHAT_STREAMING_LIVE_BURN_MAX_ABS_TOKEN_MARGIN=1000000000
```

The milestone default remains:

```text
per-key Chat Completions monitoring enabled by default
zero money margin
zero token margin
```

---

## 12. Admin and CLI surfaces

### 12.1 Admin key create/edit/detail

Implemented Chat operator surfaces show and edit the per-key policy on
`/admin/keys/create` and `/admin/keys/{gateway_key_id}`:

```text
Streaming live-burn monitoring: enabled/disabled
Cost margin, EUR: decimal, can be positive, zero, or negative
Output token margin: integer, can be positive, zero, or negative
```

The create-result page displays a safe summary of the created key's Chat
live-burn policy. The dense key list does not add a separate live-burn column;
operators use the key detail page for the editable policy.

Help text must remain explicit:

```text
Applies only to /v1/chat/completions with stream=true.
Positive margin stops streams early before the key reaches quota.
Zero margin stops near the estimated quota boundary.
Negative margin allows bounded estimated overrun; the key may finish with a negative remaining balance.
Final provider usage remains authoritative.
Live estimates are provisional, not invoice-grade.
```

When monitoring is disabled, the Admin form visibly greys and disables only the
Chat live-burn margin fields. PostgreSQL hard quota fields and Redis
rate-limit fields remain independent and editable through their own forms.
Server-side parsing must treat absent disabled margin fields safely and must not
depend on browser JavaScript.

### 12.2 CLI shape

Implemented CLI operations include:

```text
slaif-gateway keys create \
  --chat-streaming-live-burn-enabled / --no-chat-streaming-live-burn \
  --chat-streaming-live-burn-cost-margin-eur <decimal> \
  --chat-streaming-live-burn-token-margin <integer>

slaif-gateway keys set-chat-streaming-live-burn <key-id> \
  --enabled / --disabled \
  --cost-margin-eur <decimal> \
  --token-margin <integer> \
  --reason "..."
```

CLI output must remain secret-safe. The update command is audited and uses the
same service-layer validation as the dashboard.

### 12.2.1 Reusable surface pattern

Admin and CLI labels, field names, route suffixes, and help text are described
through a reusable streaming live-burn surface spec. The only active registered
surface is Chat Completions streaming:

```text
metadata_key = chat_streaming_live_burn
scope = /v1/chat/completions stream=true
```

Additional endpoint streaming live-burn surfaces can register another spec
later, but this implementation exposes and persists only the Chat policy.

### 12.3 Templates

Current key-template workflows do not carry a template-specific live-burn
policy. Template-created keys receive the per-key default policy unless a future
template-policy PR adds safe snapshot support.

Existing keys must not be silently mutated.

---

## 13. Chat Completions milestone

### 13.1 Scope

First implementation target:

```text
POST /v1/chat/completions
stream=true
visible text deltas
```

Supported live-burn estimate:

```text
choices[].delta.content
choices[].delta.tool_calls[].function.name
choices[].delta.tool_calls[].function.arguments
```

Potentially included if current stream parser already handles them safely:

```text
n > 1 streaming choices
ordinary text streaming
structured-output-compatible text chunks
```

Initially excluded from live-burn estimation:

```text
streaming audio output
streaming custom tools
hosted tools
MCP/connectors
image generation
tool execution
hidden reasoning tokens
provider-side state/background
```

### 13.2 Required behavior

For accepted Chat Completions streaming requests:

1. Load effective key live-burn policy.
2. If monitoring disabled, follow current streaming behavior.
3. If monitoring enabled:
   - compute effective remaining cost/token cutoffs after reservation;
   - initialize request-local estimator state;
   - parse visible text deltas while forwarding provider SSE;
   - update estimated output tokens/cost;
   - if cost or token threshold is crossed, stop upstream stream and emit safe SSE error;
   - suppress normal successful `[DONE]` unless usage-backed finalization succeeds.
4. If provider final usage arrives, provider usage wins.
5. If usage is missing because the gateway intentionally interrupted the
   stream, finalize an estimated interrupted accounting event with safe
   live-burn metadata instead of zero-cost success.

### 13.3 Required tests

Unit tests:

- default live-burn policy is enabled with zero margins;
- positive cost margin stops before quota boundary;
- zero cost margin stops at quota boundary;
- negative cost margin permits bounded overrun;
- positive token margin stops before token boundary;
- zero token margin stops at token boundary;
- negative token margin permits bounded token overrun;
- cost and token dimensions are enforced independently;
- whichever threshold crosses first determines stop reason;
- disabled monitoring ignores margins;
- chunk text is not stored;
- safe error code is emitted;
- normal `[DONE]` is suppressed on live-burn interruption;
- provider usage finalization still wins if available;
- missing usage remains incomplete/reconciliable, not normal success.

Streaming/provider tests:

- OpenAI Chat streaming text deltas trigger live-burn interruption.
- OpenRouter Chat streaming text deltas trigger live-burn interruption where native route supports it.
- Provider error before threshold follows provider-error path.
- Client disconnect cleanup still releases Redis concurrency/reservation according to existing behavior.
- Redis live-burn metric failure does not corrupt PostgreSQL accounting.

Admin/CLI tests:

- create/update key live-burn fields;
- render positive/zero/negative margins with explanatory text;
- CLI output never prints secrets or raw content.

---

## 14. Responses milestone

### 14.1 Scope

Second implementation target:

```text
POST /v1/responses
stream=true
typed SSE
response.output_text.delta
stateless text output
```

Supported live-burn estimate:

```text
response.output_text.delta
```

Potentially included later once the underlying features exist:

```text
image input with streamed text output
file input with streamed text output
audio input with streamed text output
structured-output streaming
function/custom tool-call streaming
reasoning-summary streaming
audio-output streaming
```

Initially excluded from live-burn estimation:

```text
structured-output deltas if not implemented
function-call argument deltas
custom-tool call deltas
reasoning-summary deltas unless explicitly supported
audio output deltas
file/audio/image cost beyond existing admission estimate
stateful lifecycle
background mode
hosted tools
MCP/connectors
```

### 14.2 Required behavior

Responses streaming is typed SSE and has distinct terminal semantics. Existing behavior must be preserved:

```text
response.completed is held until usage-backed accounting finalization succeeds
provider [DONE], if present, stays behind completed/finalization
missing usage is not normal success
finalization failure uses recovery/reconciliation behavior
```

Live-burn interruption must integrate with that model:

1. Load effective key live-burn policy.
2. If monitoring disabled, follow current Responses streaming behavior.
3. If monitoring enabled:
   - compute effective remaining cost/token cutoffs after reservation;
   - initialize estimator state;
   - parse only `response.output_text.delta` in the first implementation;
   - update estimated output tokens/cost;
   - if a threshold is crossed, stop upstream stream and emit safe typed error event;
   - suppress normal successful `response.completed` and `[DONE]` unless usage-backed finalization succeeds.
4. If provider final usage arrives, provider usage wins.
5. If usage is missing, use existing incomplete/reconciliation behavior plus safe live-burn metadata.

### 14.3 Required tests

Unit tests:

- Responses text delta estimates increment safely.
- Positive/zero/negative margins behave the same as Chat.
- Cost/token dimensions and first-hit behavior are covered.
- Disabled monitoring ignores margins.
- `response.output_text.delta` content is not stored.
- Safe typed error is emitted.
- Normal `response.completed` is suppressed on live-burn interruption unless finalization succeeded.
- Existing missing-usage/finalization-failure behavior remains.

Provider/streaming tests:

- OpenAI Responses typed SSE triggers live-burn interruption on `response.output_text.delta`.
- OpenRouter native Responses typed SSE does the same when explicitly configured.
- Provider error before threshold follows existing provider-error behavior.
- Response completed with usage before threshold finalizes normally.
- Response completed with missing usage remains incomplete/failure.

Official-client E2E:

- Mocked OpenAI Python client Responses stream sees deltas until interruption.
- Client receives an error path compatible with current SDK behavior.
- No normal success is reported when live-burn stops the stream.

---

## 15. Security and privacy invariants

The milestone must preserve:

- PostgreSQL remains authoritative for hard quota/accounting.
- Redis is temporary operational state only.
- Final provider usage/cost remains authoritative for successful accounting.
- Live estimates are provisional.
- No prompt text is stored.
- No completion text is stored.
- No streamed chunk text is stored.
- No raw request body is stored.
- No raw response body is stored.
- No tool arguments or tool outputs are stored.
- No media payloads are stored.
- No provider keys are stored/logged.
- No gateway plaintext keys are stored/logged.
- No client Authorization header is forwarded upstream.
- Hosted tools/MCP/connectors remain unsupported unless separately implemented.
- Normal tests do not use real upstream provider keys or send real email.
- All new `/v1` errors are OpenAI-shaped.
- Documentation and compatibility matrices must not claim live-burn estimates are invoice-grade billing truth.

---

## 16. Documentation awareness

This milestone should be referenced from development-governance and operator-facing documentation that already governs streaming/accounting behavior.

Important cross-reference targets include:

```text
AGENTS.md
docs/accounting.md
docs/openai-compatibility.md
docs/responses-compatibility.md
docs/provider-forwarding-contract.md
docs/security-model.md
docs/configuration.md
docs/compatibility-matrix.md
docs/key-templates.md
docs/beta-readiness.md
docs/rc-beta.md
docs/deployment.md
README.md only if top-level status/roadmap materially changes
.env.example only when settings are implemented
database-schema documentation only when persisted fields are implemented or formalized
```

Development-governance summaries should not duplicate this full milestone. They should link to it and preserve the core rules:

```text
Chat Completions first.
Responses second.
Per-key enabled default true.
Cost and token margins default zero.
Positive margin stops early.
Zero margin stops near the quota boundary.
Negative margin allows bounded estimated overrun.
Final provider usage remains authoritative.
PostgreSQL remains hard quota truth.
Redis remains temporary operational state.
No streamed content is stored.
```

---

## 17. Documentation-only milestone acceptance criteria

A documentation-only milestone PR should:

- add this milestone document;
- link it from `AGENTS.md`;
- update accounting documentation to mention the future live-burn margin milestone;
- update Chat Completions compatibility documentation to distinguish existing final-usage streaming accounting from future live-burn interruption;
- update Responses compatibility documentation the same way;
- update provider-forwarding documentation to clarify that live-burn interruption is gateway-side and provisional;
- update security documentation to prohibit streamed-content storage for live-burn counters;
- update configuration documentation only as proposed/future settings unless code implements them;
- update compatibility/readiness/RC documentation to mark the milestone planned/future, not implemented;
- update key-template documentation to mention future safe live-burn policy summaries without claiming implementation;
- avoid README unless its roadmap/current-status text is materially stale.

No runtime behavior should change in a documentation-only milestone PR.

---

## 18. Chat Completions implementation acceptance criteria

The Chat implementation PR should add:

- per-key effective live-burn policy;
- configuration defaults;
- safe parsing/validation for positive, zero, and negative margins;
- visible text-delta estimator for Chat streaming;
- cost/token cutoff computation;
- early upstream stream interruption;
- safe SSE error;
- no normal `[DONE]` on live-burn interruption;
- provider final usage still wins;
- missing usage remains incomplete/reconciliable;
- safe metadata only;
- admin/CLI surfaces if persisted;
- docs and tests.

It must not add:

- Responses live-burn behavior;
- audio streaming;
- hosted tools;
- MCP/connectors;
- image generation;
- tool execution;
- content logging;
- estimated-finalization-as-billing when provider usage is missing.

---

## 19. Responses implementation acceptance criteria

The Responses implementation PR should apply the same model to Responses typed SSE.

It should add:

- the same key live-burn policy used by Chat;
- parsing for `response.output_text.delta`;
- visible output token/cost estimates;
- interruption when cost/token cutoff is crossed;
- safe typed error event;
- existing `response.completed` hold/finalization semantics preserved;
- provider final usage still wins;
- missing usage remains incomplete/reconciliable;
- no raw chunk content storage/logging;
- docs and tests.

It must not add:

- structured-output streaming;
- function/custom tool streaming;
- reasoning-summary streaming;
- image/file/audio live-burn estimation unless those modalities are already implemented and separately scoped;
- stateful Responses;
- hosted tools;
- MCP/connectors.

---

## 20. Milestone status note

This document now records both the implemented Chat Completions streaming
live-burn slice and the remaining Responses future milestone. Runtime support
is strictly limited to `POST /v1/chat/completions` with `stream=true`;
Responses live-burn monitoring must happen through a separate scoped PR.
