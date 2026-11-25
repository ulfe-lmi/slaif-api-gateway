# OAP Report — 228-b (preprotected completion): pinned native OpenCode Responses client support

## Status

- Objective: 228-b (`oap/active` = 228-b; root-authored activation committed byte-unchanged to this branch in `3d431b175ae3554a4cab5f43b37064af23bc3e01`).
- PR: #401 (DRAFT, `AMEND_EXISTING_PR`, head branch `oap/228-opencode-responses`, base `main` at `5f0f4c34ff13f1d76ae050708a37f387e6988451`, `autoMergeRequest` null). The coding agent never merges.
- RESULT: **NEEDS_CONTINUATION** (honest incomplete).
- The 228-b completion order's item 6 — the pinned ACTUAL OpenCode 1.19.3 binary through the task-owned Gateway + real PostgreSQL + separate loopback mock upstream (no `get_provider_adapter` monkeypatch) — is staged and awaits root dispatch (`not_run`); the protected live-qualification gate and real-provider inference are `not_run`; final PR-head CI is pending; and the strict zero-retry + six-settled-request admission guarantee is UNSATISFIED pending an explicit human risk decision.
- The 228-a candidate label `PREPROTECTED_READY` (candidate reviewable) is superseded by this b-refresh; it never meant "qualified". The a-era focused OAP governance failure (1 failed / 9 passed; root order-authoring literal `NEW_PR` vs `CREATE_NEW_PR`) is resolved at 228-b (10 passed at the final b code head) and preserved as immutable history.
- No production certification, release, tag, or protected/live claim is made in this report or the manifest.

## Identification

- Objective PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/401 (DRAFT; `autoMergeRequest` null), branch `oap/228-opencode-responses`, base `main` at `5f0f4c34ff13f1d76ae050708a37f387e6988451` (verified to equal remote `main` at publication time).

Implementation head SHA: 124bb1345906ba72b9f5bf13109169710422e13c

(final publication head: the documentation-refresh commit that parents this report)
- 228-a final code head: `55482cc16b4f40530498040c70e0151433b3a9c1` (442-test focused unit regression + 18-test PG run; ruff clean).
- Final 228-b code head: `c5d007fb272d0103d9f9a396547e237334987409` (467-test focused unit regression + 20-test PG run + 10-pass governance; ruff clean). `c5d007fb` is test-only on top of `d896ad91`, so the app code is byte-identical to the running task Gateway.
- `git diff c5d007fb272d0103d9f9a396547e237334987409..124bb1345906ba72b9f5bf13109169710422e13c -- app tests` is empty: the publication commit is docs only.
- Tree IDs at the publication head (different scopes, reported separately): `HEAD:app` = `a857667b3ca7752170256b4dab7c39f4ae1b1213`; `HEAD:app/slaif_gateway` = `4f26abb76184df2a74a97fa37290f66f36708083` (equal to the final code head's tree IDs; docs-only delta).
- Code commits after the 228-a final code head (re-covered by the final 228-b code head's runs): `2b6e7e48ca2fde938e3d0f167fb506fe6201c6af`, `cb936fbd2e22da532532c844d0596c70b3d59e1f`, `fb6a521019da5ec74cab8990b77651802aa0bf0d`, `ce476f3b6ea30ae24d95fd10628929ad065ab7ae`, `49d55a9dc81bfffbf370c63f6fd0ba03b8f3c2f6`, `ea561ac96bfb57a59acf01ea3df0ec3129b844f1`, `e6687613af90fc4edc34253e2b6a264c916032d7`, `d896ad91f5de1c34bdfb753fedcc51086717fa0b`, `c5d007fb272d0103d9f9a396547e237334987409`.
- Order commit: `3d431b175ae3554a4cab5f43b37064af23bc3e01` (publish and activate the 228-b completion work order).
- 228-b documentation commit: `124bb1345906ba72b9f5bf13109169710422e13c` (consolidated record, manifest, README, dossier).
- Order: `oap/orders/228-b-opencode-responses-preprotected-completion.md` (sha256 `0b7949611f42cc2449b2aa6bcb2271842eda4543395326d4ca87b0c9db531851`, unchanged during the round).
- Active pointer: `oap/active` = 228-b (sha256 `4c6e14cc21e07df19a508a3b2ebb5ab6dcf8e2797dead74c9fd494469d141624`, unchanged during the round).
- Secondary-owned fake-peer capture checkpoints (root-reviewed, cherry-picked by primary; fake-only, never a Gateway/provider pass):
  - 228-a initial capture: local `89e536153f1c9487ef83e6ee9713970bfdd2b13c` (secondary branch `3c61d6c3daa62bccada1f3e7756611ad4e493151`);
  - 228-a corrected verifier: local `19b1569de3efbd5a1e8fff7dac0c44ebc97737d3` (secondary branch `569f2f11afdaa7aacd8556c29ee7e3b28505feea`; corrected wire shape and required encrypted-replay/call-linkage gate);
  - 228-a fix2 recapture: local `552231f6699427425f2bcdca4d1783554efc2a11` (secondary branch `f3af15335907fc5fe8c2f02705e7df4ad91d424a`; no top-level `response_id`, assistant-text continuation, default auto-title aux-first shape, visible-reasoning states observation-only, executed-artifact provenance);
  - 228-b compaction: local `ca76576019f2021f94890d85be3885d86c544f89` (secondary branch `5a2b7e81b2759f60630e06856a4ee744a0b95a11`; native client-side compaction loopback capture, synthetic trigger).
- Canonical record: `docs/verification/2026-11-23-opencode-responses-preprotected.md`.
- Manifest: `docs/verification/2026-11-23-opencode-responses-preprotected.json` (evidence index, not a verified per-obligation node-ID mapping; status `NEEDS_CONTINUATION`).

## Implementation (order items)

Carried from 228-a (unchanged): pinned native OpenCode 1.19.3 Responses client support — module + selected-profile DATA (packaged, canonical-JSON digest `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff`) + registry entry; fail-closed client-module pin; streaming-only surface; qualified `openai` / `openai-compatible` candidate pairs for this profile only; no impersonation of Codex (neutral reuse of Codex-developed validation, replay ownership, transport, and PostgreSQL accounting; legacy profiles and digest bytes unchanged); encrypted reasoning v3 reference captured only from a validated id-bearing `response.output_item.done` after successful finalized usage without altering or emitting IDs, without rewriting the emitted event, and without storing ciphertext; L1/L3 streaming rulings (native typed MESSAGE/REASONING lifecycle independent of non-empty tool count; exact `(functions,name,function)` active-set gate for new tool execution; L2 not implemented); removed-tool history replayed through the existing same-key/kind/call/name HMAC without unioning history into active tools; no DB migration.

Added at 228-b (selected native profile only; legacy validators and digest bytes unchanged):

- Provider reasoning IDs: `response.output_item.added`/`done` for reasoning must carry the actual provider IDs (the captured upstream issues them; only the pinned SDK's request-side replay drops the ID), so an id-less reasoning `done` is rejected whenever encrypted-replay is on; id-less reasoning INPUT eligibility remains a separate, still-granted fact.
- v3 ciphertext alias: capture and issuance are gated to this selected native profile only (the legacy single-ID-reference behavior is preserved for all other profiles).
- Visible reasoning lifecycle: absent/null/empty `encrypted_content` output states pass with ZERO references (no opaque alias; empty string kept verbatim; omitted summary accepted as `[]`, explicit `null` denied).
- `response.reasoning_summary_part.done` closure event: accepted only on this profile (legacy default denial; baseline 5f had no such handler).
- Orphan `done` events without a preceding `added` are rejected under the required output indexes (legacy sparse paths preserved).
- Auto-title and compaction summary requests: exactly 7 top-level fields (`include, input, max_output_tokens, model, reasoning, store, stream`), `stream: true` only, no `tools`/`tool_choice`, input a list; continuations after assistant text or compaction are 4 typeless items `[developer, user, assistant, user]` with the byte-exact summary in the assistant slot. Correction note: the 228-b order prose described the auto-title request as non-streaming; the captured receipt (`report-fix2`, `gates.defaulttitle.aux_request_facts.stream=true`) outranks that prose; no non-streaming obligation is invented and the selected profile remains fail-closed on `stream: false`.
- Factory-adapter settlement: the 2 new PostgreSQL cases (`openai-native`, `openai-compatible`) leave `gateway.get_provider_adapter` UNPATCHED — the real factory selects the real registered adapter and real httpx is intercepted by `respx` at loopback.
- No DB migration, no new framework, no production deploy/key/route/budget changes in this order.

## Proven results (exact commands; no reruns this round)

228-a runs (preserved as history):

Unit matrix at first tested implementation head `79e27c844e70a54cdf092d53b6aca8bd5bb5004b` — **338 passed in 5.29s** (6 files; mock-upstream coverage only in `tests/unit/test_responses_codex_streaming_tools.py`):

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_codex_replay_idless_reasoning.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_codex_replay_service.py -q -o addopts= -p no:cacheprovider
```

Focused unit regression at 228-a final code head `55482cc16b4f40530498040c70e0151433b3a9c1` — **442 passed in 5.81s** (7 files; separate set from the 338 matrix, 3 files shared, never summed):

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_opencode_lifecycle.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_opencode_1193_responses.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_replay_delivery.py -q -o addopts= -p no:cacheprovider
```

Real isolated PostgreSQL consumer run at 228-a final code head `55482cc1` — **18 passed in 3.27s** (11 pre-existing + 7 new; upstream mocked at `get_provider_adapter`):

```
TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_test PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/integration/test_opencode_1193_responses_postgres.py -q -o addopts= -p no:cacheprovider
```

Focused OAP governance on the 228-a activated order — **1 failed, 9 passed**: the order literal `NEW_PR` vs the validator `CREATE_NEW_PR` (root order-authoring error; order, `oap/active`, and test byte-unchanged; no test weakening). Preserved as immutable history.

228-b runs at final code head `c5d007fb272d0103d9f9a396547e237334987409`:

Same 7-file focused unit set re-executed — **467 passed in 6.00s** (supersedes the 442 count for that set; overlap with the 338-test matrix separate; never summed):

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_opencode_lifecycle.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_opencode_1193_responses.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_replay_delivery.py -q -o addopts= -p no:cacheprovider
```

Real isolated PostgreSQL — **20 passed in 4.00s** (the 18 above + 2 new parameterized cases, `openai-native` and `openai-compatible`, with `gateway.get_provider_adapter` UNPATCHED; respx loopback interception; no side effects beyond the disposable database):

```
TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_test PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/integration/test_opencode_1193_responses_postgres.py -q -o addopts= -p no:cacheprovider
```

New PG coverage facts: 2 POSTs per case, public-to-upstream model substitution, `stream is True`, Bearer-only credential, no HMAC secret / token hash / provider value in the upstream body; PG settlement asserted: 11 requests, 12,359 tokens, reserved 0/0, `cost_used_eur == Decimal("7.250052")`, 3 replay references (incl. the function-call binding), 2 finalized ledger + reservation rows.

Focused OAP governance on the canonical 228-b `AMEND_EXISTING_PR` order — **10 passed** (governance gap resolved at b; no test changes in either round):

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider
```

Lint: `ruff check app tests` clean at 228-a final code head `55482cc1` (root-verified) and re-run clean at the final 228-b code head `c5d007fb`; `git diff --check 5f0f4c34ff13f1d76ae050708a37f387e6988451..c5d007fb272d0103d9f9a396547e237334987409` and `git diff --check` at the documentation commit both clean.

Secondary fake-peer loopback checkpoints (fake-only; synthetic bearer + 127.0.0.1 loopback only; no raw content/IDs/credentials retained; NOT a Gateway/provider pass): corrected receipt `all_pass=true` at secondary source `569f2f11` (finished 2026-11-23T12:04:07Z); fix2 eight-probe recapture `all_pass=true` (receipt `/home/janezp/codex-work/slaif-228-task/report-fix2.json`, finished 2026-11-24T01:07:42Z); 228-b nine-probe compaction superset run 9/9 gates (finished 2026-11-24T09:59:04Z; the compaction positive is a synthetic-trigger fake-only client observation, not Gateway/provider compaction support). SDK tolerance is not correct-producer proof.

Task-owned native setup for order item 6 (staged; run `not_run`): task-owned PostgreSQL 16 on `127.0.0.1:54401` (`slaif228_test`, trust, loopback only); task-owned Gateway at `http://127.0.0.1:18310/v1` on code `d896ad91` (app code byte-identical to the final b code head); separate loopback mock upstream at `127.0.0.1:18031` reusing the existing `scripts/verify_agent_chat/loopback_responses_fake.py` (no second SSE producer); `REQUEST_CAPTURE_ENABLED=false`; route `slaif-228b-mock`, model `opencode228b` to `opencode228b-upstream`, streaming, all four codex capabilities on, `provider_max_retries=0`, EUR 1/M input and output pricing, `codex_limits` 1,050,000 / 32,768 / 128,000; preflight verified wrong key 401, models 403 `endpoint_not_allowed`, minimal body 400 `opencode_1193_fields`, wrong model 403, and PG counters 0 admitted / 0 reserved / 0 used (no admission). Task-local nonsecret setup record (not committed): `/home/janezp/codex-work/slaif-228-task/native/setup-228b-record.json`.

## Known gaps (preprotected qualification incomplete)

1. Order item 6: pinned ACTUAL OpenCode 1.19.3 binary through the task-owned Gateway + real PostgreSQL + separate loopback mock upstream (no `get_provider_adapter` monkeypatch) — setup staged and verified, run `not_run` (awaits root dispatch).
2. Protected live-qualification gate `not_run` (this order authorizes no protected execution; real provider inference `not_run`).
3. Final PR-head CI pending (GitHub, after push).
4. Obligation mapping: the record + manifest are an evidence index, not a verified per-obligation node-ID mapping.
5. Live plan declared, not executed; the strict zero-retry + six-settled-request admission guarantee is UNSATISFIED and pending an explicit human risk decision.

## Strict zero-retry + six-settled-request admission guarantee

Status: **UNSATISFIED** (never claimed passed).

- Source proof (pinned OpenCode session `e3c4eb242585dcd77be1a867391b7c25fd47ce52`): `packages/opencode/src/session/llm.ts:323` `maxRetries=input.retries??0`; `processor.ts:674` unconditional `Effect.retry(SessionRetry.policy)`; `retry.ts:31` `RETRY_MAX_RETRIES=5`, hard cap at 189-193, no override parameter. Zero native HTTP retries therefore cannot be promised.
- Admission proof: the 227-b PG 500 assertion (`requests_used_total==0`) shows `request_limit_total=6` does not cap total admissions across failures.
- Gateway zero-retry is gateway policy only (single-attempt forwarding); it does not extend to the pinned native client.
- Disposition: the relaxed live plan below is declared, not executed; an explicit human risk decision is required before any live qualification; the strict guarantees remain unsatisfied until proven.

## Live plan (declared, not executed)

- State: `declared_not_executed`. No launch, inference, or remote setup occurred under 228-b.
- Limits: ≤100 outer launches (actual prior spend 5, from the linked 227-c execution only); 600s per process / 1200s total; ≤2,000,000 tokens; ≤EUR 2 total at EUR 1/M input and output; ≤6 SETTLED/charged requests per key (admitted attempts may exceed 6 under stock retries).
- Retry policy: stock native retries explicitly allowed; no zero-retry promise (`RETRY_MAX_RETRIES=5` hardcoded).
- Forbidden: counter reset, production credential mining, production traffic.
- This is a relaxed guarantee, not the strict zero-retry / six-settled plan; executing it requires explicit human approval.

## Reused 227 evidence (scope-limited)

- `docs/verification/2026-11-20-hermes-opencode-chat.md`: 227-c bounded LAN Chat qualification only, that execution only, with its documented stock-retry exception (5 launches, 41,021 tokens, EUR 0.041021). Not relabeled as 228 evidence.

## Claims not made

- No production certification, release, tag, or security/compliance claim.
- No universal OpenAI/Codex/OpenCode compatibility claim; only the bounded pinned OpenCode 1.19.3 Responses profile described above.
- No protected-gate pass, no real-provider result, no live qualification of any kind; order item 6 is staged and `not_run`.
- Final PR-head CI pending (GitHub, after push); obligation mapping is an evidence index only.
- Fake-peer/loopback receipts are fake-only conformance checkpoints, never Gateway/provider passes; overlapping unit sets (338/442/467 share 3 files) are never summed.

## Protected gate

`protected_gate` = **`not_run`**; `real_provider` = **`not_run`**. No live inference, key mutation, deployment, production key binding, or real-client launch is recorded or authorized by 228-b. The strict-guarantee UNSATISFIED finding, the declared-not-executed relaxed plan, and the pending human risk decision are all separately visible in the record and manifest. Review, CI, merge, and any protected/live decision remain root's gates; the coding agent never merges.

## Publication

Report publication commit: SELF
- Report commit: report-only, sole parent `124bb1345906ba72b9f5bf13109169710422e13c`, sole diff this file; pushed as the PR #401 head.
- Remote PR #401 verified via REST after push: head = report commit; DRAFT; base `main`; `autoMergeRequest` null.
- Response: exactly two bytes `OK` on `response.fifo`, once (logged with byte dump); one detached control waiter armed to the coding pane; no second control read before the next wake.
- This report remains immutable after publication; the strict zero-retry / six-settled decision, the item-6 dispatch, and any protected/live execution remain root/human gates.
