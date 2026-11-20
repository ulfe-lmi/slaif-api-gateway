# Hermes 0.22.5 native Chat profile — `hermes-0.22.5-chat-v1` (preprotected candidate)

Objective 227-a, secondary-owned Hermes Chat binding. **Preprotected
candidate stage**: this dossier records native-client loopback evidence
only. It is NOT a live-qualification, Gateway/PostgreSQL settlement, or
production claim. The protected gate remains `not_run` until root
authorizes protected evidence.

## 1. Pinned client identity

| Fact | Value |
| --- | --- |
| Client | Hermes Agent 0.22.5 (NousResearch `hermes-agent`) |
| Release tag / direct source commit | `v0.22.5` / `bf0203a794a07aac3ff764972ab9087baa4e4f4e` (40-hex Git commit of the pinned source archive) |
| Observed runtime | native Python 3.14.9 (task-pinned toolchain, read-only) |
| SDK (closure venv) | openai-python 2.24.0, httpx 0.28.1 (install key `c8b61f7f26d2fd60`) |
| Invocation | native gateway-backed CLI via normal `hermes_bootstrap` (task-private launcher; no source patch, no dispatcher substitute) |
| Wire API | `chat_completions` (OpenAI-compatible; main run mode streaming — the auxiliary `session_title` request was a nonstreaming `response_format` JSON-schema call with `none` effort) |

## 2. Packaged profile DATA

- File: `app/slaif_gateway/modules/clients/profiles/hermes-0.22.5-chat.json`
  (shared loader document law, `schema_version 1`, document version 2).
- Canonical DATA digest (`fixture_sha256`):
  `c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327`
- Revision history: DATA revision 1 was a provisional pin; revision 2
  ("admits auxiliary none effort"; primary integration
  `47aeab13522685bbe5967498a21563075e56fd67`) is current in
  `app/slaif_gateway/modules/clients/profiles/hermes-0.22.5-chat.json`.
  Data-only vocabulary upgrades are new document bytes with a new digest
  and a re-pinned operator key; the initial DATA1 provisional pin requires
  an explicit audited rebind. There is no key rotation or auto-upgrade
  path.
- Module: `app/slaif_gateway/modules/clients/hermes_0225_chat.py` — thin
  binding (`load -> build -> register`) with source literal
  `hermes-0.22.5-chat-v1`; module version derived from the validated DATA;
  no dialect logic outside the shared engine.
- Dialect facts: `reasoning_efforts` minimal/low/medium/high/xhigh/none
  (observed: `xhigh` main requests, `none` auxiliary title request);
  assistant extra fields `reasoning`/`reasoning_content` (64 KiB each);
  tool-call ID envelope 1..128 bytes with JSON-string arguments (64 KiB).
- Vocabulary: the finite 10-name declared set (`patch`, `process_manage`,
  `read_file`, `search_files`, `terminal`, `todo_list`, `tool_call`,
  `tool_describe`, `tool_search`, `write_file`) — the bounded union of the
  baseline `cli: [terminal, file, todo]` toolsets (8 declarations on the
  initial baseline request) plus the client-local discovery bridge.
  Bounds: 32 declarations, 4,096 B description, schema depth 8, 64
  properties, 64 KiB declaration. Tool names are client-local function
  declarations and grant no hosted, routing, or execution authority.
- Observed native configuration (task-private QA profile): streaming,
  title upgrade enabled, compression on the main thread, fallback `[]`,
  no plugins/MCP/skills/user memory/profile/curator/background review.

## 3. Capture and verification method

- Pinned native CLI against the task-owned `127.0.0.1` loopback fake
  (`scripts/verify_agent_chat/loopback_chat_fake.py`) with private
  HOME/XDG, a synthetic bearer, and a finite outer watchdog. Fresh
  per-run private `HERMES_HOME` (seeded only from prepared config +
  public dependency installs) applies to the new reusable entry
  (`entry-final-positive`, `setupfail1`); the historical accepted cases
  (`loop7`, `timeout4`, `error3`, `multi1`) ran in isolated task homes
  with reused prepared state. No provider, no user profile, no real key,
  no network beyond loopback.
- Verifier: `scripts/verify_agent_chat/verify_hermes_chat_capture.py` —
  structured terminal-result gate (`{"type":"result","exit_code":0,...}`
  with exact expected text; echoed prompts or tool results alone do not
  qualify), correlated call/result tool-loop gate, journal-based
  reasoning-replay gate, current-run effective provider timeout gate,
  core-cleanup-first retention, and default whole-run-root raw cleanup
  verified before the report is written. Safe receipts carry lengths,
  short hashes, and booleans only — never raw markers or reasoning.
- Regression: 16 pure helper unit tests
  (`tests/unit/test_verify_hermes_chat_capture.py`; no clients, providers,
  subprocesses, or DB) — 16 passed (secondary 0.38 s; root independent
  run 0.30 s, exit 0); scoped lint clean.
- Accepted native loopback cases (preprotected; reused, not rerun):
  - `loop7` — compression/title/summary: 7 Chat POSTs; title request 1,
    summary request 5, summary preserved in the native main continuation
    6 (zero-based request indices); the exact unpredictable file-read
    result at 6 is absent from user prompts. Root traced all 7 native
    bodies through the current module, profile-aware Core, and safe
    upstream unchanged.
  - `timeout4` — finite native stall: 11 Chat POSTs, stable peer,
    current-run effective-timeout gate PASS (controlled QA variant: 3 s
    provider timeout). Outcome is OUTER-WATCHDOG CANCELLATION (CLI −15 at
    the 120 s watchdog) with current native timeout events; the CLI did
    not self-exit and the label is preserved.
  - `error3` — HTTP-500 observation: 11 POSTs; 68 error-code/unique-marker
    lines across two current-run logs (lines, not requests); outer-watchdog
    cancellation. No clean native error-exit claim.
  - `multi1` — two `read_file` calls/results plus reasoning replay: CLI
    exit 0 (~12 s), 3 POSTs, exactly two marker-correlated call/result
    pairs, both `reasoning` and `reasoning_content` replayed in later
    requests, markers absent from the first request; each reasoning field
    adds 9 estimate tokens for these synthetic marker strings (a property
    of the probe markers, not a general token-count fact).
  - `entry-final-positive` — the new reusable entry: 3 POSTs, 2 correlated
    calls, terminal exact with CLI 0, requested reasoning replayed,
    qualified with verified cleanup and a safe hash-only receipt.
- Setup-failure path (`setupfail1`): a seed failure yields an honest
  non-qualified safe receipt with no client/provider started; retained
  roots carry an explicit `core_cleanup_unverified` reason.

## 4. Evidence boundary (what this is and is not)

- **Is**: actual native Hermes 0.22.5 client behavior against a bounded
  fake peer — streaming Chat, native title/summary compression and
  continuation, tool-loop call/result correlation,
  reasoning/reasoning-content replay acceptance, and bounded
  stall/HTTP-error behavior under the finite outer watchdog.
- **Is not**: Gateway admission, key policy/quota reservation/
  finalization, or PostgreSQL settlement. The loopback fake is a synthetic
  peer; no gateway request was processed and no ledger row exists.
  Fake-SDK usage must never be cited as settlement evidence.
- **Not claimed**: MCP/plugin/skills, image input, any other client
  version, or signed/upstream-certified Gateway Chat support. This is a
  generic OpenAI-compatible candidate pair (pinned Hermes client +
  generic SLAIF Chat) only.
- **Production mapping**: the production model must match the gateway
  allowlist. The private `slaif227fake` model alias, the 3-second provider
  timeout, and the fake context/usage settings are controlled
  negative/compression QA variants and are never production templates.
- **Protected gate**: `not_run`. Live qualification (if ever authorized)
  requires the concrete protected plan defined by the order (see the
  [real-provider qualification boundary](../real-provider-qualification.md));
  nothing in this dossier grants it.

## 5. Known limits and follow-ups

- The pinned client's main run mode is streaming. Nonstreaming capture is
  recorded only for the auxiliary `session_title` request (a
  `response_format` JSON-schema call with `none` effort); broader
  nonstreaming chat output behavior is not claimed.
- The native CLI does not self-exit on provider stall or HTTP error;
  bounded outer-watchdog cancellation is the owned cleanup mechanism, and
  outer-watchdog outcomes are always distinguished from native SDK
  timeouts.
- Whole Hermes/profile/DATA qualification is NOT claimed; only the
  accepted slice above is recorded. Compression sub-aspects beyond the
  accepted `loop7` slice remain unverified.
- Older exploratory run roots remain task-private retained history; the
  dossier does not claim all raw roots were removed.
- The dossier's verifier evidence is pre-integration; primary owns the
  combined qualification, the
  [consolidated verification record](../verification/README.md) — its
  intended combined Hermes/OpenCode record is
  [2026-11-20-hermes-opencode-chat](../verification/2026-11-20-hermes-opencode-chat.md),
  created by primary — and the
  [operator/key-configuration guide](../first-time-operator-guide.md).
  This dossier links rather than duplicates their CLI procedures.
