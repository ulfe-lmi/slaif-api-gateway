# Chat Completions Multimodal Investigation

Checked on 2026-05-18.

This note records the current upstream evidence for Chat Completions
image/audio/file request and response shapes, and the SLAIF work required before
any of those surfaces can be enabled safely. It is a documentation decision
record only. This PR does not change runtime behavior, request policy, provider
forwarding, pricing, quota reservation, or accounting.

## Sources Checked

OpenAI official docs:

- [Chat Completions API reference](https://platform.openai.com/docs/api-reference/chat/create-chat-completion)
- [Text generation guide](https://platform.openai.com/docs/guides/chat-completions)
- [Images and vision guide](https://platform.openai.com/docs/guides/images-vision?api-mode=chat)
- [Audio and speech guide](https://platform.openai.com/docs/guides/audio)
- [File inputs guide](https://platform.openai.com/docs/guides/pdf-files?api-mode=chat)
- [GPT-4o Audio model page](https://platform.openai.com/docs/models/gpt-4o-audio-preview)

OpenAI SDK:

- Locally installed official `openai` Python package: `2.32.0`.
- Generated Chat Completions types under
  `.venv/lib/python3.12/site-packages/openai/types/chat/`.

OpenRouter official docs:

- [Multimodal overview](https://openrouter.ai/docs/guides/overview/multimodal/overview)
- [Image inputs](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding)
- [Audio](https://openrouter.ai/docs/guides/overview/multimodal/audio)
- [Chat completion API reference](https://openrouter.ai/docs/api-reference/chat-completion)
- [Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting)

Current SLAIF implementation:

- `app/slaif_gateway/services/chat_completion_field_policy.py`
- `app/slaif_gateway/services/chat_completion_request_caps.py`
- `app/slaif_gateway/services/chat_completion_route_capabilities.py`
- `app/slaif_gateway/services/hosted_tool_policy.py`
- `app/slaif_gateway/services/input_token_estimation.py`
- `app/slaif_gateway/services/accounting.py`
- `app/slaif_gateway/services/pricing.py`
- `app/slaif_gateway/providers/openai.py`
- `app/slaif_gateway/providers/openrouter.py`
- Unit tests in `tests/unit/test_request_policy_service.py` and
  `tests/unit/test_v1_chat_completions_policy.py` that cover current
  multimodal/audio/file rejection and image-input enablement.

## Current SLAIF Behavior

SLAIF now supports Chat Completions image input to text output and inline file
input to text output as narrow multimodal slices. Text content may be a string
or text content parts inside the existing message caps. User messages may also
include documented `image_url` content parts only when the resolved route
explicitly sets `capabilities.chat_completions.chat_image_inputs=true`, and
documented inline `file` content parts only when the route explicitly sets
`capabilities.chat_completions.chat_file_inputs=true`.

Supported image shape:

```json
{ "type": "image_url", "image_url": { "url": "...", "detail": "low" } }
```

The `detail` field is optional and must be one of `auto`, `low`, or `high`.
Remote `http`/`https` URLs and base64
`data:image/png|jpeg|webp|gif;base64,...` data URLs are bounded by runtime
settings. SLAIF does not fetch remote image URLs, decode image pixels, rewrite
image payloads, store/log image URLs or base64 data, or infer exact image cost
from bytes.

Supported inline file shape:

```json
{ "type": "file", "file": { "filename": "notes.txt", "file_data": "..." } }
```

`file_data` must be inline base64 data. Raw base64 is accepted by default;
`data:<mime>;base64,...` values are accepted only when
`CHAT_ALLOW_FILE_DATA_URLS=true`. Filenames, file payload size, per-message
count, per-request count, MIME types, and filename extensions are bounded by
runtime settings. SLAIF rejects `file_id`, file URLs, unknown file fields, unsafe
filenames, unsupported file types, and malformed base64. SLAIF does not fetch
file URLs, call `/v1/files`, upload files upstream, decode/rewrite file data,
store/log file data, filenames, file IDs, or file URLs, or infer exact file cost
from bytes.

SLAIF supports user-message `input_audio` parts for audio input to text output
only when the resolved route explicitly sets `chat_audio_inputs=true`.
Accepted parts use the documented Chat Completions shape:
`{ "type": "input_audio", "input_audio": { "data": "<base64>", "format": "wav" | "mp3" } }`.
The base64 payload, per-message count, per-request count, and allowed formats
are bounded by runtime settings. SLAIF rejects audio URLs, audio data URLs by
default, unsupported formats, malformed base64, assistant-message audio
references, top-level audio-output controls unless the separate audio-output
capability and pricing policy also allow them, and unknown audio fields. SLAIF
does not fetch audio URLs, transcribe audio locally, decode/rewrite audio data,
store/log audio payloads or decoded bytes, or infer exact audio cost from
bytes or duration.

SLAIF supports non-streaming Chat Completions audio output only when the
resolved route explicitly sets `chat_audio_outputs=true` and the active pricing
row includes `pricing_metadata.audio_output_price_per_1m`. Accepted requests use
top-level `modalities: ["text", "audio"]` plus top-level
`audio: { "format": "wav" | "mp3" | "flac" | "opus" | "pcm16", "voice": ... }`
with a configured built-in voice. SLAIF preserves non-streaming provider
`choices[].message.audio` objects for the client, including provider-generated
audio data and transcript, without storing or logging them. SLAIF rejects
streaming audio output, `n > 1` with audio output, custom voices, and assistant
previous-audio references. SLAIF does not transcode audio, infer exact
audio-output cost from bytes, transcript length, format, voice, or duration, or
multiply final provider usage/cost by audio output count or `n`.

SLAIF currently rejects:

- older or alternate non-text part names such as `input_image`, `input_file`,
  `image`, `audio`, and `video`;
- top-level `audio` unless paired with `modalities: ["text", "audio"]`,
  `chat_audio_outputs=true`, supported format/voice settings, and configured
  audio-output pricing metadata;
- `modalities` values other than text-only or the route-enabled non-streaming
  audio-output shape.

The current field policy rejects these shapes before provider forwarding with
safe OpenAI-shaped errors. The rejection path names only the rejected field or
content-part type. It does not store or log prompts, completions, raw request
bodies, raw response bodies, images, audio, files, base64 payloads, external
URLs, file IDs, tool payloads, provider keys, gateway plaintext keys,
Authorization headers, cookies, CSRF tokens, or session tokens.

The remaining rejection paths return safe OpenAI-shaped errors and do not log
or return raw payloads.

## Upstream Evidence Matrix

| Feature | OpenAI documented shape | SDK shape | Role restrictions | Model restrictions | Streaming clarity | Usage/pricing evidence | Current SLAIF status | Recommended next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Image input, text output | User message `content` array containing `{ "type": "image_url", "image_url": { "url": "...", "detail"?: one of "auto", "low", "high" } }`. URLs and base64 data URLs are documented. | `ChatCompletionContentPartImageParam` exists with `type: "image_url"`, `image_url.url`, and `detail` `auto`, `low`, or `high`. | OpenAI API reference exposes image parts for user messages. Developer/system messages are text-only in SDK types. | Requires a vision-capable model and explicit SLAIF `chat_image_inputs=true` route capability. Detail behavior and tokenization vary by model family. | Supported for ordinary text SSE chunks; no separate image-output stream shape is enabled. | OpenAI states images count as tokens and documents patch/tile tokenization. Provider `usage.prompt_tokens` includes image-derived tokens, but precise pre-call estimation requires dimensions, detail, model family, and possibly provider-specific behavior. | Implemented behind explicit route capability. | Keep narrow: image input to text output only. Continue to rely on caps plus provider usage/cost finalization; do not infer exact image cost from bytes. |
| File input, text output | User message `content` array containing `{ "type": "file", "file": { "file_data"?: "...", "file_id"?: "...", "filename"?: "..." } }`. The file guide shows Chat Completions base64 file data and uploaded file IDs. It explicitly says file URLs are not supported for Chat Completions. | `ChatCompletionContentPartParam.File` exists with `type: "file"`, `file.file_data`, `file.file_id`, and `file.filename`. | File parts are part of user message content. Developer/system messages are text-only in SDK types. | Requires file-capable or vision-capable models depending on file type. PDFs may include extracted text plus page images; non-PDF behavior varies. | Supported for ordinary text SSE chunks; no file-specific stream output shape is enabled. | OpenAI warns PDF parsing can add both extracted text and page images to context. File size limits and accepted types are documented, but pre-call billable tokens cannot be inferred reliably from bytes alone. | Inline `file_data` plus `filename` is implemented behind explicit `chat_file_inputs=true`; file IDs and file URLs are rejected. | Keep narrow: inline file input to text output only. Continue to rely on caps plus provider usage/cost finalization; do not infer exact file cost from bytes. |
| Audio input, text output | User message `content` array containing `{ "type": "input_audio", "input_audio": { "data": "<base64>", "format": "wav" or "mp3" } }`. | `ChatCompletionContentPartInputAudioParam` exists with base64 `data` and `format` `wav` or `mp3`. | Audio parts are user message content. Developer/system messages are text-only in SDK types. | Requires an audio-capable model such as the documented audio model family and explicit SLAIF `chat_audio_inputs=true` route capability. | Supported for ordinary text SSE chunks; no audio-output stream shape is enabled. | OpenAI usage types include `prompt_tokens_details.audio_tokens`. Model pages can price text tokens separately from audio tokens. Bytes/duration are not equivalent to billable tokens. | Implemented behind explicit route capability for text output only. | Keep narrow: audio input to text output only. Continue to rely on caps plus provider usage/cost finalization; do not infer exact audio cost from bytes or duration. |
| Text input, audio output | Top-level `modalities: ["text", "audio"]` plus `audio: { "voice": ..., "format": one of "wav", "aac", "mp3", "flac", "opus", "pcm16" }`. Non-streaming OpenAI examples return `choices[].message.audio` with base64 `data`, `id`, `expires_at`, and `transcript`. | `CompletionCreateParamsBase.modalities` allows `text` and `audio`; `ChatCompletionAudioParam` exists. Non-streaming `ChatCompletionMessage.audio` exists. Stream chunk type in the installed SDK has no `delta.audio` field. | Applies at request top level, not as a user content part. | Requires audio-output-capable model and explicit SLAIF `chat_audio_outputs=true` route capability. | Non-streaming shape is clear and implemented. Streaming remains ambiguous across providers: the installed OpenAI Chat Completions stream chunk type does not model audio deltas, while OpenRouter documents `delta.audio`. | OpenAI usage types include `completion_tokens_details.audio_tokens`. Model pages can price text tokens separately from audio tokens. OpenRouter says audio output is priced as completion tokens and returns cost/usage details. | Non-streaming implemented behind explicit route capability and `pricing_metadata.audio_output_price_per_1m`; streaming, `n > 1`, custom voices, and previous-audio references remain rejected. | Keep streaming audio output as a separate follow-up until SDK/API delta shape and accounting tests are clear. |
| Audio input, audio output | Combines user `input_audio` content with `modalities: ["text", "audio"]` and `audio` output config. | Request types exist for both sides. Non-streaming audio response exists; streaming delta is ambiguous in installed SDK. | Audio input is user content; audio output is top-level request config. | Requires bidirectional audio-capable model and both SLAIF `chat_audio_inputs=true` and `chat_audio_outputs=true` route capabilities. | Non-streaming is supported by composing the independently validated input and output shapes. Streaming audio output remains unsupported. | Both prompt and completion audio token details may matter. Text token prices are not enough. | Non-streaming supported only when both route capabilities and audio-output pricing metadata are present. | Keep streaming and `n > 1` combinations rejected until separately implemented and tested. |
| Mixed text plus image/audio/file inputs | OpenAI and OpenRouter both document content arrays that can contain multiple part types. | The user-message content union includes text, image, input audio, and file parts. | User message only for non-text parts; developer/system message SDK types remain text-only. | Requires every requested modality to be supported by the selected model/provider. | Text-output streaming can keep the existing SSE pass-through model for image/file/audio inputs; streaming audio output remains unsupported. | Mixed inputs create mixed usage surfaces: text, image-derived, file-derived, audio input, audio output, cached input, and reasoning tokens. | Text+image+inline-file+audio input is supported only when every route capability is explicit. Non-streaming audio output may compose with those inputs when `chat_audio_outputs=true` and pricing metadata are configured. File IDs, file URLs, audio URLs, and streaming audio output remain rejected. | Defer streaming audio output and file-ID/file-URL combinations until each surface has its own caps, capability flags, pricing, and accounting coverage. |
| Interaction with `n > 1` | OpenAI documents `n` as multiple choices and charges generated tokens across choices. | SDK supports `n`; stream chunks can contain multiple choices. | No modality-specific role change. | Model/provider support may vary. | Text streaming multiple choices is already supported by SLAIF. Audio output with `n > 1` is not clear enough for immediate support. | Do not multiply provider usage by `n`; PR #157 already established final usage is authoritative once. Pre-call output reservation multiplies possible text output per choice, while image/file/audio/message input is estimated once. | Image, inline file, or audio input with `n > 1` is supported only when both the modality capability and `chat_multiple_choices=true` are set. `n > 1` with audio output is rejected. | Keep final provider usage/cost authoritative once; add separate tests before enabling multiple audio-output choices. |
| Interaction with local function tools | Function tools are local/client-side intent. | SDK supports function tools with Chat Completions. | No modality-specific role change. | Model/provider support may vary. | Text streaming function tools are already supported. | Function schemas are ordinary input material; modality usage is separate. | Image, inline file, audio input, or non-streaming audio output with function tools is supported only when both the relevant modality capability and `chat_function_tools=true` are set. | Keep hosted tools separate and denied unless explicitly implemented later. |
| Interaction with non-streaming custom local tools | Custom tools are local/client-side intent. | SDK supports non-streaming custom tools and custom tool calls. | No modality-specific role change. | Model/provider support may vary. | Streaming custom tools remain unsupported. | Custom tool definitions are ordinary input material; modality usage is separate. | Image, inline file, audio input, or non-streaming audio output with non-streaming custom local tools is supported only when both the relevant modality capability and `chat_custom_tools=true` are set. | Keep streaming custom tools rejected. |
| Interaction with streaming custom local tools | Upstream stream-delta shape remains unclear in the installed SDK. | Installed SDK stream chunk tool deltas model function tools only. | Not applicable. | Not applicable. | Unsupported by SLAIF. | Not applicable. | Rejected. | Keep rejected. Do not use multimodal work to reopen streaming custom tools. |
| Interaction with `response_format` / structured outputs | OpenAI supports response formatting for Chat Completions, but model and modality combinations can differ. | SDK supports `response_format`. | No modality-specific role change. | Structured output support is model-specific. | Text streaming with structured output is supported today; streaming audio output remains unsupported. | Structured-output schemas are ordinary input material; modality usage is separate. | Image, inline file, audio input, or non-streaming audio output can compose with JSON mode/structured outputs only when the route enables both capabilities and the request passes caps. | Keep streaming audio output and file-ID/file-URL combinations separate. |
| Interaction with `logprobs` | Chat Completions supports text-token logprobs where model-compatible. | SDK supports `logprobs` and `top_logprobs`. | No modality-specific role change. | Model-specific. | Text streaming logprobs are represented. Audio/file/image-specific logprob meaning is not documented clearly enough for SLAIF. | Logprob data is response metadata, not a billing category. | Image, inline file, audio input, or non-streaming audio output can compose with logprobs only when the route enables both capabilities and the request passes caps. | Keep streaming audio output and file-ID/file-URL combinations separate. |

## Billing And Accounting Analysis

Multimodal Chat Completions should not be enabled as blind JSON passthrough.
Each modality adds admission-time and finalization surfaces beyond ordinary
text-only token accounting.

Likely billing/accounting surfaces:

- ordinary text input tokens;
- ordinary text output tokens;
- image input tokens or provider image-token-equivalent usage;
- audio input tokens or provider audio-token-equivalent usage;
- audio output tokens or provider audio-token-equivalent usage;
- file input tokens or provider file-processing usage;
- cached input tokens;
- reasoning tokens;
- provider-reported cost, especially for OpenRouter;
- provider-specific or ambiguous usage fields that SLAIF does not yet parse.

For finalization, SLAIF can precisely finalize only from provider-reported
usage/cost fields that are present, understood, non-negative, and covered by
tests. Current accounting parses prompt, completion, total, cached, reasoning,
audio-output token details, and provider-reported OpenRouter cost fields. It
does not infer modality cost from payload bytes. Non-streaming audio output uses
`pricing_metadata.audio_output_price_per_1m` for OpenAI-local audio-output token
costs when provider usage reports audio output tokens; OpenRouter
provider-reported cost remains authoritative where present.

For pre-call admission, SLAIF needs conservative estimation or explicit bounded
policy per modality. Image/audio/file payload bytes are not billable tokens.
Base64 size alone is useful for request-size caps, but it is not reliable final
cost. Image costs can depend on model family, dimensions, detail level, patch or
tile algorithms, and provider behavior. File costs can depend on extracted text,
page images, OCR, spreadsheet augmentation, or native file handling. Audio costs
can depend on audio tokenization, duration, format, model family, and whether
the request produces audio output.

If a provider returns modality-specific usage fields, SLAIF needs explicit
parsing and accounting tests before enabling that modality. If the provider does
not return sufficient usage/cost detail, enabling the modality for cost-limited
keys should fail closed or require an explicit estimated-confidence ledger
semantics that operators can review. This investigation does not recommend new
special SLAIF billing categories unless upstream pricing or usage requires them.
The first implementation should continue to prefer provider usage and
provider-reported cost where available.

Multiple choices do not change finalization: PR #157 already established that
provider-reported total usage/cost is finalization authority once, and SLAIF
does not multiply provider usage by `n`.

## Privacy And Security Analysis

Image, audio, and file payloads can contain personal data, classroom data,
workshop data, credentials, documents, screenshots, voices, faces, location
clues, or other sensitive material. SLAIF must not store or log raw payloads.

Required boundaries before enabling any modality:

- do not store or log base64 image/audio/file payloads;
- do not store or log raw external URLs, because URLs can contain signed query
  strings, bearer tokens, object IDs, personal data, or internal hostnames;
- do not store or log file IDs without an explicit safe-metadata policy, because
  IDs can reveal provider-side storage references or ownership assumptions;
- add request-size and per-part size caps before provider forwarding;
- add content-type, data-URL, file extension, and format validation where
  applicable;
- reject unknown content part subfields unless a provider-compatible
  pass-through area is explicitly designed and tested;
- keep provider-secret isolation unchanged: client `Authorization`, cookies,
  CSRF/session headers, provider keys, and gateway internals must never be
  forwarded or logged;
- treat provider URL fetching as provider-side network access. Forwarding an
  image or file URL is not hosted web search, but it still has privacy and
  egress implications because the provider, not SLAIF, may fetch the URL;
- keep MCP/connectors and hosted tools separate and denied unless a future
  policy explicitly enables them.

## Capability Metadata Plan

Future route/model capability flags should be explicit and separate. Endpoint
and model permission must not imply modality permission.

Recommended future flags, following current naming style:

- `chat_image_inputs`
- `chat_file_inputs`
- `chat_audio_inputs`
- `chat_audio_outputs`
- `chat_multimodal_inputs`
- `chat_streaming_audio_outputs`, only if a supported streaming audio shape is
  implemented and tested
- `chat_multimodal_with_n_choices`, only if combined admission estimates and
  provider behavior are tested
- `chat_multimodal_structured_outputs`, only if the combination is tested

Clarifications:

- model permission does not imply modality permission;
- modality permission does not imply hosted-tool permission;
- audio output permission does not imply audio input permission;
- file input permission does not imply hosted file search permission;
- image input permission does not imply image-generation tool permission;
- OpenRouter provider/model metadata may inform proposals, but runtime support
  still requires local route capabilities, pricing, accounting, and tests.

## Recommended Implementation Sequencing

Use small implementation PRs rather than one broad multimodal passthrough.

1. Image input to text output.
2. Inline file input to text output.
3. Audio input to text output.
4. Non-streaming text input to audio output.
5. Audio input plus audio output, after input and output audio are independently
   supported.
6. File ID or file URL support, only if ownership, lifecycle, privacy, and
   pricing policy are clear.
7. Streaming audio output, only if the SDK/API stream delta shape and final
   usage behavior are clear enough to test safely.
8. Mixed-modality combinations and interactions with `n > 1`, local function
   tools, non-streaming custom local tools, structured outputs, and logprobs.

Each implementation PR should include:

- explicit route/model capability flag;
- request-shape validation;
- content part count, payload byte, URL, file ID, and format caps;
- input estimation strategy and admission tests;
- provider usage parsing for relevant modality usage fields;
- pricing catalog support or explicit fail-closed behavior;
- accounting finalization tests;
- OpenAI and OpenRouter mocked provider tests when relevant;
- official OpenAI Python client mocked E2E tests;
- redaction and no-storage tests;
- docs updates.

## Proposed Minimal First Slice

The first implementation slice is image input to text output only and is now
implemented behind `chat_image_inputs=true`.

Reasons:

- OpenAI and OpenRouter both document `image_url` content parts for Chat
  Completions-style requests.
- The response can remain ordinary text Chat Completions output.
- Streaming text output can likely keep the existing SSE pass-through model.
- The main new hard parts are request caps, image validation, conservative image
  token estimation, model capability metadata, and usage/finalization tests.

Inline file input to text output is now implemented as the second narrow slice.
Audio input to text output is now implemented as the third narrow slice.
Non-streaming audio output is now implemented as the fourth narrow slice with
explicit route capability, pricing metadata, provider usage/cost finalization,
and no generated-audio or transcript storage. Uploaded file IDs, file URLs,
streaming audio output, and `n > 1` with audio output remain disabled because
ownership, lifecycle, privacy, stream-shape, and pricing policy are still
separate concerns.

## Decision

Keep Chat Completions file IDs, file URLs, streaming audio output, `n > 1` with
audio output, image generation, and broader media-output support disabled on
current `main`. Image input, inline file input, audio input to text output, and
non-streaming audio output are enabled only through explicit route capabilities,
conservative caps, provider usage/cost finalization, provider adapter tests,
official-client E2E coverage, and redaction/no-storage tests.
