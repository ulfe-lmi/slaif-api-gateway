# OAP Report — 228-a (preprotected): pinned native OpenCode Responses client support

## Status

- Objective: 228-a (`oap/active` = 228-a; root-authored activation committed byte-unchanged to this branch).
- PR: #401 (DRAFT, `CREATE_NEW_PR`, head branch `oap/228-opencode-responses`, base `main`, `autoMergeRequest` null). The coding agent never merges.
- RESULT: **NEEDS_CONTINUATION**.
- The implementation is reviewable; preprotected qualification remains incomplete. The record/manifest status `PREPROTECTED_READY` means the candidate is reviewable, not qualified: the protected live-qualification gate and real-provider inference are `not_run`, the focused OAP governance run is 1 failed / 9 passed (root order-authoring error; root owns canonical 228-b on the same PR), final PR-head CI is pending, and the strict zero-retry + six-settled-request admission guarantee is UNSATISFIED pending an explicit human risk decision.
- No production certification, release, tag, or protected/live claim is made in this report or the manifest.

## Identification

- Objective PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/401 (DRAFT; `autoMergeRequest` null), branch `oap/228-opencode-responses`, base `main` at `5f0f4c34ff13f1d76ae050708a37f387e6988451` (PR #395 merge; actual-main gates independently verified SUCCESS on 2026-11-23 per the activation record).

Implementation head SHA: 76e773140a88e1b658fffc12885b437ab8c8cf2f

(final publication head: documentation-refresh commit that parents this report)
- First tested implementation head: `79e27c844e70a54cdf092d53b6aca8bd5bb5004b` (338-test unit matrix + original 11-test PG run).
- Final code head: `55482cc16b4f40530498040c70e0151433b3a9c1` (442-test focused unit regression + 18-test PG run; ruff clean).
- `git diff 55482cc1..76e77314 -- app tests` is empty: every commit after the final code head is docs only.
- Tree IDs at the publication head (different scopes, reported separately): `HEAD:app` = `30610d166c7de6a55510774a76af51125f54e044`; `HEAD:app/slaif_gateway` = `1c254ceb09b9ebf155102fc15e8d25c1f985b566`.
- Code commits after the first tested head (re-covered by the final code head's runs): `8106929b5545611e3d3200606bca86b61800fc02`, `488c5776eeac3dfec1ecd8469e9b20af3ec803db`, `a146d1d5e78d71c151695cc87b72afa1595ff4a4`, `ae38ec9e1e7bdec706064ba761c5c8bb8bd0f5c4`, `55482cc16b4f40530498040c70e0151433b3a9c1`.
- Documentation commits: `bbaa8c4414e491f84a3fa1da894e1b012b1bfd36`, `7a2c7234c0f3116ee69c0be902a717a8f1df1cdc`, `8c21b68cab899ef61ade40b6b917da4de2bdf949`, `a7583a50f3bc522c457611f31e273bec4865b27c`, `685fd6503b22df073e0c54e5746ba3f45501cde3`, `cd591ee7cd51373e7b353888c38500f0f6002f96`.
- Order: `oap/orders/228-a-opencode-responses-preprotected.md` (sha256 `63e47ae1ededf2394629dc6d2bcf0c9030484c43a8fcc260782baf7852243052`, unchanged during the round).
- Active pointer: `oap/active` = 228-a (sha256 `d16a8030581139d5876cc44a9a1888ba0029bd9b7dcb95e55f11518ef78881e6`, unchanged during the round).
- Secondary-owned fake-peer capture checkpoints (root-reviewed, cherry-picked by primary; fake-only, never a Gateway/provider pass):
  - initial capture: local `89e536153f1c9487ef83e6ee9713970bfdd2b13c` (secondary branch `3c61d6c3daa62bccada1f3e7756611ad4e493151`);
  - corrected verifier: local `19b1569de3efbd5a1e8fff7dac0c44ebc97737d3` (secondary branch `569f2f11afdaa7aacd8556c29ee7e3b28505feea`; corrected wire shape and required encrypted-replay/call-linkage gate).
- Canonical record: `docs/verification/2026-11-23-opencode-responses-preprotected.md`.
- Manifest: `docs/verification/2026-11-23-opencode-responses-preprotected.json` (evidence index, not a verified per-obligation node-ID mapping).

## Implementation (order items)

- Pinned native OpenCode 1.19.3 Responses client support: module + selected-profile DATA + registry entry; fail-closed client-module pin (present-but-null fixture digest -> `client_module_fixture_mismatch`); streaming-only surface (`stream=false` -> `opencode_1193_field_shape`); qualified `openai` / `openai-compatible` candidate pairs for this profile only.
- No impersonation of Codex: neutral Codex-developed validation, replay ownership, transport, and PostgreSQL accounting are reused; the OpenCode selected profile is a separate profile with its own DATA and gates; legacy profiles and digest bytes unchanged.
- Encrypted reasoning v3 reference: the profile-qualified ciphertext alias is captured only from a validated id-bearing `response.output_item.done` after successful finalized usage, alongside the existing ID reference, without altering or emitting IDs, without rewriting the emitted event, and without storing ciphertext; id-bearing reasoning inputs are rejected in the native flat form (`opencode_1193_input_item`); legacy visible idless behavior unchanged; present-invalid-ID denial preserved.
- Streaming per root rulings: L1/L3 implemented — native typed MESSAGE/REASONING lifecycle dispatched independently of non-empty tool count; tool-event flag plus exact `(functions,name,function)` active-declaration set gates new tool execution (empty active set means NO new calls); L2 NOT implemented — the fake's `_ev` `response_id` is not client-wire authority and shared strict `_only_fields` was not relaxed; pinned-SDK required output/content indexes enforced on the selected profile.
- Removed-tool history: bounded flat historical identity is parsed, then the existing same-key/kind/call/name HMAC is proven even when the tool is removed from current declarations; history is never unioned into active tools.
- PostgreSQL settlement and replay: real isolated-PG consumer-run scope at `handle_response_create` (real route-capability gate, real strict SSE validator, real PG settlement + replay references; upstream mocked at `get_provider_adapter`); failed stream -> estimated finalization with 0 references.
- No DB migration, no new framework, no production deploy/key/route/budget changes in this order.

## Proven results (exact commands; no reruns this round)

Unit matrix at first tested implementation head `79e27c84` — **338 passed in 5.29s** (6 files):

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_codex_replay_idless_reasoning.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_codex_replay_service.py -q -o addopts= -p no:cacheprovider
```

Focused unit regression at final code head `55482cc1` — **442 passed in 5.81s** (7 files; separate set from the 338 matrix, 3 files shared, never summed):

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_responses_codex_streaming_opencode_lifecycle.py tests/unit/test_responses_codex_streaming_idless_reasoning.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_opencode_1193_responses.py tests/unit/test_opencode_1193_responses_module.py tests/unit/test_responses_replay_delivery.py -q -o addopts= -p no:cacheprovider
```

Real isolated PostgreSQL consumer run at final code head `55482cc1` — **18 passed in 3.27s** (11 pre-existing + 7 new):

```
TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:54401/slaif228_test PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/tmp-228 TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/integration/test_opencode_1193_responses_postgres.py -q -o addopts= -p no:cacheprovider
```

New PG coverage: positive settlement + immediate idless continuation; altered ciphertext -> `responses_codex_replay_reference_not_found`; foreign key -> same 404 code; unknown model -> `model_not_allowed_for_key` with calls == 0; id-bearing reasoning input -> `opencode_1193_input_item`; failed stream -> estimated finalization 513/5/518, 0 refs, reservation finalized 32513; missing replay capability -> `responses_route_capability_not_supported`. Four benign warnings (2 SQLAlchemy `distinct()` notices + 2 pytest-asyncio deprecation notices).

Focused OAP governance on new activation — **1 failed, 9 passed** in 0.37s:

```
PYTHONDONTWRITEBYTECODE=1 TMPDIR=/home/janezp/codex-work/slaif-228-tmp TMP=$TMPDIR TEMP=$TMPDIR .venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -o addopts= -p no:cacheprovider
```

Failed test: `test_initial_round_declares_new_pr_and_one_objective_one_pr`. Root cause: the activated order line `PR mode: NEW_PR` does not match the validator literal `PR mode: CREATE_NEW_PR` required for `-a` initial rounds — a root order-authoring error (227-a/227-b precedent). The activated order, `oap/active`, and the test are byte-unchanged; no test was weakened. Root owns canonical **228-b AMEND_EXISTING_PR** on the same PR #401 to resolve the governance format.

Lint: ruff clean at final code head `55482cc1` (root-verified); `git diff --check` clean across the branch diff and at the documentation commit.

Secondary fake-peer loopback checkpoint (fake-only; synthetic bearer + 127.0.0.1 loopback only; no raw content/IDs/credentials retained): corrected receipt `all_pass=true` at secondary source `569f2f11` (finished 2026-11-23T12:04:07Z): text 5.978s / 1 req; tool loop 5.53s / 2 req, 1/1 correlated tool result, final 38B exact marker; reasoning 5.578s / 2 req, 5-item continuation, `encrypted_replay_verified=true`, `call_linkage_exact=true`. This is a fake-peer conformance checkpoint of the pinned SDK consuming a standards-shaped stream; it is **NOT** a Gateway or provider pass, and SDK tolerance is not correct-producer proof.

## Known gaps (preprotected qualification incomplete)

1. governance 1/10 (order literal NEW_PR vs validator CREATE_NEW_PR); root owns canonical 228-b AMEND_EXISTING_PR on the same PR.
2. protected live-qualification gate not_run (this order authorizes no inference or remote setup).
3. final PR-head CI pending (GitHub, after push).
4. obligation mapping: record + manifest are an evidence index, not a verified per-obligation node-ID mapping.
5. live plan declared not executed; strict zero-retry + six-settled-request admission guarantee pending explicit human risk decision.

## Strict zero-retry + six-settled-request admission guarantee

Status: **UNSATISFIED** (never claimed passed).

- Source proof (pinned OpenCode session `e3c4eb242585dcd77be1a867391b7c25fd47ce52`): `packages/opencode/src/session/llm.ts:323` `maxRetries=input.retries??0`; `processor.ts:674` unconditional `Effect.retry(SessionRetry.policy)`; `retry.ts:31` `RETRY_MAX_RETRIES=5`, hard cap at 189-193, no override parameter. Zero native HTTP retries therefore cannot be promised.
- Admission proof: the 227-b PG 500 assertion (`requests_used_total==0`) shows `request_limit_total=6` does not cap total admissions across failures.
- Gateway zero-retry is gateway policy only (single-attempt forwarding); it does not extend to the pinned native client.
- Disposition: the relaxed live plan below is declared, not executed; an explicit human risk decision is required before any live qualification; the strict guarantees remain unsatisfied until proven.

## Live plan (declared, not executed)

- State: `declared_not_executed`. No launch, inference, or remote setup occurred under 228-a.
- Limits: ≤100 outer launches (actual prior spend 5, from the linked 227-c execution only); 600s per process / 1200s total; ≤2,000,000 tokens; ≤EUR 2 total at EUR 1/M input and output; ≤6 SETTLED/charged requests per key (admitted attempts may exceed 6 under stock retries).
- Retry policy: stock native retries explicitly allowed; no zero-retry promise (`RETRY_MAX_RETRIES=5` hardcoded).
- Forbidden: counter reset, production credential mining, production traffic.
- This is a relaxed guarantee, not the strict zero-retry / six-settled plan; executing it requires explicit human approval.

## Reused 227 evidence (scope-limited)

- `docs/verification/2026-11-20-hermes-opencode-chat.md`: 227-c bounded LAN Chat qualification only, that execution only, with its documented stock-retry exception (5 launches, 41,021 tokens, EUR 0.041021). Not relabeled as 228 evidence.

## Claims not made

- No production certification, release, tag, or security/compliance claim.
- No universal OpenAI/Codex/OpenCode compatibility claim; only the bounded pinned OpenCode 1.19.3 Responses profile described above.
- No protected-gate pass, no real-provider result, no live qualification of any kind.
- Final PR-head CI pending (GitHub, after push); obligation mapping is an evidence index only.
- Fake-peer/loopback receipts are fake-only conformance checkpoints, never Gateway/provider passes.

## Protected gate

`protected_gate` = **`not_run`**; `real_provider` = **`not_run`**. No live inference, key mutation, deployment, production key binding, or real-client launch is recorded or authorized by 228-a. The strict-guarantee UNSATISFIED finding, the declared-not-executed relaxed plan, and the pending human risk decision are all separately visible in the record and manifest. Review, CI, merge, and any protected/live decision remain root's gates; the coding agent never merges.

## Publication

Report publication commit: SELF
- Report commit: report-only, sole parent `76e773140a88e1b658fffc12885b437ab8c8cf2f`, sole diff this file; pushed as the PR #401 head.
- Remote PR #401 verified via REST after push: head = report commit; DRAFT; base `main`; `autoMergeRequest` null.
- Response: exactly two bytes `OK` on `response.fifo`, once (logged with byte dump); one detached control waiter armed to the coding pane; no second control read before the next wake.
- 228-b (root-owned, AMEND_EXISTING_PR, same PR #401) will resolve the governance format and finish the declared artifact gaps; this report remains immutable.
