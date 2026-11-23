# OpenCode 1.19.3 native Chat profile — `opencode-1.19.3-chat-v1` (preprotected candidate)

Objective 227-a, secondary-owned OpenCode Chat binding. This dossier
records the native-client loopback evidence from that preprotected
candidate stage. That loopback evidence is NOT a live-qualification,
Gateway/PostgreSQL settlement, or production claim. The protected gate was
`not_run` through 227-b; a bounded, human-authorized live LAN
qualification was executed in 227-c and is recorded in the
[consolidated verification record](../verification/2026-11-20-hermes-opencode-chat.md)
(not in this dossier). The loopback evidence recorded here remains not a
production claim.

## 1. Pinned client identity

| Fact | Value |
| --- | --- |
| Client | OpenCode 1.19.3 (`anomalyco/opencode`) |
| Release tag / direct commit | `v1.19.3` / `e3c4eb242585dcd77be1a867391b7c25fd47ce52` (tag type: commit, via `gh api repos/anomalyco/opencode/git/ref/tags/v1.19.3`) |
| Distribution | glibc single-file executable, `opencode-linux-x64-baseline` |
| Archive SHA-256 | `531cff2441129c30f0edd5878af494108ad07f5feb46d7ee29a2a5b830a5765d` |
| Executable SHA-256 (pinned, verified by root) | `179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9` |
| Chat provider package | `@ai-sdk/openai-compatible` 2.0.41 (ai 6.0.168) |
| Observed runtime / UA | bun 1.3.14 / `opencode/1.19.3 ai-sdk/provider-utils/4.0.23 runtime/bun/1.3.14` |
| Wire API | `chat_completions` (always streams in `run` mode; nonstreaming Chat not observed) |

## 2. Packaged profile DATA

- File: `app/slaif_gateway/modules/clients/profiles/opencode-1.19.3-chat.json`
  (shared loader document law, `schema_version 1`).
- Canonical DATA digest (`fixture_sha256`):
  `2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14`
- Module: `app/slaif_gateway/modules/clients/opencode_1193_chat.py` — thin
  binding (`load -> build -> register`) with source literal
  `opencode-1.19.3-chat-v1`; no dialect logic outside the shared engine.
- Dialect facts: all five generic Chat `reasoning_effort` values including
  `xhigh` (proven difference vs the default validator); assistant extra
  fields `reasoning`/`reasoning_content` (64 KiB each); tool-call ID envelope
  1..128 bytes with JSON-string arguments (64 KiB).
- Vocabulary: the 9-tool **denied-web-baseline** reviewed capture
  (`bash, edit, glob, grep, read, skill, task, todowrite, write`).
  `webfetch` was observed only under a permissive task configuration
  (10 declarations); it is configuration-dependent and deliberately
  **outside v1** until a reviewed DATA revision with a new digest. Tool
  names are client-local function declarations and grant no hosted,
  routing, or execution authority.
- Bounds envelope the pinned capture observations (observed maxima:
  declaration 5,309 B, description 4,662 B, schema depth 6, properties 5,
  tool-call IDs 30/34 B, arguments 33 B).

## 3. Capture and verification method

- Pinned executable against the task-owned `127.0.0.1` loopback fake
  (`scripts/verify_agent_chat/`), isolated task-owned HOME/XDG, task-owned
  config with a synthetic bearer, `--pure` (external integrations disabled),
  bounded 240 s timeouts. No provider, no user profile, no real key, no
  network beyond loopback.
- Structural capture facts (sanitized): `tests/fixtures/opencode/1.19.3/chat/`
  (structural digest `c84570f8dbbefb727ec90b17df2de802257951bda65e78b352df4742392208d3`
  over the seven `structural_*.json` files); public provenance in
  `provenance.json`. Raw content, raw IDs, and credentials are not retained.
- Verifier: `scripts/verify_agent_chat/verify_opencode_chat_capture.py`
  (pinned binary identity enforced; bounded fake readiness; per-probe facts
  captured before journal deletion; safe honest failure reporting;
  cross-request session-stability predicates with 8-hex hashes only;
  owned-process termination; default private artifact cleanup verified
  before the report is written; report paths inside the run root rejected).
- Regression run (fixed verifier, 2026-11-20T03:56:22Z, run root cleaned and
  verified): `all_pass=true` — text probe exact sentinel; toolloop probe with
  exact 46-byte unpredictable file marker round-tripped through the
  correlated native `read` tool result (`correlated_tool_result`,
  `unverified_calls=[]`); 9 declarations and `xhigh` on both main requests;
  session hint stable across the two same-session requests and distinct
  across fresh runs.

## 4. Evidence boundary (what this is and is not)

- **Is**: actual native OpenCode 1.19.3 client behavior against a bounded
  fake peer — native tool-loop execution, call/result correlation, envelope
  shape, session-hint behavior, reasoning-delta acceptance.
- **Is not**: Gateway admission, key policy/quota reservation/finalization,
  or PostgreSQL settlement. The loopback fake is a synthetic peer; no
  gateway request was processed and no ledger row exists. Fake-SDK usage
  must never be cited as settlement evidence.
- **Protected gate**: `not_run` through 227-b. The bounded,
  human-authorized live LAN qualification was executed in 227-c: run 1
  (20.3 s) is preserved as a framing failure (final 32 B vs 33 B marker,
  sha8 `9f4bbeb2`, trailing-newline mismatch, not a pass); run 2 (20.358 s)
  passed with strict raw-byte equality (final 32 B == 32 B marker, no
  normalization), native `read` tool completed with callID and output,
  2 steps, 0 error events, exit 0. All 4 OpenCode requests finalized 200
  FINALIZED, 29,546 tokens, EUR 0.029546, zero reservations/fences
  (see the [consolidated verification
  record](../verification/2026-11-20-hermes-opencode-chat.md)).

## 5. Known limits and follow-ups

- **Native client configuration (227-c live)**: the run used a custom
  provider entry with explicit `@ai-sdk/openai-compatible` pointed at the
  task gateway — NOT the built-in OpenAI or Responses path. Main effort
  xhigh and the captured tool profile were unchanged.
- Nonstreaming Chat was never emitted by the client in `run` mode; the
  profile does not claim a nonstream capture.
- Responses-surface facts (flat declarations, ID-less replay) are objective
  228 scope and are not claimed here.
- The dossier's verifier evidence is pre-integration; primary owns the
  combined qualification and the consolidated verification record.
