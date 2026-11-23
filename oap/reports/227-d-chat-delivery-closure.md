# OAP Report — 227-d (Chat delivery closure): docs reconciliation, run1 provenance correction, task-runtime cleanup

## Status

- Objective: 227-d (`oap/active` = 227-d; root-authored activation committed byte-unchanged).
- PR: #395 (DRAFT, AMEND_EXISTING_PR; the coding agent never merges).
- Result: closure complete — current docs reconciled with executed 227-c live results; the c report's run1 provenance conflation explicitly superseded (c report immutable, unmodified); task-runtime cleanup executed and verified.
- Qualification: 227-c live LAN qualification remains EXECUTED as recorded; NO reruns, no new inference in 227-d. Remaining gates are root-owned and PENDING: final exact-head CI on this report commit, review, guarded merge. 228 not activated.

## Identification

- Implementation head SHA: 556a371f35f41370d81b205db10b9728fef1050d
- Implementation tree: b937a0353226cba0233b0a9bba33ca9bb7286639
- Activation commit (root-authored order publish + activate, byte-unchanged): fadd600de65571c7d4eb46d0a9e3b17389cdce8f
- Executable candidate (unchanged from 227-c): b2a0d950e122d612594f55ba54e18fe80d2644c7 (tree f7dd2d382d7aa674ff8f2c8e97911df280b7e6e5; app tree 17a9caadc83aa1603bfef62bc1f43fab59f3a80f)
- Order: oap/orders/227-d-chat-delivery-closure.md (sha256 b4086e73efba27660f8cc5057964d482cf1e9b9a310d1edae8986f0b6783adbe, unchanged during the round)
- Active pointer: oap/active = 227-d (sha256 378ce28308527a3a0c6768e0886eec0254858ef8247237c0b97a6d52448fc77f, unchanged during the round)
- Superseded (immutable, unmodified): oap/reports/227-c-lan-chat-qualification.md (sha256 3177a306c8dede320bc29e409d89cf8a1a78b1770976f31263efd729d625bbc6)
- Main integration identity: 8cb35eb7dd12fb3454915fe334fafa115da6cbfa (origin/main at candidate time)
- DATA digests (unchanged): Hermes c5e34d46270280d7e08639c01c28065380a2a80843c1114ac1f1ad2a2744d327 (v2); OpenCode 2bd4f2599456892bb5d5119a85c9ffe9525796c1aa934ad46b49ce34d18f0e14 (v1)

## Correction (supersedes the c narrative; c remains immutable)

- A. Pre-spawn driver typo (STOUT->STDOUT): NO native process spawned — a setup failure, NOT a launch, not counted in launch totals; root still counted its 1.01 s toward the wall budget (1.01 s + 11.0 s = 12.01 s consumed before run 3).
- B. Run 1 = first ACTUAL native launch: 1.01 s, exit 1, missing runtime dependency in the task venv; 0 admitted / 0 reserved.
- C. Run 2 unchanged: 11.0 s, fake provider slug in the wire model -> HTTP 403 `model_not_allowed_for_key` (gate working correctly); 0 admitted / 0 reserved.
- D. Run 3 unchanged: 30.01 s, strict raw-byte final==marker PASS (32/32).
- All current docs (module-architecture, both client dossiers, verification record, obligations manifest) carry the corrected provenance; `docs/first-time-operator-guide.md`'s line-612 "not_run" sentence is superseded by the record (that guide is not editable in this order and remains unchanged).
- Conservative totals unchanged: 5 launches (H3+O2); 42.02/40.658/82.678 s; 41,021 tokens / EUR 0.041021.

## Docs reconciliation (order items 1-2)

- module-architecture + both dossiers: the protected live gate was `not_run` through 227-b; 227-c executed it (scoped, human-accepted bounded gate); the docs now link the SAME existing verification record. Historical loopback/fake/PG receipts kept as history.
- Exact client/source/SDK/pin/config/transport boundaries, bare-model/custom-provider config facts, stock-retry exception, and the opaque-hop limitation are stated; no Responses/plugin/MCP/image/future-version/production claims.
- Operator instructions complete (install, authenticated Chat binding via typed key-policy CLI, server-only provider credential, caps 8192/32768, restart, native model/provider config, rollback by removing the optional Chat binding; no DB migration, no silent conversion, no secret values).

## Checks this turn (227-d)

- JSON parse of the obligations manifest OK; exact round-trip formatting preserved.
- `git diff --check` rc=0 across the 5-file diff; documented reference/link targets verified present.
- Manifest invariants re-verified: `preprotected.missing == []`; `protected.status == executed`; DATA digests untouched; 227-a/b/c historical state preserved.
- Skips mandated by order: no pytest (unit/full/native/PG) reruns; no fixture-digest changes; no governance test rerun (227-c precedent; final-head CI supplies the required gate); no live provider/client invocations.
- GitHub CI on implementation head 556a371f, reported exactly as observed at report-writing time (2026-11-23): 9 of 10 check runs completed/success (CodeQL; Analyze (python); Analyze (javascript-typescript); Unit, lint, and migration head; OpenAI-compatible E2E tests; Docker Compose smoke; Documentation hygiene; Playwright browser smoke; Analyze Python) and 1 in_progress (PostgreSQL integration tests); the run was not complete at writing and CI is NOT reported as passed. The c final CI runs 45146822297/45146822175/45146516020 are activation checkpoints, never future-head passes.

## Reused checks (no rerun; exact provenance)

- 557 unit tests at tested head 5c2bacf83578f5a23b6e9700656e8bfd26dc373c (tree 430aae04aaa2f4dbaf4ff529623d022ff3a09278; app tree 0ab1e80ad89a6578b17b0bfcaa99fa5e8ccab21e), incl. test_verify_hermes_chat_capture.py; root's 16-check on that file is independent OVERLAPPING evidence, never summed (no 573).
- Ruff clean at that head.
- Governance: 2 failed/8 passed at 227-a (order-format, resolved by root canonical b); focused new-active-state governance 10/10 after b; five other governance files pass (incl. agentic_client_integration_governance, provider_governance).
- Candidate CI: 9 jobs / 3 workflow identities + CodeQL aggregate root-verified SUCCESS at b2a0d950 before traffic.
- 227-b obligation collection: 19 groups / 140 refs, one collection 606 nodes, collection-only.

## Cleanup (227-d, executed and verified — exact details in the record "227-d closure" section and manifest `cleanup_227_d`)

- Preconditions: all native clients stopped; PG authoritative: all 7 requests 200 FINALIZED; zero pending reservations/holds/fences.
- Both task keys revoked via typed CLI (rc 0, status revoked, usage preserved, no reset), with audit reasons; `valid_until` 2026-11-24T08:25:52.058841+00:00 (Hermes) / 2026-11-24T08:25:59.536015+00:00 (OpenCode) as recorded.
- 12 pre-deletion receipt sha256s recorded before deletion (table in the record/manifest).
- Graceful stops after exact PID/cwd/datadir identity re-verification: Gateway 3944229 -> 18300 closed; Redis 3944362 -> 6390 closed; PG16 3936772 `pg_ctl stop -m fast` -> 54399 closed, data directory KEPT.
- 15 content-free private paths deleted (auth inputs, client configs/backups incl. the 4 expected 0600 Hermes config hits, histories/transcripts, markers, ephemeral driver outputs); task root, live control-waiter log, control machinery, and PG data kept.
- Scans: root independent pre-cleanup scan (441 non-venv work/log/gateway files vs both full task bearers + intended LAN bearer) -> only the 4 expected 0600 Hermes config hits (all deleted); final post-deletion scan (2,709 files; 3 full-secret needles loaded privately into a 0600 file, then deleted) -> 0 unexpected hits; raw native histories gone.
- No unrelated /tmp cleanup; no FIFO type/inode changes; no GPU-cancellation claim.

## Final counters and accounting (unchanged from 227-c)

- 5/100 launches; 42.02/40.658/82.678 s; 41,021 tokens / EUR 0.041021 (ceilings 2,000,000 / EUR 2).
- Hermes 3/6 (10,864 in / 611 out / 11,475 total / EUR 0.011475); OpenCode 4/6 (29,546 / EUR 0.029546); 7x200 FINALIZED; zero holds/fences/reservations.
- Root accounting evidence: slaif_calculated x7 (task-configured pricing, NOT a provider invoice); 3/7 cached-input fallback warnings (slaif_calculated_with_fallbacks); needs_reconciliation false x6 / null x1; no billing-precision claim.

## Limitations and honest disclosures

- Strict global zero-retry/6-admission plan: historical proposal, UNSATISFIED as a universal guarantee; the executed qualification ran under the human-accepted bounded gate (accepted; no pending human decision).
- Upstream hop beyond the LAN edge (10.8.132.55:18021) is opaque -> unverified client-side.
- Chat support does not qualify OpenCode Responses, Hermes Responses, plugins, MCP, images, future client versions, or production certification.
- Stock-retry exception bounded to the 227-c execution (none observed); zero-retry guarantee not claimed.
- Final exact-head CI on this report commit PENDING (root gate); PR #395 stays DRAFT.

## Protected gate

- Protected live test: EXECUTED in 227-c (not rerun in 227-d); plan of record + human-accepted bounded gate as recorded in the 227-b manifest / 227-c report.
- CI gate before protected traffic: satisfied on candidate b2a0d950 (root-verified 9 jobs / 3 identities + CodeQL) before first launch.
- Final gate: exact-head CI on this report commit + root review + guarded merge PENDING (root-owned).

## Publication

- Implementation head SHA: 556a371f35f41370d81b205db10b9728fef1050d
- Report publication commit: SELF
