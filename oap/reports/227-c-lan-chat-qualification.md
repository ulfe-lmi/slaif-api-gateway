# OAP Report — 227-c (live LAN qualification): Hermes + OpenCode native Chat cases on frozen candidate b2a0d950

## Status

- Objective: 227-c (`oap/active` = 227-c, unchanged during the round).
- PR: #395 (DRAFT, AMEND_EXISTING_PR; never merge/auto-merge by the coding agent).
- Result: both required native cases terminal POSITIVE on the frozen root-accepted candidate; ALL historical failures preserved, none relabeled.
- Qualification status: LIVE LAN qualification EXECUTED and qualified within 227-c order caps under the human-approved bounded exception. Implementation is reviewable; remaining gates are root-owned (final exact-head CI recheck on this report commit, review, guarded merge) and PENDING.

## Identification

- Implementation head SHA: c600595315a05bd9e638ec0b09a320794f79dc72
- Implementation tree: f0478b92e6efec03953c5319be908809e92cfa40
- Executable candidate SHA: b2a0d950e122d612594f55ba54e18fe80d2644c7
- Executable candidate tree: f7dd2d382d7aa674ff8f2c8e97911df280b7e6e5
- Executable candidate app tree (app/slaif_gateway): 17a9caadc83aa1603bfef62bc1f43fab59f3a80f
- Executable candidate parents: 4d5597220b14651f4355115c56c491c2174867be (227-c order publish + activate) and 8cb35eb7dd12fb3454915fe334fafa115da6cbfa (merged origin/main).
- Main integration identity: 8cb35eb7dd12fb3454915fe334fafa115da6cbfa (origin/main at candidate time; PRs #392/#393/#396/#397/#398/#399/#400).
- Order: oap/orders/227-c-lan-chat-qualification.md (sha256 1e77d9754e1082d772fbc64247b74f62269c07a35ac7d8a677510e743ba4be81, unchanged during the round).
- Active pointer: oap/active = 227-c (sha256 b91d46f38f58b5e9decda71476f498d9400bc6d5846d3287d6b42f0deea1b7eb, unchanged during the round).
- App-tree note: the candidate app tree (17a9caad...) is NOT byte-identical to the 227-b tested-head app tree (0ab1e80a...); the origin/main merge changed app code (e.g., PR #399). Both identities are recorded in the manifest.
- DATA digests (unchanged): Hermes c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327 (v2); OpenCode 2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14 (v1).

## Gap resolution (227-b -> 227-c)

- 227-b closed the preprotected obligation mapping/plan gaps (19 groups / 140 refs, one collection 606 nodes, collection-only, protected not_run). 227-c executes the protected live LAN qualification itself:
  - The 227-b strict one-process/no-rerun zero-retry/6-admission proposal is retained as the reviewed plan of record but was NOT the executed contract; the executed run used the human-approved bounded exception (up to 100 LAN launches, stock client built-in retries allowed, bounded tests only) with the order ceilings.
  - Diagnosed pre-run config failures (Hermes run1 setup typo before spawn; Hermes run2 fake provider slug in task config) were repaired within the order and recorded as preserved failures; no key/route/cap/model-gate changes.
  - The zero-native-retry and 6-admission strict guarantees remain UNSATISFIED as universal guarantees; they held only in observation (no retries observed) under the human exception. Acceptance of that semantic is a root/human decision item.
- The remaining 227-b declared gap (final exact-head CI gate) stays root-owned: root independently verified all 9 required jobs across the 3 workflow identities + CodeQL aggregate SUCCESS on the exact executable candidate before the first native launch; the final exact-head CI recheck on this report commit is still pending (root gate).

## Evidence (reused receipts; exact provenance in the record/manifest)

Reused (no rerun):
- 557 unit tests passed at 227-b tested head 5c2bacf83578f5a23b6e9700656e8bfd26dc373c (tree 430aae04aaa2f4dbaf4ff529623d022ff3a09278; app tree 0ab1e80ad89a6578b17b0bfcaa99fa5e8ccab21e), including test_verify_hermes_chat_capture.py; root's independent 16-check on that file is OVERLAPPING evidence, never summed (no 573).
- Ruff clean at that head.
- Governance: 10/10 pass for the new active-state order plus 5 other governance files pass (agentic_client_integration_governance, provider_governance, and three others), as recorded in the manifest.
- 227-b obligation collection: 19 groups / 140 refs, one collection 606 nodes, collection-only (no tests executed) at 902a6e33.
- PostgreSQL integration CI receipts 785 pass / 77 skip (historical, prior heads, in the record).
- 227-b CI run IDs 44754446428/44754446541/44754442388 are historical (report head 87d20421).

New in 227-c (focused):
- Candidate CI gate: all 9 required jobs across the 3 workflow identities + separate CodeQL aggregate SUCCESS on exact candidate b2a0d950e122d612594f55ba54e18fe80d2644c7, root independently verified before any native launch.
- Run-3 offline resolver demo proving the single-line config repair (wire bare model qwen38-27b, pool custom:slaif227fake, base URL unchanged).
- PostgreSQL/Redis/gateway-log reconciliation queries after each terminal (ledger rows, reservations/holds/fences, request_diagnostics, Redis dbsize).

Native launch results (PostgreSQL settlement authoritative):
- Hermes (3 admitted): 3x 200 FINALIZED — 5178/76/5254 EUR 0.005254 @09:05:41.99Z; 5346/97/5443 EUR 0.005443 @09:05:44.66Z; 340/438/778 EUR 0.000778 @09:05:55.24Z => 10864 in / 611 out / 11475 total / EUR 0.011475. Client-reported final event 10524/173/10697 (+5253 cache-read) recorded separately; PostgreSQL authoritative.
- OpenCode (4 admitted): all 4 requests 200 FINALIZED; 29546 tokens; EUR 0.029546; zero reservations/holds/fences.
- Aggregate: 41,021 tokens / EUR 0.041021 (ceilings 2,000,000 / EUR 2).
- Positive-case assertions: Hermes run3 and OpenCode run2 both strict raw-byte final == marker (32/32 bytes, no normalization), real local tool read + continuation + final marker equality, zero error events on the passing runs.

## Limitations and honest disclosures

Failures (all preserved, none relabeled):
- Hermes run1: 1.01s setup failure before spawn (driver typo STOUT->STDOUT); exit 1; 0 admitted / 0 reserved.
- Hermes run2: 11.0s; native config carried fake provider slug; wire model "slaif227fake/qwen38-27b" rejected HTTP 403 model_not_allowed_for_key (gateway gate correct); 0 admitted / 0 reserved; proven by native request dump (private).
- OpenCode run1: 20.3s; trailing-newline framing mismatch — final 32B vs marker 33B (terminal 0x0a, marker sha8 9f4bbeb2); strict raw-byte final_equals_marker=FALSE, NOT relabeled pass; its 2 requests were admitted and settled (counted in OpenCode totals).

Unknowns/skips:
- Upstream provider-to-backend hop opaque beyond the gateway-to-provider edge; labeled unverified.
- GET /v1/models with a Chat-only key legitimately 403 (expected; one benign occurrence in the gateway log).
- No partial disconnect occurred; partial-disconnect finalization would be ESTIMATED semantics (limitation, not exercised).
- No new tests were added or rerun for 227-c wording.

Budget (consumed / remaining):
- Outer launches: 5/100 (Hermes 3, OpenCode 2); 95 remaining.
- Wall: Hermes cumulative 42.02s (<=600; 557.98s remaining); OpenCode cumulative 40.658s (<=600; 559.342s remaining); aggregate 82.678s (<=1200; 1117.322s remaining).
- Tokens/cost: 41,021 / EUR 0.041021 (<=2,000,000 / <=EUR 2; 1,958,979 tokens / EUR 1.958979 remaining).
- Settled requests/key: Hermes 3/6 (3 remaining), OpenCode 4/6 (2 remaining).
- Stock retries: authorized by the human bounded exception; none observed.

Docs/security/privacy/accounting/cleanup:
- Docs: 227-c live section added to docs/verification/2026-11-20-hermes-opencode-chat.md; obligations manifest updated in place (one manifest, objective advanced to 227-c with full historical provenance; protected.status = executed).
- Security/privacy: REQUEST_CAPTURE_ENABLED=False throughout; provider credential server-side only; client envs isolated allowlists (task gateway key only); no plaintext sk-slaif- in any artifact or CLI log; private 0600 auth-input files pending final coordinated cleanup (root decision); /tmp inode exhaustion (1048576/1048576) worked around via owned home task runtime root.
- Accounting: all admitted requests 200 FINALIZED; zero pending reservations/holds/fences; Redis dbsize 0; request_diagnostics empty.
- Cleanup: task services (PG/Redis/Gateway) kept alive until coordinated cleanup; worktree clean at b2a0d950 (frozen); no source/test/config changes in this report commit.

## Protected gate

- Protected live test: EXECUTED in 227-c (this report). Plan of record: the reviewed 227-b strict proposal; executed under the human-approved bounded exception instead.
- CI gate before protected traffic: satisfied for candidate b2a0d950e122d612594f55ba54e18fe80d2644c7 (9 jobs / 3 workflow identities + CodeQL aggregate, root-verified before first launch).
- Final gate: root exact-head CI recheck on this report commit + root review + guarded merge remain PENDING (root-owned). PR #395 stays DRAFT; no merge/auto-merge performed by the coding agent.

## Publication

- Implementation head SHA: c600595315a05bd9e638ec0b09a320794f79dc72
- Report publication commit: SELF
