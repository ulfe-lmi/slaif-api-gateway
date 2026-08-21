# Codex CLI Compatibility

Status: **LOCAL GATEWAY E2E QUALIFIED FOR ONE PINNED PROFILE; BOUNDED REAL
OPENAI PILOT PREPARED; REAL PROVIDER E2E NOT RUN**.

This is the canonical versioned contract for Codex CLI traffic through SLAIF.
It records evidence; it does not enable Codex traffic, relax gateway policy, or
claim production/provider compatibility.

## Captured baseline

Checked on 2026-08-18:

| Property | Pinned value |
| --- | --- |
| Binary | `/usr/bin/codex` |
| Raw version output | `codex-cli 0.147.0` |
| Official release/source tag | `rust-v0.147.0` |
| Bundled model | `gpt-5.6-sol` |
| Capture profile | `api-key-responses-baseline` |
| Wire endpoint | `POST /v1/responses` |
| Fixture | `tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json` |
| Approved canonical fixture SHA-256 | `436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432` |
| Immutable 004-baseline compatibility result | `not_compatible` |
| Current runtime status | Exact local gateway E2E qualified for the pinned route/key/profile contract below; bounded real-OpenAI pilot prepared but not executed; `real_provider_e2e=false` and full compatibility is not claimed |

Primary references:

- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Codex advanced configuration and custom providers](https://developers.openai.com/codex/config-advanced)
- [Codex 0.147.0 release](https://github.com/openai/codex/releases/tag/rust-v0.147.0)
- [Pinned request-compression tests](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/tests/suite/request_compression.rs)
- [Pinned model-catalog schema](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/protocol/src/openai_models.rs)
- [Pinned loopback Responses server](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/app-server-test-client/src/loopback_responses_server.rs)
- [Pinned Responses metadata vocabulary](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/src/responses_metadata.rs)
- [Pinned Responses-lite tool serialization](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/tools/src/responses_api.rs)
- [Pinned Responses-lite namespace construction](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/tools/src/tool_spec.rs)
- [Pinned Responses-lite request construction](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/src/client.rs)

The bundled model metadata is part of the pin. For this binary,
`gpt-5.6-sol` selects Responses-lite/code-mode behavior, a `shell_command`
shell type, freeform apply-patch support, parallel tool calls, and text/image
input. A CLI version alone is therefore not a sufficient compatibility key.
`codex debug models --bundled` reads the catalog compiled into the binary
without a remote refresh. Codex also supports `model_catalog_json` to replace
the startup catalog; using a replacement would be a different profile and
requires a distinct fixture and review.

## Protocol qualification and profile-v2 configuration

Qualification profiles are immutable server-defined registry entries. The
current built-in entry is `openai-gpt-5.6-sol-codex-0.147-v1` (registry
metadata version 2), pinned to CLI `0.147.0`, model `gpt-5.6-sol`, OpenAI
Responses/compact, the limits below, and the fixture digest in this document.
Route metadata may contain only the exact `{version, profile_id,
fixture_sha256}` identity declaration; it cannot declare capabilities, limits,
provider claims, or qualification. Unknown, drifted, mixed, or mismatched
declarations fail closed. Version-1 `codex_qualification` remains supported
unchanged for the existing route pair.

The registry distinguishes configured, mocked-conformant, protocol-qualified,
and live-qualified evidence. The built-in profile is protocol-qualified from
local mocked/provider-boundary evidence; `real_provider_e2e` and live
qualification remain false. No later model or provider is registered as
qualified by this framework objective.

Codex custom-provider selection belongs in the user's Codex configuration, not
in a repository checkout. The official configuration reference states that
project-local config cannot safely override provider/authentication settings,
including `model_provider` and `model_providers`.

Objective 010 adds a strict local `protocol_qualified` state. It is neither a
model-name inference nor a production/real-provider claim. Both an exact
enabled `/v1/responses` route and its reciprocal exact
`/v1/responses/compact` route must carry the complete pinned
`capabilities.codex_qualification` object, exact route gates and
`codex_limits`, one another's UUID, enabled provider metadata, and active
complete pricing/accounting (including FX when needed). Both rows must also be
selected by normal provider-constrained runtime ranking, so a stale qualified
row shadowed by another matching route fails closed. Each nested Responses map
must also pass the existing runtime parser for its exact operation: both require
`text=true` and strict known boolean flags, ordinary Responses requires
stateless streaming plus route streaming, and compact requires `compact=true`;
the fully gated operation checks all five Codex gates and strict limits.
Missing declaration is `not_declared`; malformed, partial, unknown, disabled,
stale, or incomplete state is invalid/not ready with fixed safe reason codes.

Codex 0.147.0 profile v2 loads a named file over the base user config. The
gateway renderer therefore returns two separate credential-free artifacts. The
first is a fragment to merge into `$CODEX_HOME/config.toml`:

```toml
[model_providers.slaif]
name = "OpenAI"
base_url = "https://api.ulfe.slaif.si/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
requires_openai_auth = false
supports_websockets = false
```

The second is the complete gateway-owned content for
`$CODEX_HOME/slaif.config.toml`:

```toml
model = "gpt-5.6-sol"
model_provider = "slaif"

[features]
remote_compaction_v2 = false
```

Do not add `profile = "slaif"`, `[profiles.slaif]`,
`[profiles.slaif.features]`, or `model_catalog_json`. Those are not the
reviewed profile-v2 contract. Exact bundled slug `gpt-5.6-sol` supplies the
pinned model catalog and instructions.

The user would set the normal OpenAI-compatible variable to a gateway-issued
key:

```bash
export OPENAI_API_KEY="sk-slaif-..."

codex --profile slaif
```

SLAIF validates that gateway key and later substitutes the server-side upstream
provider credential. `slaif-gateway codex inspect` reports only deterministic
safe qualification fields from local configuration.
`slaif-gateway codex profile --base-url https://api.ulfe.slaif.si/v1` prints
the two distinct artifacts after requiring exactly one ready Responses pair;
`--json` returns the same fixed targets and contents without credentials. The
commands never write Codex config or accept/read a key. The admin route pages
show the parsed badge/reasons while retaining raw capabilities for audit.

The admin key-creation Codex protocol-pilot checkbox is confirmed and
standard-key-only. It requires exactly one ready provider, model
`gpt-5.6-sol`, endpoints `/v1/models`, `/v1/responses`, and
`/v1/responses/compact`, no allow-all policy, positive finite request/token/EUR
cost limits, and an audit reason. A fresh readiness check happens before key
mutation. The resulting Responses policy contains only the five canonical
Codex gates and local `function`/`custom` tool types. This does not enable
hosted tools, MCP, background work, provider state, trusted calibration, or
external execution. The plaintext-once and direct email-delivery creation
results show only those fixed capability/tool names when the policy exists;
the email result still contains no plaintext, and ordinary no-policy and
rotation/template results omit the section.

The profile verifier uses the rendered two-file layout with exact
`/usr/bin/codex` 0.147.0, a fixed child-only dummy key, dead external proxies,
and a numeric-loopback Responses server. It proves the named profile selects
the exact model/provider, bundled catalog, V1 compaction configuration, and
ordinary uncompressed JSON without legacy-profile/catalog warnings. It prints
only booleans, counts, and version and discards raw payloads. Its truthful
interface is exactly `.venv/bin/python scripts/verify_codex_profile.py`: the
verifier owns its ephemeral loopback URL, accepts no arguments, and rejects
extras with a fixed error that does not reflect operator text. The unified
objective-011 local gateway phase gate is distinct, and
`real_provider_e2e` remains false.

### Unified local gateway phase gate

`scripts/verify_codex_gateway_e2e.py` is the manual objective-011 phase gate.
It runs exact `/usr/bin/codex` 0.147.0 separately for five bounded scenarios
through a real local SLAIF app, an explicitly disposable PostgreSQL test
database, private no-persistence Redis, and a scripted numeric-loopback OpenAI
mock. It covers text plus client-side exec/edit, multi-round tool and encrypted
reasoning replay, below/edge/above long-context usage, cache read/write,
reasoning usage, V1 compact and continuation, pre-provider hard-quota
rejection, stream interruption, and a structured provider error.

The verifier requires `TEST_DATABASE_URL`, refuses ambient `DATABASE_URL`,
any scheme other than `postgresql+asyncpg`, non-numeric-loopback hosts,
implicit ports, query strings, fragments, whitespace/control ambiguity, and
database names without `test`, `dev`, or `local`. The canonical URL has an
explicit safe user, optional simple password, `127.0.0.1`, explicit TCP port,
and one disposable database path; socket/host/options overrides are rejected.
The operator must create one empty disposable database explicitly and drop
that exact database after the run. The only supported invocation is:

```bash
unset DATABASE_URL OPENAI_API_KEY OPENAI_UPSTREAM_API_KEY OPENROUTER_API_KEY
unset RUN_UPSTREAM_TESTS
TEST_DATABASE_URL='postgresql+asyncpg://USER:PASSWORD@127.0.0.1:5432/DISPOSABLE_TEST_DB' \
  .venv/bin/python scripts/verify_codex_gateway_e2e.py
```

`USER`, `PASSWORD`, and `DISPOSABLE_TEST_DB` are placeholders; set the actual
dummy DSN through a private environment mechanism and never print or retain it
in shell history. The script migrates only the validated target, generates
standard keys through `KeyService`, and uses one shared preparation path to
create and verify a `0700` temporary root/home/workspace plus two `0600`
credential-free profile-v2 files before every child. It keeps raw HTTP/SSE/
subprocess material only in bounded memory. Exact proof requires the linked
successful exec-output sentinel and exact structured final marker, complete
Decimal component/native/EUR cost mappings and zero reserved money for every
successful key/ledger, exact zero-cost failure ledgers, and distinct
interruption/provider-error body sentinels. All per-run values join the known
text/JSON-column scan; replay rows must remain HMAC-only. Fixed output contains
booleans and counts only. Normal pytest, CI, application startup, import,
packaging, migrations, Docker, and HPC do not invoke it.

This establishes only:

```text
local_gateway_e2e_qualified=true
bounded_real_openai_pilot_prepared=true
real_provider_e2e=false
```

The separately authorized human procedure is
[Codex 0.147.0 bounded OpenAI pilot](runbooks/codex-openai-pilot.md). It was not
run by objective 011 and is not permission to call a real provider.

## Capture and privacy boundary

`scripts/capture_codex_protocol.py` is a manually invoked evidence tool, not an
application component or test runner. For every live capture it:

- checks exact raw/normalized CLI version before binding or writing;
- uses a private temporary `CODEX_HOME` and empty working directory;
- passes `--ephemeral`, `--ignore-user-config`, `--ignore-rules`,
  `--skip-git-repo-check`, read-only sandbox, and approval policy `never`;
- disables startup update checks and supplies no search flag, MCP configuration,
  plugin state, auth store, history, memory, rules, or project `AGENTS.md`;
- removes inherited provider/auth variables by constructing a small child
  environment and supplies one fixed dummy token only;
- binds an ephemeral server to numeric `127.0.0.1` and accepts exactly one
  bounded `POST /v1/responses` request;
- keeps raw headers/body and subprocess output in memory only, then discards
  them without printing or writing them;
- persists only allowlisted structural types, field names, discriminators,
  tool taxonomy/schema shape, selected catalog metadata, and safe findings.

The fixed mock sends only `response.created` and `response.completed` with one
synthetic ID and zero synthetic usage. Codex accepted the stream and exited
successfully. No model output or tool execution occurred.

The API-key capture had no request `Content-Encoding`. This matches the pinned
official test showing that API-key authentication is not compressed even when
request compression is enabled. The separate ChatGPT-backend authentication
path can use zstd when enabled. Neither observation is a promise about later
Codex releases, and SLAIF does not add decompression support here.

## Immutable captured compatibility baseline

The checked-in diff is derived from the sanitized request plus the gateway
rules that existed when objective 004 captured it. Those classifier constants
are now frozen and clearly named as the 004 baseline so later runtime support
cannot rewrite historical evidence. The fixture and its SHA remain unchanged,
and live verification must still reproduce the exact canonical document.

Supported top-level names observed were `input`, `model`, `store`, `stream`,
`text`, and the `tool_choice` field name. `tool_choice` is nevertheless rejected
for this request because Responses-lite carries tools inside an input item
instead of the gateway's required top-level local-tool array.

| Captured element | Immutable 004-baseline result | Safe reason code |
| --- | --- | --- |
| `client_metadata` | Rejected | `responses_field_not_supported` |
| `include` | Rejected | `responses_multimodal_not_supported` |
| `parallel_tool_calls` | Rejected | `responses_tools_not_supported` |
| `prompt_cache_key` | Rejected | `responses_state_not_supported` |
| `reasoning` | Rejected | `responses_field_not_supported` |
| `text.verbosity` | Rejected | `responses_field_not_supported` |
| `tool_choice` without top-level `tools` | Rejected | `responses_tool_choice_invalid` |
| `additional_tools` input item | Rejected | `responses_input_item_type_not_supported` |
| Captured message items carrying `id` | Rejected | `responses_input_item_invalid` |
| `namespace` tool containers | Rejected | `responses_hosted_tool_not_supported` |
| Nested tools inside captured namespaces | Rejected with their container | `responses_hosted_tool_not_supported` |
| `response.created` | Supported event | `supported_stream_event` |
| `response.completed` | Supported terminal event | `supported_stream_event` |

The observed namespaces are `functions` and `collaboration`. Sanitized nested
tool names are `exec`, `wait`, `request_user_input`, `followup_task`,
`interrupt_agent`, `list_agents`, `send_message`, `spawn_agent`, and
`wait_agent`. In the immutable fixture they are evidence, not authorization;
the separately gated runtime allowlist is defined below and grants no execution
permission. Tool-description values, schema property
names, defaults, examples, grammar-definition values, prompts, instructions,
client IDs, and authorization values are absent from the fixture.

Because required captured elements were rejected by the frozen 004 classifier,
that historical result remains `not_compatible`. Current runtime support is
documented separately below; endpoint/model permission still must not be
interpreted as Codex tool permission.

## Current bounded request, declaration, and streaming round-trip slices

Current runtime policy can accept a tool-free projection of the captured
request envelope, but only through two explicit gates using the same capability
name:

- the authenticated key's sanitized
  `responses_policy.allowed_capabilities` must explicitly contain
  `codex_request_envelope`; and
- the resolved route must explicitly set
  `capabilities.responses.codex_request_envelope=true`.

The key gate is default-deny for missing or malformed policy and returns
`responses_codex_envelope_not_allowed` before route or database work. The route
flag is a known capability whose conservative default is `false`; route denial
happens before Redis, pricing, quota reservation, or provider work. Headers and
model names do not identify or authorize Codex traffic.

With both gates, `POST /v1/responses` accepts and reconstructs only:

- `include`, canonicalized to the exact singleton
  `reasoning.encrypted_content`;
- boolean `parallel_tool_calls` without granting tool permission;
- an opaque, non-empty UTF-8 `prompt_cache_key` of at most 256 bytes;
- bounded `reasoning` containing `effort` and optional
  `context="all_turns"`;
- `text.verbosity` as `low`, `medium`, or `high`, composed with the existing
  approved `text.format` surface; and
- a bounded conservative ASCII `id` on otherwise-supported message items.

`client_metadata` is accepted only as a small string-valued object using the
pinned 0.147.0 source vocabulary: `x-codex-installation-id`, `session_id`,
`thread_id`, `turn_id`, `x-codex-window-id`, and
`x-codex-turn-metadata`. The embedded turn-metadata string is never parsed.
After validation the entire object is dropped: it is not forwarded, metered,
hashed, stored, logged, audited, exported, or echoed. Prompt-cache values and
message IDs are forwarded transiently but are likewise never stored, logged,
audited, exported, echoed, or treated as identity/state authority.

Provider-forwarded envelope and message-ID material is counted conservatively
in admission estimation. Estimation evidence exposes only safe field names and
byte/token counts, never values. Provider final usage/cost remains authoritative.

Responses-lite client-tool declarations form a second, independent slice. An
`additional_tools` input item is accepted only when the key and route each
enable both `codex_request_envelope` and `codex_client_tools`. Neither
capability implies the other, neither is added to default or calibration policy,
and request headers, model names, endpoint permission, or ordinary top-level
function/custom-tool capabilities cannot substitute for them. Key or shape
denial occurs before route/database work; route denial occurs before Redis,
pricing, quota, or provider work.

The accepted input shape is exactly one `type="additional_tools"`,
`role="developer"` item with exactly two unique namespace containers. The
gateway accepts and emits them in this deterministic order:

| Namespace | Exact nested tools |
| --- | --- |
| `functions` | `exec` (`custom`), `wait` (`function`), `request_user_input` (`function`) |
| `collaboration` | `followup_task`, `interrupt_agent`, `list_agents`, `send_message`, `spawn_agent`, `wait_agent` (all `function`) |

Namespace names, tool names, types, and placement are exact. Unknown, missing,
duplicate, moved, wrong-type, nested namespace, extra-field, hosted, MCP,
connector, authorization, header, secret, approval, server, shell-tool,
apply-patch-tool, computer, web/file search, code-interpreter, image-generation,
and tool-search shapes fail closed. Function schemas reuse the bounded local
function validation plus explicit depth and property-count limits. `exec`
requires a bounded `lark` or `regex` grammar. Its description may explain
client-local shell/patch work, but SLAIF and the provider execute nothing.
Only inside this exact, fully gated taxonomy, each child function/custom tool
description has a fixed 20,000-byte qualification cap and all namespace plus
child descriptions retain the 32,768-byte aggregate cap. The pinned 0.147.0
`exec` description is 18,137 bytes. Namespace descriptions and ordinary
top-level function/custom tools remain capped at 4,096 bytes; model names,
headers, endpoint permission, and ordinary tool capabilities cannot reach the
Codex-only allowance.

The same exact taxonomy permits the singular JSON-schema property `header`
only for `functions.request_user_input` at
`parameters.properties.questions.items.properties.header`. Pinned source uses
it as a short UI label, not an HTTP header. The recursive scan continues below
that schema property and across every sibling; plural/alternate header keys,
the singular key at any other path/tool, and authorization, secret, connector,
server, approval, MCP, and hosted-type markers remain denied. This exception
does not apply to ordinary Responses tools.

With these declarations, `tool_choice` is limited to the strings `none`,
`auto`, or `required`; the pinned profile uses `auto`. Named/object choices are
denied. The declarations, descriptions, schemas, grammar, and choice are
conservatively included in admission estimation and provider input. Safe policy
evidence contains only approved category names and aggregate byte/token counts,
never descriptions, schema property names, grammar, arguments, results, or
client identifiers. Those private values must not be persisted, logged,
audited, or exported, and model-request accounting never claims client tool or
service cost.

Streaming client-tool events and replay form a third independent slice. A
request using them requires all three capabilities on both the key and route:
`codex_request_envelope`, `codex_client_tools`, and
`codex_streaming_tool_events`. The third key gate fails before route/database
work; the third route gate fails before Redis, pricing, quota, or provider work.
It is never added by defaults, trusted-calibration discovery, or ordinary
function/custom-tool permission.

For a request with the exact declarations above, a request-scoped validator
admits only bounded, correctly ordered instances of:

- `response.created` and `response.in_progress`;
- `response.output_item.added` and `response.output_item.done` for declared
  function calls, `functions.exec` custom calls, messages, or reasoning;
- `response.function_call_arguments.delta`;
- `response.custom_tool_call_input.delta`;
- `response.reasoning_summary_part.added`,
  `response.reasoning_summary_text.delta`, and
  `response.reasoning_summary_text.done`;
- `response.reasoning_text.delta`, `response.output_text.delta`, and
  `response.completed`.

IDs, call IDs, indexes, cumulative arguments/input, text deltas, event counts,
and aggregate bytes are capped and linked incrementally. Unknown event types,
duplicate or orphan items, mismatched IDs/indexes/names/namespaces/types,
unapproved authority, and provider `response.failed`, `response.incomplete`, or
`error` events fail closed to a safe gateway event. The validated
`response.completed` event remains held until usage-backed finalization.

A following stateless request may replay only exact validated function calls or
the declared `functions.exec` custom call together with exactly one immediately
following matching output per call. Orphans, reordered pairs, mismatches,
duplicates, unknown declarations, hosted authority, and over-size payloads fail
closed. Function output remains a bounded string. For the pinned Code Mode
profile only, `functions.exec` output may also be the exact bounded list of
`input_text` parts emitted by Codex 0.147.0. Reconstructed replay input is
deep-copied and all canonical bytes are included in admission estimation.

Encrypted reasoning and durable multi-turn replay form a fourth independent
slice. Encrypted reasoning input and accepted encrypted reasoning done-events
require `codex_request_envelope` plus the default-off
`codex_encrypted_reasoning_replay` capability on both key and route. Streaming
tool generation/replay retains the independent `codex_client_tools` and
`codex_streaming_tool_events` gates. The strict validator accepts
`encrypted_content` only as a non-empty capped opaque string on the exact
`response.output_item.done` reasoning shape with a required safe ID and exact
summary-text array. The replay request additionally permits only the pinned
client's exact `content=null`; the done event itself remains the exact
four-field item. Plaintext/non-empty `content`, unknown/status/authority
fields, wrong-event placement, and per-item or cumulative overflow fail closed;
the validated upstream frame is forwarded unchanged.

Only fully validated reasoning and function/custom done items become transient
reference candidates. After final provider usage and successful PostgreSQL
accounting, the gateway HMACs item/call IDs with domain-separated use of the
existing versioned secret and writes only owner key, source ledger/request,
provider/route/model, kind, approved tool identity, timestamps, and 24-hour
expiry. Raw IDs and HMAC digests are never logged, exposed, or used as provider
state. A later request must resolve every reference to the same key before route
selection, then match provider/route/model before Redis, pricing, quota, or
provider work. Cross-key, expired, unavailable-secret-version, name/kind, and
route mismatches use safe denial. Client replay cannot combine with
`previous_response_id`, stored Responses state, or Conversations. Persistence
failure occurs after accounting, suppresses normal completion, and preserves
charged usage truth.

Encrypted reasoning, summaries, call arguments/inputs, outputs, raw IDs, and
digests never enter PostgreSQL content fields, ledger metadata, logs, metrics,
audit, exports, or errors. Candidate objects contain IDs only until the
immediate HMAC operation and contain no encrypted/summary/argument/result data.

Live-burn monitoring counts output text, function arguments, custom input,
reasoning summary text, and reasoning text. Matching done events are not double
counted; a done value is counted only if its delta family was absent. The event
that crosses a threshold is withheld. Provider final usage/cost remains
authoritative; missing usage, provider error, or disconnect after any counted
output finalizes as estimated interrupted accounting.

Fully gated Codex admission additionally requires a strict top-level route
`codex_limits` object with positive integer `context_window_tokens`,
`default_max_output_tokens`, and `max_output_tokens`, where default <= maximum
< context. It is checked after route resolution and before Redis/pricing/quota.
The qualification profile uses 32,768 default output, 128,000 maximum output,
and 1,050,000 context, also bounded by operator ceilings. These are configured
qualified-model values, not universal hardcoded facts or an unlimited-output
promise; ordinary Responses remains at the 1,024 default.

Codex usage accounting strictly separates cached reads, cache writes, uncached
input, ordinary output, and reasoning output. Route-model pricing metadata must
provide the cache-write rate and long-context threshold/input/output
multipliers. The qualification data uses a 272,000 threshold, 1.25x cache
write, 2x long input, and 1.5x long output. Admission reserves the maximum
plausible rates; actual local accounting uses exact provider components and
applies the long tier to the full request only above the threshold. These are
configuration, not model-name inference, and local calculated cost is not
provider-invoice truth. OpenRouter provider-cost authority remains unchanged.

V1 remote compaction forms a fifth independent slice. Both key and route must
enable `codex_compaction` plus all four earlier Codex capabilities. The request
is rebuilt from the exact pinned compact fields and history, and all prior
HMAC ownership is verified before side effects. Because the pinned V1 request
omits `max_output_tokens`, SLAIF also omits that upstream field while reserving
the validated route maximum (128,000 for the qualification profile) as output
exposure for context, quota, pricing, and safe evidence. The provider must
return one bounded opaque compaction item and supported final usage in a strict
top-level envelope containing only required `output`/`usage` and optional safe
`id`, `object`, and `created_at`. After PostgreSQL accounting, SLAIF persists
only a versioned, length-delimited HMAC over both the item ID and encrypted
content plus safe ownership/routing/expiry metadata; normal compact success
metrics and the response follow that persistence, so a persistence failure is
charged but produces neither normal success signal. Ordinary Responses and
non-Codex compact behavior are unchanged. Neither raw component is stored,
logged, audited, exported, or exposed. Later
create/compact replay must prove the same composite for the same key/provider/
model and an explicitly compatible route. V2 `compaction_trigger`, background,
hosted tools, MCP, and provider-side authority remain unsupported.

Pinned Codex 0.147.0 preserves
`internal_chat_message_metadata_passthrough` for the OpenAI provider identity
used to induce remote compaction. That internal/warehouse-only object can hold
turn and executed-tool details that SLAIF neither needs nor permits downstream.
Only when the key has all five Codex capabilities, the gateway accepts this
exact field as null or a canonical JSON object of at most 32,768 bytes on
message (including omitted `type`), reasoning, function/custom call and output,
or compaction history items. It copies the item, validates the field's type and
size without interpreting nested contents, and deletes the field before normal
item validation. The field is therefore absent from canonical/provider input,
metering, replay candidates, HMAC material, persistence, logs, audits, metrics,
exports, errors, and verifier evidence and contributes zero model-input tokens.
Ordinary or partially gated requests, `additional_tools`, hosted/provider
tools, unknown item types, and any other endpoint retain strict unknown-field
or unsupported-shape rejection; the metadata field grants no authority.

Pinned Codex 0.147.0 also defines optional `id` on
`function_call_output` and `custom_tool_call_output`. Only the fully gated
client-tool replay validator accepts it, using the same non-secret ASCII
item-ID pattern and 128-character limit as other Codex history IDs. A present
ID is preserved in canonical/provider input, included completely in input-token
and cost estimation, and subject to request-wide uniqueness across message,
reasoning, call, output, and compaction IDs. It creates no replay candidate or
separate HMAC authority: the output remains usable only immediately after its
matching HMAC-owned call and `call_id`. Ordinary outputs, malformed IDs,
unknown fields, duplicates, or broken/cross-type linkage remain fail-closed.
Raw output IDs are never persisted, logged, audited, exported, or placed in
safe evidence.

This is one partial client-side streaming tool loop plus opaque V1 compaction,
not general Codex compatibility. Codex/the downstream client owns and performs the local tool
execution; SLAIF only validates and forwards the bounded model protocol.
Hosted tools, MCP/connectors, provider-side authorization,
arbitrary namespaces, shell/patch/computer/web/file-search authority, gateway
tool execution, background/provider state, broader replay, WebSocket behavior,
and production/release claims remain disabled.

## Regeneration and verification

Only a human or active work order may invoke the installed Codex binary:

```bash
.venv/bin/python scripts/capture_codex_protocol.py capture \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --output tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json \
  --write-fixture

.venv/bin/python scripts/capture_codex_protocol.py verify-live \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json

.venv/bin/python scripts/verify_codex_tool_roundtrip.py \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json

.venv/bin/python scripts/verify_codex_reasoning_replay.py \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline \
  --fixture tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json

.venv/bin/python scripts/verify_codex_context_compaction.py \
  --codex-binary /usr/bin/codex \
  --expected-cli-version 0.147.0 \
  --model gpt-5.6-sol \
  --profile api-key-responses-baseline

.venv/bin/python scripts/verify_codex_profile.py
```

The reasoning-replay verifier uses the same private temporary home/work directory,
dummy key, stripped environment, and numeric loopback-only network boundary.
It accepts exactly three in-memory requests. Fixed streams request only
side-effect-free Code Mode `text("SAFE_REPLAY_ONE")` and
`text("SAFE_REPLAY_TWO")`, deliver one synthetic opaque encrypted reasoning
item, and finish only after the third request proves exact client replay of the
reasoning and linked call/output history. It provides no shell, filesystem,
network, or nested-tool authority. Only bounded safe counts/booleans/types are
printed; request bodies, headers, IDs, ciphertext, summaries, arguments,
results, prompts, subprocess output, and assistant text are never persisted or
printed. The older two-request tool-only verifier remains historical focused
evidence.

The context/compaction verifier is also numeric-loopback-only, uses a dummy
key and private temporary directories, and calls no real provider. Its fixed
safe mock exercises prompt-cache reuse, cache-write/cached/reasoning usage on
both sides of the configured long-context threshold, exactly one V1 compact
request, the exact captured body passing the gateway compact policy with route-
maximum exposure, opaque compaction replay, and post-compact continuation. Only safe
counts/booleans/types are emitted; requests, responses, headers, IDs, cache
keys, ciphertext, prompts, tool payloads, subprocess output, and assistant text
are neither printed nor persisted. This is local protocol qualification only;
no production or real-provider qualification occurred.

The objective-010 profile verifier is distinct: it writes the renderer's two
credential-free documents into a private temporary `CODEX_HOME`, passes the
dummy key only in the child environment, and invokes exact Codex 0.147.0 with
`--profile slaif`. Its one ordinary uncompressed Responses request proves that
profile v2 selected the base provider and named-profile model without legacy
profile or replacement-catalog warnings. It discards the request and subprocess
output and prints only the fixed version/boolean/count summary.

Normal pytest, CI, application startup, packaging, Docker, migrations, and HPC
verification must never run any live action.

Pure fixture validation and both live paths pin the complete canonical JSON
document to the approved SHA-256 above after semantic and safety validation.
Appending, removing, or changing any content therefore fails with a fixed safe
integrity error before live evidence can be returned to the write path or
accepted for comparison. The digest is not configurable by command line or
environment.

For a Codex upgrade, create a new version directory and fixture, pin the exact
release tag/model/profile, review the bundled model metadata, repeat the
loopback capture and compatibility diff, and preserve the old fixture. Never
overwrite historical evidence or silently accept wire drift. Any structural
drift requires a new reviewed fixture plus an explicit code/documentation pin;
it cannot silently overwrite the existing evidence.

## Future objectives

Execution and acceptance of the separately authorized real-provider pilot, V2
compaction, and any release decision remain future strategic work-order
boundaries. Local profile materialization, `protocol_qualified`, and the local
gateway phase gate grant none of them implicitly; each requires activated
scope, tests, privacy review, human authorization where applicable, and GitHub
acceptance.
Until then, SLAIF makes no Codex production, provider, or release compatibility
claim.
