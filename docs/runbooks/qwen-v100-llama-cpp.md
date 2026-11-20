# Qwen on V100: llama.cpp template and gateway instruction order

Use this runbook when Codex continuation after compaction fails with
`upstream_llm_bindings_placement_conflict`, or the backend rejects a late
instruction with `System message must be at the beginning.` Read the
[upstream adapter contract](../upstream-llm-adapter.md) and
[Codex tuning guide](../codex-tuning-qwen.md) alongside it.

The deployed example covers `qwen3.8-27b-V100` and
`qwen3.8-27b-V100-repaired`. Both need the same backend template behavior and
gateway selector. The repaired route's extra proxy does not fix instruction
ordering by itself. This is configuration work, not a gateway-engine patch.

## Why both layers must change

Codex can retain a user summary and then insert developer instructions after
it. The prefix-only Qwen template rejects those instructions. The gateway's
`llama-cpp-qwen-v1` profile historically moved instructions to the beginning,
but that changes chronology. Requests with positional tool-call bindings reject
such reordering before inference. Keep this guard enabled.

First enable late instructions in the backend template; then select a
preserve-order gateway profile. Changing only the gateway exposes the backend
template error. Changing only the template leaves the gateway's reordering
profile selected.

## 1. Inspect and back up the backend

Identify the actual llama-server process, model, startup service and template
override. Save the launch configuration and the template actually returned by
`GET /props`; do not assume an on-disk candidate is active. Check every exposed
API path, including the original and repaired proxy paths.

Before restarting, drain active work. Preserve the model/quantization, context,
GPU parameters, parsers, credentials, ports, reasoning and vision settings.
Install an external Jinja override through the installed server's supported
`--jinja` / `--chat-template-file` mechanism. Update the persistent launch
configuration, rather than only a temporary process invocation.

The template change is in the loop handling messages after the leading
instruction block. Replace its unconditional late-instruction exception with
a separate ChatML message at that position. For the reviewed template, the
branch is:

```jinja
{%- if message.role == "system" or message.role == "developer" %}
    {%- set instruction_content = render_content(message.content, false, true)|trim %}
    {{- '<|im_start|>' + message.role + '\n' + instruction_content + '<|im_end|>' + '\n' }}
```

This is a fragment, not a replacement template. Retain the existing `elif`
branches, leading-instruction handling, tools, reasoning controls and media
handling. In particular, keep `is_system_content=true` so instruction images
and videos remain rejected. Rebase the change on the service's actual template;
do not blindly replace a different model's template with this example.

The verified deployment template SHA-256 is:

```text
18fec282bbb9161ac58936b0c13b34a8fc175fca44467ace5aa3802d5ce59514
```

This hash identifies that deployment's complete template; it is not a universal
hash for every supported Qwen build.

## 2. Verify the actual llama.cpp renderer

Test `/apply-template` on each service path using this chronology:

```text
system(prefix), user(history), assistant(reply), developer(later instruction), user(followup)
```

Also test a late system instruction and a retained-user-summary followed by
developer instructions. Require preserved content, chronological order and a
separate instruction boundary. Compare previously supported histories with
the original renderer, including tools, tool results, reasoning and vision.
Python Jinja2 checks alone do not qualify the installed llama.cpp renderer.

The verified llama.cpp build normalizes `developer` to `system` before Jinja
runs. Accept this existing normalization explicitly when comparing expected
roles: the late developer instruction renders as a separate system message at
its original position. The gateway still forwards the original roles. This
backend does not retain the system/developer distinction, and a template
override cannot restore information already normalized by the engine. Do not
claim literal role preservation or change user/tool messages into instructions.

Run short live checks for late-instruction following, tool-call/result
continuation, streaming completion, usage, reasoning and vision-history replay.
Restart with the persistent configuration and re-check the served template.

## 3. Switch both gateway routes

After backend verification, inspect the effective registry:

```bash
slaif-gateway upstream-llm profiles
```

Back up each complete route capability document. Through the audited route
editor or `ModelRouteService.update_model_route`, replace only `upstream_llm`
with this packaged selector:

```json
{
  "version": 1,
  "profile": "responses-passthrough-v1",
  "revision": 1,
  "sha256": "5084f47909d5b919ea329524bae2d382a772936034af7cba7290bbfdf1cc521a"
}
```

Keep the containing route's other capabilities, provider, model, endpoint,
streaming flag, visibility, limits and notes. A selector fragment is not a
complete `--capabilities-file`; that option replaces the complete capabilities
document. Record an audit reason. For a coordinated two-route change, the
service layer can update both routes in one transaction.

The packaged profile preserves instruction placement and tool encoding. If an
external registry is configured, confirm the selector exists in that active
registry. Database route-selector changes do not require worker restarts;
changing the registry file itself does. This change requires no key rotation,
key-pin migration, quota reset or client model-catalog change.

## 4. Verify through the gateway

Use a permitted gateway key and the real public model slugs. Test a fresh tool
call, supply a synthetic client tool result, append a later developer
instruction, and continue with the gateway-issued tool reference intact.
Check successful SSE completion, the expected answer, and finalized usage.
Exercise both routes. A backend Chat test alone does not verify this path.

A synthetic retained-summary shape covers the original placement conflict but
is not proof of actual Codex-triggered compaction. Record those separately.
For client qualification, also run compaction and continuation with the exact
supported Codex version/profile. See the
[dated verification record](../verification/2026-11-19-v100-instruction-order.md).

## Rollback and unrelated errors

Save an executable backend rollback procedure before deployment. If the
backend override must be removed, first stop new affected traffic and drain
active work, restore the previous gateway selectors through the audited
service, and restore the backend launch configuration/template. The former
`llama-cpp-qwen-v1` selector is revision 1, SHA-256
`75ba8eda0ed9206474ee091ad1138c641cd4198fe71850322712e944c29a4d7b`.
Restoring it also restores the known post-compaction limitation; it is not a
solution for histories containing late instructions and tool bindings.

Do not delete replay records or alter keys during rollback. A replay-reference
404 is a separate failure: records are durable PostgreSQL metadata, and an old
failed stream can leave an unowned call in client history. Preventing new
partial-delivery failures does not reconstruct those missing historical records.
Context estimation, image geometry, output allowances and backend context limits
are also separate; do not adjust them to solve instruction ordering.
