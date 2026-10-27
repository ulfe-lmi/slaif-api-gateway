# Configurable upstream LLM adapter

> **Status:** Implemented, with synthetic and mocked transport verification.
> No live provider or complete Codex session qualification is implied.

The `configured-upstream-llm` server module applies operator-selected upstream
compatibility operations after normal gateway validation and admission. It
uses the existing bounded Local Coding Responses transport, credential
handling, identity signing, error handling, and SSE framing. Ordinary endpoint,
key, model, route, quota, replay, pricing and accounting checks still apply.
It supports Responses create and streaming only. It does not implement remote
compaction; Codex client-local summarization uses normal Responses requests.

This addresses a specific mismatch: Codex local compaction can reinsert
developer instructions after retained user messages, while some llama.cpp
Qwen chat templates reject instructions outside the initial block with
`System message must be at the beginning.` It is independent of image-tool
support in the llama.cpp Responses parser.

## Packaged profiles

All three presets use the same adapter class. Profile names are data identities;
they never select Python classes or provider names.

| Profile | Instruction placement | Tool encoding |
| --- | --- | --- |
| `responses-passthrough-v1` | Preserve | Preserve |
| `llama-cpp-qwen-v1` | Leading system/developer block | Preserve |
| `native-vllm-v1` | Preserve | Existing bidirectional native-vLLM codec |

vLLM is a no-op for instruction placement in this configuration. Its tool
declarations and streaming events still require the existing native-vLLM
translation. Native-vLLM limits, request-scoped call linkage, custom-tool
wrapping, event checks and terminal-ID restoration are unchanged.

The instruction operation stably partitions only top-level canonical
`system`/`developer` messages ahead of the remaining input. It preserves their
individual roles, contents, metadata and relative order. All remaining items
retain their relative order and contents, including tool calls, results,
images, reasoning and summaries. It never searches text for role-looking
instructions or promotes user/tool content. Top-level `instructions` remains
unchanged. The operation is idempotent for continued and resumed histories.

**Semantic tradeoff:** moving instructions changes their temporal position.
This is an explicit operator compatibility choice for a prefix-only template,
not a claim that arbitrary histories are semantically identical after
reordering. Use `preserve` for backends that accept the original order.

## Inspect and select a profile

The read-only command prints packaged data and exact selectors without a
database connection or inference:

```bash
slaif-gateway upstream-llm profiles
```

Keep the existing `local_coding` transport contract and add this route-owned
capability for the shipped llama.cpp preset:

```json
{
  "upstream_llm": {
    "version": 1,
    "profile": "llama-cpp-qwen-v1",
    "revision": 1,
    "sha256": "75ba8eda0ed9206474ee091ad1138c641cd4198fe71850322712e944c29a4d7b"
  }
}
```

This is an addition to the complete route capabilities, not a replacement for
the transport, Responses gates, context/output limits or other route policy.
Apply changes through `ModelRouteService.update_model_route` or the audited
route editor, preserving unrelated fields. No key rotation or key-profile
migration is required. The provider kind must be `openai_compatible`.
Native-vLLM, native video and completion-service route selectors cannot be
combined with this selector.

The static registry permits the ordinary OpenAI client and the existing
`codex-0.162-responses-v1` client module to meet this module; pairing grants no
endpoint or tool permissions. Older Codex modules have no new pair. Routes
without `upstream_llm` keep their existing adapters.

## External configuration

Set server-side `UPSTREAM_LLM_PROFILES_FILE` to a mounted absolute JSON file.
Empty uses packaged data. An external file replaces the complete registry;
it is not implicitly merged. For example:

```json
{
  "schema_version": 1,
  "profiles": [
    {
      "profile_id": "my-prefix-only-model-v1",
      "revision": 1,
      "instruction_placement": "leading_system_developer",
      "tool_encoding": "preserve"
    }
  ]
}
```

Only `preserve` / `leading_system_developer` instruction placement and
`preserve` / `native_vllm` tool encoding are accepted. The modes are independent;
other combinations use the same reviewed primitives without a code change.
Native-vLLM tool encoding requires static bearer identity. Preserved tool
encoding also supports the existing signed Local Coding contract.
Normalization precedes serialization and signing, so signatures cover the
exact transformed bytes.

For Docker Compose, mount the file read-only and supply the setting through
an operator overlay (substitute the actual absolute host path):

```yaml
services:
  api:
    environment:
      UPSTREAM_LLM_PROFILES_FILE: /run/slaif/upstream-llm/profiles.json
    volumes:
      - /absolute/operator/profiles.json:/run/slaif/upstream-llm/profiles.json:ro
```

Files must be regular, at most 64 KiB, non-symlink, and not group/world-writable;
external paths cannot traverse symlinks. At most 32 unique profiles are allowed.
Duplicate JSON fields, unknown fields, invalid versions, unknown operations
and stale route pins are rejected. No expressions, templates, imports,
arbitrary JSON rewriting, destinations, credentials or policy overrides are
supported. Client requests cannot select files or profiles.

Inspect proposed data before configuring routes:

```bash
slaif-gateway upstream-llm profiles --file /absolute/operator/profiles.json
```

The HTTP application and database CLI load an immutable process snapshot.
Invalid configured data refuses startup without silently using defaults.
Editing a loaded file has no live effect. Increment the revision for a behavior
change, inspect its new digest, restart all relevant workers with the reviewed
file, and update route pins through the audited service. Coordinate updates
while affected routes are drained: mismatched workers reject stale pins.
Keep the old profile under a separate ID during a staged migration if
uninterrupted rollback is required.

## Verification and rollback

Normal verification is offline. It covers the prefix-only-template failure,
instruction roles and contents, compacted histories and continuation,
tool/image linkage, pass-through byte equivalence, native-vLLM function/custom
translation in non-streaming and SSE transports, exact transformed-body
signing, profile identity/permissions, and unchanged legacy adapters.

A live check, when explicitly authorized, should include compaction followed
by another user turn and a tool round trip. A successful template render alone
does not establish model quality or complete client qualification.

Rollback restores prior audited route capabilities and, for external data,
the prior file and worker snapshot. Do not delete replay references, rotate
keys, reset quotas, or alter client catalogs as part of adapter rollback.
