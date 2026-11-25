# 228-a/228-b OpenCode 1.19.3 Responses Module — Preprotected Verification Record

Record finalized 2026-11-24, refreshed 2026-11-25 (228-c final
candidate `b6e85b79` evidence, LAN1 failure + wire repair, run 2
terminal FAIL at a later stream event; the 228-a/228-b content is
preserved as labeled history).
This filename is dated 2026-11-23 to match the crosslinks already
committed in `docs/responses-compatibility.md`.
All evidence was produced at the tested implementation heads named
below (labeled per head; the later code commits are re-covered by the
467-test focused regression, the 20-test PG run, and the 10-pass
governance run at the final 228-b code head).

## Status

- Objective status: `NEEDS_CONTINUATION` (honest incomplete). The 228-b
  completion order's item 6 — the pinned ACTUAL OpenCode 1.19.3 binary
  through the task-owned Gateway + real PostgreSQL + separate loopback
  mock upstream (no `get_provider_adapter` monkeypatch) — loopback mock
  half COMPLETE: six pinned OpenCode 1.19.3 cases passed through the
  task-owned Gateway + real PostgreSQL + separate loopback mock (no
  `get_provider_adapter` monkeypatch); root-verified PG reconciliation:
  21 finalized ledger rows / 21 finalized reservations, 227,998 tokens,
  0 pending/reserved; receipts/journals preserved (see 228-c
  checkpoint). The protected LAN launch half of item 6 is partially
  executed: the root-dispatched LAN1 native tool-loop run failed at
  the task Gateway validator (demonstrated missing `output_index`
  transport defect; zero settled usage); the bounded wire repair
  landed at final candidate head `b6e85b79` with all CI green; the
  root-dispatched LAN retry (run 2, `runs/228c-native-lan-2`)
  TERMINAL FAILED at 130.544 s: the repaired first missing-index
  gap was passed, but five main attempts then failed at a LATER
  stream event with the same `responses_stream_event_not_supported`
  code (charged as estimates); one auto-title aux settled (612 in
  / 46 out); all 6/6 key settled-request slots consumed. No key
  replacement, reset, or cap change. A bounded settled-request
  extension (6 -> 12, same key, within the unchanged remaining
  token/cost/time budgets) was requested asynchronously from the
  human maintainer; no traffic or quota mutation until that
  explicit reply. The 228-a candidate
  label `PREPROTECTED_READY` (candidate reviewable) is superseded by
  this b-refresh; it never meant "qualified".
- Protected live-qualification gate: final qualification `not_run`
  (LAN1 + one HTTP diagnostic probe executed, both failed at the task
  Gateway validator with zero settled usage; repair verified in CI;
  run 2 executed and TERMINAL FAILED at a later stream event; the
  exact later-rejection structure is to be captured by the prepared
  task-local observer extension before the next scoped fix).
- Real provider inference: ATTEMPTED; tool loop FAILED during
  upstream-response validation (LAN1
  native tool loop + one synthetic HTTP diagnostic probe + run 2
  native tool loop; every main attempt terminated at the task Gateway
  validator with `response.failed` code
  `responses_stream_event_not_supported`; LAN1 + probe: 10 failed
  ledger rows / 10 released reservations, zero settled; run 2: one
  auto-title aux settled (612 in / 46 out) + five main failures
  charged as estimates (48,422 tokens / EUR 0.048422), 6 finalized
  reservations, all 6 key request slots consumed; provider usage unknown
  not zero, key 6 used / 49,080 tokens / EUR 0.04908 / 0 reserved /
  0 fenced; the only other LAN traffic is the read-only metadata
  preflight GET documented in the 228-c checkpoint).
- Governance: resolved at 228-b — focused OAP governance 10 passed at
  the final 228-b code head (the a-era 1 failed / 9 passed is preserved
  as immutable history; see below).
- Strict zero-retry plus six-settled-request admission guarantee:
  `UNSATISFIED` (source-verified; recorded as a limitation, not a
  requirement). The human-approved bounded LAN plan explicitly allows
  stock native retries; six is a settled-request quota and failed
  admissions can release reservations. This is not a pending
  human-decision gate (see Approved bounded live plan).
- Final PR-head CI: GREEN — three workflow identities, 9/9 jobs on
  candidate head `b6e85b79` (verified 2026-11-25 ~05:45Z): CI run
  `45553132761` (6 jobs), CodeQL `45553132702` (1 job), Code Quality
  PR #401 `45553124958` (2 jobs), CodeQL aggregate success. AGENTIC-40
  machine gate bound in the manifest `preprotected_index_repair_gate` block:
  604 verified unique node IDs (12 unit files of the 582 combined run
  plus the 22-case PG file) with node-set hash and all-pass receipts
  (cross-reference only; no duplicated arrays here).
- No production certification, universal compatibility, or security
  certification claim.

## Heads and publication state

- Base main: `5f0f4c34ff13f1d76ae050708a37f387e6988451` (PR 395 merge).
- First tested implementation head:
  `79e27c844e70a54cdf092d53b6aca8bd5bb5004b` (338-test unit matrix plus
  the original 11-test PG run, both below).
- 228-a final code head: `55482cc16b4f40530498040c70e0151433b3a9c1`
  (442-test focused unit regression plus 18-test PG run, both below;
  `ruff check app tests` clean).
- Final 228-b code head: `c5d007fb272d0103d9f9a396547e237334987409`
  (467-test focused unit regression, 20-test PG run, and 10-pass
  governance, all below; `ruff check app tests` clean). `c5d007fb` is
  test-only on top of `d896ad91`, so the app code is byte-identical to
  the running task Gateway.
- 228-c guard-fix code head: `05dddb3e513749c61c31995dd6486fbe10fa14bd`
  (on top of the 228-b report head `e3a66894`; the app delta is the
  selected-native closure-property correction only). Tree identities:
  `HEAD:app` = `4d8d54632126cc04bc9974fa11092b7aa9047a46`;
  `HEAD:app/slaif_gateway` = `f753105b38ddc43761db908c3073da79eb864ab9`.
  Profile DATA is unchanged: fixture (canonical document) digest
  `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff`,
  client module `opencode-1.19.3-responses-v1` version `1`.
- 228-c final app candidate head:
  `3dde03bf6b7018f6bef2abfe9b0f645a5951a073` (chain from the 228-c
  guard-fix head: `087895cd` aux-dispatch + fake assistant-message
  standardization, `aeac5014` test-only umask follow-up, `6356589f`
  docs-only attempt record, `3dde03bf` strict-boolean fix). This is the
  app tree the task Gateway ran for all six loopback cases. Tree
  identities: `HEAD:app` =
  `e2e6ba68fd0329f7717c1057295c942e2ccb4c0c`;
  `HEAD:app/slaif_gateway` =
  `f7bad64806ba0e83901daba7c5c460ce1b03dbc7`. Profile DATA unchanged
  (same fixture digest; client module `opencode-1.19.3-responses-v1`
  version `1`).
- 228-c final repair candidate head:
  `b6e85b7930c20cb36f5142aea146fba617867aaf` (chain from the 228-c
  final app candidate: `b66b8b05` docs, `2f7970fa` docs, `564d21ba`
  merge of `origin/main` `79265a89`, `b6e85b79` scoped
  missing-`output_index` wire repair). This is the app tree the task
  Gateway currently runs and the head of the all-green CI. Tree
  identities: `HEAD:app` =
  `bf0958c7cae0bde896a9395ea96c03709fd3f752`;
  `HEAD:app/slaif_gateway` =
  `5e8c1606f37e9f2882b3fb1647259e56792c29c6`. Profile DATA unchanged
  (same fixture digest; client module
  `opencode-1.19.3-responses-v1` version `1`).
- Remote main reconciliation: remote `main` advanced to
  `79265a8919a74a71083eded279bfcf79d00cd80a` (merge of docs-only PR
  #402, `docs/responses-input-items-64k`: four docs about the ~65536
  input-items limit — `docs/codex-tuning-qwen.md`,
  `docs/configuration.md`, `docs/runbooks/codex-input-item-count.md`,
  `docs/upgrade-runbook.md`; disjoint from `app/` and `tests/`, so the
  app tree and all six case evidence are unaffected). Remote `main` IS
  now an ancestor: `origin/main` was merged into this branch through
  primary Git ownership as `564d21ba` before the final candidate
  freeze (no rebase, no reset; all repo docs and the untracked trio
  preserved).
- Tree identities at `55482cc16b4f40530498040c70e0151433b3a9c1`:
  `HEAD:app` = `30610d166c7de6a55510774a76af51125f54e044`;
  `HEAD:app/slaif_gateway` = `1c254ceb09b9ebf155102fc15e8d25c1f985b566`.
- Tree identities at `c5d007fb272d0103d9f9a396547e237334987409`:
  `HEAD:app` = `a857667b3ca7752170256b4dab7c39f4ae1b1213`;
  `HEAD:app/slaif_gateway` = `4f26abb76184df2a74a97fa37290f66f36708083`.
- Documentation-only commits: `bbaa8c4414e491f84a3fa1da894e1b012b1bfd36`
  (responses-compatibility), `7a2c7234c0f3116ee69c0be902a717a8f1df1cdc`
  (provider-forwarding-contract), `8c21b68cab899ef61ade40b6b917da4de2bdf949`
  (accounting), `a7583a50f3bc522c457611f31e273bec4865b27c`
  (security-model), `685fd6503b22df073e0c54e5746ba3f45501cde3`
  (first-time-operator-guide), `cd591ee7cd51373e7b353888c38500f0f6002f96`
  (verification record and manifest).
- Code commits after the first tested head:
  `8106929b5545611e3d3200606bca86b61800fc02` (v3 ciphertext alias
  captured from a validated id-bearing done; bounded native idless
  reasoning input; legacy visible-idless gate restored),
  `488c5776eeac3dfec1ecd8469e9b20af3ec803db` (removed flat
  function-tool historical replay via the existing same-key call
  HMAC), `a146d1d5e78d71c151695cc87b72afa1595ff4a4` (pinned-SDK
  required output/content indexes on selected-profile stream items),
  `ae38ec9e1e7bdec706064ba761c5c8bb8bd0f5c4` (summary-part closure,
  exact cipher added item, flat-function streaming flag),
  `55482cc16b4f40530498040c70e0151433b3a9c1` (tests only).
  228-b: `2b6e7e48ca2fde938e3d0f167fb506fe6201c6af` (aux-title form,
  assistant output-text history, empty visible reasoning),
  `cb936fbd2e22da532532c844d0596c70b3d59e1f` (unit coverage for the
  same), `fb6a521019da5ec74cab8990b77651802aa0bf0d` (provider reasoning
  IDs required; cipher capture gated to the selected profile; visible
  absent/null/empty lifecycle; orphan-done rejection),
  `ce476f3b6ea30ae24d95fd10628929ad065ab7ae` (v3 alias issuance
  selected-profile-only), `49d55a9dc81bfffbf370c63f6fd0ba03b8f3c2f6`
  (OpenCode-only sparse-visible exception),
  `ea561ac96bfb57a59acf01ea3df0ec3129b844f1` (aux/compaction summary
  stream-true-only), `e6687613af90fc4edc34253e2b6a264c916032d7`
  (focused unit coverage),
  `d896ad91f5de1c34bdfb753fedcc51086717fa0b` (part.done closure scoped
  to the selected native profile),
  `c5d007fb272d0103d9f9a396547e237334987409` (tests only: HTTP-mock
  factory-adapter settlement).
- Accepted secondary cherry-picks (fake-only capture checkpoints):
  local `89e536153f1c9487ef83e6ee9713970bfdd2b13c` from secondary
  `3c61d6c3daa62bccada1f3e7756611ad4e493151` (initial capture);
  local `19b1569de3efbd5a1e8fff7dac0c44ebc97737d3` from secondary
  `569f2f11afdaa7aacd8556c29ee7e3b28505feea` (corrected wire and
  verifier); local `552231f6699427425f2bcdca4d1783554efc2a11` from
  secondary `f3af15335907fc5fe8c2f02705e7df4ad91d424a` (fix2 recapture:
  no top-level response_id, assistant-text continuation, default
  auto-title aux-first shape, visible-reasoning states); local
  `ca76576019f2021f94890d85be3885d86c544f89` from secondary
  `5a2b7e81b2759f60630e06856a4ee744a0b95a11` (native client-side
  compaction loopback capture, synthetic trigger).
- Final publication head: pending — the report's parent is this
  documentation-refresh commit.
- PR: DRAFT PR #401 (one numeric objective = one PR; created by 228-a,
  amended by 228-b); title "Add pinned native OpenCode Responses client
  support"; base `main`; auto-merge disabled.

## Scope and identity

- Module: `opencode-1.19.3-responses-v1` (engine version string `1`),
  distinct from the Codex and Chat modules.
- Profile DATA: `modules/clients/profiles/opencode-1.19.3-responses.json`,
  fixture digest `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff`.
- Pinned client: OpenCode 1.19.3 (tag `v1.19.3`, source commit
  `e3c4eb242585dcd77be1a867391b7c25fd47ce52`), binary SHA256
  `179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9`,
  `@ai-sdk/openai` 3.0.88 (not the Chat `@ai-sdk/openai-compatible`
  2.0.41), `ai` 6.0.168, OpenAI Responses wire API.
- Selection: only the authenticated server-side key metadata pin
  `metadata_json.responses_policy.client_module`
  (`{id, version, fixture_sha256}`). An absent or `null` pin leaves the
  default module unchanged; a present malformed, unknown, stale, or
  digest-mismatched pin fails closed before admission
  (`client_module_metadata_invalid`, `unsupported_client_module`,
  `client_module_fixture_mismatch`; a present-but-`null` digest is a
  fixture mismatch). Headers, model names, and request metadata never
  select a module.
- Qualified server pairs: `openai` and `openai-compatible` only; any
  other key/route pair is denied `400 incompatible_client_server_pair`
  before forwarding (also at input-token counting).
- Streaming-only exact field shape `{include, input, max_output_tokens,
  model, reasoning, store, stream, tool_choice, tools}`; `stream` must be
  `true` (else `opencode_1193_field_shape`), `store` `false`,
  `tool_choice` `"auto"`, `include` accepts only
  `reasoning.encrypted_content`; `developer`/`user` roles are typeless;
  `reasoning` is `{"effort": minimal|low|medium|high|xhigh}`;
  `max_output_tokens` 1..1,048,576 (the captured 32000 is an
  observation, not a cap).
- Flat strict 9-tool set (`bash edit glob grep read skill task todowrite
  write`): ≤32 declarations, description ≤20,000 B, depth ≤8,
  ≤64 properties, declaration ≤65,536 B; call id 1..128 chars,
  arguments ≤65,536 B.
- Id-less encrypted reasoning: owned ciphertext-derived v3 reference
  (`slaif-codex-replay:v3:reasoning:{len}:{ciphertext}`), HMAC-only,
  `item_id=None`, bounded ciphertext (non-empty, ≤1,048,576 B) held in
  immediate memory only, persisted only after successful finalized
  output, bound to the same key and the same route/provider/model. The
  v3 alias is captured only from a VALIDATED id-bearing
  `response.output_item.done` reasoning item after finalized usage; the
  emitted stream event is not rewritten. Id-bearing reasoning inputs
  are rejected in this native flat form
  (`opencode_1193_input_item`); legacy visible idless behavior is
  unchanged. `allow_idless_encrypted_reasoning` is default `False` in
  every other policy spec; legacy presets and legacy digest bytes are
  unchanged; no schema change.
- Streaming lifecycle and tool authority (L1/L3, implemented): the
  native typed message/reasoning lifecycle dispatches independently of
  a non-empty tool count (a zero-tool auxiliary lifecycle is covered);
  stream tool events plus the exact `(functions, name, function)`
  active declaration set gate new tool execution; custom, hosted, and
  obsolete generated calls are denied.
- L2 not implemented: the loopback fake's `_ev` added `response_id`
  unconditionally, which is not client-wire authority; the shared
  strict `_only_fields` check is not relaxed on that evidence.
- Required indexes: selected-profile stream items must carry the
  pinned-SDK required output/content indexes with item/call linkage;
  generic optional-index acceptance is not conformance proof; legacy
  profiles are preserved.
- Historical tool identity: removed flat function-tool history replays
  only through the existing same-key/kind/callID/name HMAC, even when
  the tool is no longer declared; history is never unioned into the
  current active declaration.
- 228-b streaming/output semantics (selected native profile only;
  legacy validators and digest bytes unchanged): provider reasoning
  `added`/`done` events must carry the actual provider IDs (the
  captured upstream issues them; only the SDK's request-side replay
  drops the ID), so an id-less reasoning `done` is rejected whenever
  encrypted-replay is on, while id-less reasoning INPUT eligibility
  remains a separate, still-granted fact; the v3 ciphertext alias is
  captured and issued only for this selected profile, so legacy
  profiles keep single-ID-reference behavior; the visible
  absent/null/empty `encrypted_content` output lifecycle passes with
  ZERO references (no opaque alias; empty string kept verbatim;
  omitted summary accepted as `[]`, explicit `null` denied); the
  `response.reasoning_summary_part.done` closure event is accepted only
  on this profile (legacy default denial); orphan `done` events without
  a preceding `added` are rejected under the required output indexes
  (legacy sparse paths preserved); the auto-title and compaction
  summary requests are exactly 7 top-level fields (`include, input,
  max_output_tokens, model, reasoning, store, stream`), `stream: true`
  only, no `tools`/`tool_choice`, input a list (3 items observed for
  auto-title, 2 for compaction); continuations after assistant text or
  compaction are 4 typeless items `[developer, user, assistant, user]`
  with the byte-exact summary in the assistant slot. Correction note:
  the 228-b order prose described the auto-title request as
  non-streaming; the captured receipt (`report-fix2`,
  `gates.defaulttitle.aux_request_facts.stream=true`) outranks that
  prose, and no non-streaming obligation is invented.
- Retry boundary: the gateway strict zero-retry rule is gateway policy,
  not a native client guarantee. The pinned OpenCode session hardcodes
  `RETRY_MAX_RETRIES=5` with no override parameter above the SDK default
  `maxRetries = input.retries ?? 0`, so zero native HTTP retries are
  never claimed for this profile.
- No DB migration, no engine upgrade; a pin change is data-only (new
  bytes + digest + re-pin + restart).

## Evidence

### Unit matrix at the first tested head (labeled; mock-upstream only where noted)

- Head: first tested implementation head
  `79e27c844e70a54cdf092d53b6aca8bd5bb5004b`.
- Result: `338 passed in 5.29s`.
- Files (6): `test_codex_replay_idless_reasoning.py`,
  `test_responses_codex_streaming_idless_reasoning.py`,
  `test_opencode_1193_responses_module.py`,
  `test_responses_codex_multiturn_replay.py`,
  `test_responses_codex_streaming_tools.py`,
  `test_codex_replay_service.py` (all under `tests/unit/`).
- Mock-upstream coverage: `respx`/`httpx` appear only in
  `tests/unit/test_responses_codex_streaming_tools.py` (inside this
  matrix); the other five files are pure unit.
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_codex_replay_idless_reasoning.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_codex_replay_service.py -q -o addopts= -p no:cacheprovider`

### Focused unit regression at the 228-a final code head (history)

- Head: final code head `55482cc16b4f40530498040c70e0151433b3a9c1`.
- Result: `442 passed in 5.81s`.
- Files (7): `test_responses_codex_streaming_opencode_lifecycle.py`,
  `test_responses_codex_streaming_idless_reasoning.py`,
  `test_responses_codex_streaming_tools.py`,
  `test_responses_codex_client_tools.py`,
  `test_opencode_1193_responses.py` (secondary-owned; run, never
  edited), `test_opencode_1193_responses_module.py`,
  `test_responses_replay_delivery.py` (all under `tests/unit/`).
- Separate set from the 338-test matrix (3 files shared); the two
  results are never summed.
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_opencode_lifecycle.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_opencode_1193_responses.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_replay_delivery.py -q -o addopts= -p no:cacheprovider`

### Focused unit regression at the final 228-b code head

- Head: final 228-b code head `c5d007fb272d0103d9f9a396547e237334987409`.
- Result: `467 passed in 6.00s`.
- Same 7-file set as the 442 run above, re-executed at the final b
  head; supersedes the 442 count for that set. Overlap with the
  338-test matrix (3 files) remains separate; no results are summed.
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_opencode_lifecycle.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_opencode_1193_responses.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_replay_delivery.py -q -o addopts= -p no:cacheprovider`

### Real isolated PostgreSQL integration at the 228-a final code head (history)

- Head: final code head `55482cc16b4f40530498040c70e0151433b3a9c1`.
- Result: `18 passed in 3.27s` (11 pre-existing + 7 new); 4 warnings
  (2 benign SQLAlchemy `distinct()` notices + 2 benign
  pytest-asyncio deprecation notices); no side effects beyond the
  disposable database.
- Scope: native-Gateway + PostgreSQL + mock-upstream consumer run at
  `handle_response_create`: real route-capability gate
  (`enforce_responses_route_capabilities`), real strict SSE validator,
  real PostgreSQL settlement + replay references; upstream mocked at
  `get_provider_adapter`. HTTP ingress/authentication remains covered
  by the existing e2e (not re-run).
- New coverage: positive settlement plus immediate idless
  continuation; negatives — altered ciphertext →
  `responses_codex_replay_reference_not_found`, foreign key → same 404
  code, unknown model → `model_not_allowed_for_key` with `calls == 0`,
  id-bearing reasoning input → `opencode_1193_input_item`, failed
  stream → estimated finalization (513/5/518, 0 references,
  reservation finalized 32,513), missing replay capability →
  `responses_route_capability_not_supported`.
- Database: task-owned isolated PostgreSQL 16 on `127.0.0.1:54401`,
  database `slaif228_test` (explicit `TEST_DATABASE_URL` only).
- Command:
  `TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_test PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/integration/test_opencode_1193_responses_postgres.py -q -o addopts= -p no:cacheprovider`

### Real isolated PostgreSQL at the final 228-b code head

- Head: final 228-b code head `c5d007fb272d0103d9f9a396547e237334987409`.
- Result: `20 passed in 4.00s` (the 18 above + 2 new); no side effects
  beyond the disposable database.
- Scope change: the 2 new parameterized cases (`openai-native`:
  provider `openai`, kind `openai`; `openai-compatible`: provider
  `mock228b-compat`, kind `openai_compatible`) leave
  `gateway.get_provider_adapter` UNPATCHED — the real factory selects
  the real registered adapter and real httpx is intercepted by `respx`
  at `127.0.0.1` loopback. The 18 prior tests keep their
  `get_provider_adapter`-mocked scope.
- Wire facts asserted: 2 POSTs per case, public-to-upstream model
  substitution, `stream is True`, Bearer-only credential, and no HMAC
  secret / token hash / provider value in the upstream body.
- PG settlement asserted: 11 requests, 12,359 tokens, reserved 0/0,
  `cost_used_eur == Decimal("7.250052")`, 3 replay references (incl.
  the function-call binding), 2 finalized ledger + reservation rows.
- Command:
  `TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_test PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/integration/test_opencode_1193_responses_postgres.py -q -o addopts= -p no:cacheprovider`

### Secondary fake-peer loopback capture (synthetic; labeled)

- Two accepted cherry-picks, both fake-only capture checkpoints (NOT a
  Gateway/provider pass): local
  `89e536153f1c9487ef83e6ee9713970bfdd2b13c` from secondary
  `3c61d6c3daa62bccada1f3e7756611ad4e493151` (initial capture; the
  original `report-final.json` is preserved as provisional,
  pre-correction, fake-only); local
  `19b1569de3efbd5a1e8fff7dac0c44ebc97737d3` from secondary
  `569f2f11afdaa7aacd8556c29ee7e3b28505feea` (corrected wire and
  verifier: the loopback fake no longer adds an artificial
  `response_id`; required full-byte encrypted-replay and exact
  call-linkage gate plus pure negative tests).
- Corrected receipt `all_pass=true` (executed at secondary source SHA
  `569f2f11afdaa7aacd8556c29ee7e3b28505feea`, finished
  2026-11-23T12:04:07Z): text 5.978 s / 1 request; tool loop 5.53 s /
  2 requests, 1/1 correlated tool result, final 38 B exact marker;
  reasoning 5.578 s / 2 requests, 5-item continuation,
  `encrypted_replay_verified=true`, `call_linkage_exact=true`.
- Cleanup predicates: `run_root_cleaned=true`,
  `cleanup_verified=true`, `fake_process_terminated=true`,
  `session_distinct_across_probes=true`.
- Extended fake-only checkpoints (same synthetic loopback boundary):
  the fix2 eight-probe recapture (receipt
  `/home/janezp/codex-work/slaif-228-task/report-fix2.json`,
  `all_pass=true`, finished 2026-11-24T01:07:42Z) and the 228-b
  nine-probe compaction superset run (9/9 gates, finished
  2026-11-24T09:59:04Z). Per-probe facts, executed-artifact provenance
  hashes, and the honest deviations are in the dossier
  (`docs/agentic-clients/opencode-1.19.3-responses-v1.md`); the
  compaction positive is a synthetic-trigger fake-only client
  observation, not Gateway/provider compaction support.
- Synthetic bearer + `127.0.0.1` loopback only; no raw content, IDs,
  or credentials retained.
- The corrected wire proves the pinned SDK consumes a standards-shaped
  stream; SDK tolerance alone is not correct-producer proof.

### Lint

- `ruff check app tests` — clean at the 228-a final code head
  `55482cc16b4f40530498040c70e0151433b3a9c1` (root-verified) and re-run clean at the final 228-b code
  head `c5d007fb272d0103d9f9a396547e237334987409`.
- `git diff --check 5f0f4c34ff13f1d76ae050708a37f387e6988451..55482cc16b4f40530498040c70e0151433b3a9c1`
  and `git diff --check 5f0f4c34ff13f1d76ae050708a37f387e6988451..c5d007fb272d0103d9f9a396547e237334987409`
  — both clean.

### Focused OAP governance (new activation)

- Result: `1 failed, 9 passed in 0.37s`.
- Failed: `test_initial_round_declares_new_pr_and_one_objective_one_pr`.
- Root cause: activated order line 3 reads `PR mode: NEW_PR`, while the
  validator requires the literal `PR mode: CREATE_NEW_PR` (or its
  backticked form) for `-a` initial rounds.
- Disposition: the activated order, `oap/active`, and the test are
  unchanged (order rule: commit the activated order byte-unchanged; no
  test weakening). Same class as the immutable 227-a order-format
  finding; the canonical 228-b `AMEND_EXISTING_PR` on the same PR
  (227-b precedent) is this objective.
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider`

### Focused OAP governance (228-b canonical order)

- Head: final 228-b code head `c5d007fb272d0103d9f9a396547e237334987409`.
- Result: `10 passed`. The canonical 228-b `AMEND_EXISTING_PR` order
  passes the focused governance suite in full; the a-era 1 failed / 9
  passed above is preserved as immutable history (no test changes in
  either round).
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider`

### 228-c final candidate evidence (b6e85b79; CI green)

- 582-test combined focused unit run at candidate head `b6e85b79`
  (12 unit files, one run; receipts are never summed): includes the
  29-test new repair file (pure validator cases plus 3 wire cases)
  and root's independently re-run 242-test subset
  (`test_responses_codex_streaming_tools.py` 197 +
  `test_responses_codex_streaming_opencode_lifecycle.py` 45).
- The 3 wire cases are a SUBSET of the 29-test file: synthetic
  profile with AuthGatewayKey-style DB/route fixtures; HTTP
  authentication is NOT proven there — HTTP evidence remains the six
  loopback cases and the existing e2e.
- 22-test real isolated PostgreSQL run (exit 0) on the NEW
  disposable database `slaif228_index_fix_test` (`TEST_DATABASE_URL`
  on `postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_index_fix_test`;
  the qualification DB `slaif228_test` was not touched). Same
  auth-scope wording: AuthGatewayKey-style fixtures; HTTP auth
  separate. The two new cases: (a) missing-`output_index` two-turn
  settlement — only the FIRST added-absence is observed natively, the
  second-turn extension is SYNTHETIC; (b) contradictory-terminal
  denial → `response.failed` +
  `responses_stream_event_not_supported` with estimated settlement +
  finalized reservation + 0 refs.
- AGENTIC-40 machine gate: one `--collect-only` over the verified
  12-file 582 selection plus the 22-case PG file = 604 unique node
  IDs; the node-set list, count, hash, and all-pass execution receipts
  are bound in the manifest `preprotected_index_repair_gate` block
  (cross-reference only; no duplicated arrays here). External checks:
  the three workflow identities / 9 jobs listed in Status, all green.
- Mock-half reuse: all six loopback cases' upstream events carry
  explicit output indexes, so the repair derives nothing for them
  (inert); their evidence is reused without rerun.

### 228-c LAN half (partially executed; repair landed; run 2
terminal FAIL at a later stream event)

- LAN1 (root-dispatched, run root `runs/228c-native-lan-1`,
  `live_tool_loop`, short-lived key `d2ee3f25…`, model
  `qwen38-27b`, 540 s watchdog): 134.178 s / exit 1 / no tool;
  `response.failed` code `responses_stream_event_not_supported`. PG:
  9 failed ledger rows (HTTP 200, accounting failed) + 9 released
  reservations; key 0 used / 0 reserved / 0 fenced; provider usage
  UNKNOWN (not zero — provider work occurred before the gateway
  failure point); the prior 21 mock finalized rows preserved.
- HTTP diagnostic probe (root-executed, exactly 1 request, 1.406 s,
  exit 0, same key/candidate, 7-field stream body, max output 128,
  no retries): first rejection was
  `response.output_item.added` (seq 2, item present, top-level
  `output_index` ABSENT, unknown keys 0) — demonstrates the cause of
  the FIRST failure; NOT proof of no later gap. +1 failed row / +1
  released reservation → key totals 10 failed / 10 released, 0 used.
- Observer artifacts (0600, preserved; hashes recorded before the
  observer Gateway was retired):
  `native/obs228c-rejections.json` sha256
  `ea6698514492c7a6893b27ae151b00cbf515032030458f558d53f9908f87ccae`
  (2303 B); `gw-observer.out` sha256
  `0943f75e50dc344369c965c163ba8b290c7118965fe689a94bb83193cad248e9`
  (183 B); `gw-observer.err` sha256
  `10235a3ce4b354893b4bcb6c14915efd9a6dce1a7902e5cb0f861390e678645d`
  (276 B).
- Bounded wire repair (candidate `b6e85b79`): typed profile flag
  `repair_missing_output_indices` (default `False`), enabled only for
  the selected native pair (exact client module identity plus resolved
  server module `openai-compatible`); `require_output_indices = True`
  kept; derived positions fail closed on ambiguity, conflict,
  orphans, or order contradiction; the terminal-order guard covers
  BOTH `response.completed` and `response.incomplete` forms; the
  original provider status is preserved on the wire (validation-only
  normalization is never forwarded); legacy profiles unchanged.
- LAN retry (run 2, `runs/228c-native-lan-2`): root-dispatched on the
  all-green candidate (400 s watchdog, within the 423.758 s remaining
  at last observation); TERMINAL FAILED at 130.544 s / exit 1 / no
  tool / one error event / final marker mismatch / config removed /
  canary clean. The repaired first missing-index gap was passed;
  five main attempts then failed at a LATER stream event with the
  same `responses_stream_event_not_supported` code (5 rows charged
  as estimates; 47,940 in / 482 out); one auto-title aux settled
  (612 in / 46 out); all 6/6 key settled-request slots consumed, so
  the final 429 on the last attempt is secondary to the stream
  defect. Key PG totals: 1 finalized + 5 estimated + 10 failed
  ledger rows; 6 finalized + 10 released reservations; 49,080
  tokens / EUR 0.04908; 0 reserved / 0 fenced; no key replacement,
  no reset, no cap change. The settled-request extension (6 -> 12,
  same key, unchanged remaining token/cost/time budgets) was
  requested asynchronously from the human maintainer; no traffic or
  quota mutation until the explicit reply. The exact later rejection
  structure is to be captured by the prepared task-local observer
  extension (safe public metadata only; offline canary 65/65 PASS;
  no server started) before any next scoped code fix. Spend to date
  under the bounded plan (root conservative count): 8 LAN tests (7
  native outer + 1 HTTP diagnostic probe); after run 2,
  293.214 s OpenCode / 851.194 s aggregate wall remaining; no counter reset.

### Task-owned native setup (loopback mock half complete; LAN half partially executed; run 2 terminal FAIL at a later stream event)

- Services: task-owned PostgreSQL 16 on `127.0.0.1:54401` (database
  `slaif228_test`, trust, loopback only; PID 33486); the six
  loopback cases ran on the task Gateway at
  `http://127.0.0.1:18310/v1` running app candidate `3dde03bf`; the
  observer Gateway (PID 1168152) used for the LAN1 diagnosis was
  retired and replaced by a normal hook-free uvicorn Gateway PID
  1233012 running the final candidate `b6e85b79` (app tree
  `bf0958c7`), same private env, `WEB_CONCURRENCY=1`,
  `REQUEST_CAPTURE_ENABLED=false`, private 0600 log
  `native/gateway-b6e85b79-hookfree.log`; separate loopback mock
  upstream at `127.0.0.1:18031` (PID 1074660, compaction case)
  reusing the existing
  `scripts/verify_agent_chat/loopback_responses_fake.py` (no second
  SSE producer).
- Gateway env: `REQUEST_CAPTURE_ENABLED=false`, Redis rate limits off;
  route `slaif-228b-mock`, model `opencode228b` to upstream
  `opencode228b-upstream`, streaming, all four codex capabilities on,
  `provider_max_retries=0`, EUR 1/M input and output pricing,
  `codex_limits` 1,050,000 / 32,768 / 128,000, and task-scoped
  `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=8192` (shared default
  4096 unchanged; operator must set and restart).
- Task key: `/v1/responses`-only. Preflight verified wrong key 401,
  models 403 `endpoint_not_allowed`, minimal body 400
  `opencode_1193_fields`, wrong model 403, and PG counters
  0 admitted / 0 reserved / 0 used (no admission).
- Short-lived LAN key `d2ee3f25…` (0600 private file, value never
  printed; `/v1/responses`-only, hosted denied): pin
  `opencode-1.19.3-responses-v1` version `1` digest
  `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff`;
  the four required capabilities (`codex_request_envelope`,
  `codex_client_tools`, `codex_streaming_tool_events`,
  `codex_encrypted_reasoning_replay`); provider `qwen-student-lan`,
  model `qwen38-27b`; max 6 settled requests, 970,454 tokens,
  EUR 0.970454; expiry re-narrowed to
  2026-11-25T06:35:59.992285Z (all other row fields verified
  unchanged); 0 used / 0 reserved / 0 fenced; no settled provider
  usage (LAN1 + probe failed at the gateway validator; provider usage
  unknown, not zero).
- Pinned-binary launcher (task-local, nonsecret setup record, not
  committed; the secondary-owned live tool-loop branch executed for
  LAN1, probe, and run 2): loopback mock half complete (six cases,
  see the 228-c checkpoint); the LAN half is partially executed
  (LAN1 + probe failed at the gateway validator; run 2 TERMINAL
  FAILED at a later stream event — see the "228-c LAN half" evidence
  subsection).

### Not run

- Order item 6, protected LAN half: PARTIALLY EXECUTED — LAN1
  (root-dispatched) and one HTTP diagnostic probe executed; both
  failed at the task Gateway validator with zero settled usage (10
  failed ledger rows / 10 released reservations; key 0 used /
  0 reserved / 0 fenced; provider usage unknown, not zero). The
  demonstrated missing-`output_index` defect is repaired at
  `b6e85b79` (all CI green); the root-dispatched run 2 retry
  (`runs/228c-native-lan-2`) TERMINAL FAILED at 130.544 s / exit 1 /
  no tool / final marker mismatch. The repaired first missing-index
  gap was passed; five main attempts then failed at a LATER stream
  event with the same `responses_stream_event_not_supported` code
  (5 charged as estimates, 47,940 in / 482 out; one auto-title aux
  settled, 612 in / 46 out; 6/6 key slots consumed). The exact
  later-rejection structure is to be captured by the prepared
  task-local observer extension (offline canary 65/65 PASS; no
  server started) before the next scoped fix. The CI/setup review
  gate is satisfied (CI green); this is not a human decision.
- Real provider inference: ATTEMPTED; tool loop FAILED during
  upstream-response validation (see the
  "228-c LAN half" evidence subsection); one auxiliary request
  settled with provider-reported usage and five main failures were
  charged as estimates; actual main provider work/cost is unknown.
  The only other LAN traffic is the read-only metadata
  preflight GET.
- Protected live-qualification gate: final qualification `not_run`
  (LAN1 + one HTTP diagnostic probe failed at the task Gateway
  validator with zero settled usage; run 2 executed and TERMINAL
  FAILED at a later stream event; the prepared task-local observer
  extension will capture the exact later-rejection structure before
  the next scoped fix).

## Findings

1. Streaming gap resolved per root rulings: L1/L3 implemented
   (lifecycle dispatch independent of a non-empty tool count; the
   tool-event flag plus the exact active
   `(functions, name, function)` set gates new tool execution); L2
   intentionally not implemented (the fake `_ev` `response_id` is not
   client-wire authority; the shared strict `_only_fields` check is
   not relaxed); pinned-SDK required output/content indexes enforced
   on the selected profile; legacy profiles and digest bytes
   unchanged.
2. Present-but-`null` fixture digest → `client_module_fixture_mismatch`
   (fail closed), distinct from an absent/`null` pin (default module
   unchanged).
3. Streaming-only: `stream: false` → `opencode_1193_field_shape`.
4. Id-less reasoning v3: the ciphertext alias is captured only from a
   validated id-bearing done after finalized usage (emitted event not
   rewritten); id-bearing reasoning inputs are rejected in the native
   flat form; legacy visible idless behavior unchanged; denial matrix
   (altered/foreign/stale cipher, wrong route/provider/model, present
   invalid id, same-key immediate continuation) covered in the unit
   and PG runs.
5. PostgreSQL settlement/replay coverage: 18 tests at the 228-a final
   code head, and 20 at the final 228-b code head (the 2 new cases
   leave `get_provider_adapter` unpatched: real factory, real
   registered adapter for both `openai` and `openai_compatible` kinds,
   respx loopback interception, wire-level and settlement assertions);
   all labeled as a native-Gateway + PostgreSQL + mock-upstream
   consumer run at `handle_response_create` (real route gate, strict
   SSE validator, PG settlement and replay references).
6. Retry boundary as stated above; the strict zero-retry and
   six-settled-request admission guarantee remains `UNSATISFIED`
   (source-verified; recorded as a limitation, not a requirement).
   Stock native retries are explicitly allowed by the human-approved
   bounded LAN plan (and by the 227-c LAN Chat qualification, that
   execution only); six is a settled-request quota and failed
   admissions can release reservations.
7. 228-b governance: the canonical 228-b `AMEND_EXISTING_PR` order
   passes the focused OAP governance suite 10/10 at the final b code
   head; the a-era 1/10 (order literal `NEW_PR` vs validator
   `CREATE_NEW_PR`) is preserved as immutable history, with order,
   `oap/active`, and test unchanged in both rounds.
8. 228-b streaming/output semantics as listed under Scope and identity:
   provider reasoning IDs required on added/done (id-less done
   rejected, id-less input eligibility separate); selected-profile-only
   v3 alias issuance, `part.done` closure, and orphan-done rejection;
   visible absent/null/empty output lifecycle with zero references;
   7-field stream-`true` aux/compaction summary requests; 4-typeless
   continuations.
9. Correction: the 228-b order prose called the auto-title request
   non-streaming; the captured receipt (`report-fix2`,
   `aux_request_facts.stream=true`) outranks that prose; no
   non-streaming obligation was invented and the selected profile
   remains fail-closed on `stream: false`.

## 227 reuse (labeled, not relabeled)

The 227-c bounded LAN Chat qualification record
(`docs/verification/2026-11-20-hermes-opencode-chat.md`) is reused only
as "227-reused": Chat-only, that execution only, with its documented
stock-retry exception. No 227 evidence is relabeled as a 228 execution,
and nothing in it qualifies this Responses module.

## 228-c checkpoint (loopback mock half complete; LAN half partially executed — LAN1 failed, wire repair at b6e85b79, run 2 terminal FAIL at a later stream event)

- Guard correction: `response.reasoning_summary_part.done` is now
  scoped by the new selected-native typed stream property
  `allow_reasoning_summary_part_done` (enabled only in the OpenCode
  1.19.3 module policy spec) instead of the legacy
  `allow_sparse_visible_reasoning` flag; legacy sparse/empty
  visible-reasoning profiles keep the baseline denial.
  Legacy-negative and native-positive regressions added; 314-test
  focused unit run over the 4 directly affected files and
  `ruff check` on all 6 changed files pass at
  `05dddb3e513749c61c31995dd6486fbe10fa14bd`.
- Owned task services restarted onto that exact app tree: Gateway
  PID 663637 (127.0.0.1:18310/v1) and loopback mock PID 663347
  (127.0.0.1:18031/v1, existing `loopback_responses_fake.py`,
  baseline case); process identity/readiness verified across
  separate tool calls; PG revalidated (6 task keys, 1 route, usage
  ledger/reservations/diagnostics 0, `requests_used_total` sum 0,
  alembic `0028_demo_web_control`). No evidence reset.
- LAN target fresh nonsecret readiness: `10.8.132.55:18021` TCP
  connect OK; unauthenticated `GET /v1/models` → 401 (target up, no
  credentials used).
- Safe LAN preflight (authenticated `GET /v1/models` read-only metadata
  only; no LAN inference sent): task PG now also holds the
  accepted LAN target as provider `qwen-student-lan`
  (`openai_compatible`, base `http://10.8.132.55:18021/v1`,
  `max_retries=0`, timeout 60 s, key resolved from
  `LAN228_UPSTREAM_API_KEY` at adapter creation) with route
  `qwen38-27b` -> `qwen38-27b` on `/v1/responses` (streaming, same four
  Codex capabilities as the loopback pair, `codex_limits` set to the
  real LAN model limits 245760/32768/32768) and EUR 1.00/M task
  pricing. The operator-owned bearer (reviewed `qwen-student-lan`
  profile, mode 0600, value never printed) was copied only into the
  0600 task Gateway env file. No LAN task key was created; the
  short-lived key is created only at dispatch time.
- Task Gateway restarted once more for the new env var: new PID
  678046 (long-lived session 70659), 127.0.0.1:18310/v1, app tree
  byte-identical to the `05dddb3e` guard-fix checkpoint (HEAD
  `2cb87417` is docs-only); listener, process env var presence,
  401 unauth probe, and clean worktree revalidated across separate
  tool calls; PG revalidated (2 providers, 2 routes, 6 task keys,
  usage ledger/reservations/diagnostics 0). No evidence reset.
- Loopback case preparation (no traffic): pre-c fake
  `state.json`/`requests.jsonl` journals (b-era test state plus the
  22:42 restart-verification direct-fake probe) archived verbatim per
  case under `archive-228c-prep-20261124T225629Z/`; all six case
  `scenario.json` files match the launcher case selectors
  (`assistant_tool` baseline with auto-title, three
  `reasoning_visible` cipher states absent/null/empty,
  `reasoning_continuation`, `compaction` with no completed-read or
  marker predicates); all client run-roots verified absent (launcher
  requirement). Loopback dispatch state: ready, awaiting
  root-reviewed dispatch.
- Marker seam correction (root-ordered): the fake-side
  `run/expected_marker.bin` for the baseline plus the three
  `reasoning_visible` cases was replaced from dangling symlinks to
  private 0600 unpredictable 40-byte newline-free regular files
  (bytes never printed; old links archived under
  `archive-228c-seam-fix-20261125T011035Z/`); `reasoning_continuation`
  and `compaction` keep their static sentinels (still dangling,
  recorded honestly). Client run-roots remained absent.
- No-tools aux/compaction dispatch + fake assistant-message
  standardization checkpoint
  `087895cd478d17a259adb6be1e952ecc2d5f6f21`: the selected OpenCode
  streamed lifecycle now dispatches from `stream is True` alone
  (taxonomy absent or empty => empty active set, so every new
  generated tool call still fails closed); key/route capability gates
  and the 0.149 dialect unchanged. The loopback fake assistant
  message added/done now carry the standard shape
  (`in_progress`/empty content -> `completed`/output_text;
  producer-only, no gateway relaxation). Test-only umask hygiene
  follow-up `aeac5014cf0bf943236506d6d57f2a78426f83fd` (app tree
  unchanged: `HEAD:app` `8af923e0ffbc895652101fdf009a96b09379018d`,
  `HEAD:app/slaif_gateway` `c462b6580306f37c412b17961d2833f197a33ad2`).
  Focused 244-test unit run over the 3 affected files and
  `ruff check` on all 4 changed files pass; executed fake sha256
  `118ec65e28dbedc686f6154ed7137dd5553a21220d6d5ab2423ea0e7fb51e250`
  (older receipts historical for that hash).
- Owned services restarted onto that app tree: Gateway PID 1013775
  (long-lived session 80060) and loopback mock PID 1004007 (session
  64614, baseline case, clean dispatch-time journal state);
  healthz 200, fake models 200, listeners verified across separate
  tool calls; PG unchanged at restart (ledger/reservations/diagnostics
  0). No evidence reset.
- First native loopback baseline dispatch (root-dispatched,
  2026-11-25T01:46Z; root-verified preconditions: Gateway health 200,
  task-key models 403, plan exit 0, no key leak, PG 0/0, fake state
  absent): ATTEMPTED, FAILED on the main request, honestly preserved.
  The auto-title auxiliary request (7 top-level fields, no tools,
  stream=true) forwarded and settled: PG 1 successful finalized ledger
  row (input 4 / output 2 tokens) + 1 finalized reservation; 0
  `response_references`, 0 `codex_replay_references`, 0 diagnostics.
  The main 9-tool request was rejected pre-upstream by the task
  Gateway with HTTP 400 code `opencode_1193_tool_declaration` (no
  error param; the validation-stage row is not in
  `request_diagnostics`). Client exit 1, elapsed 6.83 s, binary
  1.19.3 sha256
  `179ca421d61eefeadfa0c50e084a6e79c1623734732f0f4593f81ccfd3ab7ee9`
  (unchanged); receipt and private logs preserved in the run root; PG
  usage preserved (no reset). The root-traced hypothesis was
  CONFIRMED by the secondary synthetic-only direct-fake diagnostic
  (facts in the strict-value diagnostic bullet below); the bounded
  native-only fix followed.
- Credential isolation after the attempt: the task key (75 B, sha8
  `f9c03464`) is absent from every file under the fake case directory;
  the fake journal records the upstream Authorization as a redacted
  placeholder Bearer (token_sha256_8 `980e55c0`, the mock upstream
  key), i.e. the task Gateway key never reached the mock.
- Strict-value diagnostic (secondary, synthetic-only direct-fake; the
  task Gateway was not touched): all 9 flat function tools on the wire
  carry `strict: false` as a JSON boolean with exactly the 5 declared
  keys; description sizes 399–4694 B; max serialized declaration
  5210 B; the fake-only native loop passed (exit 0, 6.532 s, exact
  marker, read completed, config removed, no key leak); journals
  removed per approved cleanup; safe facts in task-root-only
  `runs/228c-strict-diagnostic-result.json`. Note (presence vs value):
  the initial validator assumed `strict is True`; the earlier
  structural capture recorded `strict` field presence only, which is
  insufficient about the value; the current pinned native diagnostic
  established the wire value `false` (the pinned OpenCode source
  agrees). No client/version change across eras is claimed; the
  module must accept the observed value, not coerce it.
- Bounded native-only fix
  `3dde03bf6b7018f6bef2abfe9b0f645a5951a073`: `_validate_tool_declaration`
  now accepts both boolean values for `strict` (existing `true`
  preserved; observed `false` added), still rejects `0`/`1`/
  strings/`null`/omission/unknown fields, and preserves the upstream
  `false` verbatim (no coercion). 106-test focused unit run over the
  directly affected files plus `ruff check` on the changed files pass.
  Secondary-owned fixtures/verifier untouched.
- Historical failed attempts (preserved, labeled; their usage is
  included in the reconciliation below, never reset):
  - attempt 1 (app head `087895cd`): main request rejected
    pre-upstream with 400 `opencode_1193_tool_declaration` (the
    strict-is-True validator; root cause per the confirmed
    diagnostic); title aux settled (1 ledger row 4/2 + 1 finalized
    reservation).
  - retry 1 (app head `3dde03bf`, before the 8192 cap): main request
    rejected with 400 `responses_tool_invalid_shape`, param
    `tools[0].description` (shared default 4096-byte description cap;
    the pinned bash declaration is 5210 B serialized); title aux
    settled.
- Task-scoped description cap: the task Gateway env (0600 file) sets
  `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=8192` explicitly.
  The shared code default (4096) is NOT widened; an operator running
  this module must set the same env var and restart. The loopback
  fake script sha256
  `118ec65e28dbedc686f6154ed7137dd5553a21220d6d5ab2423ea0e7fb51e250`
  was unchanged across the per-case fake restarts.
- SIX actual loopback cases PASSED (root-dispatched one at a time;
  pinned OpenCode 1.19.3; task Gateway on `3dde03bf` with the 8192
  cap; real PG; separate loopback mock; fresh client run-roots under
  task `runs/228c-native-*`; all exit 0, run-local config removed,
  task-key canary clean):
  - `228c-native-baseline-retry2` assistant_tool baseline (6.732 s):
    9/9 case predicates; final 40 B byte-exact marker; read tool
    completed; upstream 3 POSTs (auto-title aux + 2 mains); both
    mains carried 9/9 `strict: false` preserved verbatim, max
    description 4699 B; reused baseline key (no reset).
  - `228c-native-reasoning` encrypted reasoning continuation
    (6.379 s): 6/6 cipher+linkage predicates; issued cipher 64 B
    (sha8 `28b052fa`); full-byte encrypted replay equal to the issued
    ciphertext; final 32 B byte-exact static sentinel.
  - `228c-native-visible-absent` (6.43 s) /
    `228c-native-visible-null` (6.38 s) /
    `228c-native-visible-empty` (6.732 s): 8/8 each; reasoning
    encrypted_content transitions absent→absent, null→null,
    empty→empty_string (kept verbatim); 40 B byte-exact markers; NO
    opaque references issued for the visible states.
  - `228c-native-compaction` (6.681 s): 10/10; upstream 4 POSTs (2
    aux); summary request exactly 7 top-level fields (stream true, no
    tools); 164 B summary; continuation restored the 9 tools with 4
    typeless items `[developer, user, assistant, user]` carrying the
    byte-exact summary; 33 B byte-exact static sentinel; synthetic
    overflow usage 225000/2000.
- Root independent reconciliation (authoritative PG; the agent did
  not re-query): 21 successful finalized ledger rows / 21 finalized
  reservations; 225,694 input + 2,304 output = 227,998 tokens,
  EUR 0.227998 (task pricing EUR 1/M input and output,
  `slaif_calculated`, not a provider invoice); 0 reserved, 0
  diagnostics, 0 non-finalized rows; 8 `codex_replay_references` =
  6 function_call + 2 reasoning (each an ID reference plus the
  selected-profile v3 ciphertext alias), all mock route; 0
  `response_references`; in all six fake journals the upstream
  Authorization hash matches the server MOCK secret, differs per
  gateway key, and every full gateway key is absent. POST counts:
  compaction 4, the other five cases 3 each, plus 2 historical failed
  title aux = 21. Per-key final counters: baseline 5/6 requests
  (104 tokens), reasoning 3/6 (62), each visible case 3/6 (92 each),
  compaction 4/6 (227,556).
- Protected LAN launch: partially executed — LAN1 (root-dispatched)
  failed at the task Gateway validator (demonstrated missing
  `output_index` transport defect; 9 failed ledger rows / 9 released
  reservations; zero settled usage; provider usage unknown, not
  zero); one root-executed HTTP diagnostic probe (1.406 s) confirmed
  the first rejection structure (+1 failed row / +1 released
  reservation). The bounded wire repair landed at final candidate
  `b6e85b79`; all CI green (three workflow identities / 9 jobs); the
  root-dispatched run 2 retry (`runs/228c-native-lan-2`) TERMINAL
  FAILED at 130.544 s at a later stream event (first repaired gap
  passed; five main attempts failed with the same
  `responses_stream_event_not_supported` code; one auto-title aux
  settled 612 in / 46 out; 47,940 in / 482 out charged as
  estimates; 6/6 key slots consumed; key totals 49,080 tokens / EUR
  0.04908; no replacement, no reset, no cap change). The bounded LAN
  plan remains human-approved; the settled-request extension (6 ->
  12, same key, unchanged remaining budgets) is an asynchronous
  request to the human maintainer — no traffic or quota mutation
  until the explicit reply. Details in the "228-c LAN half" evidence
  subsection.

## Approved bounded live plan (partially executed; run 2 terminal FAIL at a later stream event)

Status: PARTIALLY EXECUTED under this gate. The bounded LAN
qualification is already human-approved ("Approve 100 LAN tests with
built-in retries"); there is no further human decision gate. LAN1
(root-dispatched native tool loop) and one synthetic HTTP diagnostic
probe were executed; both terminated at the task Gateway validator
with zero settled usage (10 failed ledger rows / 10 released
reservations; key 0 used / 0 reserved / 0 fenced; provider usage
unknown, not zero). The demonstrated missing-`output_index` defect is
repaired at final candidate `b6e85b79` with all CI green; the
root-dispatched run 2 retry TERMINAL FAILED at 130.544 s at a later
stream event (no tool; final marker mismatch; one auto-title aux
settled 612 in / 46 out; five charged as estimates 47,940 in /
482 out; 6/6 key slots consumed; key totals 49,080 tokens / EUR
0.04908). No counter reset. The order-item-6 loopback mock half is
complete (six cases, see 228-c checkpoint).

- Limits: ≤100 outer launches (actual prior spend: 5 of the 227-c
  bounded LAN Chat qualification, linked below, not duplicated);
  600 s process / 1200 s total; ≤2,000,000 tokens; ≤EUR 2 total at the
  task pricing EUR 1/M input and output.
- Requests: ≤6 SETTLED/charged requests per key (settled-request
  quota); admitted attempts may exceed 6 under stock native retries,
  and failed admissions can release reservations.
- Retries: stock native retries explicitly allowed; NO zero-retry
  promise (the pinned OpenCode session hardcodes
  `RETRY_MAX_RETRIES=5` with no override parameter).
- Forbidden: no counter reset, no production credential mining, no
  production traffic.
- Actual prior spend (227-reused; linked, failure history preserved):
  5 launches, 41,021 tokens, EUR 0.041021.
- 228-c LAN spend to date (root conservative count): 8 LAN tests (7
  native outer + 1 HTTP diagnostic probe); after run 2,
  293.214 s OpenCode / 851.194 s aggregate wall remaining; after run 2: key PG totals 1 finalized + 5
  estimated + 10 failed ledger rows, 6 finalized + 10 released
  reservations, 49,080 tokens / EUR 0.04908, 0 reserved / 0 fenced;
  all mock and LAN rows preserved; no reset, no key replacement, no
  cap change.
- The strict zero-retry plus six-settled-request admission guarantee
  remains `UNSATISFIED` under this plan; it is recorded as a
  limitation, is NOT a requirement of the approved plan, and is NOT a
  pending human decision (the b-era generic pending-human retry
  wording is corrected here). Never claimed passed.

## Known failures and pending gates

1. Focused OAP governance — RESOLVED at 228-b: 10/10 at the final b
   code head. The a-era 1 failed / 9 passed (activated-order literal
   `NEW_PR` vs validator `CREATE_NEW_PR`) is preserved as immutable
   history; order, tests, and `oap/active` were unchanged in both
   rounds.
2. Order item 6 (228-b/c) — loopback mock half COMPLETE: six pinned
   ACTUAL OpenCode 1.19.3 cases passed through the task-owned Gateway
   (`3dde03bf`) + real PostgreSQL + separate loopback mock upstream
   (no `get_provider_adapter` monkeypatch); root independent PG
   reconciliation: 21 finalized ledger rows / 21 finalized
   reservations, 227,998 tokens, EUR 0.227998, 0 reserved/pending,
   8 replay references (6 function_call + 2 reasoning), credential
   isolation verified in all six journals. Historical failed attempts
   preserved and labeled: attempt 1 (400
   `opencode_1193_tool_declaration`, strict-is-True validator per the
   confirmed diagnostic, head `087895cd`) and
   retry 1 (400 `responses_tool_invalid_shape`, description cap, head
   `3dde03bf` pre-8192); both title aux settled; usage included, no
   reset. Fixes: `3dde03bf` (accept both `strict` boolean values,
   preserved verbatim) + task-scoped
   `RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=8192` (shared
   default 4096 unchanged; operator must set + restart). The
   protected LAN half of item 6 is partially executed: LAN1
   (root-dispatched) failed at the task Gateway validator
   (`response.failed` code
   `responses_stream_event_not_supported`; demonstrated missing
   `output_index`); the bounded wire repair is at final candidate
   `b6e85b79` (all CI green); the root-dispatched run 2 retry
   TERMINAL FAILED at 130.544 s at a later stream event (no tool;
   final marker mismatch; same `responses_stream_event_not_supported`
   code after the repaired first gap; one auto-title aux settled
   612 in / 46 out; five charged as estimates 47,940 in / 482 out;
   6/6 key slots consumed; key totals 49,080 tokens / EUR 0.04908;
   no replacement, no reset, no cap change). LAN1 and the probe
   left zero settled usage (10 failed ledger rows / 10 released
   reservations; key 0 used / 0 reserved; provider usage unknown,
   not zero).
3. Strict zero-retry plus six-settled-request admission guarantee:
   `UNSATISFIED`. Source proof: pinned OpenCode session
   `packages/opencode/src/session/llm.ts` line 323
   `maxRetries = input.retries ?? 0`, `processor.ts` line 674
   unconditional `Effect.retry(SessionRetry.policy)`, `retry.ts` line
   31 `RETRY_MAX_RETRIES = 5` with a hard cap at lines 189–193 and no
   override parameter. The 227-b PG 500 assertion
   (`requests_used_total == 0`) shows `request_limit_total = 6` does
   not cap total admissions across failures. The b-era "human risk
   decision pending" wording is corrected: recorded as a limitation
   (never claimed passed); the human-approved bounded LAN plan
   explicitly allows stock native retries, so this strict variant is
   not a requirement of that plan and not a pending human-decision
   gate.
4. LAN1 (228-c, root-dispatched native LAN tool loop, run root
   `runs/228c-native-lan-1`): 134.178 s / exit 1 / no tool;
   `response.failed` code `responses_stream_event_not_supported`;
   9 failed ledger rows (HTTP 200, accounting failed) + 9 released
   reservations; key 0 used / 0 reserved / 0 fenced; provider usage
   UNKNOWN (not zero). The root-executed HTTP diagnostic probe
   (1.406 s) demonstrated the first rejection structure:
   `response.output_item.added` with top-level `output_index` ABSENT
   (not proof of no later gap). Bounded wire repair landed at
   `b6e85b79` (flag `repair_missing_output_indices` default `False`,
   selected-native pair only, `require_output_indices=True` kept,
   terminal-order guard on both completed and incomplete forms,
   original provider status on the wire, legacy unchanged); the
   root-dispatched run 2 retry TERMINAL FAILED at a later stream
   event (the prepared task-local observer extension will capture
   the exact rejection structure before the next scoped fix).
5. Protected live-qualification gate: final qualification `not_run`
   (LAN1 failed; repair at `b6e85b79` with all CI green; run 2
   TERMINAL FAILED at a later stream event).
6. Final PR-head CI: RESOLVED — all green on candidate `b6e85b79`
   (three workflow identities / 9 jobs: CI `45553132761`, CodeQL
   `45553132702`, Code Quality `45553124958`), verified 2026-11-25
   ~05:45Z.
7. Obligation mapping: AGENTIC-40 machine gate bound in the manifest
   `preprotected_index_repair_gate` block — one `--collect-only` over the
   verified 12-file 582 selection plus the 22-case PG file = 604
   unique node IDs, with node-set list, count, hash, and all-pass
   execution receipts (no duplicated arrays). The live plan is
   partially executed (LAN1 + probe failed at the gateway validator;
   run 2 TERMINAL FAILED at a later stream event).
8. AGENTIC-40 gate: satisfied for the current candidate — 604-node
   machine binding (manifest) plus 9/9 external CI identities. All
   further protected traffic (including diagnostics) requires this
   exact all-green candidate; no exception.
