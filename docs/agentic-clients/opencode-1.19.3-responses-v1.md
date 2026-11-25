# OpenCode 1.19.3 native Responses capture — `opencode-1.19.3-responses-v1` (preprotected candidate)

Objective 228-a, secondary-owned OpenCode Responses binding. This dossier
records the native-client loopback capture from that preprotected candidate
stage. That loopback evidence is NOT a live qualification, Gateway/
PostgreSQL settlement, or production claim. The protected gate is `not_run`,
the packaged profile DATA was subsequently packaged by primary
(section 2); the protected gate remains `not_run`, and the current
objective status is recorded in the consolidated verification record
(228-b: `NEEDS_CONTINUATION`; 228-c completed the mock half — six
pinned-binary loopback cases through the task-owned Gateway and real
PostgreSQL — while the protected LAN half and gate remain `not_run`).

## 1. Pinned client identity

| Fact | Value |
| --- | --- |
| Client | OpenCode 1.19.3 (`anomalyco/opencode`) |
| Release tag / direct commit | `v1.19.3` / `e3c4eb242585dcd77be1a867391b7c25fd47ce52` (tag type: commit, via `gh api repos/anomalyco/opencode/git/ref/tags/v1.19.3`; same pinned commit as the Chat capture) |
| Distribution | glibc single-file executable, `opencode-linux-x64-baseline` |
| Archive SHA-256 | `531cff2441129c30f0edd5878af494108ad07f5feb46d7ee29a2a5b830a5765d` |
| Executable SHA-256 (pinned) | `179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9` |
| Responses provider package | `@ai-sdk/openai` bundled in the pinned executable (package entry 3.0.88, nested copy 3.0.84; no runtime npm install observed) |
| ai SDK version | 6.0.168 |
| Observed runtime / UA | bun 1.3.14 / `opencode/1.19.3 ai-sdk/provider-utils/4.0.40 runtime/bun/1.3.14` (the executable bundles multiple provider-utils copies; the UA reflects the copy that handled the request — the Chat capture observed 4.0.23) |
| Wire API | `responses` (`/v1/responses`, always streaming in `run` mode; nonstreaming never observed) |

## 2. Packaged profile DATA

- **Status: packaged.** A `schema_version 1` profile JSON exists at
  `app/slaif_gateway/modules/clients/profiles/opencode-1.19.3-responses.json`
  (fixture digest — canonical JSON digest —
  `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff`),
  and the client module `opencode-1.19.3-responses-v1` (engine version
  `1`) is implemented and selected via the authenticated key-metadata
  pin; this dossier, the sanitized fixtures, and the verifier fed that
  packaging.
- Wire facts proven by this capture (recorded as the packaged frozen
  dialect; this dossier remains the capture provenance, not the
  module's behavior spec): 9 top-level request fields
  (`include, input, max_output_tokens, model, reasoning, store, stream,
  tool_choice, tools`); nested `reasoning: {effort: "xhigh"}` (not a
  top-level `reasoning_effort` string); `max_output_tokens` 32000 emitted
  from a configured 32768 limit; `store: false`; `stream: true`;
  `tool_choice: "auto"`; `include: ["reasoning.encrypted_content"]`;
  flat tool declarations with the `strict` key present on all 9
  (presence only — the capture verifier never recorded the value; the
  current pinned-native wire value `false` is separately established by
  the 228-c direct-fake diagnostic; see the fixture provenance note);
  proven difference vs the Chat wire's nested declarations without
  `strict`; typeless input
  message items (`role` + `content`, no `type`/`id`/`status`); ID-less
  continuation replay of `reasoning`, `function_call`, and
  `function_call_output` items (verbatim `encrypted_content` replay, no
  `id`/`status` keys).
- Vocabulary: the 9-tool **denied-web-baseline** reviewed capture
  (`bash, edit, glob, grep, read, skill, task, todowrite, write`).
  `webfetch` is configuration-dependent and deliberately **outside v1**
  until a reviewed DATA revision with a new digest. Tool names are
  client-local function declarations and grant no hosted, routing, or
  execution authority.

## 3. Capture and verification method

- Pinned executable against the task-owned `127.0.0.1` loopback Responses
  fake (`scripts/verify_agent_chat/loopback_responses_fake.py`), isolated
  task-owned HOME/XDG, task-owned config with a synthetic bearer bound to a
  custom provider entry with explicit `npm=@ai-sdk/openai` (the built-in
  `openai` provider entry must not be used; it selects a different default
  path), `--pure` (external integrations disabled), bounded 240 s timeouts.
  No provider, no user profile, no real key, no network beyond loopback.
- Structural capture facts (sanitized):
  `tests/fixtures/opencode/1.19.3/responses/` (structural digest
  `00127fa1b5ea43ac0a936ddf5d179d084eaf70512dc9d59a6e6f2a11253cbd53`
  over the eight `structural_*.json` files); public provenance in
  `provenance.json`. Raw content, raw IDs, and credentials are not
  retained; session values appear only as sha256-8.
- Verifier:
  `scripts/verify_agent_chat/verify_opencode_responses_capture.py`
  (pinned binary identity enforced; bounded fake readiness; per-probe
  structural facts captured before journal deletion; cross-request
  session-stability predicates with 8-hex hashes only; owned-process
  termination; default private artifact cleanup verified before the report
  is written).
- Corrected final run (2026-11-23T12:04:07Z, run root cleaned and
  verified; the earlier 11:25:50Z run remains as the provisional
  pre-correction receipt at
  `/home/janezp/codex-work/slaif-228-task/report-final.json`, fake-only and
  NOT a Gateway/provider pass): `all_pass=true`, three probes, ~18.5 s
  wall total, per probe:
  - text: exit 0, 5.978 s, 1 request, exact final text;
  - toolloop: exit 0, 5.53 s, 2 requests (session sha8 `2ee98e47` stable),
    native `read` tool call correlated 1/1, final 38 B exactly equal to the
    38 B unpredictable marker (`correlated_tool_result`); the wrapped read
    output (192 B) is not raw file bytes and not byte-equal to the marker;
  - reasoning replay: exit 0, 5.578 s, 2 requests (session sha8
    `760705ef` stable), continuation input 5 items
    (`[null, null, reasoning, function_call, function_call_output]`),
    reasoning item keys `[encrypted_content, summary, type]` with no
    `id`/`status`, 64-byte synthetic encrypted content replayed with
    full-byte equality to the issued value (sha8 `f2719d31`) plus exact
    issued call_id/tool_name call/output linkage. The verifier now GATES
    the reasoning sentinel on that full-byte equality AND exact
    call/output linkage; presence or a short hash alone never passes, and
    SDK tolerance is not correct producer proof.
- Wire-correctness fixes in the loopback fake for the corrected run:
  `response.created` status `in_progress` (valid), text deltas carry
  `content_index` 0, and the reasoning-probe function call occupies output
  slot 1 (reasoning item slot 0).
- Sanitized receipt of the corrected run:
  `/home/janezp/codex-work/slaif-228-task/report-fix1.json`, produced by
  `.venv/bin/python scripts/verify_agent_chat/verify_opencode_responses_capture.py
  --run-root /home/janezp/codex-work/slaif-228-task/run-fix1
  --report /home/janezp/codex-work/slaif-228-task/report-fix1.json` against
  the correction commit on `oap/228-opencode-responses-qual` (parent
  `3c61d6c3`; source SHA in the handoff notice). Cleanup predicates
  `artifacts.run_root_cleaned=true`, `artifacts.cleanup_verified=true`,
  `fake_process_terminated=true` are in the report.
- Extended recapture (fix2, 2026-11-24, eight probes): sanitized receipt
  `/home/janezp/codex-work/slaif-228-task/report-fix2.json` — `all_pass=true`,
  `EXIT=0`, finished `2026-11-24T01:07:42Z`, cleanup verified, all privacy
  flags false, sessions distinct. Executed-artifact provenance (recorded in
  `provenance.json`): verifier sha256
  `9b531cb02a3bef99d9ee32abb4442897058e43efaf7676680272deb23e79df14`,
  loopback fake sha256
  `3dc2120712a24780e3918a3e39be00c45c1c42981bfefcd643a6b75b524f2527`,
  executed against worktree HEAD `569f2f11afdaa7aacd8556c29ee7e3b28505feea`
  at run time (NOT the post-run commit that updates these fixtures).
  Per probe (all exit 0, denied-web 9-tool / xhigh / 32000 baseline):
  - text: 5.828 s, 1 request (session sha8 `b728f8db`), exact final text;
  - toolloop: 5.578 s, 2 requests (session sha8 `9c20a369` stable),
    correlated `read` tool result, final 38 B == marker 38 B exact;
  - reasoning replay: 5.581 s, 2 requests (session sha8 `080846e0`
    stable), full-byte cipher equality (sha8 `d1c28cd0`) + exact issued
    call/output linkage, gate passed;
  - assistant text + tool continuation (NEW): 5.728 s, 2 requests (session
    sha8 `01d4076c`), turn-1 output slots assistant text 0 / function_call 1
    (created status valid); the SDK KEPT the turn-1 assistant lead text in
    the turn-2 continuation input as a typeless assistant message
    (`{role: assistant, content: [{type: output_text, ...}]}`); final text
    from the correlated tool result, exact marker equality;
  - default auto-title auxiliary (NEW, run WITHOUT `--title` suppression):
    5.678 s, 2 requests (session sha8 `221d1bea` stable across both),
    request order `[0 tools, 9 tools]` — the auto-title auxiliary request
    goes FIRST with 7 top-level fields (no `tools`, no `tool_choice`;
    `model`/`stream`/`store`/`max_output_tokens`/`include`/`reasoning`/
    `input` all present, input a 3-item list); the main request is second;
  - visible reasoning states (NEW, observation-only, three probes): the
    fake issues the reasoning item's `encrypted_content` as absent / null /
    empty string. The SDK DROPPED absent and null (turn-2 input 4 items,
    no reasoning item, replayed state `null`, `matches_issued` false) and
    KEPT the empty string verbatim (turn-2 input 5 items, item keys
    `[encrypted_content, summary, type]`, no `id`/`status`, replayed
    `empty_string`, `matches_issued` true; `e3b0c442`/0 bytes recorded as
    values DERIVED from the empty-string state). All three still reach the
    exact 38 B marker final text with correlated tool results. These are
    NOT encrypted-ownership passes: the full-cipher gate remains required
    on the encrypted case, and visible states grant no opaque authority.
  - compaction trace: `post_paths_other_than_responses_seen = []`, no
    `/v1/responses/compact` endpoint observed — an EMPTY trace, i.e. no
    compaction-form pass is claimed for this client.
- 228-b client-side compaction capture (2026-11-24, nine-probe superset
  run re-executing all eight fix2 probes plus the new compaction
  probe): sanitized receipt
  `/home/janezp/codex-work/slaif-228-task/runs/228b-compaction-20261124T095812Z-report.json`
  — `all_pass=true`, `EXIT=0`, finished `2026-11-24T09:59:04Z`, 9/9
  gates pass, run root cleaned and verified, all privacy flags false,
  sessions distinct across probes. Executed-artifact provenance
  (recorded in `provenance.json`): verifier sha256
  `21058f39d10e43fac0d3dea18c4d9042b28693616132cd6222a0aab9382f615f`,
  loopback fake sha256
  `f68cc805b14f33f66bab814ff3edced99a7e6e595ad243ecc7fc6552eac7eeba`,
  executed against worktree HEAD `f3af15335907fc5fe8c2f02705e7df4ad91d424a`
  with the compaction fake/verifier edits as UNCOMMITTED working-tree
  changes at run time — executed-script provenance, NOT the post-run
  commit that adds the fixture. The trigger is synthetic: the fake
  emits overflow usage (225000 in / 2000 out) crossing the
  pinned-source usable threshold (245760 − 20000 = 225760) after an
  intentionally unanswered turn-1 `read` tool call. Observed (fake-only,
  NOT a Gateway/provider pass):
  - R1 (main): baseline 9-field / 9-tool contract; the fake issues the
    `read` function call (filePath `probe.txt`), which is never
    executed → zero `function_call_output`; synthetic usage
    `[225000, 2000]`;
  - R2 (summary request, NEW observed shape): 7 top-level fields
    (`include`, `input`, `max_output_tokens`, `model`, `reasoning`,
    `store`, `stream`); the `tools` key is ABSENT (the pinned source
    suggested an empty list) and `system`/`tool_choice` are absent;
    `max_output_tokens` is 32000 (the source constant is 4096 — the
    observed wire value supersedes it); 2 typeless input items
    `[developer, user]` with the pinned-source buildPrompt marker in
    the user item (`packages/core/src/session/compaction.ts:161`);
  - R3 (continuation, NEW observed shape): 9 fields, tools restored
    (9, flat, all strict), `tool_choice` `auto`; 4 typeless input items
    `[developer, user, assistant, user]` — index 1 the pinned-source
    compaction user text (`packages/opencode/src/session/message-v2.ts:241`,
    22 B), index 2 the BYTE-EXACT fake-issued safe synthetic summary
    (assistant item, `output_text` part), index 3 the pinned-source
    continuation instruction
    (`packages/opencode/src/session/compaction.ts:531`); both order
    predicates hold; `fc_outputs_total` 0. HONEST DEVIATION from the
    earlier "full chronological list" prediction: the original prompt
    user item and the aborted turn-1 assistant output were FULLY
    REPLACED (`first_user_text_equals_original_prompt` false), so the
    gate is presence-and-order based, not position-based;
  - final client text: exact 24-byte static sentinel, exit 0, 5.528 s,
    session stable across all 3 requests (sha8 `6145d992`);
  - compaction trace for this run: `post_paths_other_than_responses_seen
    = []`, `responses_compact_endpoint_observed` false — compaction ran
    entirely client-side against `POST /v1/responses`; no
    compact-endpoint participation is claimed.
- Prior receipts remain as-is: `report-final.json` (provisional
  pre-correction), `report-fix1.json` (accepted corrected run), and
  `report-fix2.json` (eight-probe accepted run).
- SSE consumption: the client consumed the native `@ai-sdk/openai` 3.x
  event vocabulary without error (envelope keys `type`,
  `sequence_number`, plus per-event fields; reasoning summary part/delta
  events; `response.completed` with
  `usage.input_tokens/output_tokens/total_tokens`). Standards-shape proof:
  the SSE event envelope carries NO top-level `response_id`; the response
  `id` appears only inside the `response.created` and `response.completed`
  `response` objects, and the client consumed that standards-shaped stream
  cleanly with no Gateway validator relaxation.

## 4. Evidence boundary (what this is and is not)

- **Is**: actual native OpenCode 1.19.3 client behavior against a bounded
  fake peer on the Responses wire — streaming SSE consumption, native
  tool-loop execution with call/result correlation, gated encrypted-reasoning
  continuation replay (full-byte equality + exact call/output linkage),
  gated native client-side compaction (synthetic overflow trigger on the
  loopback fake; observed summary/continuation request shapes), envelope
  shape, session-hint behavior.
- **Is not**: Gateway admission, key policy/quota reservation/finalization,
  or PostgreSQL settlement. The loopback fake is a synthetic peer; no
  gateway request was processed and no ledger row exists. Fake-SDK usage
  must never be cited as settlement evidence.
- **Observation-only probes**: the assistant-text-continuation and
  visible-reasoning-state probes document SDK keep/drop behavior only; they
  are not ownership, settlement, or provider guarantees.
- **Compaction probe boundary**: the 228-b compaction positive is a
  fake-only client-behavior observation driven by a synthetic usage
  trigger; it proves neither Gateway/provider compaction support nor any
  `/v1/responses/compact` (or other endpoint) participation, and the
  issued summary is a safe synthetic template (no content retained).
- **Protected gate**: `not_run`. No live LAN or provider run occurred for
  the Responses wire in 228-a (preprotected candidate stage only). The
  consolidated verification record carries the current objective status
  (228-b: `NEEDS_CONTINUATION`; 228-c: the mock half is complete — six
  pinned-binary loopback cases passed through the task-owned Gateway,
  real PostgreSQL, and a separate loopback mock upstream — while the
  bounded LAN half and this protected gate remain `not_run`, awaiting
  the root CI/setup review of the frozen candidate).

## 5. Known limits and follow-ups

- The captured `encrypted_content` is synthetic (64 B base64, fake-issued);
  no format, length, or codec claim about real provider encrypted reasoning
  is made.
- Nonstreaming Responses was never emitted by the client in `run` mode;
  this capture claims streaming only.
- Session-hint headers (`x-opencode-session-id`, `x-session-affinity`,
  `x-session-id`; three equal values per request) are client-generated
  hints: stability/distinctness predicates only, rejected as authority.
- Compaction capture limits: client-side only on the Responses wire. The
  summary request deviates from the pinned source in two recorded ways
  (`tools` key absent rather than an empty list; `max_output_tokens`
  32000 rather than the 4096 source constant), and the continuation
  fully replaces the pre-compaction history rather than appending to it.
  No real-provider overflow, no encrypted-summary ownership, and no
  compact-endpoint behavior is claimed.
- Retry posture: the strict zero-retry rule is a separate concern from
  stock native retries. The 227-c bounded LAN Chat qualification is
  executed historical evidence whose human-approved 100-LAN-launch
  stock-retry exception applied to that execution only; the standing,
  separately approved bounded 228 LAN plan for this module explicitly
  allows stock native retries as a plan term (not a new exception or
  human gate). The native OpenCode client retry constant was pinned at 5
  in source inspection, and a zero-native-retry configuration is
  unproven/unsupported in stock. Any live Responses execution under the
  228 plan must reference the 227-c totals
  (5 launches / 41,021 tokens / EUR 0.041021) without resetting them.
- Primary owns the packaged profile DATA, the module binding, the combined
  qualification, and the consolidated verification record; this dossier's
  evidence is pre-integration.
