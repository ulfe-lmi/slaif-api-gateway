# 228-a OpenCode 1.19.3 Responses Module — Preprotected Verification Record

Record finalized 2026-11-24. This filename is dated 2026-11-23 to match
the crosslinks already committed in `docs/responses-compatibility.md`.
All evidence was produced at the tested implementation heads named
below (dual-labeled; the later code commits are re-covered by the
442-test focused regression and the 18-test PG run at the final code
head).

## Status

- Preprotected candidate: `PREPROTECTED_READY`.
- Protected live-qualification gate: `not_run` (this preprotected order
  authorizes no inference or remote setup).
- Real provider inference: `not_run`.
- Known failure pending root ruling: focused OAP governance
  1 failed / 9 passed (activated-order format literal; see below).
- Strict zero-retry plus six-settled-request admission guarantee:
  `UNSATISFIED` (source-verified; the relaxed live plan below requires
  an explicit human risk decision; see Proposed future live plan).
- Final PR-head CI: pending (GitHub, after push; not claimed as pass).
- No production certification, universal compatibility, or security
  certification claim.

## Heads and publication state

- Base main: `5f0f4c34ff13f1d76ae050708a37f387e6988451` (PR 395 merge).
- First tested implementation head:
  `79e27c844e70a54cdf092d53b6aca8bd5bb5004b` (338-test unit matrix plus
  the original 11-test PG run, both below).
- Final code head: `55482cc16b4f40530498040c70e0151433b3a9c1`
  (442-test focused unit regression plus 18-test PG run, both below;
  `ruff check app tests` clean).
- Tree identities at `55482cc16b4f40530498040c70e0151433b3a9c1`:
  `HEAD:app` = `30610d166c7de6a55510774a76af51125f54e044`;
  `HEAD:app/slaif_gateway` = `1c254ceb09b9ebf155102fc15e8d25c1f985b566`.
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
- Accepted secondary cherry-picks (fake-only capture checkpoints):
  local `89e536153f1c9487ef83e6ee9713970bfdd2b13c` from secondary
  `3c61d6c3daa62bccada1f3e7756611ad4e493151` (initial capture);
  local `19b1569de3efbd5a1e8fff7dac0c44ebc97737d3` from secondary
  `569f2f11afdaa7aacd8556c29ee7e3b28505feea` (corrected wire and
  verifier).
- Final publication head: pending — the report's parent is this
  documentation-refresh commit.
- PR: not yet published (one numeric objective = one DRAFT PR); title
  "Add pinned native OpenCode Responses client support".

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

### Focused unit regression at the final code head

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

### Real isolated PostgreSQL integration at the final code head

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
- Synthetic bearer + `127.0.0.1` loopback only; no raw content, IDs,
  or credentials retained.
- The corrected wire proves the pinned SDK consumes a standards-shaped
  stream; SDK tolerance alone is not correct-producer proof.

### Lint

- `ruff check app tests` — clean at the final code head
  `55482cc16b4f40530498040c70e0151433b3a9c1` (root-verified).
- `git diff --check 5f0f4c34ff13f1d76ae050708a37f387e6988451..55482cc16b4f40530498040c70e0151433b3a9c1`
  — clean.

### Focused OAP governance (new activation)

- Result: `1 failed, 9 passed in 0.37s`.
- Failed: `test_initial_round_declares_new_pr_and_one_objective_one_pr`.
- Root cause: activated order line 3 reads `PR mode: NEW_PR`, while the
  validator requires the literal `PR mode: CREATE_NEW_PR` (or its
  backticked form) for `-a` initial rounds.
- Disposition: the activated order, `oap/active`, and the test are
  unchanged (order rule: commit the activated order byte-unchanged; no
  test weakening). Same class as the immutable 227-a order-format
  finding; root owns the canonical 228-b `AMEND_EXISTING_PR` on the
  same PR (227-b precedent).
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider`

### Not run

- Real provider inference: `not_run`.
- Protected live-qualification gate: `not_run`.

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
5. PostgreSQL settlement/replay coverage: 18 tests at the final code
   head, labeled as a native-Gateway + PostgreSQL + mock-upstream
   consumer run at `handle_response_create` (real route gate, strict
   SSE validator, PG settlement and replay references; upstream mocked
   at `get_provider_adapter`).
6. Retry boundary as stated above; the strict zero-retry and
   six-settled-request admission guarantee remains `UNSATISFIED`
   (source-verified; see Known failures and pending gates); the only
   recorded stock-retry exception remains the human-authorized bounded
   227-c LAN Chat qualification, applied to that execution only.

## 227 reuse (labeled, not relabeled)

The 227-c bounded LAN Chat qualification record
(`docs/verification/2026-11-20-hermes-opencode-chat.md`) is reused only
as "227-reused": Chat-only, that execution only, with its documented
stock-retry exception. No 227 evidence is relabeled as a 228 execution,
and nothing in it qualifies this Responses module.

## Proposed future live plan (declared; NOT executed)

Status: protected/`not_run`. This preprotected order authorizes no
inference, no remote setup, and no counter reset; the plan below is a
declaration only, for a later root/human decision.

- Limits: ≤100 outer launches (actual prior spend: 5 of the 227-c
  bounded LAN Chat qualification, linked below, not duplicated);
  600 s process / 1200 s total; ≤2,000,000 tokens; ≤EUR 2 total at the
  task pricing EUR 1/M input and output.
- Requests: ≤6 SETTLED/charged requests per key; admitted attempts may
  exceed 6 under stock native retries.
- Retries: stock native retries explicitly allowed; NO zero-retry
  promise (the pinned OpenCode session hardcodes
  `RETRY_MAX_RETRIES=5` with no override parameter).
- Forbidden: no counter reset, no production credential mining, no
  production traffic.
- Actual prior spend (227-reused; linked, failure history preserved):
  5 launches, 41,021 tokens, EUR 0.041021.
- The strict zero-retry plus six-settled-request admission guarantee
  remains `UNSATISFIED` under this relaxed plan and requires an
  explicit human risk decision before execution.

## Known failures and pending gates

1. Focused OAP governance: 1 failed / 9 passed (activated-order
   literal `NEW_PR` vs validator `CREATE_NEW_PR`); order, tests, and
   `oap/active` unchanged; root owns the canonical 228-b
   `AMEND_EXISTING_PR` on the same PR (227-b precedent).
2. Strict zero-retry plus six-settled-request admission guarantee:
   `UNSATISFIED`. Source proof: pinned OpenCode session
   `packages/opencode/src/session/llm.ts` line 323
   `maxRetries = input.retries ?? 0`, `processor.ts` line 674
   unconditional `Effect.retry(SessionRetry.policy)`, `retry.ts` line
   31 `RETRY_MAX_RETRIES = 5` with a hard cap at lines 189–193 and no
   override parameter. The 227-b PG 500 assertion
   (`requests_used_total == 0`) shows `request_limit_total = 6` does
   not cap total admissions across failures. Human risk decision
   pending; never claimed passed.
3. Protected live-qualification gate: `not_run`.
4. Final PR-head CI: pending (GitHub, after push).
5. Obligation mapping: this record and its manifest are an evidence
   index, not a verified per-obligation node-ID mapping; the proposed
   live plan is declared, not executed.
