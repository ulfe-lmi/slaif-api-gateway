# OAP Report — 228-c (completion): pinned native OpenCode 1.19.3 Responses qualification — execution complete

## Status

- Objective: 228-c (`oap/active` = 228-c, sha256 `b0108d082cf3aba601a15c6ef67324b6a3b25697ec8f070f806e382164bf08f2`; order `oap/orders/228-c-opencode-responses-completion.md`, sha256 `1ed339303afe8cd02d65a61430cee6e8d930a53ab69ed35434732d1d0683c0bd`; both unchanged during the round).
- PR: #401 (`AMEND_EXISTING_PR`), branch `oap/228-opencode-responses`, base `main` at `79265a8919a74a71083eded279bfcf79d00cd80a` (verified remote `main` at publication time); `autoMergeRequest` null; the coding agent never merges.
- RESULT: **PASS** — execution COMPLETE: order item 6 (pinned ACTUAL OpenCode 1.19.3 through the task-owned Gateway + real PostgreSQL + separate loopback mock upstream, then the bounded protected LAN half) is fully executed; the remaining delivery (review/merge) is root-owned.
- Native source executed at `28d3fbd98dbf49fa593f16afb7e0f09c63c00019` (app tree `aacd71af485c8ce5aede42e256f5b687a94f4196`); no source/test/DATA/schema/digest change after it — `git diff 28d3fbd9..f9521102 -- app tests oap` is empty. All `28d3fbd9` CI gates passed (root-verified before the LAN4 dispatch: three workflow identities / 9 jobs + CodeQL aggregate success).
- No production certification, release, tag, or security/compliance claim.

## Identification

Implementation head SHA: f9521102502aa427772197527cb49e564fa709dc

- 228-c code commits (native-only, selected pair, legacy validators and digest bytes unchanged): `087895cd478d17a259adb6be1e952ecc2d5f6f21` (no-tools aux/compaction dispatch), `3dde03bf6b7018f6bef2abfe9b0f645a5951a073` (accept both `strict` booleans, preserved verbatim), `b6e85b7930c20cb36f5142aea146fba617867aaf` (missing-`output_index` wire repair), `6f041c83a49f933361c6faa64c832a1bd3213940` (argument-closure client fact + strict-index separation), `28d3fbd98dbf49fa593f16afb7e0f09c63c00019` (create-only empty-placeholder projection).
- Canonical record: `docs/verification/2026-11-23-opencode-responses-preprotected.md` (status PROTECTED_QUALIFIED_DELIVERY_PENDING; full evidence, labeled historical failures, budget metrics).
- Manifest: `docs/verification/2026-11-23-opencode-responses-preprotected.json` (`final_native_qualification` PASS + metrics).
- Dossier: `docs/agentic-clients/opencode-1.19.3-responses-v1.md` (protected-qualified; pin digest `592c5d1baa7aa3a805320411f3f961521ba72b30cc34cafe01cb755ddf69f0ff` unchanged).

## Implementation (three bounded fixes)

1. Pinned native profile with id-less replay semantics (228-a/b core, carried): selected-native streaming lifecycle; encrypted-reasoning v3 alias captured only from a validated id-bearing `response.output_item.done` after finalized usage; visible absent/null/empty states pass with zero opaque references; 7-field stream-true aux/compaction requests; 4 typeless continuations.
2. SSE index repair + argument closure (228-c): `repair_missing_output_indices` (default `False`, selected-native pair only, `require_output_indices = True` kept, ambiguity/conflict/orphan/order-contradiction rejection, terminal-order guard on completed + incomplete forms, original provider status preserved on the wire) and the `allow_function_arguments_done` client fact with strict supplied-index equality; legacy sparse/default paths unchanged.
3. Create-only empty visible-reasoning projection (`28d3fbd9`): ONLY the exact 56-byte id-less placeholder `{"type":"reasoning","summary":[],"encrypted_content":""}` is omitted from the forwarded CREATE body copy and deducted from the create estimate before the ceil; input-token-count denial preserved; compact keeps full bytes; `omit_empty_visible_reasoning` default `False`, `True` only in the OpenCode module; validation/resource/ownership/HMAC remain on the full history.

No schema change, no key migration, no automatic re-pin; profile `id`/`version`/`fixture_sha256` unchanged.

## Results (mock + live; precise limits)

- Mock half (loopback; mock usage is not settlement evidence): six pinned OpenCode 1.19.3 cases PASS through the task-owned Gateway + real PostgreSQL + separate loopback mock (mock-secret auth, route `slaif-228b-mock` / model `opencode228b`): 21 finalized ledger rows + 21 finalized reservations, 227,998 tokens, 8 replay references (6 function_call + 2 reasoning), credential isolation verified in all six journals.
- Live half (bounded: one tool-loop run per dispatch, key caps 6 -> 12 -> 14, token/cost/time ceilings, <=100 outer launches, task pricing EUR 1/M — not a provider invoice): final native LAN4 **PASS** — one actual client, 32.197 s / exit 0; one read completed with matching call-ID and result marker; final 32 B byte-exact raw; 0 errors; run-local config removed; all five auth canaries clean. Settlement: 3 HTTP 200 FINALIZED (825 + 6,959 + 7,088) = 14,872 tokens / EUR 0.014872; exactly one native HMAC read reference (same key/functions/read/provider/model), proven from FINALIZED usage.
- Failed attempts preserved and labeled (details linked in the canonical record's "228-c LAN half" subsections): LAN1 134.178 s gateway-validator failure (missing `output_index`; 10 failed rows, 0 settled) + 1.406 s HTTP diagnostic probe; run 2 130.544 s later-stream-event failure (5 mains charged as estimates + 1 title aux; 6/6 slots); LAN3 upstream provider 400 `item[content] is not an array` (6 failed rows; 2 settled). Provider usage on failed streams is unknown, not zero.
- Key and cleanup (root-owned, audited): final key snapshot 14 total / 13 used / 88,621 tokens / EUR 0.088621, 0 reserved; all 8 synthetic task keys REVOKED with all usage retained; all 50 reservations terminal; Gateway 1421855 / fake 1074660 / PG 33486 stopped (ports 18310/18031/54401 closed); 7 plaintext key files + env snapshots removed; 15,499 owned raw files disposed; 13 sanitized receipts + PG data retained; shared binary and original operator credential source untouched.

## Reused 227 evidence (scope-limited)

- `docs/verification/2026-11-20-hermes-opencode-chat.md`: the 227-c bounded LAN Chat qualification only, that execution only (5 launches, 41,021 tokens, EUR 0.041021), its documented stock-retry exception applied to that execution only. Not relabeled as 228 evidence; nothing in it qualifies this Responses module.

## Claims not made

- No production certification, release, tag, or security/compliance claim; protected-qualified is not released.
- No universal OpenAI/Codex/OpenCode compatibility claim; only the bounded pinned OpenCode 1.19.3 Responses profile.
- Mock-half usage is fake-upstream accounting at task pricing, never provider settlement; live figures are task-pricing, not a provider invoice.
- CI for `f9521102` (docs) and this report commit is PENDING at publication (exact truth, never rewritten); the `28d3fbd9` CI gate was all-green and root-verified before the LAN4 dispatch.
- The strict zero-retry + six-settled-request admission guarantee remains UNSATISFIED (source-proven limitation, recorded — never claimed passed; the approved bounded plan explicitly allowed stock native retries).
- Review, CI, merge, and any release decision remain root's gates; the coding agent never merges.

## Publication

Report publication commit: SELF
- Report commit: report-only, sole parent `f9521102502aa427772197527cb49e564fa709dc`, sole diff this file; pushed and verified as the PR #401 remote head.
- PR #401 marked ready for review with title/body updated to the full final scope, verified via REST after the report push (`autoMergeRequest` null).
- Response: exactly two bytes `OK` on `response.fifo`, once; one detached control waiter armed via the existing `wait-control-and-wake.sh` (`TMUX_PANE=%9`); no second control read before the next wake.
- This report is immutable after publication.
