# Codex image-history payload size

Use this runbook for `responses_input_image_data_url_too_large` when the
gateway reports that the Responses input image data URLs exceed its size
limit. The exact aggregate message means the combined encoded image data in
one request crossed `RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES`.

Also check the route adapter's separate `max_body_bytes` setting for a generic
HTTP 502 `Provider request failed` on a large history. The Local Coding and
native-vLLM adapters currently report their serialized-body limit with that
generic error, before sending an upstream request. The same error can have
other causes; without request-size or failure-branch evidence, it does not
prove a size rejection or a backend outage.

Codex can resend earlier image tool results with subsequent turns. The check
therefore includes images retained in the submitted conversation, not just
the image most recently opened. It is separate from image-count acceptance,
geometry-based image token estimation and the backend context window. Retrying
the same unchanged history does not reduce its byte size.

## Default versus deployed settings

The Qwen deployment example uses these operator overrides as of 2026-11-22:

| Setting | Packaged default | Deployment example |
| --- | ---: | ---: |
| `RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST` | 0, no gateway image-count cap | 0 |
| `RESPONSES_MAX_IMAGE_DATA_URL_BYTES` | 20,971,520 (20 MiB) per encoded image | unchanged |
| `RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES` | 41,943,040 (40 MiB) per request | 134,217,728 (128 MiB) |
| Nginx API `client_max_body_size` | inspect the deployment's active configuration | `128m` |
| Route adapter `max_body_bytes` | 67,108,864 (64 MiB) | 134,217,728 (128 MiB) |

The aggregate counts the UTF-8 bytes of complete data URLs, including their
base64 data and MIME prefix. Base64 adds approximately one third to the binary
image size. These byte counts are not text-token estimates. The override is
gateway-wide for Responses requests; it grants no additional key, endpoint,
model or media permissions. Packaged defaults remain unchanged.

The whole HTTP body also contains text, tools, JSON framing and other input.
A 128 MiB aggregate image ceiling does not promise that 128 MiB of images plus
additional material fits a 128 MiB transport ceiling. The per-image cap and
all other policy/backend limits remain independent.

The adapter checks the complete serialized upstream JSON, after translation,
including text, image data URLs, tool declarations/results and JSON framing.
It is a byte limit, not a token estimate, output allowance or context window.
Serialization and tool translation can change the byte size from the incoming
HTTP body. Raising only image admission or Nginx's limit leaves the adapter's
64 MiB default active unless the route overrides it too.

## Configure and reload

Put the deployment override outside the checkout, alongside the deployment's
other operator configuration. For a production Compose deployment:

```yaml
services:
  api:
    environment:
      RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES: "134217728"
```

Combine this overlay with the existing production Compose files. A Settings
environment change requires recreating all HTTP API workers. A CLI subprocess
reading Settings alone does not prove existing workers reloaded. No schema
migration, compatibility-preset revision, key rotation or backend restart is
required. Background workers do not process these HTTP admission checks.

For active deployments, use a rolling replacement: start an API instance with
the same reviewed image, secrets, network and configuration plus this override;
verify readiness and its runtime setting; reload the reverse proxy to send new
requests there; then let old requests finish before replacing the old instance.
Restore the canonical routing and remove the temporary instance after it drains.
Do not interrupt a long generation just to update this limit. Previously
accepted requests retain their process's original Settings snapshot.

Check the API virtual host's effective Nginx body ceiling as well. Changing
only the application setting cannot bypass an earlier HTTP 413 from the proxy.
If the deployment already allows `128m`, this example requires no proxy-size
change. Keep the existing streaming buffering/timeouts intact.

## Configure the route adapter ceiling

This is existing PostgreSQL route configuration, not a new environment variable
or a compatibility-preset edit. Set `max_body_bytes` within the route's existing
transport contract, preserving every sibling and the selected adapter:

| Public model slug | Capability group | Deployment value |
| --- | --- | ---: |
| `qwen3.8-27b` | `local_coding_vllm` | 134,217,728 |
| `qwen3.8-27b-repaired` | `local_coding_vllm` | 134,217,728 |
| `qwen3.8-27b-rtx3090` | `local_coding_vllm` | 134,217,728 |
| `qwen3.8-27b-rtx3090-repaired` | `local_coding_vllm` | 134,217,728 |
| `qwen3.8-27b-V100` | `local_coding` | 134,217,728 |
| `qwen3.8-27b-V100-repaired` | `local_coding` | 134,217,728 |

The configured upstream-LLM selector on V100 remains unchanged; the byte cap
belongs to its `local_coding` transport contract. The packaged contract accepts
an integer from 1 through 268,435,456 bytes. Omitting the field uses 67,108,864.
The table is a deployment example, not a change to packaged defaults.

Use the normal administration CLI in the deployment's complete runtime
environment. Export the current route, construct a **complete** capabilities
file, then review and execute a fresh plan. Use new filenames for each operation;
the CLI does not overwrite plan files.

```bash
route_id='<existing Responses route UUID>'
slaif-gateway routes show "$route_id" --json > route-before.json
python3 - <<'PY'
import json
from pathlib import Path

route = json.loads(Path("route-before.json").read_text())
caps = route["capabilities"]
groups = [name for name in ("local_coding_vllm", "local_coding") if name in caps]
assert len(groups) == 1, "Expected exactly one existing transport contract"
caps[groups[0]]["max_body_bytes"] = 134217728
document = {"schema_version": 1, "capabilities": caps}
with Path("route-body-cap.json").open("x") as output:
    output.write(json.dumps(document, indent=2) + "\n")
PY
slaif-gateway routes update "$route_id" \
  --capabilities-file route-body-cap.json --dry-run route-body-cap.plan.json --json
```

Review the saved plan: only the intended contract's `max_body_bytes` should
change. `--capabilities-file` replaces the complete capabilities document, so
do not supply the small transport fragment alone. The file wrapper requires
`schema_version` and `capabilities`; a bare capabilities object is not accepted.
Execute the reviewed plan unchanged:

```bash
slaif-gateway routes update "$route_id" \
  --execute route-body-cap.plan.json \
  --reason 'Align adapter body ceiling with the 128 MiB ingress limit' --json
slaif-gateway routes show "$route_id" --json
```

Execution audits the route update and refuses stale plans. New requests read
the updated route without an API/worker restart, image rebuild, schema migration,
backend restart, key rotation or key-pin migration. Requests already in progress
keep their resolved route snapshot. This setting does not change the current
generic 502 error classification for requests exceeding the adapter ceiling.

## Verify without consuming GPU inference

Use the same complete runtime environment as the API and check readiness plus:

```python
from slaif_gateway.config import get_settings

settings = get_settings()
assert settings.RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES == 134217728
assert settings.RESPONSES_MAX_IMAGE_DATA_URL_BYTES == 20971520
assert settings.RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST == 0
```

For a public-ingress boundary check, send synthetic valid image data whose
combined encoded size exceeds 40 MiB but is below 128 MiB, with every image
below 20 MiB. Use a model slug deliberately unavailable to the test key.
`model_not_allowed_for_key` or `model_not_found` shows that image-size validation
passed and routing policy stopped the request before quota or inference.
Choose a slug absent from the deployment and key policy; never rely on a real
model being denied by accident. Do not log the data URLs or credentials.

That check proves ingress policy handling, not model vision quality or
large-context inference. Record the distinctions in verification evidence.
For an actual vision check, separately use a permitted model and bounded
synthetic images. The accepted image formats and route capabilities are
documented in [Responses compatibility](../responses-compatibility.md).

An ingress-only test using a denied model does **not** exercise the adapter.
Separately read all affected route contracts in the running API environment,
construct their actual adapters, and check `_exact_body` with synthetic content
above 64 MiB but below 128 MiB. Check a body above 128 MiB is still refused.
Calling that serialization method alone performs no HTTP or inference and
checks byte handling only; synthetic base64 strings need not be real images
for this isolated transport check. Do not claim it proves image decoding or
large-context inference. Record only sizes, limits and outcomes, not payloads.

## Recovery and rollback

After the new API workers are serving, retry the existing conversation. A byte
limit rejection does not itself require deleting history or rotating its key.
If the per-image or complete-body limit is reached next, reduce image size or
have the client compact/reconstruct visible history; changing token estimates
or the image count is not a byte-size remedy.

Rollback restores the previous API environment value and uses the same rolling
reload. Histories above the former 40 MiB aggregate limit will be rejected again
after rollback. Preserve user conversations and durable replay ownership.

For an adapter-only rollback, export the current route again and restore only
the original `max_body_bytes` leaf from the saved pre-change configuration. If
it was absent, remove the leaf to restore the 64 MiB default. Preserve any
intervening sibling edits, generate a new reviewed plan, and execute it through
the same CLI. Do not replay an already-applied plan or replace current routes
blindly with an old snapshot. Adapter-only rollback requires no restart and
can make histories above 64 MiB fail again.

## Deployment evidence — 2026-11-20

The operator applied the 128 MiB override using the existing reviewed image
for gateway main `0940d8a28f3a413d2a2cc6f4962c0efcafd71e13`. The per-image
20 MiB cap and zero image-count cap were checked unchanged. The active API
Nginx body ceiling was already `128m`.

A synthetic public request contained seven valid PNG data URLs totalling
48,934,550 encoded bytes, each 6,990,650 bytes. Its complete JSON body was
48,934,920 bytes. It passed image-size validation and returned the intended
HTTP 403 `model_not_allowed_for_key`; no provider inference was performed.
Operational backups and rollout state remain outside the repository. No real
user images, request bodies, credentials or opaque replay IDs are committed.

## Deployment evidence — 2026-11-22

On engine main `0c0ffec2a8ff70fc3c304471a5427dd2ab8a8058`, all six routes above
still inherited the 64 MiB adapter default after the earlier image-admission
increase. An isolated adapter check accepted a 62,914,995-byte serialized body
and rejected seven 10 MiB synthetic image strings with HTTP 502
`provider_request_error`, without making HTTP calls. Direct A100 transport
probes with a deliberately nonexistent model reached normal HTTP 404 model
validation through a 125,829,264-byte request; they requested no inference.

The operator set only each route contract's `max_body_bytes` to 134,217,728
through reviewed, audited CLI plans. All other route fields and existing key
configuration remain unchanged. No engine source, packaged default, preset,
schema or backend setting changed. The original failing request's byte count
and internal failure branch were not retained, so this evidence establishes
the configuration mismatch and its reproducible error, not conclusive
attribution of that historical request.

Verification constructed all six adapters from the updated route records using
the installed engine image in a network-isolated container. Each accepted a
73,400,814- or 73,400,815-byte serialized synthetic body and rejected a body
above 128 MiB. No provider credentials, HTTP calls or GPU inference were used.
All 90 existing key configurations and all route configuration outside the six
byte-cap leaves were checked unchanged. These checks exercise serialization,
not image decoding or a replay of the original user's request.
