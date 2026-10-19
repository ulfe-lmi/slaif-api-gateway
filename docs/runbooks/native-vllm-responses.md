# Native vLLM Responses adapter

The `local-coding-vLLM` server module connects a native vLLM Responses backend
to the existing validated Responses representation. It is selected explicitly
per route, independent of provider slug, address, model or hardware. The
existing `local-coding-v1` wrapper transport remains separate.

## Select the backend

Configure an `openai_compatible` provider with its actual `/v1` base URL and a
server-side bearer-secret environment variable. Through the audited route
editor/service, select a streaming `/v1/responses` route with this capability:

```json
{
  "local_coding_vllm": {
    "contract_version": "local-coding-vLLM",
    "route_name": "local_gpu",
    "tool_policy_version": "responses-tool-policy-v1",
    "identity_mode": "static",
    "replay_mode": "process_local_inclusive_horizon_fail_closed",
    "deployment_mode": "single_worker"
  }
}
```

Preserve the route's other capabilities, limits and profile declaration. Remove
`local_coding` when selecting `local_coding_vllm`; declaring both is rejected.
The module name and contract version above are case-sensitive. Provider kind
alone selects the generic adapter, not this module.

Only static bearer authentication is supported. The replay/deployment fields
retain the shared static contract vocabulary; they do not assert that native
vLLM implements signed identity or server-side replay protection. No signed
identity mode is accepted and no derived principal/session/repository headers
are sent. The default client and exact `codex-0.162-responses-v1` client have
explicit registry pairs; older Codex dialects do not inherit this pair.

Endpoint, model, tool and all four Codex capability grants, route limits,
complete pricing, hard quotas and gateway replay ownership still apply. No key
migration or database migration is required. Context/download profiles are
selected separately; see the [Qwen runbook](codex-qwen38.md).

## Wire translation

The module flattens validated namespace function declarations into
`namespace.tool` names. Only the approved custom `functions.apply_patch`
declaration is lowered to a native function with one required string property,
`input`, containing raw patch text. Its grammar is not enforced by native vLLM;
the client patch parser still validates the patch. Original declarations remain
in the gateway's canonical request for admission, accounting and replay checks.

On return, exact declared names restore namespace and function/custom type.
The adapter accepts `async` and `caller` only when absent or null. Custom JSON
arguments must be an object with exactly one string `input`; duplicate keys,
extra properties and malformed JSON fail. Custom arguments are buffered until
the native arguments-done event, then emitted as bounded custom-input deltas.
Native custom-call argument events are replaced, not forwarded as function
calls. Output events and completed responses use the same conversion. Replay
converts canonical custom calls and outputs back to native function items.

Native vLLM can regenerate both tool identifiers in the terminal response.
The adapter restores the closed stream's identifiers only when output position,
declared wire name and complete arguments match exactly. Changed, missing or
unclosed calls fail. These identifiers are protocol linkage, not user identity.
Canonical events then pass the existing validator and same-key/provider/route
replay reference gates. Non-streaming responses use their own native identifiers.

State is per request: at most 256 declared tools, three tool items and 1 MiB of
native JSON arguments per tool, with at most 65536 native argument fragments.
Fragment buffers join once at completion. UTF-8 deltas retain the existing 64-KiB ceiling.
Input event sequences must be consecutive from zero; translated output events
are resequenced. The existing bounded SSE framer, body ceiling, credential
substitution, redirect policy, usage handling and accounting lifecycle remain
in force. No tool is executed by the gateway and no payload is logged by the
adapter.

Only Responses create/streaming is implemented. Chat, compact, storage and
auxiliary endpoints are not added by this adapter. New native fields, non-null
authority fields and undeclared tools require separate reviewed support.

## Test and rollback

Deploy the binary before selecting the route contract. Confirm readiness, then
run a fresh pinned Codex process with a disposable workspace: create a file via
`apply_patch`, read it with `exec_command`, and check the exact file and final
response. Verify usage finalization and unchanged quotas, then test the existing
wrapper route. A short pass does not qualify long-context inference, compaction,
images, connectors or other vLLM versions. Synthetic transport/state-machine
coverage is in `tests/unit/test_local_coding_vllm.py`; live evidence is recorded
separately in the [Qwen verification record](../verification/codex-qwen38-live-smoke.md).

Back up route metadata and deployment configuration before selection. To roll
back, restore the previous route capability through the audited service before
downgrading the binary. Restoring `local-coding-v1` also requires its compatible
backend wrapper; it does not make a native backend compatible automatically.
