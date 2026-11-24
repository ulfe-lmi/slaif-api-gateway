# 228-a OpenCode 1.19.3 Responses Module — Preprotected Verification Record

Record finalized 2026-11-24. This filename is dated 2026-11-23 to match
the crosslinks already committed in `docs/responses-compatibility.md`.
All evidence was produced at the tested implementation head named below.

## Status

- Preprotected candidate: `PREPROTECTED_READY`.
- Protected live-qualification gate: `not_run` (this preprotected order
  authorizes no inference or remote setup).
- Real provider inference: `not_run`.
- Known failure pending root ruling: focused OAP governance
  1 failed / 9 passed (activated-order format literal; see below).
- No production certification, universal compatibility, or security
  certification claim.

## Heads and publication state

- Base main: `5f0f4c34ff13f1d76ae050708a37f387e6988451` (PR 395 merge).
- Tested implementation head: `79e27c844e70a54cdf092d53b6aca8bd5bb5004b` (all evidence below).
- Documentation-only commits after it: `bbaa8c4414e491f84a3fa1da894e1b012b1bfd36` (responses-compatibility),
  `7a2c7234c0f3116ee69c0be902a717a8f1df1cdc` (provider-forwarding-contract), `8c21b68cab899ef61ade40b6b917da4de2bdf949` (accounting), `a7583a50f3bc522c457611f31e273bec4865b27c`
  (security-model), `685fd6503b22df073e0c54e5746ba3f45501cde3` (first-time-operator-guide).
- Branch head at record time: `685fd6503b22df073e0c54e5746ba3f45501cde3` (this record's parent).
- Final publication head: pending — the reviewed secondary
  loopback-capture commit will be cherry-picked before report
  publication.
- PR: not yet published (one numeric objective = one DRAFT PR).

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
  `item_id=None`, bounded ciphertext (non-empty, ≤1,048,576 B) held
  in immediate memory only, persisted only after successful finalized
  output, bound to the same key and the same route/provider/model;
  `allow_idless_encrypted_reasoning` is default `False` in every other
  policy spec; legacy presets and legacy digest bytes are unchanged; no
  schema change.
- Retry boundary: the gateway strict zero-retry rule is gateway policy,
  not a native client guarantee. The pinned OpenCode session hardcodes
  `RETRY_MAX_RETRIES=5` with no override parameter above the SDK default
  `maxRetries = input.retries ?? 0`, so zero native HTTP retries are
  never claimed for this profile.
- No DB migration, no engine upgrade; a pin change is data-only (new
  bytes + digest + re-pin + restart).

## Evidence

### Unit matrix (labeled; mock-upstream only where noted)

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

### Real isolated PostgreSQL integration

- Result: `11 passed in 1.38s`; no side effects beyond the disposable
  database.
- Database: task-owned isolated PostgreSQL 16 on `127.0.0.1:54401`,
  database `slaif228_test` (explicit `TEST_DATABASE_URL` only).
- Command:
  `TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_test PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/integration/test_opencode_1193_responses_postgres.py -q -o addopts= -p no:cacheprovider`
- Warnings: 1 (Alembic `path_separator` deprecation notice only).

### Secondary fake-peer loopback capture (synthetic; labeled)

- Branch `oap/228-opencode-responses-qual`, capture commit
  `3c61d6c3daa62bccada1f3e7756611ad4e493151`.
- `all_pass=true`: text exact sentinel (5.828 s); tool loop correlated
  read with final 38 B exact (5.78 s); reasoning replay
  `equals_issued` 64 B (5.527 s).
- Synthetic bearer + `127.0.0.1` loopback only; no raw content, IDs, or
  credentials retained; run root cleaned.
- State: root capture review in progress; secondary is correcting
  verifier issues in the same order (presence-only correlation, 8-hex
  equality, duplicate output index 0 for reasoning + function). The
  final reviewed SHA is pending; primary cherry-picks only the reviewed
  SHA before report publication. The Gateway is not broadened for
  malformed fake SSE.

### Lint

- `ruff check app tests` — clean at the tested implementation head
  `79e27c84…` (all subsequent commits are documentation-only).

### Focused OAP governance (new activation)

- Result: `1 failed, 9 passed in 0.37s`.
- Failed: `test_initial_round_declares_new_pr_and_one_objective_one_pr`.
- Root cause: activated order line 3 reads `PR mode: NEW_PR`, while the
  validator requires the literal `PR mode: CREATE_NEW_PR` (or its
  backticked form) for `-a` initial rounds.
- Disposition: the activated order, `oap/active`, and the test are
  unchanged (order rule: commit the activated order byte-unchanged; no
  test weakening). Same class as the immutable 227-a order-format
  finding; awaiting root canonical ruling (227-b precedent).
- Command:
  `PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider`

### Not run

- Real provider inference: `not_run`.
- Protected live-qualification gate: `not_run`.

## Findings

1. Streaming gap: progress events carrying `response_id` fail the
   three-layer strict field check. Pending root ruling; no L1/L2/L3
   source change made.
2. Present-but-`null` fixture digest → `client_module_fixture_mismatch`
   (fail closed), distinct from an absent/`null` pin (default module
   unchanged).
3. Streaming-only: `stream: false` → `opencode_1193_field_shape`.
4. Id-less reasoning v3 denial matrix (covered in the unit matrix):
   flag-off default; missing/empty/oversized ciphertext; duplicate
   identical ciphers in one request; id-present reasoning carrying a
   ciphertext; present invalid id; persist + verify same-key/same-route
   immediate continuation; altered/foreign/stale reference and
   route/provider/model mismatch all denied; mixed exact-once replay;
   legacy digest bytes unchanged; v3/v1 domain separation; streaming
   flag variants.
5. Retry boundary as stated above; the only recorded stock-retry
   exception remains the human-authorized bounded 227-c LAN Chat
   qualification, applied to that execution only.

## 227 reuse (labeled, not relabeled)

The 227-c bounded LAN Chat qualification record
(`docs/verification/2026-11-20-hermes-opencode-chat.md`) is reused only
as "227-reused": Chat-only, that execution only, with its documented
stock-retry exception. No 227 evidence is relabeled as a 228 execution,
and nothing in it qualifies this Responses module.

## Known failures and root rulings pending

1. Focused OAP governance: 1 failed / 9 passed (activated-order format
   literal `NEW_PR` vs validator `CREATE_NEW_PR`); order, tests, and
   active pointer unchanged; awaiting root canonical ruling.
2. Streaming gap: `response_id` progress events vs the three-layer
   strict field check; pending root ruling.
3. Secondary loopback capture: verifier corrections in progress in the
   same order; final reviewed SHA pending root integration review.
