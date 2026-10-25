# Configured completion services

Facial scoring and ZAP-IT use **one** `CompletionServiceAdapter`. Service
differences live in strict JSON profiles shipped under
`app/slaif_gateway/modules/servers/completion_service/profiles/`.
They serve custom clients using non-streaming `POST /v1/chat/completions`;
they are not Codex routes or arbitrary OpenAI model replacements.

| Profile | Public model | Native path / transport | Backend authentication | Assistant content |
| --- | --- | --- | --- | --- |
| `facial-scoring-v1` | `facial-manipulation-scoring` | `/v1/score`, multipart `image` | `X-API-Key`, `FACIAL_SCORING_API_KEY` | Existing score/unscorable text |
| `zap-it-v1` | `zap-it-1` | `/v1/responses`, inline image and YAML file | Bearer, `ZAP_IT_API_KEY` | Canonical `zap-it.public.v1` JSON text |

Both transports use the operator-configured provider origin. Profiles contain
no backend address or credential value. They select reviewed mapping primitives,
fixed upstream paths, authentication header/prefix, model identities, image MIME
types, byte limits, and output schema. There are no templates, expressions,
imports, subprocesses or user-selected network destinations. Adding a profile
for an existing primitive needs data and qualification, not another adapter class.
A new wire protocol still needs a reviewed reusable mapping primitive.

## Provider and route setup

Create provider metadata with `kind=module`, an operator-controlled HTTPS origin
(without `/v1`), the profile's credential environment-variable reference,
`max_retries=0`, and a finite timeout. Facial scoring normally uses 30 seconds;
ZAP-IT can require 180 seconds to cover its bounded inference deadline. Internal
HTTP requires the existing explicit insecure-HTTP confirmation and audit reason.
Never put credentials into route capabilities, profile files, notes, URLs or logs.

Use an exact model route on `/v1/chat/completions`, `supports_streaming=false`,
with the matching public and upstream model from the table. Build capabilities
using the existing service layer:

```python
from slaif_gateway.services.chat_completion_route_capabilities import (
    completion_service_chat_completion_capabilities,
)

capabilities = {
    "chat_completions": completion_service_chat_completion_capabilities(),
    "completion_service": {"version": 1, "profile": "zap-it-v1"},
}
```

For facial scoring, replace the profile ID with `facial-scoring-v1` and use
provider slug `facial_scoring`. Existing facial routes without this selector
continue to resolve the same shared adapter and bundled facial profile; no
key or database migration is required. Legacy adapter imports are aliases,
not a second implementation. ZAP-IT providers use the explicit selector;
unconfigured/unknown native modules still fail closed.

Add an enabled pricing row for the same provider, upstream model and endpoint:
currency `EUR`, `request_price=0`, `input_price_per_1m=0`,
`output_price_per_1m=0`. Both profiles use existing fixed-request module billing:
reserve one request, zero tokens and the configured request cost, finalize one
request and zero provider tokens, release failures through the normal accounting
path. Zero price does not bypass quotas, key expiry/revocation or Redis controls.

Grant intended keys the exact model, provider and endpoint, with image/multimodal
capabilities and suitable request/concurrency limits. ZAP-IT's backend supports
one active inference; use one concurrent request per key and coordinate access
across keys with backend/operator admission. Gateway per-key concurrency does
not create a global one-slot queue. No new keys or grants are implicit in route
creation. Keep providers/routes disabled until their credentials and policy are
configured. Metadata changes use the existing audited dashboard/service layer.

## Client examples

Use the standard environment variables:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="https://api.ulfe.slaif.si/v1"
```

Both services use the same SDK call. For ZAP-IT, the single text part is the
complete API-safe YAML configuration, not a natural-language prompt:

```python
import base64
import json
from pathlib import Path
from openai import OpenAI

image_url = "data:image/png;base64," + base64.b64encode(
    Path("image.png").read_bytes()
).decode("ascii")
result = OpenAI().chat.completions.create(
    model="zap-it-1",
    messages=[{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": image_url}},
        {"type": "text", "text": Path("task.yaml").read_text(encoding="utf-8")},
    ]}],
)
projection = json.loads(result.choices[0].message.content)
assert projection["schema_version"] == "zap-it.public.v1"
```

For facial scoring, use `model="facial-manipulation-scoring"`, omit the YAML
part, and read `result.choices[0].message.content` as score/unscorable text.
Existing facial text parts remain validation-only and are not forwarded.

## Bounds and privacy

The bundled profiles accept exactly one inline base64 image. Facial scoring
retains PNG/JPEG/WebP/GIF compatibility; ZAP-IT accepts PNG/JPEG/WebP and exactly
one non-empty YAML text part in one user message. Core request limits also
apply; profile limits can narrow them, never grant a capability. Bundled image
data-URL limits are 10 MiB encoded; YAML is at most 256 KiB; decoded upstream
responses are bounded to 2 MiB, including error bodies. Image decoding and
API-safe YAML semantic validation remain the backend's responsibility. YAML
bytes are placed in an inline `application/yaml` file without interpreting
them, executing them or treating their fields as gateway routing instructions.

No streaming, remote images, extra images/messages for ZAP-IT, tools,
non-default generation controls, client-selected paths/headers, ZIP output,
debug artifacts or image-generation calls are accepted. The adapter sends only
the selected image and (for the YAML mapping) configuration. It never sends the
gateway key, cookies or other client headers. Results have the normal Chat
Completion envelope and zero token usage. ZAP-IT returns the public JSON
projection only; masks, ZIPs, native L3/debug data and the optional annotated PNG
are outside this profile. A malformed/private/incomplete upstream envelope
fails with a safe gateway error rather than being passed through.

The public gateway does not add `/v1/completions`, multipart ingress or module
Responses ingress. ZAP-IT's private `/v1/completions` remains a separate native
operator API; the shared adapter deliberately calls its documented public
Responses facade. An upstream path name does not select the gateway wire API.

## Operator overrides and verification

Set `COMPLETION_SERVICE_PROFILE_DIR` to an absolute operator-owned directory
containing the selected `<profile-id>.json` files to override bundled profiles.
Files must be regular, at most 64 KiB, not symlinks or group/world-writable.
Only safe profile IDs are accepted; route metadata cannot supply paths or
inline profile bodies. Unknown JSON fields and mapping types fail closed.
Profiles are cached per process: restart all API workers after edits. The
directory is a complete source for selected profiles, not a fallback merge.
Package presets are included in the built wheel/container.

Verification uses mock upstreams and an isolated PostgreSQL database. Existing
facial tests continue to verify the unchanged score protocol; ZAP-IT tests
verify exact outbound JSON, credential isolation, output validation, byte bounds
and actual gateway HTTP handling. Both profiles exercise real PostgreSQL
pricing, reservation/finalization/release, quota exhaustion, revocation, expiry
and audit boundaries. This does not claim live inference, image accuracy,
production qualification or deployment of a route/key grant. Deployment and an
authorized upstream smoke remain operator steps after review.
