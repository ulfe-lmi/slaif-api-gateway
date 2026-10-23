# Client compatibility presets

Compatibility vocabulary belongs in operator-owned, versioned JSON files.
The installed engine interprets a bounded rule language; adding an optional
metadata field or changing its allowed values does not require a source patch
or image rebuild. Semantic transport, identity, authorization, replay ownership,
and accounting remain code-enforced contracts.

The existing `CODEX_COMPATIBILITY_PROFILE_FILE` setting selects one file at
process bootstrap. The snapshot is immutable until restart. A configured file
that is missing, malformed, oversized, or unsupported refuses startup. There is
no silent fallback or per-request file reload.

## Shipped files and identities

`slaif-gateway codex presets --json` lists the shipped presets. The index is
`app/slaif_gateway/modules/clients/profiles/presets.json`:

| Preset | CLI provenance | Data revision | Format |
| --- | --- | --- | --- |
| `codex-0.162.1` | `rust-v0.162.1` | 10 | schema 2 |
| `codex-0.163.0` | `rust-v0.163.0` | 12 | schema 2 |
| `codex-0.164.0` | `rust-v0.164.0` | 13 | schema 2 |

The existing static module ID `codex-0.162-responses-v1` names the decoder
generation. Its active version and fixture digest come from the selected data
file, and the preset records exact CLI/source provenance. That ID grants no
client, model, provider, endpoint, or execution permission. Separate client
versions still require separate evidence; shipping a preset is not a broad
qualification or production-certification claim.

The canonical digest binds the entire schema-2 document, including all field
rules, normalization actions, features, namespaces, grammar, and ceilings.
Changing any of those changes the digest. Increase `revision` when changing
behavior; same-revision/different-digest migration is rejected. Existing keys
fail closed until their pins are explicitly migrated under audit.

The packaged fallback remains the frozen revision-8 schema-1 profile. Schema-1
revision behavior is described by a checksum-frozen historical data resource;
no revision-number conditionals remain in the decoder. New operator policy
belongs in schema 2. Legacy files and frozen migration selectors remain usable
for deliberate rollback.

## Schema-2 dialect rules

The editor schema ships at
`app/slaif_gateway/resources/client-compatibility-preset.schema.json`.
The runtime parser additionally enforces UTF-8 byte limits, nesting and node
budgets, cross-references, monotonic numeric bounds, and empty-only dropping.
There are no executable expressions, imports, user regexes, remote references,
network operations, or permissive catch-all rules.

Alongside namespace/name rules and existing hard-capped limits, a schema-2
document has this required section:

```json
"dialect": {
  "features": {
    "schema_property_names": true,
    "sparse_visible_reasoning": true,
    "empty_visible_reasoning": true,
    "sparse_function_events": true
  },
  "custom_tools": [
    {"namespace": "functions", "name": "apply_patch", "type": "custom"}
  ],
  "extensions": {
    "message.assistant": {
      "status": {
        "action": "preserve",
        "value": {"kind": "enum", "values": ["completed"]}
      }
    },
    "part.output_text": {
      "annotations": {
        "action": "preserve",
        "value": {"kind": "array", "max_items": 0, "items": {"kind": "null"}}
      }
    }
  }
}
```

These are data examples, not special field names in the validator. To allow a
new inert field, add its rule to the appropriate scope in the external file,
increase the revision, validate, restart, and migrate pins. The same executable
then accepts that field. Removing its rule restores strict rejection.

Scopes are finite: `request`, explicitly typed `message.assistant`,
`message.user`, `message.developer`, `message.system`, `part.input_text`,
`part.output_text`, `part.input_image`, `part.input_file`, `part.input_audio`,
and `item.function_call`, `item.function_call_output`,
`item.custom_tool_call`, `item.custom_tool_call_output`, `item.reasoning`, and
`item.compaction`. Output-text rules apply only to assistant history. Unknown
scopes and unknown fields remain rejected.

| Value rule | Required settings | Behavior |
| --- | --- | --- |
| `null` | none | Exactly JSON null |
| `boolean` | none | Boolean only; integers are different |
| `enum` | `values` | Exact typed scalar values; no coercion |
| `integer` | `minimum`, `maximum` | Bounded integer, excluding booleans |
| `number` | `minimum`, `maximum` | Bounded finite integer/float, excluding booleans |
| `string` | `minimum`, `maximum` | UTF-8 byte bounds |
| `array` | `max_items`, `items` | Every element must match one child rule |
| `object` | `fields` | Declared properties only, each with `required` and `value` |
| `one_of` | `rules` | One of at most four bounded rules |

Absent optional fields remain absent. Null, empty, and nonempty values are
distinct. For example, an empty-array annotations rule rejects null, objects,
and nonempty arrays. A preset may explicitly describe a bounded nonempty
metadata structure using object/array rules; it gains no hosted-tool authority.

`preserve` retains the validated value exactly. `drop` is permitted only for
rules that accept exclusively empty/null values; it cannot discard meaningful
text, state, arguments, or results. Droppable request fields remain visible
until independent core gates run, preventing normalization from hiding an
unauthorized dialect shape.

The four feature settings select already implemented bounded parser/state-machine
behavior. They do not add event names or executable handlers. Custom-tool entries
declare syntax for explicitly named builtin-namespace tools. They never cause
the gateway to execute a tool, enable a hosted tool, or teach a backend a new
transport encoding; exact server contracts still apply.

## Immutable core boundaries

Preset rules wrap the existing validators. They validate and temporarily separate
declared optional metadata, run unchanged core validation, then restore only
validated preserved metadata. Unknown fields continue to reach strict core
rejection. Core field overrides are rejected when loading the preset.

Data cannot change message type/role/content, tool call IDs or arguments,
encrypted reasoning, routing/model selection, credentials or headers, endpoint
policy, token/output limits, quotas, replay identity, or billing. Tool/reasoning
terminal state remains validated by the core. Authority-bearing metadata names
are refused recursively. Existing key, route, provider, pricing, independent
capability, replay, and quota gates all still run.

Preset extensions require all three existing Codex gates on both key and route:
request envelope, client tools, and streaming tool events. They never apply to
ordinary OpenAI requests or implicitly typed messages. Additional reasoning or
compaction gates remain independently required for those item families.

Preserved metadata is conservatively included in input estimation before hard
input/context admission and PostgreSQL reservation. A request may carry at most
65,536 preserved compatibility-metadata bytes. Rules are limited to depth 6,
256 value-rule nodes, 32 optional fields across scopes, 64 array items, and 32
enum choices. Numeric/string ceilings are engine-fixed. No preset can raise the
existing namespace, schema, declaration, context, or output hard caps.

Neither preset inspection nor request validation persists prompt/history data,
raw IDs, tool arguments/results, annotations, or credentials. Errors report fixed
safe categories and the offending public parameter, never values or rule contents.

## Reasoning and replay budgets

Schema 2 also accepts an optional `replay_limits` object. When present, all
eight settings below are required, positive integers, and digest-bound. When
absent, the frozen decoder defaults remain unchanged, including its historical
8,192-byte visible reasoning part limit. This preserves existing profile
identities. These settings belong in the external preset rather than field
exceptions in source code.

| Setting | Shipped 0.163.0 revision 12 | Engine ceiling |
| --- | ---: | ---: |
| `max_reasoning_visible_parts` | 64 | 256 |
| `max_reasoning_visible_part_bytes` | 262,144 | 1,048,576 |
| `max_reasoning_visible_bytes` | 1,048,576 | 4,194,304 |
| `max_reasoning_summary_parts` | 64 | 256 |
| `max_reasoning_summary_bytes` | 65,536 | 1,048,576 |
| `max_encrypted_reasoning_item_bytes` | 262,144 | 262,144 |
| `max_encrypted_reasoning_request_bytes` | 1,048,576 | 1,048,576 |
| `max_compaction_item_bytes` | 1,048,576 | 1,048,576 |

Part and summary byte budgets cannot exceed their enclosing aggregate budget.
These are UTF-8 byte counts; arrays have independent part-count bounds. Reasoning
is preserved and included in input estimation. Global body/text, route context,
quota, capability and replay-ownership checks still apply. Increasing a replay
budget cannot raise the model's context or output allowance. Codex can replay
reasoning even when its transcript view does not display it. A reasoning replay
size error is distinct from throttling and from malformed backend tool arguments.

## Operator workflow

Export and inspect a new file, outside the repository and image:

```bash
slaif-gateway codex presets --json
slaif-gateway codex export-preset codex-0.163.0 \
  --output /operator/client-compatibility/candidate.json
slaif-gateway codex inspect-profile-file \
  /operator/client-compatibility/candidate.json --json
```

Export refuses to overwrite an existing file. Presets contain no credentials.
They are server-side policy, not the user's `qwen-students.config.toml`.
Export creates mode 0600. Grant the serving account read access to the file
and traversal access to its directory before promotion; the secret-loading
entrypoint may drop root privileges before reading the preset. Keep operator
write access separate from the container's read-only mount.

Mount its host directory read-only into API and maintenance containers and set:

```text
CODEX_COMPATIBILITY_PROFILE_FILE=/run/slaif/client-compatibility/active.json
```

The directory mount makes atomic file replacement visible to new processes.
If mounting a single file instead, recreate containers after replacement so
the mount references the new inode. Restart the processes
to bind the new snapshot; editing a mounted file never changes an already
running process. Use the same secret-loading entrypoint and profile mount for
maintenance commands as for the API.

Before promotion, record the current image, file, revision, digest, and database
backup. Preview each affected key migration while the candidate image/file is
available. Drain ingress and API traffic, ensure no unsettled reservations,
then apply audited migrations and start the new API. This decoder generation
has one active profile per process, so all affected active keys must have the
matching pin. Do not mix old/new snapshots across serving workers.

```bash
slaif-gateway codex show-profile --json
slaif-gateway codex migrate-key-profile KEY_UUID \
  --from-version OLD_REVISION --from-digest OLD_DIGEST \
  --reason "Reviewed external client compatibility preset" --json
# Review the dry run, then repeat that command with --apply.
```

For rollback, use the new engine with the saved previous file, explicitly
migrate pins back to that active snapshot, then restore the prior image and
configuration. Credentials, quotas, throttling, expiry, usage, and other policy
must remain unchanged by migration. Existing HMAC replay ownership is not
weakened by accepting metadata fields.

After promotion, verify readiness and perform a bounded exact-client sequence:
assistant commentary, one local tool call/result, a final answer, then another
user turn that naturally replays the previous final answer. Text-only or a
single tool round trip does not cover this sequence. Qualification must record
the exact binary, preset digest, model/catalog, backend, accounting, and
client/transport limitations as required by `AGENTIC_CLIENT_INTEGRATION.md`.

The optional `dialect.features.tool_output_images` selector accepts bounded
input_text/input_image tool-result arrays through the existing image validator.
It is off when absent. Image counts, decoded-byte limits, context estimation,
and explicit image-input permissions on both key and route remain mandatory.
It does not enable files, audio, image generation, or arbitrary result objects.

Verification: [2026-10-20 deployment evidence](verification/2026-10-20-external-client-presets.md).

## Codex 0.164.0 declaration compatibility

Revision 13 retains the older built-in namespaces and adds the observed `clock`
and `collaboration` names plus the exact `functions.exec` custom declaration.
Namespace/type vocabulary remains bounded preset data. The native-vLLM adapter
wraps approved custom input strings in the same bounded JSON `input` field for
transport and reverses that wrapper on streaming/non-streaming/replay paths.
It neither interprets nor executes custom text; core policy and declared-call
identity still govern admission. Unknown namespaces, undeclared calls and
unapproved custom types remain rejected. A profile-pin migration changes no
credentials, quotas, routing permissions, or throttling.

See the [bounded 0.164 verification record](verification/2026-10-23-codex-0164.md).
