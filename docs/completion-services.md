# Configured completion services

Facial scoring and ZAP-IT use **one** `CompletionServiceAdapter`. Service
differences live in strict JSON profiles shipped under
`app/slaif_gateway/modules/servers/completion_service/profiles/`.
They serve custom clients using non-streaming `POST /v1/chat/completions`;
they are not Codex routes or arbitrary OpenAI model replacements.

| Profile | Public model | Native path / transport | Backend authentication | Assistant content |
| --- | --- | --- | --- | --- |
| `facial-scoring-v1` | `facial-manipulation-scoring` | `/v1/score`, multipart `image` | `X-API-Key`, `FACIAL_SCORING_API_KEY` | Existing score/unscorable text |
| `zap-it-v1` | `zap-it-1` | `/v1/responses`, inline image and YAML file | Bearer, `ZAP_IT_API_KEY` | Canonical `zap-it.public.v1` JSON text plus one annotated PNG |

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

Since objective 199 this setup is a reviewed CLI workflow (no operator
Python). The provider creation stays DISABLED until explicitly enabled, and
a capabilities-file route preparation stays DISABLED until the operator
passes `--enabled` - keep both disabled until the credentials and key grants
are reviewed:

```text
# ZAP-IT backend (facial scoring: --provider facial_scoring,
# --api-key-env-var FACIAL_SCORING_API_KEY, --timeout-seconds 30)
slaif-gateway providers add --provider zap_it \
  --api-key-env-var ZAP_IT_API_KEY --kind module \
  --base-url https://zap-it.internal --timeout-seconds 180 \
  --max-retries 0 --reason "module backend"

# Exact model route on /v1/chat/completions, non-streaming
slaif-gateway routes add --requested-model zap-it-1 --match-type exact \
  --provider zap_it --upstream-model zap-it-1 \
  --endpoint /v1/chat/completions --no-streaming \
  --capabilities-file /tmp/zap-it-route-caps.json \
  --reason "completion service route (preparation)"

# After reviewing credentials and key grants:
slaif-gateway providers enable zap_it
slaif-gateway routes enable <route-uuid>
```

The capabilities file is the COMPLETE strict document (schema version 1, at
most 64 KiB): the narrow non-streaming text/image Chat profile plus the
profile selector. For ZAP-IT:

```json
{
  "schema_version": 1,
  "capabilities": {
    "chat_completions": {
      "chat_text": true,
      "chat_streaming": false,
      "chat_function_tools": false,
      "chat_custom_tools": false,
      "chat_legacy_functions": false,
      "chat_structured_outputs": false,
      "chat_json_mode": false,
      "chat_logprobs": false,
      "chat_reasoning_usage": false,
      "chat_cached_input_usage": false,
      "hosted_web_search": false,
      "hosted_file_search": false,
      "hosted_code_interpreter": false,
      "hosted_computer_use": false,
      "hosted_image_generation": false,
      "hosted_tool_search": false,
      "external_mcp_connectors": false,
      "chat_video_inputs": false,
      "chat_image_inputs": true,
      "chat_multimodal": true,
      "chat_audio": false,
      "chat_file_inputs": false,
      "chat_audio_inputs": false,
      "chat_audio_outputs": false,
      "chat_service_tier_non_default": false,
      "chat_multiple_choices": false
    },
    "completion_service": {"version": 1, "profile": "zap-it-v1"}
  }
}
```

For facial scoring, replace the profile ID with `facial-scoring-v1` and use
provider slug `facial_scoring` with the matching public/upstream model from
the table. Later reviewed adjustments go through the two-step
`routes update --dry-run/--execute` plan workflow. Existing facial routes
without this selector continue to resolve the same shared adapter and
bundled facial profile; no key or database migration is required. Legacy
adapter imports are aliases, not a second implementation. The registry
contains one generic descriptor; service/provider names occur in
binding/profile JSON data, not routing branches. ZAP-IT providers use the
explicit selector; unconfigured/unknown native modules still fail closed.

Route configuration that selects a completion profile is validated at
CONFIGURATION time, before any write (objective 199): the complete
candidate must first resolve, through the EXISTING pure server-module
resolution, to a supported server module - an unregistered `module`-kind
provider with no selector and no legacy binding is refused before any
write or audit. Configured-completion routes - an explicit
`completion_service` selector OR the implicit legacy profile binding for
the provider slug - additionally require a `module` kind on the chat
completions endpoint with `max_retries=0` (the completion adapter's
zero-retry rule), the profile in the SAME profile directory the runtime
uses - the bundled directory, or the absolute, non-symlink operator
directory configured through `COMPLETION_SERVICE_PROFILE_DIR` (files
regular, non-symlink, 0600, at most 64 KiB; when an operator directory is
configured, the bundled directory is not visible) - and the profile's
public/upstream model must match the route's requested/upstream model.
The configuration must not advertise streaming (the route
`supports_streaming` flag or the `chat_completions.chat_streaming`
capability): the completion adapter refuses stream values other than
`false`, so reviewed streaming declarations are refused, never silently
stripped. These are configuration-time checks: they validate
configuration, not credential or model readiness, and perform no
credential loading, adapter construction, or network call.

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
creation. Keep providers/routes disabled until their credentials and policy
are configured. These metadata changes use the audited CLI (objective 199)
or the existing audited dashboard/service layer.

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
# images is an explicit Chat response extension for custom clients.
image_url = result.choices[0].message.model_extra["images"][0]["image_url"]["url"]
assert image_url.startswith("data:image/png;base64,")
Path("annotated.png").write_bytes(base64.b64decode(image_url.split(",", 1)[1], validate=True))
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
responses are bounded to 2 MiB for the facial profile and 32 MiB for the
text-and-image profile, including error bodies. The latter additionally limits
the decoded output image to 16 MiB; both ceilings apply. Image decoding and
API-safe YAML semantic validation remain the backend's responsibility. YAML
bytes are placed in an inline `application/yaml` file without interpreting
them, executing them or treating their fields as gateway routing instructions.

No streaming, remote images, extra images/messages for ZAP-IT, tools,
non-default generation controls, client-selected paths/headers, ZIP output,
debug artifacts or client-selected image-generation tools are accepted. The adapter sends only
the selected image and (for the YAML mapping) configuration. It never sends the
gateway key, cookies or other client headers. Results have the normal Chat
Completion envelope and zero token usage. ZAP-IT returns the public JSON
projection plus exactly one final labelled PNG. The profile requests the
backend's fixed image-output declaration and validates its completed output
item before mapping the PNG; it does not forward client tool declarations.
Masks, ZIPs and native L3/debug data are outside this profile. A malformed/private/incomplete upstream envelope
fails with a safe gateway error rather than being passed through.

The public gateway does not add `/v1/completions`, multipart ingress or module
Responses ingress. ZAP-IT's private `/v1/completions` remains a separate native
operator API; the shared adapter deliberately calls its documented public
Responses facade. An upstream path name does not select the gateway wire API.

## Generic text-and-image output mapping

The shared `json_fields` response mapping works with any configured service
using the supported transports. It does not inspect service names, model
names or schema names in code. A profile selects the text with `text_pointer`
and can select one base64 image using `image_output.pointer`, its declared
PNG/JPEG/WebP MIME type and a decoded byte ceiling. These are bounded JSON
pointers (including fixed array indexes and RFC 6901 escapes), never expressions,
URLs, templates or executable functions. Optional `response_checks` enforce
exact typed scalar markers; `response_array_lengths` enforce exact cardinality.
For example, an unrelated multipart service can use:

```json
{
  "response_mapping": "json_fields",
  "text_pointer": "/caption",
  "image_output": {
    "pointer": "/picture",
    "media_type": "image/png",
    "max_decoded_bytes": 16777216
  },
  "max_response_bytes": 33554432
}
```

This excerpt is merged into a full service profile. It requires no new adapter
class or service-name condition. With no `result_schema_version`, text is passed
as a string; with one, it must contain a JSON object bearing that configured
schema version and is canonically serialized. With no `image_output`, the
mapping remains text-only. A selected image is required: missing, malformed,
oversized, wrong-signature or failed-marker results reject the whole completion
rather than silently dropping the image or returning partial text.

The response keeps `choices[0].message.content` as text and adds:

```json
{"images":[{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}]}
```

`message.images` is a documented custom-client Chat extension, not a claim that
standard OpenAI Chat image output or automatic SDK/UI image rendering is
supported. The official SDK retains it in `message.model_extra`; custom clients
can decode the inline image. No remote image URL is fetched or returned by this
mapping. Strict base64, non-empty data, declared MIME signatures and encoded,
decoded and complete-response byte bounds are checked. The gateway does not
fully decode/re-encode the image or claim pixel-format/image-quality validation.

For Responses-shaped backends, `request_image_output: true` adds the one fixed
`image_generation` declaration to the translated upstream request. This is a
generic transport option, allowed only alongside an image-output mapping and the
Responses request mapper. Native multipart backends that already return an image
leave it false. The ZAP-IT profile configures its output paths, completed-state
checks and two-item cardinality in JSON; it uses the backend's deterministic
annotation renderer, not a generative model. Other services can select entirely
different response fields with the same engine. This setting does not enable
public client tools, a gateway image-generation endpoint, streaming, or new key
authority. Fixed-request accounting and privacy are unchanged.

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
