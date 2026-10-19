# Qwen 3.8 27B through Codex

> **Status:** Bounded operator procedure; Codex CLI 0.162.1
> **Scope:** Exact Codex 0.162 client module with a Local Coding Responses backend

Use the [clean two-file client configuration](../../examples/codex/qwen38-27b/README.md).
It contains no hardware, institution, or private host names.
The [verification record](../verification/codex-qwen38-live-smoke.md) separates
real gateway/model tests from synthetic fixtures and operator reports.

## Gateway setup

1. Configure an explicit `local-coding-v1` Responses route for the public model
   alias `qwen38-27b`, with the backend's actual `/v1` base URL and server-side
   credential. A static bearer backend requires its route's static-bearer
   authentication contract; do not assume it implements the signed Local
   Coding request-identity protocol. See the [Local Coding contract](../provider-forwarding-contract.md#local-coding-server-module).
2. Enable all four capabilities on both the route and gateway key:
   `codex_request_envelope`, `codex_client_tools`,
   `codex_streaming_tool_events`, and `codex_encrypted_reasoning_replay`.
   Select the correct client module and model allowance on the key. Selecting
   the model or enabling a generic Codex checkbox alone is insufficient.
3. Supply valid route `codex_limits` and complete Codex pricing. A free route
   still needs explicit zero prices for input, output, cached input, reasoning,
   and cache writes, plus valid `codex_accounting` thresholds/multipliers.
   Zero cost does not bypass policy or token accounting. Follow the exact
   [route/pricing prerequisites](../responses-compatibility.md).
4. Deploy the updated executable engine and explicitly migrate existing keys
   to its active profile. `slaif-gateway codex show-profile --json` must report
   the intended revision and digest. Packaged revision 8 has digest
   `1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11`.
5. For large namespace descriptions, review
   `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES`. Its default is 4,096 bytes;
   a reviewed deployment used 65,536. This also affects ordinary function
   descriptions. The Codex module still enforces 20,000 bytes per tool,
   262,144 total namespace/tool description bytes, and declaration limits.
   Recreate affected API processes after changing environment settings.

Keep backend credentials on the gateway and give clients only gateway-issued
keys. A user/key owner need not be an administrator to make model requests.
Test backend reachability from the API container's network context; a host-only
probe does not prove the container can reach a VPN backend. Configure the VPN
and firewall deliberately, rather than exposing every backend port publicly.

## Register the route for downloads

The registry includes `qwen38-27b-codex-0.162-v1` for CLI 0.162.1 and client
module `codex-0.162-responses-v1`, revision 8. Registration does not change key
permissions or automatically qualify existing routes. Through the audited
route editor/service, set the route's top-level capabilities declaration to:

```json
"codex_profile": {
  "version": 2,
  "profile_id": "qwen38-27b-codex-0.162-v1",
  "fixture_sha256": "1d1e5b05587d1a8bf1f90057e43e357b7b3627dc3268ec09108e5fafa52e6d11"
}
```

Preserve the other capability fields. This profile requires upstream and
public model `qwen38-27b`, provider kind `openai_compatible`, a streaming
Responses route, all four Codex flags above, and exact context/default-output/
maximum-output limits of 131072/8192/16384, with complete pricing.
Run `slaif-gateway codex inspect --json` and resolve any readiness reasons.
A ready route's Administration detail page then offers **Download Codex
config** and **Download model catalog**. These are authenticated admin
downloads, contain no key, and do not grant a client access by themselves.
The existing OpenAI profile keeps its separate base-fragment workflow.

This profile retains `live_qualification=false`: bounded real text/tool tests
are evidence, not a complete provider, long-context or compaction qualification.
To roll back the route declaration, restore its saved prior capabilities
through the audited editor/service before downgrading the executable. This
changes neither key-module pins nor quotas.

## Client configuration and smoke

Use an HTTPS gateway URL ending in `/v1`, including the port if it differs
from 443. The examples use `env_key = "OPENAI_API_KEY"`; no embedded token or
`auth.json` edit is needed. For the repository example, replace the placeholder URL. The downloaded
TOML already contains the public gateway URL; its catalog path is relative to
Codex home. Save both files there. Start a new Codex process after edits.

The example catalog sets `use_responses_lite=true`. This makes Codex declare
tools in an initial `additional_tools` input item; the selected gateway module
validates and lowers that prefix to the backend's namespace `tools` field.
Nonempty top-level client `tools` are outside this profile. Disabling apps and
plugins reduces declarations but does not remove built-in local tools.

First run `codex --profile qwen38` with: “Reply exactly CLEAN_PROFILE_OK. Do not
use tools.” Then run the same profile in a disposable directory: ask it to
create `smoke.txt` with `apply_patch`, read it using `exec_command`, and report
its exact content. Check both tool results and the final response. A text-only
pass does not establish multi-turn tool compatibility.

Keep context and compaction settings consistent between TOML and catalog and
within both the backend capacity and route limits. The examples use 131,072
context tokens and 100,000 for compaction. The larger settings in an existing
client deployment must not be copied as universal Qwen hardware guarantees.
Images, plugins, remote compaction, and hosted web tools need their own
capability review and verification.

## Upgrade, pin migration, and rollback

Back up the database and deployment configuration and record the old image,
profile file, revision, and digest. Drain traffic and avoid mixed profile
snapshots across workers. Use the same configuration and secret-loading
entrypoint for maintenance CLI commands as for the API; `docker compose exec`
does not re-run a container's entrypoint or populate variables it exported.

With the new binary, preview the exact source pin and then apply:

```bash
slaif-gateway codex show-profile --json
slaif-gateway codex migrate-key-profile KEY_UUID \
  --from-version OLD_REVISION --from-digest OLD_DIGEST \
  --reason "Qwen Codex compatibility update" --json
# Review source, target, preserved fields, and dry-run status first.
slaif-gateway codex migrate-key-profile KEY_UUID \
  --from-version OLD_REVISION --from-digest OLD_DIGEST \
  --reason "Qwen Codex compatibility update" --json --apply
```

No database schema migration is introduced here. Key material, restrictions,
quotas, expiry, and usage are preserved; the profile pin changes under audit.
The source must match exactly. Do not edit key metadata with ad hoc SQL.

For rollback to an older data-revision image, load the saved old profile file
through `CODEX_COMPATIBILITY_PROFILE_FILE` **using the new binary**, preview
and apply migration from the new pin to that active old profile, then restore
the old image/configuration and verify readiness before reopening traffic.
Frozen `0162-v1`/`0162-v2` selectors serve their specific historical images;
they do not mean an arbitrary previous data revision. See the
[upgrade runbook](../upgrade-runbook.md) for the complete lifecycle.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Client tool namespaces not enabled | Independent key grants and matching route flags |
| Selected client module unavailable | Exact active revision/digest; then client tool placement and catalog loading |
| Exact approved namespace set rejected | Actual names, types, duplicates, counts, and selected engine; this message covers several classifier failures |
| Namespace description exceeds size limit | Namespace description setting and aggregate Codex ceilings |
| Provider authority rejected at a schema property | Updated engine distinguishes property labels from authority-bearing values; real provider/hosted authority remains denied |
| Custom `apply_patch` rejected | Updated engine, exact `functions.apply_patch` custom grammar declaration, key pin, and local custom-tool route support |
| Stream closes before completion | Correlate gateway and backend logs; check the precise unsupported event or accounting/disconnect reason |
| Sparse function-argument event rejected | Revision-8 engine and matching key pin; missing coordinates remain tied to the active declared call |
| Empty encrypted-content continuation rejected | Revision-7 engine and matching key pin; visible empty ciphertext must not become encrypted replay authority |
| Local file tool fails | Client sandbox and workspace permissions; distinguish this from gateway rejection of the following turn |

A successful `/v1/models` proves authenticated discovery, not inference.
Nginx access lines commonly appear only when a request finishes. Correlate
request IDs between gateway logs, backend request headers, and usage records.
A pending quota reservation shows admission but does not prove model output;
inspect final ledger outcome and error type. Distinguish client disconnects
from `responses_stream_event_not_supported` and other gateway validation errors.
A backend `BrokenPipeError` can be the consequence of the gateway closing an
unsupported stream, not evidence that the model itself failed.

Standard debug logging is not a full request-body capture facility. The merged
[operator request-capture feature](incoming-request-capture.md) provides a
separate, default-off, explicitly armed and bounded capture workflow, including
classifier diagnostics. Follow that runbook's enable/arm/read/disarm procedure;
DEBUG alone does not capture the actual declaration. Keep captures outside
source control and share only the authorized evidence. Capture settings do not
change validation, quota, or forwarding policy.

## Explicit larger-context profiles

Keep the original 131072-token profile available for existing deployments. Two
separate static profiles provide larger contexts without changing its identity:

| Profile ID | Public/upstream model | Context | Local compaction | Named client profile |
| --- | --- | ---: | ---: | --- |
| `qwen38-27b-240k-codex-0.162-v1` | `qwen38-27b` | 245760 | 208125 | `qwen38_240k` |
| `qwen3.8-27b-256k-codex-0.162-v1` | `qwen3.8-27b` | 262144 | 221184 | `qwen38_256k` |

Both require the same Codex revision 8, flags, pricing prerequisites and
8192/16384 default/maximum output limits. Select the exact profile declaration
and matching route context together through the audited route service. Download
both files again after changing the route profile, then start a fresh client
with the named profile above. Generated TOML and JSON use identical context and
compaction values. Model spellings are intentional and must match the backend.

These limits are explicit operator/backend configuration, not a universal Qwen
capacity claim. A successful short tool test does not qualify full-context
inference or compaction. Both retain `live_qualification=false`; no new tool
authority, image support, key quota, or provider qualification follows.

## Native vLLM backends

For a native vLLM Responses endpoint rather than a compatible wrapper, explicitly
select the separate [local-coding-vLLM adapter](native-vllm-responses.md). Keep
the same independent key/route grants, zero-price dimensions and context/profile
limits. A native `/models` or text pass alone does not qualify Codex tool calls.
