# Image estimates and native video verification — 2026-10-20

The human requested a reasonable correction for base64 images being counted as
text tokens, then explicitly requested direct video-file input as well. Existing
credentials, key policies and throttling must stay unchanged.

A fork of the saved /tmp Lena conversation reproduced
responses_codex_context_window_exceeded on exact Codex 0.163.0 targeting Qwen A100.
The original session file hash stayed unchanged. Its 474,454-byte PNG appears as
a 632,630-character data URL. The existing byte/3 estimate accounts for about
210,900 input tokens for that media alone. A manual authenticated native
/tokenize probe, without inference, returned 314 tokens for the Lena image
prompt. A generated 1,670-byte MP4 with four requested frames returned 84 tokens.
No raw history, media, credentials, argument strings or raw IDs are copied into
this report. Request capture stays off.

The correction uses explicit bounded model-route media budgets for admission,
TPM and quota/cost reservation, preserving provider usage/cost finalization.
It defers only encoded-media token material until route selection, then checks
the complete estimate before side effects. URL, byte/count, replay, route and
key gates remain independent. Waiting revalidates current budgets. Default
unconfigured image routes retain their previous estimate. Native Chat video
requires explicit route permission, budget and a forwarded operator frame cap.
It is not direct video input in Codex Responses, whose deployed backend has no
video input type. No video-generation or arbitrary-provider claim follows.

Focused estimation, request policy and route-capability coverage passed 542
tests. Full regression, PostgreSQL, deployment and live receipts will be
appended after execution. This is not full browser/HPC/release qualification.

Documentation impact: media estimation and direct-video policy are documented
in docs/media-input-estimation.md; Responses and forwarding/compatibility
contracts link that bounded policy. Runtime policy data ships as a separate
JSON resource and is not embedded in code or key metadata.
