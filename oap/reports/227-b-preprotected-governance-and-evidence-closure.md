# OAP Report — 227-b (preprotected): governance continuation, obligation-mapping closure, and evidence economy on PR #395

## Status

**PREPROTECTED_READY** (preprotected candidate, not mergeable).

The implementation is reviewable; all required PREPROTECTED obligations are
satisfied with honest evidence, so `preprotected.missing` is derived as `[]`
in the one obligation manifest. This is NOT a qualification: the protected
live gate remains **`not_run`**, the strict zero-automatic-retry and
≤6-total-admission guarantees remain **UNSATISFIED** per pinned client
source, the human target/risk decision is pending, and the final exact-head CI
gate is PENDING (root's gate). No live traffic, deploy, or merge authority
follows from this report.

## Identification

- Objective PR: https://github.com/ulfe-lmi/slaif-api-gateway/pull/395
  (DRAFT; `autoMergeRequest` null), branch `oap/227-hermes-opencode-chat`,
  base `main` at `0940d8a28f3a413d2a2cc6f4962c0efcafd71e13`.
Implementation head SHA: `16053df020ff1baa52bed39701877e2306319e5e`
(reported implementation), tree `590385bdda1f3020525c21c4d702161d8a9cc97c`.
- Tested implementation head:
  `5c2bacf83578f5a23b6e9700656e8bfd26dc373c`,
  full tree `430aae04aaa2f4dbaf4ff529623d022ff3a09278`,
  `app/slaif_gateway` tree `0ab1e80ad89a6578b17b0bfcaa99fa5e8ccab21e`.
  `git diff 5c2bacf8..16053df0 -- app tests` is empty: every commit after the
  tested head is docs/manifest/report only.
- Pinned profile DATA digests (unchanged): Hermes DATA2
  `c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327`;
  OpenCode DATA1 `2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14`;
  string versions `"2"` / `"1"`; frozen Codex contracts preserved.
- Base ancestry (factual): while this branch was under review, remote `main`
  advanced `0940d8a2` → `4500e16fa0b5f177aa25313c6a72321307b52efc` via merged
  PR #394 (docs only: five Codex image-limit doc files, disjoint from this
  PR's `app`/`tests`). The base remains an ancestor of remote `main`; no
  rebase or merge was performed or is required by 227-b.
- 227-a history: the 227-a report (immutable,
  `oap/reports/227-a-hermes-opencode-chat-preprotected.md`,
  SHA256 `ecc96ca53d4e5975e1632d51d08943f8d8e618b872dcd733f61f91f21e511885`,
  report-only SELF `b87ad897`) was NEEDS_CONTINUATION with three declared
  gaps. 227-b (AMEND_EXISTING_PR, same PR, no second PR) closes all three
  honestly. The 227-a order (SHA256
  `4d24d84bef3b7c7d2f1a4b4f70e380dc84debf95da726c8a922735dcadd0f546`) and
  report are unchanged.

## Gap resolution (227-a → 227-b)

1. **governance:227-a-order-format — RESOLVED.** The activated 227-a order's
   format (title line `# Objective 227-a — …`; prose PR-mode declaration)
   caused `tests/unit/test_oap_governance.py` to report **2 failed / 8
   passed** (EXIT 1) — recorded as the historical 227-a finding, not
   rewritten. Root published the canonical 227-b order (first line
   `# OAP Work Order — 227-b`, standalone `PR mode: AMEND_EXISTING_PR`) and
   set `oap/active` = 227-b (commit `a9539700`), replacing the ACTIVE
   selector legitimately; the archived order and the validator were not
   edited or weakened. Focused unchanged `test_oap_governance.py` against the
   NEW active 227-b state: **10 passed, EXIT 0** — the only test rerun in
   this round; no skips/xfails.
2. **obligation-mapping — RESOLVED.** The ONE existing manifest
   (`docs/verification/2026-11-20-hermes-opencode-chat-obligations.json`) is
   now the required per-obligation mapping: **19 required groups, 140
   unique mapped test-node/fixture/evidence refs**, collection-checked once
   against 606 collected nodes at primary head `902a6e33` (collection only —
   NOT executed, NOT a pass count). The accepted secondary-owned mapping
   commit `c9035be723700605a534360c432156acf06e6097` (sole parent
   `a953970009b85a8024f220f8e5ccecbb40014a1d`, sole file the manifest,
   SHA256 `570680cec209492b08cf995a4483975931b514bd4c84330a126c23436db7bd6d`)
   was cherry-picked by the PRIMARY coding agent as `cf62d28b` after root
   review, with primary-side sync (`16053df0`): governance history renamed to
   `historical_227_a_failed_tests` (current failed list empty), resolution
   text clarified (no app/unit/native rerun; focused new-active-state
   governance DID run 10/10), and the native evidence level labelled as
   native fake-peer loopback + fixture unit evidence for both clients
   (OpenCode real verifier receipt linked).
3. **protected-live-test-plan — RESOLVED as an artifact.** A complete
   concrete PROPOSED protected live qualification plan (topology, numeric
   ceilings, baseline preservation, planned positive, planned assertions,
   stop rules) is recorded in the record + manifest. It is
   **proposed/unconfirmed**: human target authority and protected execution
   remain pending, and drafting the plan does not satisfy actual protected
   authorization/execution. `protected.status` stays **`not_run`**.

## Evidence (reused receipts; exact provenance in the record/manifest)

- **Unit**: 9 affected files → **557 passed, EXIT 0**, Python 3.12, tested at
  literal head `5c2bacf83578f5a23b6e9700656e8bfd26dc373c` (tree
  `430aae04…`, app tree `0ab1e80a…`; NOT current HEAD). The 557 include the
  16 `test_verify_hermes_chat_capture.py` helpers; the independent root 16-node
  check (earlier commit `f9dd35b6`) is OVERLAPPING evidence, not additive —
  never summed to 573. Only the `TestR4ChatBindingRevalidation` held-slot
  cases use fake rate-limiter/quota seams (unit fake-slot proof); the PG
  lifecycle does NOT prove R4 held-slot revalidation or real Redis behavior.
- **PostgreSQL lifecycle** (owned disposable PG16; chronological, OVERLAPPING
  receipts — not summable): operator run 4 includes the first binding case 1;
  runtime run 2 includes the earlier Hermes success 1; streamed successes
  were two separate one-case executions; both HTTP-500 release tests are
  **Hermes-only currently** (declared coverage gap, no OpenCode parameters
  exist); `e645b381` = 2 disconnect profiles + 1 quota-429; `e3e97918`
  hardened and re-executed the SAME 2 disconnect profiles (supersedes the
  older 2 within that batch). Client disconnect after partial output settles
  **estimated** usage (finalization), not reservation release. Does not prove
  real Redis/R4 held-slot behavior.
- **Native loopback** (task-owned 127.0.0.1 fake peer; REUSED, not rerun):
  Hermes `loop7`/`timeout4`/`error3`/`multi1`/`entry-final-positive`;
  OpenCode structural captures plus the accepted native verifier receipt
  (2026-11-20T03:56:22Z, `all_pass=true`, dossier section 3). Fake peer only:
  no gateway admission, no PG settlement, no live provider.
- **Static**: `ruff check app tests` → All checks passed (at the tested
  head); `git diff --check` clean on all 227-b commits.
- **Governance**: canonical 227-b active state → `test_oap_governance.py`
  **10 passed, EXIT 0** (new focused run); reused
  `test_agentic_client_integration_governance.py` +
  `test_provider_governance.py` → **5 passed**.
- **CI**: root verified all 9 individual required jobs + the separate CodeQL
  aggregate SUCCESS at `a9539700`. The final exact-head CI gate (post-JSON
  integration, this head) is **PENDING and root's gate**; pending/skipped/
  missing checks are never labeled pass, and §40/§51 of the contract require
  required external CI checks represented, head-scoped, and green before any
  protected traffic.

## Limitations and honest disclosures

- Both HTTP-500 release tests are Hermes-only currently; OpenCode HTTP-500
  release is a declared coverage gap.
- PG partial-output disconnect proves transport close + estimated
  finalization on the mocked upstream; a client exit does not prove upstream
  cancellation.
- Historical secondary full-unit run (Python 3.13) failed one named
  OpenRouter audio test (`test_v1_chat_completions_forwarding.py::test_openrouter_nonstreaming_audio_input_request_preserves_provider_reported_cost`);
  aggregate counts/causality unknown; no unrelated fix made, no full matrix
  rerun claimed.
- `setupfail1` receipt cleanup is unverified/retained (manual cleanup only).
- **Strict protected ceilings UNSATISFIED as a guarantee** (source-proven,
  NOT passed): Hermes async-aux path hardcodes one same-provider retry and
  `_TIMEOUT_NO_RETRY_TASKS` blips still retry; pinned OpenCode
  `processor.ts:674` applies an unconditional `Effect.retry` with
  `retry.ts:31 RETRY_MAX_RETRIES=5` hard cap and no override parameter. The
  PG 500-release assertions show `requests_used_total==0` — i.e.
  `request_limit_total=6` does NOT cap 6 total admitted attempts across
  failures; the 6-ADMITTED strict proposal is therefore UNSATISFIED. The
  **relaxed** alternative (stock native retries explicitly allowed; **6
  SETTLED/charged requests per key**, admitted attempts may exceed 6;
  1,000,000 accounted tokens; EUR1.00 per profile / EUR2.00 aggregate;
  600s per profile / 1200s aggregate) is recorded as an explicit
  **human risk decision only** — not executed, not waived, no client patch,
  no accounting change, no proxy/budget framework.
- 227-a report source-ownership SHA typo (corrected in the current record,
  immutable report not edited): the secondary Hermes dossier commit is
  `14b4a170983dfac35b34b9bd89585ec3d74fd859` (integrated as `d5e798bf`); the
  accepted contract-doc source `2e50035738af24a0cf4b0dcd9f05e5adf7c9fca0`
  was integrated as `d776b92a`. Source ownership and history preserved; no
  secondary push or PR.
- Quota/accounting/Redis foundations unchanged versus base `0940d8a2`; the
  changed services are auth, Chat orchestration/request-caps/request-policy,
  key policy, and key service.
- The protected plan is a proposal from pinned historical reports, not
  current remote health, credential, route-capability, or deployed-version
  evidence; fresh target/contract verification and approved provider
  credentials are prerequisites AFTER separate human authorization.

## Protected gate

`protected.status` = **`not_run`**. No live inference, key mutation,
deployment, production key binding, or real-client launch is recorded or
authorized by 227-b. The proposed plan, the strict-ceiling UNSATISFIED
finding, the relaxed-alternative human decision, and the pending exact-head CI
gate are all separately visible in the record and manifest. Review, CI, and
merge remain root's gates; the coding agent never merges.

## Publication

Report publication commit: SELF (sole parent
  `16053df020ff1baa52bed39701877e2306319e5e`, sole diff this file).
- Remote PR #395 head verified = this report commit; DRAFT; no auto-merge.
- Immutables preserved: 227-a order SHA256 `4d24d84b…f546`; 227-a report
  SHA256 `ecc96ca53d4e5975e1632d51d08943f8d8e618b872dcd733f61f91f21e511885`; 227-b order SHA256 `8e6dc2da…90`; `oap/active`
  SHA256 `bd7995df…9e`; accepted secondary manifest commit `c9035be7` bytes SHA256
  `570680cec209492b08cf995a4483975931b514bd4c84330a126c23436db7bd6d`
  (source bytes as cherry-picked, BEFORE primary sync in `16053df0`; the
  current in-branch JSON hash differs by the three primary-side sync fields).
- Response: exactly two bytes `OK` on `response.fifo`, once; control wake
  armed to the coding pane directly.
