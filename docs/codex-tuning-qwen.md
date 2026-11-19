# Codex tuning through the gateway: three Qwen backends

This is an operator and client setup guide for **Codex 0.167.1**, using three
original public routes: Qwen on V100/llama.cpp, A100/vLLM, and RTX3090/vLLM.
The settings below describe one deployment and provide adaptable templates.
Context capacity belongs to the loaded model and server configuration; a GPU
name alone does not establish it. These examples are not full-context
qualification or a production-certification claim.

## Start with the three configuration layers

| Layer | Owns | Where to change it |
| --- | --- | --- |
| Codex client | selected model slug, provider URL, catalog, reasoning, compaction, tools, local permissions | selected `$CODEX_HOME/<profile>.config.toml` and its model-catalog JSON |
| Gateway | allowed endpoints/models, compatibility preset, route adapter, input estimates, output budgets, quotas, rate limits | API/worker Settings, audited route/key CLI or dashboard |
| Backend | actual context, generation limits, template, reasoning implementation, image preprocessing, batching/KV memory | llama.cpp/vLLM service configuration |

Changing a client display name grants no access and changes no server limit.
Changing a gateway limit adds no backend capacity. Changing the loaded model or
chat template can require requalification even when the public slug stays the
same. Keep all three layers consistent.

## Worked budgets

The example uses decimal token counts: **64K = 64,000; 128K = 128,000**.
All six original/repaired Responses routes have the same requested output
policy. The original three cases are:

| Original public slug | Backend/adapter | Actual backend context | Gateway estimation ceiling | Default output | Maximum output |
| --- | --- | ---: | ---: | ---: | ---: |
| `qwen3.8-27b-V100` | llama.cpp; `llama-cpp-qwen-v1` | 196,608 | 400,000 | 64,000 | 128,000 |
| `qwen3.8-27b` | vLLM; native vLLM tool codec | 262,144 | 393,216 | 64,000 | 128,000 |
| `qwen3.8-27b-rtx3090` | vLLM; native vLLM tool codec | 100,000 | 150,000 | 64,000 | 128,000 |

The padded gateway ceiling tolerates estimator differences. It is **not** the
value to advertise as client/model context. The backend still enforces its real
capacity. Preserve the current ceiling when changing output policy; this guide
does not recommend padding a new deployment without measured justification.

The default is inserted when the client omits `max_output_tokens`. An explicit
request can choose a smaller value or request up to the route maximum, subject
to operator, context, pricing, quota, and rate-limit checks. The maximum alone
does not make every call reserve 128,000 output tokens.

For ordinary generation, the necessary backend condition is:

```text
actual input tokens + requested output budget <= actual backend context
```

Input includes instructions, tool declarations, history, replay and image
tokens. Reasoning, visible answer text, and generated tool arguments consume
the output budget. A long thinking phase can use most of it before a visible
answer appears.

| Backend | Input headroom with 64,000 output | Conservative example auto-compact trigger | Input headroom with 128,000 output |
| --- | ---: | ---: | ---: |
| V100 | 132,608 | 112,000 | 68,608 |
| A100 | 198,144 | 170,000 | 134,144 |
| RTX3090 | 36,000 | 28,000 | impossible |

These triggers leave margin for estimator disagreement and the next tool result;
they are starting points, not mathematical guarantees. **RTX3090 cannot generate
128,000 output tokens in a 100,000-token context, even with an empty prompt.**
Its 128,000 gateway maximum is a policy ceiling. Clients must request a feasible
budget; increasing it requires a larger verified backend context/model.

An existing 85,000-token compaction trigger on RTX3090 is unsuitable for a
64,000 default output allowance. Plan client rollout alongside the route change.
For a request near the 128,000 maximum on V100/A100, compact earlier or explicitly
use a smaller output budget. A remote `/responses/compact` call has its own
output-reservation policy; it reserves the configured compact default, capped at applicable maxima. These templates use
local compaction and leave `remote_compaction_v2=false`.

## Install a profile that actually selects Qwen

The [templates](../examples/codex/qwen38-tuning/README.md) supply three separately
selectable profiles and a shared catalog. They use the actual backend contexts
and the conservative triggers above. The installer writes absolute catalog paths,
keeps files private, and refuses to overwrite existing profiles or the catalog.

```bash
export OPENAI_BASE_URL="https://your-gateway.example/v1"
python3 examples/codex/qwen38-tuning/install.py
# Use your normal secret-management mechanism to supply a gateway-issued key.
export OPENAI_API_KEY="sk-slaif-..."
codex --profile qwen-v100
# Other choices:
# codex --profile qwen-a100
# codex --profile qwen-rtx3090
```

The selected profile sets `model`, `model_provider`, and `model_catalog_json`.
The model is selected by **slug**, including the uppercase `V100`, not
`display_name`. `env_key = "OPENAI_API_KEY"` supplies the gateway Bearer token.
Keep upstream credentials on the gateway. An inline
`experimental_bearer_token` is unnecessary and should not be committed.

Use `/status` after startup to check model, provider and client version. A
successful test against an unselected/default OpenAI model proves nothing about
the Qwen route. A new client version needs its own reviewed compatibility preset
and smoke tests; the CLI version, model catalog, tools and provider form one
compatibility boundary.

## Client settings and their effects

| Setting | Example/meaning | Tuning consequence |
| --- | --- | --- |
| `model` | exact public slug | selects gateway route and key allowlist entry |
| `model_provider` | `slaif_qwen` | selects the custom Responses provider, not default OpenAI |
| `model_catalog_json` | absolute installed catalog path | supplies per-model capabilities and context/compaction metadata |
| catalog `context_window` / `max_context_window` | verified backend context | do not replace with a padded gateway estimate ceiling |
| catalog `auto_compact_token_limit` | 112,000 / 170,000 / 28,000 | triggers local history compaction with output headroom |
| `model_context_window`, `model_auto_compact_token_limit` | optional TOML overrides | inspect existing overrides before relying on catalog values |
| `model_reasoning_effort` | `medium` | higher effort can increase output and latency; backend support must agree |
| catalog reasoning levels | `none`, `low`, `medium`, `xhigh` in this example | advertising a level does not implement it in the backend |
| `supports_parallel_tool_calls` | `false` | client tool behavior; distinct from concurrent HTTP requests per key |
| `use_responses_lite` | `true` | client tool-declaration dialect; requires the matching gateway preset |
| `shell_type` / `apply_patch_tool_type` | `unified_exec` / `freeform` | changes tool vocabulary; keep qualified values |
| `truncation_policy.limit` | 10,000 tokens | per-tool-output trimming policy; not the conversation context size |
| `input_modalities` | text/image | requires matching key, route and backend image support |
| `incremental_tools` | `true` | requires the revision-16 declaration-history engine/preset |
| `worktrees` | `false` | avoids a client worktree tool namespace in this template |
| `web_search` | `disabled` | no implied hosted search permission |
| `remote_compaction_v2` | `false` | local compaction; enabling remote compaction requires its own route/key support |
| `approval_policy` / `sandbox_mode` | `on-request` / `workspace-write` | local shell/file permissions; independent of gateway policy |

The examples do not enable `--yolo`. It changes local approvals and sandboxing;
it does not raise model, token, quota or gateway limits. Avoid adding unsupported
temperature, verbosity or reasoning-summary fields merely because another
backend accepts them. The [official configuration reference](https://developers.openai.com/codex/config-reference/)
describes the keys; these templates deliberately target 0.167.1.

## Gateway settings and output changes

The [six-model budget manifest](../examples/codex/qwen38-tuning/output-budgets.json)
lists the requested Responses route scope. It is a change specification, not a
complete route-capabilities import. Use partial audited updates, preserving
media estimation, context ceilings, adapter bindings and all key policies:

```bash
slaif-gateway routes list --json
# For EACH reviewed Responses route UUID, including repaired counterparts:
slaif-gateway routes update ROUTE_UUID \
  --codex-default-max-output-tokens 64000 \
  --codex-max-output-tokens 128000 \
  --dry-run /private/new-route-output-plan.json --json
slaif-gateway routes update ROUTE_UUID \
  --execute /private/new-route-output-plan.json \
  --reason "Reviewed Qwen 64K default / 128K maximum output budgets" --json
slaif-gateway routes show ROUTE_UUID --json
```

Use a distinct new plan file per route. Review its fingerprint and change list
before execution. The six routes are the original three plus their
`-repaired` variants; the additional proxy does not imply extra model capacity.
Changing these database-backed limits does not rotate keys or alter their
quotas. Existing client files are not rewritten by a route update.

| Gateway control | Purpose |
| --- | --- |
| route `codex_limits.default_max_output_tokens` | injected and reserved only when the client omitted a limit; smaller explicit requests are preserved |
| route `codex_limits.max_output_tokens` | ceiling for explicit create requests; larger requests are clipped down |
| route `codex_limits.context_window_tokens` | admission estimate ceiling; input estimate plus output allowance must fit |
| `CODEX_ABSOLUTE_MAX_OUTPUT_TOKENS` | operator ceiling; currently 128,000 by default |
| `CODEX_ABSOLUTE_MAX_INPUT_TOKENS` | separate operator input ceiling |
| `DEFAULT_MAX_OUTPUT_TOKENS` / `HARD_MAX_OUTPUT_TOKENS` | ordinary Chat/Responses defaults; Codex extended limits require independent key/route gates |
| key endpoint/model/provider grants | independent access control; a client catalog entry grants nothing |
| key quota and rate-limit policy | reserves estimated input plus output before inference; can reject a request before any answer |
| wait mode / maximum wait | queues eligible rate-limited requests within the configured bound; does not enlarge token or context limits |
| concurrency per key | simultaneous requests, distinct from tools within one turn |
| replay-reference TTL | lifetime of same-key/provider/route replay ownership; preserve durable database state across restarts |

A 20,000-token input with the default output budget reserves exposure for about
84,000 tokens. Hard-quota settlement uses actual reported usage and releases
unused reservation; rate windows have their own rules. Raising defaults can
therefore increase admission pressure even when actual answers stay short.
See [accounting](accounting.md) and [live-burn policy](streaming-live-burn-margin.md).
Process Settings and preset-file changes require affected process restarts;
database route-policy edits are handled through the audited route service.

The gateway client compatibility preset and a route's historical
`codex_profile` qualification declaration are different objects. Revision 16
(`codex-0.167.1`) does not mean that a frozen 0.162 download profile has been
requalified. Readiness checks can refuse a new 64,000 default against an older
profile whose tested maximum is lower. Preserve that honest result; use a
matching reviewed qualification profile rather than rewriting historical
fixture identities. The new templates are client setup examples, not READY claims.

## Backend templates and adapter selection

| Case | Backend settings to verify | Gateway adapter |
| --- | --- | --- |
| V100 / llama.cpp | actual configured context 196,608; correct GGUF/template; Responses and image support; instruction placement | configured upstream LLM adapter, `llama-cpp-qwen-v1` for the prefix-only template |
| A100 / vLLM | served model ID, `max_model_len=262144`, compatible reasoning parser and image processor, Responses SSE/tool format | `local_coding_vllm` native tool codec |
| RTX3090 / vLLM | served model ID, `max_model_len=100000`, KV/batching capacity and compatible reasoning/image support | `local_coding_vllm` native tool codec |

Verify the running service properties or launch configuration; do not infer
capacity from the public model name. Native vLLM flattens declared tool
namespaces and translates them back. The llama.cpp/Qwen preset uses its reviewed
instruction placement and tool encoding. Their route blocks are not interchangeable.
See the [upstream adapter guide](upstream-llm-adapter.md).

The incremental-tool compiler removes validated declaration metadata while
preserving ordinary messages. A genuine late developer/system instruction may
be incompatible with a prefix-only backend template; the adapter returns
`upstream_llm_bindings_placement_conflict` rather than silently reorder it.
Only use a preserve-order adapter/template combination after verifying backend
support. This is separate from the corrected string/one-part-array tool hint
recognition described in the [upgrade runbook](upgrade-runbook.md).

## Images, tool histories and payload bounds

Use the route's geometry-based `media_input_estimation.image_geometry` with the
actual model preprocessing contract. This deployment uses a 16-pixel patch,
spatial merge 2, minimum 64 and overhead 64 tokens, with a configured fallback
image allowance. The merged grid has an effective 32-pixel stride. These are
estimator inputs, not universal image-token facts; unknown geometry and remote
URLs use the documented fallback rather than downloading data inside admission.
Encoded image/data-URL bytes must not be counted as ordinary text tokens.

`RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST=0` removes the gateway image-count cap in
this example. Request-byte, validated media, model context and backend limits
still apply. Do not reintroduce an image-count workaround for token-estimation
errors. Video-frame extraction and direct video capabilities have independent
route/request bounds; disabling the image count does not enable arbitrary video.

The compatibility preset owns tool namespace vocabulary, declaration/schema
limits, visible-reasoning sizes and replay shapes. Those byte/item bounds are
separate from output token budgets. A long answer fitting 128,000 tokens can
still hit a bounded item/frame limit. Update presets through reviewed data
revisions; preserve key-pin migration and restart requirements. See
[client compatibility presets](client-compatibility-presets.md).

## What happens at an output limit

A valid `response.incomplete` with
`status=incomplete`, `incomplete_details.reason=max_output_tokens`, and bounded
authoritative usage is an output-limited terminal. The vLLM representation
`response.completed` with the same incomplete status/reason is handled too.
The gateway preserves the provider event, partial answer and reason, finalizes
usage before releasing the terminal, and retains the ordinary failure boundary
for malformed envelopes, unknown reasons, missing usage and accounting failures.
The hosted web-search path keeps its separate settlement restrictions.

Only fully validated completed tool/reasoning items may become replay
references after settlement. Incomplete tool arguments never become executable
or replayable through the gateway; malformed/truncated native tool encoding
still fails its codec contract. A provider that labels an exhausted response
`completed` without a reason cannot be reliably corrected from token count alone.

Codex itself may display an output-limit notice and partial result. This change
preserves its [pinned incomplete-response handling](https://github.com/openai/codex/blob/0a94398fa60c4fac0e7659e4213a0a36e613dd46/codex-rs/codex-api/src/sse/responses.rs);
it does not manufacture a completed answer or promise automatic continuation.
The [Responses event reference](https://developers.openai.com/api/reference/resources/responses/streaming-events/)
defines the canonical event.

## Verify and diagnose

1. Confirm the client version, selected profile/model and `/status`.
2. Check backend context and adapter identity from the gateway's network.
3. Inspect the effective key policy and route configuration using
   `slaif-gateway keys policy effective KEY_UUID --json` and
   `slaif-gateway routes show ROUTE_UUID --json`.
4. Check `slaif-gateway codex show-profile --json` and the route's qualification
   report. A serving key and a historical download profile are separate checks.
5. Test a short text reply, shell/tool round trip and image input using the
   intended model. Force a small explicit output limit in a controlled test to
   check incomplete status and settlement without generating 64K tokens.
6. Resume a test session and exercise tool updates and local compaction.
   Compare provider usage with finalized ledger rows. Tiny smokes do not qualify
   the entire context/output envelope or all client versions.

| Symptom | First checks |
| --- | --- |
| wrong model / model not allowed | selected slug/provider and key allowlist |
| `output_token_limit_exceeded` before generation | explicit budget versus route/operator maxima |
| context-window rejection | full input estimate plus output allowance; image geometry; actual backend context |
| 429 | estimated reservation, token/request window, concurrent requests and wait policy |
| output-limit notice | provider status/reason, thinking consumption, requested/default budget |
| generic stream failure | unsupported event, malformed tool encoding, missing usage or transport failure |
| replay-reference unavailable | durable ownership/TTL and key/provider/route; an older failed stream may have left orphaned history—rewind before that turn; preserve the database during upgrades |

Use content-free diagnostics first. Do not log bearer keys, tool contents,
images or whole conversations to tune these controls.

For Codex event delivery, see the [replay delivery barrier settings](configuration.md#codex-replay-delivery-barrier).
Tool events wait for accounting and replay commit; this may delay their display
until generation finishes. This change does not increase model token limits.
