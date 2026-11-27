# Static client and server module architecture

> **Status:** Current internal architecture contract
> **Audience:** Maintainers and contributors

SLAIF keeps protocol decoding and upstream translation in statically registered
modules while the Gateway core remains the sole authority for authentication,
effective policy, routing, quota, accounting, Redis controls, pricing, audit,
privacy, and failure behavior.

See [the detailed normative agentic-client integration contract](../AGENTIC_CLIENT_INTEGRATION.md)
for the versioned client/server boundaries and qualification rules.

```text
client → client module → Gateway core → server module → upstream
```

## Unequal trust interfaces

Client modules receive only an endpoint and the validated-at-ingress mapping
needed to normalize an untrusted client dialect. They return fresh canonical
request facts, bounded capability intents, and explicitly untrusted identity
hints. They cannot authenticate, query PostgreSQL, use Redis, select a route or
provider, reserve quota, price, audit, perform HTTP, or grant authority.

Server modules receive only core-resolved provider/route facts and a canonical
provider request after policy and admission. They return the existing safe
provider response, stream, usage, and failure types. They cannot authenticate a
public key, mutate policy, reserve or finalize quota directly, or receive the
public Gateway bearer.

The initial default client module is the immutable `openai-default` module for
ordinary Chat Completions and Responses create traffic. Versioned Codex client
modules are separate static entries: `codex-0.147-responses-v1` owns the
qualified legacy profile; `codex-0.149-responses-v1` owns its bounded
structural request facts (version `5` adds the optional bounded
`additional_tools` declaration item ID); and `codex-0.162-responses-v1`
owns its bounded 0.162.1 additional-tools profile as a data-revision module:
the effective module version is the validated profile DATA revision
(packaged default revision `8`) and the fixture digest binds the canonical
digest of the shipped compatibility policy DATA
(`slaif_gateway/modules/clients/profiles/codex_0162.json`), which defines the
namespace literals/prefixes, bounded identifier grammar, and ceilings
(including the namespace-scoped leading-underscore connector tool names).
Schema-2 [client compatibility presets](client-compatibility-presets.md) also
own optional metadata field/value rules and bounded feature modes. The core
uses a generic interpreter around its existing validators; it does not infer
allowances from revision numbers. No preset can override protected fields or
permissions.

The operator-only `CODEX_COMPATIBILITY_PROFILE_FILE` override loads a
validated data revision >= 3 once at bootstrap with the same installed
engine and no rebuild; data revisions `1`/`2` remain frozen migration
selectors only. These newer
modules are
default-denied: `codex-0.149-responses-v1` has one reviewed
`local-coding-v1` pair, and `codex-0.162-responses-v1` has reviewed
`local-coding-v1`, `local-coding-vLLM`, and `configured-upstream-llm`
pairs. The registry binds ONE profile DATA revision per process (one-shot
guarded bootstrap), and the shipped preset `codex-0.167.1` (DATA revision
`16`) additionally activates the bounded positional-update
declaration-history lifecycle (see
[Responses compatibility](responses-compatibility.md)). Pair metadata is
finite compatibility data; it does not grant an endpoint, model, route,
provider, capability, pricing mode, hosted tool, or key permission.

`modules/clients/registry.py` exposes the active identity through one
accessor, `active_client_module_facts(module_id)` (responses registry
first, then the agent-chat registry; `.pin` is the exact
`{id, version, fixture_sha256}` triple). The admin GUI key-create
client-use choices and the compatibility dashboard read the active
snapshot through that accessor to build and annotate NEW key pins
(229-a); frozen qualification constants remain evidence only and are
never a runtime version gate.

## Static registration

Module IDs, versions, descriptors, factories, and client/server pairings are
literal source-code allowlists under `app/slaif_gateway/modules/`. Unknown IDs,
duplicate registrations, unsupported endpoints, and absent pairings fail closed
before provider construction and before a new side effect. The architecture
does not use `importlib`, entry points, arbitrary dotted paths, reflection-based
loading, package discovery, admin-supplied classes, a plugin marketplace, or a
third-party module SDK.

The old `slaif_gateway.modules.facial_scoring` import path is a thin
compatibility re-export. Its implementation is shared with ZAP-IT under
`modules/servers/completion_service/`; the former server path also re-exports
the same class. Strict external JSON profiles select reviewed transport and
response-mapping primitives, not code paths or plugin classes. One `configured-completion` descriptor serves every configured service;
legacy provider/default-profile bindings are JSON data. No service name selects
a code branch or adapter class. The generic output-field mapper supports text
plus one inline image using configured JSON pointers. See [completion services](completion-services.md). Provider construction delegates to the
server registry; there is no parallel production factory.

## Chat client profile selection

The first agent-harness Chat profiles are served by a shared neutral Chat
profile engine (`modules/clients/agent_chat.py`): one pure, data-driven
decoder for every reviewed Chat profile, with thin statically shipped
harness bindings (`hermes_0225_chat`, `opencode_1193_chat`) that bind one
packaged profile document each. The initial entries are
`hermes-0.22.5-chat-v1` (profile DATA revision `2`, fixture digest
`c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327`) and
`opencode-1.19.3-chat-v1` (DATA revision `1`, fixture digest
`2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14`).
Both are `chat_completions` wire profiles; their tool vocabularies,
assistant reasoning fields, reasoning-effort values, tool-call ID grammar,
and per-profile ceilings ship as trusted validated DATA under
`modules/clients/profiles/`, not as Python tool-name inventories.

A Chat profile is selected ONLY from the optional authenticated
server-side key metadata tuple `metadata_json.chat_client_module`
(`{id, version, fixture_sha256}`). An absent pin keeps the existing
`openai-default` Chat behavior unchanged, and a present explicit `null`
clears only the Chat binding during key configuration updates. A present
pin that is malformed, unknown (including Responses-only modules), stale,
or digest-mismatched fails closed before Chat admission; it never
silently degrades to the default and never affects the Responses
endpoint, whose `responses_policy.client_module` pin remains
Responses-scoped. Headers, User-Agent strings, model names, and
client-request metadata never select or widen a profile.

Chat profiles pair only with explicit, finite, Chat-capable server
transports (generic OpenAI-compatible candidate pairs). The signed Local
Coding server module remains a Responses-only transport and cannot serve
Chat. As with every module, pairing is compatibility data, not an
endpoint, route, provider, capability, pricing, or authority grant:
policy, caps, routing, quota, pricing, and PostgreSQL accounting stay
Gateway-core facts.

Data-versus-engine upgrade boundary: a data-only vocabulary upgrade is
new document bytes with a new digest and requires a re-pinned operator
key and process restart; there is no per-tool source upgrade, automatic
upgrade, or silent key-rotation path. Engine semantics changes are
version-owned in source. Both profiles remain preprotected candidates and
nothing in the profile DATA grants live qualification (see the client
dossiers under [agentic clients](agentic-clients/hermes-0.22.5-chat-v1.md)).
The protected live-qualification gate was `not_run` through 227-b; a
bounded, human-authorized live LAN qualification was executed in 227-c
against the pinned Hermes 0.22.5 and OpenCode 1.19.3 clients only (generic
OpenAI-compatible candidate pairs), and is recorded in the
[consolidated verification record](verification/2026-11-20-hermes-opencode-chat.md).
That execution grants no Responses, plugin, MCP, or image claim, no future
client version, and no production certification; the stock-native retry
exception applied only to that 227-c execution, and the downstream hop
beyond the gateway-to-provider edge remains unverified.

## OpenCode Responses client profile

Pinned native OpenCode Responses support is served by the dedicated static
client module `opencode_1193_responses` (module id
`opencode-1.19.3-responses-v1`, engine version `1`), which binds one packaged
profile document under `modules/clients/profiles/opencode-1.19.3-responses.json`
(fixture digest
`592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff`). The
profile DATA records the reviewed client identity — OpenCode 1.19.3
(source tag `v1.19.3`, source commit
`e3c4eb242585dcd77be1a867391b7c25fd47ce52`), `@ai-sdk/openai` 3.0.88,
Responses wire API — and a frozen dialect: reasoning efforts
`minimal`…`xhigh`, the nine bounded local tool names `bash`, `edit`,
`glob`, `grep`, `read`, `skill`, `task`, `todowrite`, `write`, and bounded
declaration limits. The profile ships as validated DATA, not as a Python
tool-name inventory.

The module is selected ONLY from the authenticated server-side key metadata
tuple `metadata_json.responses_policy.client_module` (`{id, version,
fixture_sha256}`). An absent pin keeps the default Responses module
unchanged; a present malformed, unknown, stale, or digest-mismatched pin
fails closed (`client_module_metadata_invalid`,
`unsupported_client_module`, or `client_module_fixture_mismatch`) before
admission — a present-but-`null` digest is rejected as a fixture
mismatch. Headers, model names, and request metadata never select a module.

The normalized body is the exact captured first-turn shape and is
streaming-only: the top-level field set is exactly `{include, input,
max_output_tokens, model, reasoning, store, stream, tool_choice, tools}`;
`stream` must be `true` (a `false` value is denied with
`opencode_1193_field_shape`), `store` must be `false`, `tool_choice` must be
`"auto"`, `include` is limited to `reasoning.encrypted_content`, input roles
are `developer`/`user`, and `tools` is the flat strict function declaration
list drawn from the nine bounded names. No per-request relaxation exists.

The OpenCode Responses module pairs only with the two named server
transports `openai` and `openai-compatible`; the signed Local Coding server
module and every other server module are rejected. As with every module,
pairing is compatibility data, not an endpoint, route, provider, capability,
pricing, or authority grant.

Id-less encrypted reasoning: the pinned SDK replays `function_call` /
`function_call_output` and encrypted reasoning items without item IDs or
statuses, so the module opts into the `allow_idless_encrypted_reasoning`
policy flag and the owned ciphertext-derived reference path. References bind
a domain-separated v3 digest of the bounded ciphertext (immediate memory
only), persist only after successful finalized output, and are bound to the
same key and route/provider/model. No fabricated protocol IDs, no raw
reasoning content, and no schema change are introduced; present invalid IDs
and any issued-ID/ciphertext association keep their existing denials. The
legacy Codex and default presets are unchanged.

Retry and streaming boundaries: the gateway-side strict zero-retry
forwarding rule is a gateway policy, not a promise about native client
behavior. The pinned OpenCode session hardcodes a bounded native retry
policy (`RETRY_MAX_RETRIES=5`, no override parameter) above an SDK default
of zero retries, so zero native HTTP retries must never be claimed for this
profile; the 227-c human-authorized bounded LAN qualification (Chat
profiles) is executed historical evidence whose documented stock-retry
exception applied to that execution only. The standing, separately
approved bounded 228 LAN plan for this Responses module (human-approved;
execution gated on the root CI/setup review of the frozen candidate, not a
new human decision) explicitly allows stock native retries as a plan term.
The 228-b streaming-gap ruling is resolved: L1/L3 are implemented
(lifecycle dispatch independent of a non-empty tool count; the tool-event
flag plus the exact active `(functions, name, function)` set gates new
tool execution), L2 is intentionally not implemented (a fake-added
`response_id` is not client-wire authority; the shared strict
`_only_fields` check is not relaxed; the loopback fake no longer emits an
artificial `response_id`), and the pinned-SDK required output/content
indexes are enforced on the selected profile with legacy validators
unchanged.

Data-versus-engine upgrade boundary: a data-only profile upgrade is new
document bytes with a new digest and requires a re-pinned operator key and
process restart; the module itself introduces no database migration. Engine
semantics changes are version-owned in source. This profile remains a
preprotected candidate with the mock half of its preprotected obligations
completed: six pinned OpenCode 1.19.3 loopback cases (assistant tool loop,
encrypted reasoning continuation, visible reasoning absent/null/empty,
and compaction) passed through the actual task Gateway and real PostgreSQL
against the separate loopback upstream fake, as recorded in
`docs/verification/2026-11-23-opencode-responses-preprotected.md`. The LAN
half and the protected live-qualification gate remain `not_run` for this
module, and the profile grants no production-certification claim.

## Change ownership

The [configurable upstream LLM adapter](upstream-llm-adapter.md) is the single
`configured-upstream-llm` descriptor for operator-owned Responses compatibility
profiles. It composes reviewed instruction-placement and native tool-codec
operations from strict revision/digest-bound JSON data. Existing Local Coding
and native-vLLM routes retain their original adapters until a route explicitly
selects the new module. Static registration and client/server pairing remain
in code; profile names cannot select executable classes.

Client syntax and dialect changes should normally remain client-module changes.
Upstream protocol, header, body, and response translation changes should
normally remain server-module or shared transport changes. Any new authority,
admission, quota, pricing, accounting, audit, retention, or privacy semantics
require Gateway-core review even when a module is involved.

The current facial-scoring module remains the bounded post-MVP,
non-streaming Chat image adapter. Its fixture packaging, hashes, dimensions,
manifest provenance, zero-EUR request pricing, authentication, accounting,
privacy, retry, and error behavior are unchanged.

Codex 0.149 client syntax is structurally captured and registered with exactly
one static Local Coding server pair. The pair is non-authorizing: endpoint,
model, route, provider, capability, pricing, quota, accounting, identity, and
tool decisions remain Gateway-core facts. The Local Coding server module is a
Responses-create/Responses-SSE transport only; it uses a separate service
Bearer and, in signed mode, derived opaque HMAC identity fields. Its
process-local inclusive-horizon fail-closed replay boundary
(`process_local_inclusive_horizon_fail_closed`) requires the reviewed
single-worker deployment contract; signed routes carry explicit bounded
skew/TTL metadata that the Gateway validates while the Local peer configures
it out-of-band, and server module version `2` records that replay-behavior
change without changing the `local-coding-v1` contract ID. The observed `tool_search` and `web_search` declarations
remain bounded adapter-managed candidates and never grant hosted authority.

The Local Coding SSE transport uses a module-local incremental byte framer
before shared typed validation. It bounds one line, one wire frame, joined
`data:` bytes, and data-segment cardinality using the reviewed static
derivation in the provider-forwarding contract. It consumes raw identity
encoding, rejects unsupported content encoding before iteration, strictly
decodes complete lines/data, and exposes only content-free peak-state
diagnostics. This boundary is Local Coding-specific; OpenAI/OpenRouter Chat
and generic Responses adapters retain their separate streaming paths.
The exact Codex 0.149 Local pair additionally owns the bounded visible-
reasoning request dialect and the strict reasoning/function/message stream
profile. Module version `4` additionally carries a default-empty, request-
derived fact for exact top-level zero-argument function declarations. Only the
pair-local strict stream validator consumes that fact, and it accepts the
provider's empty-string closure without synthesizing an argument event. The
ordinary delta/`arguments.done` lifecycle, generic/default clients, and other
pairs remain unchanged. Visible reasoning may omit or explicitly null its item
ID without
fabrication; encrypted reasoning remains independently ID-bound and gated.
ID-less function/custom tool-call items are part of the exact 0.149 Local pair
only: the mandatory call ID is authenticated through the existing same-key,
same-route/provider/model HMAC replay reference, without fabricating an item
ID. The second-turn adjacent call/output contract remains pair-local and
default-denied for every other client or server.

Client-module profile facts are limited to the reviewed module ID, version,
and fixture digest. One bounded operator migration path exists for pinned
0.149-v4 keys: the `codex` CLI upgrade/rollback commands move the
`client_module` compatibility metadata between the frozen 0.149-v4 tuple and
either 0.149-v5 or 0162-v1, and keys on the exact 0162-v1 tuple may hop
to 0162-v2 (and back), with only those six transition edges legal,
dry-run by default, and no schema or quota change. For the 0162 data
profile, `codex migrate-key-profile` moves one exact key between the active
bootstrap profile snapshot and the frozen 0162-v1/v2 legacy tuples using an
explicit `--from-version`/`--from-digest` source (dry-run by default,
single-transaction row-locked metadata + audit); same-revision/different-
digest drift fails closed, and legacy/stale pins are denied until an
explicit migration. Identity hints from Codex
metadata are transient
untrusted input and are never stored, logged, audited, exported, hashed, or
forwarded.

## Qwen Local coding compatibility continuation

The packaged 0.162 profile is now revision **8**. Engine changes are version
owned: revision 4 permits schema property-map labels such as `secret` while
still recursively checking their values for provider authority; revision 5
adds only the custom grammar tool `functions.apply_patch` through declaration,
streaming, and replay; revision 6 accepts bounded Local visible reasoning SSE
with omitted `output_index` and empty encrypted content; revision 7 permits
that same empty-ciphertext visible reasoning in continuation input. An empty
ciphertext never creates an encrypted-replay reference or authorization.
Revision 8 accepts sparse Local function-argument deltas and bounded argument
done events tied to the active declared call, with exact argument matching and
duplicate/late-event rejection. Existing visible-text shape, size, capability,
and opaque replay checks remain.
Ordinary Responses and older client modules keep their own policies.

These semantics require the updated engine; editing profile DATA alone cannot
install them. No database migration is needed. Upgrade key pins explicitly;
see the [Qwen runbook](runbooks/codex-qwen38.md),
[clean client examples](../examples/codex/qwen38-27b/README.md), and
[bounded verification record](verification/codex-qwen38-live-smoke.md).

The static `vllm-chat-video-v1` server module is Chat-only and pairs with the
default client. Explicit route metadata supplies its inline video frame cap;
it delegates ordinary wire forwarding and credentials to the existing native
OpenAI-compatible adapter. It has no key, quota, accounting or routing authority,
and creates no new Codex client/server pair. See
[media input estimation](media-input-estimation.md).
