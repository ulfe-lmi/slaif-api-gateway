# Codex image-history payload size

Use this runbook for `responses_input_image_data_url_too_large` when the
gateway reports that the Responses input image data URLs exceed its size
limit. The exact aggregate message means the combined encoded image data in
one request crossed `RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES`.

Codex can resend earlier image tool results with subsequent turns. The check
therefore includes images retained in the submitted conversation, not just
the image most recently opened. It is separate from image-count acceptance,
geometry-based image token estimation and the backend context window. Retrying
the same unchanged history does not reduce its byte size.

## Default versus deployed settings

The Qwen deployment example uses this operator override as of 2026-11-20:

| Setting | Packaged default | Deployment example |
| --- | ---: | ---: |
| `RESPONSES_MAX_IMAGE_PARTS_PER_REQUEST` | 0, no gateway image-count cap | 0 |
| `RESPONSES_MAX_IMAGE_DATA_URL_BYTES` | 20,971,520 (20 MiB) per encoded image | unchanged |
| `RESPONSES_MAX_TOTAL_IMAGE_DATA_URL_BYTES` | 41,943,040 (40 MiB) per request | 134,217,728 (128 MiB) |
| Nginx API `client_max_body_size` | inspect the deployment's active configuration | `128m` |

The aggregate counts the UTF-8 bytes of complete data URLs, including their
base64 data and MIME prefix. Base64 adds approximately one third to the binary
image size. These byte counts are not text-token estimates. The override is
gateway-wide for Responses requests; it grants no additional key, endpoint,
model or media permissions. Packaged defaults remain unchanged.

The whole HTTP body also contains text, tools, JSON framing and other input.
A 128 MiB aggregate image ceiling does not promise that 128 MiB of images plus
additional material fits a 128 MiB transport ceiling. The per-image cap and
all other policy/backend limits remain independent.

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

## Recovery and rollback

After the new API workers are serving, retry the existing conversation. A byte
limit rejection does not itself require deleting history or rotating its key.
If the per-image or complete-body limit is reached next, reduce image size or
have the client compact/reconstruct visible history; changing token estimates
or the image count is not a byte-size remedy.

Rollback restores the previous API environment value and uses the same rolling
reload. Histories above the former 40 MiB aggregate limit will be rejected again
after rollback. Preserve user conversations and durable replay ownership.

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
