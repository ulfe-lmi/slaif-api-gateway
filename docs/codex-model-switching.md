# Switching models in a Codex conversation

The gateway allows verified client-executed function/custom-tool history to
continue on another permitted model route. This includes original/repaired
routes, different providers, and histories containing calls from multiple
previous routes. The source route does not need to remain the selected route.

This change applies to gateway replay authorization. It does not add a client
module/server pairing or make every backend understand every tool or media
format. Use the [Codex compatibility boundary](codex-compatibility.md) and
[Responses contract](responses-compatibility.md) for supported shapes.
The [dated verification record](verification/2026-11-19-codex-model-switching.md)
separates the local regression evidence from live-provider qualification.

## What moves and what stays bound

| History | Model switching |
| --- | --- |
| Ordinary text and accepted visible reasoning without ciphertext | Ordinary bounded, metered request input; no opaque-reference lookup |
| Verified client function/custom calls and their matching results | Portable across model/provider/route changes under the same gateway key |
| Encrypted reasoning | Source provider/route/model binding remains required |
| Opaque compaction state | Existing source binding and explicitly configured compact-route exceptions remain required |
| Provider-managed `previous_response_id` or Conversations | Separate owned lifecycle; this change does not make that state portable |

Every historical call must still pass the selected client's declaration,
positional binding and call/result validation. Its item ID, or an explicitly
qualified ID-less call's call ID, must match an active HMAC ownership record
for the same gateway key and exact kind/tool identity. A present wrong item ID
does not fall back to call-ID lookup. Cross-key, unknown, expired, ambiguous or
renamed references remain rejected. The gateway does not execute these tools;
results are supplied by the client as before.

Source provider/route/model metadata remains unchanged in the durable reference
row for provenance. Moving history neither copies nor rebinds that row and
does not require key rotation, policy-pin migration or a database migration.

## Destination checks still apply

The current key must allow the newly requested model, endpoint and provider.
The destination route must be enabled, support the selected client/server
pair and requested capabilities, and accept the history's tool/media shapes.
Normal pricing, quota, output/context policy and accounting apply to the new
request on the destination route. Historical references grant no access to a
model, provider, hosted tool or execution capability.

The common replay check is used by Responses create, input-token counting and
the supported compact path. Each endpoint retains its existing client/server
and capability boundaries. Local Coding create-only routes do not gain a
remote compact endpoint through this change.

## Continuing an existing conversation

Select the new permitted model and retry the conversation. Plain tool history
already stored by the gateway needs no conversion or reissue. The client can
return to a previous model after accumulating history on other routes.

If the request includes opaque state from a different provider/route/model,
`responses_codex_replay_route_mismatch` still rejects it before quota or
inference. Its message identifies opaque reasoning/compaction as the obstacle.
Continue on the original route or have the client construct visible history,
such as a local summary, before changing models. The gateway does not silently
discard ciphertext or fabricate a summary. A history containing incompatible
opaque state from multiple routes cannot satisfy one destination binding.

`responses_codex_replay_reference_not_found` is different: the reference could
not be authorized under the key. Switching models cannot create a missing
record. An old failed stream may have left a call in local history before its
ownership record was saved; the delivery-barrier fix prevents new occurrences
but cannot reconstruct missing historical records. Back up the local history
before targeted repair. Do not delete the whole conversation or gateway replay
database as a default recovery step.

## Operator verification

Use synthetic content and tool results to exercise A → B → A under one key,
including function/custom calls, ID-less replay where qualified, retained
summary/late-instruction history and a mixed-source transcript. Check the
expected result and destination accounting. Verify wrong-key, changed-tool,
expired-reference, forbidden-destination and opaque-state denials separately.
Keep request contents, raw replay IDs, ciphertext and HMAC digests out of logs
and committed evidence. Normal tests use mocked provider HTTP and disposable
PostgreSQL; real provider inference is a separate, explicitly reported check.
