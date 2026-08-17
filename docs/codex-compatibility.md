# Codex CLI Compatibility

Status: **PARTIAL REQUEST-ENVELOPE SUPPORT, NOT CODEX-COMPATIBLE**.

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
| Current runtime status | Non-tool envelope slice only; still `not_compatible` |

Primary references:

- [Codex configuration reference](https://developers.openai.com/codex/config-reference)
- [Codex advanced configuration and custom providers](https://developers.openai.com/codex/config-advanced)
- [Codex 0.147.0 release](https://github.com/openai/codex/releases/tag/rust-v0.147.0)
- [Pinned request-compression tests](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/tests/suite/request_compression.rs)
- [Pinned model-catalog schema](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/protocol/src/openai_models.rs)
- [Pinned loopback Responses server](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/app-server-test-client/src/loopback_responses_server.rs)
- [Pinned Responses metadata vocabulary](https://github.com/openai/codex/blob/rust-v0.147.0/codex-rs/core/src/responses_metadata.rs)

The bundled model metadata is part of the pin. For this binary,
`gpt-5.6-sol` selects Responses-lite/code-mode behavior, a `shell_command`
shell type, freeform apply-patch support, parallel tool calls, and text/image
input. A CLI version alone is therefore not a sufficient compatibility key.
`codex debug models --bundled` reads the catalog compiled into the binary
without a remote refresh. Codex also supports `model_catalog_json` to replace
the startup catalog; using a replacement would be a different profile and
requires a distinct fixture and review.

## Future user configuration

Codex custom-provider selection belongs in the user's Codex configuration, not
in a repository checkout. The official configuration reference states that
project-local config cannot safely override provider/authentication settings,
including `model_provider` and `model_providers`.

The intended configuration after a future compatibility objective succeeds is:

```toml
model = "gpt-5.6-sol"
model_provider = "slaif"

[model_providers.slaif]
name = "SLAIF API Gateway"
base_url = "https://api.ulfe.slaif.si/v1"
env_key = "OPENAI_API_KEY"
wire_api = "responses"
requires_openai_auth = false
```

The user would set the normal OpenAI-compatible variable to a gateway-issued
key:

```bash
export OPENAI_API_KEY="sk-slaif-..."
```

SLAIF validates that gateway key and later substitutes the server-side upstream
provider credential. The example is a target configuration only: the captured
0.147.0 profile is currently rejected and must not be presented as working.

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
`wait_agent`. They are evidence of the client request shape, not a SLAIF tool
allowlist or execution permission. Tool-description values, schema property
names, defaults, examples, grammar-definition values, prompts, instructions,
client IDs, and authorization values are absent from the fixture.

Because required captured elements are rejected, the overall status is
`not_compatible`. Endpoint/model permission must not be interpreted as Codex
tool permission.

## Current bounded request-envelope slice

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

This is not a Codex compatibility claim. The captured profile still includes
Responses-lite `additional_tools`, namespace/nested tool containers, a
tool-dependent `tool_choice`, and Codex reasoning/tool stream event families
that remain denied pending objectives 006 through 008. Hosted tools, MCP,
background/state expansion, and WebSocket behavior are also not enabled.

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
```

Normal pytest, CI, application startup, packaging, Docker, migrations, and HPC
verification must never run either live action.

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

Objectives 006 through 011 remain separate strategic work-order boundaries.
The request-envelope slice grants none of them implicitly. Responses-lite
input/tool handling, permission mapping, streaming expansion, quota/accounting
work, end-to-end validation, operator guidance, and any release decision each
require their own activated scope, tests, privacy review, and GitHub acceptance.
Until then, SLAIF makes no Codex production, provider, or release compatibility
claim.
