# Media input estimates and direct video

Encoded transport bytes are not vision tokens. A 474,454-byte PNG becomes a
632,630-character data URL, but the deployed Qwen tokenizer counted only 314
tokens for the corresponding image prompt. The previous byte/3 context estimate
therefore rejected valid image history before inference.

## Route-owned admission budgets

The optional model-route capability data below replaces encoded media URL
material with a conservative token budget for each typed media part:

```json
"media_input_estimation": {
  "version": 1,
  "image_tokens": 16896,
  "video_tokens": 65536,
  "video_frames": 4
}
```

The shipped examples are in
`app/slaif_gateway/resources/media-input-estimation-presets.json`. Operators
merge the selected data into route capabilities using existing audited route
administration. Budgets are model/preprocessor policy, not universal tokenization
facts, exact per-image counts or billing units. Review them when backend
preprocessing changes. No client compatibility revision or key migration is
involved. Missing budgets retain the existing conservative estimate for images;
video requires an explicit budget and frame policy. Malformed policy fails closed.
Each token budget must be a positive integer no larger than 1,050,000; frame
limits must be integers from 1 to 32. Those are engine ceilings, not defaults.

Raw request, image/video bytes, image/video count, text and schema limits still
run before routing. Only the media portion of the preliminary token check is
deferred; after current key/model/provider/route gates, the complete configured
estimate is checked against the operator input cap and Codex route context.
Plain text containing a data URL remains text. Real text can still exhaust the
context window. Image tool-result history and user-image content use the same
estimator without changing their contents. Extracted video frames represented
as input images receive one image budget each.

Since objective 199, partial budget edits are a reviewed CLI plan step: the
three `--media-*` flags merge the selected leaves only (omitted leaves and all
sibling capability groups are preserved), and the plan must be executed
unchanged:

```text
slaif-gateway routes update <route-uuid> --dry-run /tmp/media-plan.json \
  --media-image-tokens 16896 --media-video-tokens 65536 --media-video-frames 4

slaif-gateway routes update <route-uuid> --execute /tmp/media-plan.json \
  --reason "reviewed media budget"
```

A complete `media_input_estimation` group can also ship inside a
`--capabilities-file` COMPLETE replacement document.

The same estimate feeds TPM admission, cost/token reservation and interruption
accounting. Provider-reported actual usage/cost remains authoritative on success.
The engine retains the unadjusted count so lazy-wait route revalidation computes
the current estimate once, including when a budget is removed or changed. No
request bodies, media, raw identifiers or URLs enter safe diagnostics.

## Direct video input

The deployed native vLLM backend exposes video input through Chat Completions,
not its Responses input union. Direct video is therefore a bounded opt-in
`POST /v1/chat/completions` surface. Codex continues to use Responses for image
history; this change does not add a video viewer to Codex or translate video
into fabricated Responses items.

A key must already permit Chat Completions and the model/provider. The selected
route must additionally set `chat_completions.chat_video_inputs=true`, use the
reviewed native `openai_compatible` transport, select the static
`vllm_chat_video={"version":1}` server contract and configure video tokens/frames.
Other providers and unconfigured routes fail closed. Existing keys are not
modified or automatically granted a new endpoint/model. OpenAI/OpenRouter
native-video compatibility is not claimed by this native-vLLM slice.

Only user-message inline `video_url` parts containing MP4 or WebM base64 data
URLs are accepted. Remote URLs, local/file URLs, extra fields, client-selected
frame/processor controls and video generation remain rejected. The gateway does
not fetch, decode, extract frames from, store or rewrite the video. The native
backend receives the operator's `media_io_kwargs.video.num_frames` limit after
public payload normalization, so clients cannot raise it. Limits default to one
video per request and 10,485,760 encoded URL bytes via
`CHAT_MAX_VIDEOS_PER_REQUEST` and `CHAT_MAX_VIDEO_DATA_URL_BYTES`; existing global
body/ingress limits can be lower and still apply.

Use the ordinary OpenAI Python client and standard environment variables:

```python
import base64
from pathlib import Path
from openai import OpenAI

video = base64.b64encode(Path("clip.mp4").read_bytes()).decode("ascii")
response = OpenAI().chat.completions.create(
    model="qwen3.8-27b",
    max_tokens=128,
    messages=[{"role": "user", "content": [
        {"type": "text", "text": "Describe this video."},
        {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + video}},
    ]}],
)
print(response.choices[0].message.content)
```

This is video input for a text answer. It creates no Files/Uploads lifecycle,
video-generation endpoint, streaming video output or general provider support.
Verification is recorded in [the scoped report](verification/2026-10-20-media-input-estimation.md).
