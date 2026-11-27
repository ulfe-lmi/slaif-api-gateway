# OAP Report — 229-b (completion): working client combinations, readiness, plain-language key-form help and errors — execution complete

## Status

- Objective: 229-b (`oap/active` working-tree bytes `229-b`, sha256 `9e7dd3d9376c8eef20bd38cf05dee016cc654130a2a1b1868fa990345fa9838d`, committed byte-unchanged in this PR); order `oap/orders/229-b-key-creation-completion.md` (sha256 `a3aef1d9d273c793d86f5f712ee8143d933abe2bbd8ce3cc21d876b8c3af7a39`), committed with the objective.
- PR: #403 (same PR amended by 229-b; created by 229-a), branch `oap/229-key-creation-active-profiles`, base `main` at `f1feec6bca0fd55f83d78c5badef2ab0b13ee304`; PR kept as a DRAFT; no auto-merge; the coding agent never merges.
- RESULT: **PASS** — the five advertised end-states blocked by ROOT's independent review are fixed and re-proven (below); the remaining delivery (CI gates, root review, guarded merge, actual-main verification) is root-owned and pending.
- No production certification, release, tag, or security/compliance claim. No provider traffic, no real email, no production `DATABASE_URL` at any point.

## Identification

Implementation head SHA: fcde6745aedfb5eeda79e6d5e94c5d9961f2429a

Report publication commit: SELF

- PR #403 head at publication: the implementation head `fcde6745` (verified via GitHub before this report commit).
- Canonical record: `docs/verification/2026-11-27-key-creation-active-profiles.md` ("229-b continuation" section: the five gaps, exact evidence, honesty notes).
- Unrelated untracked local files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) preserved; they are not part of this PR.

## Implementation (three fix families; code/template-only)

1. **Combined clients + shared readiness** — each enabled client's required endpoints are present in the composed policy (operator's explicit lists plus preset union; extras governed by the deliberate requested policy) and a shared local readiness path resolves the selected models/providers the way the live resolver would (selected enabled providers and routes, actual route selection, streaming requirement, registered client/server pair, active pricing) and fails safely BEFORE any key/email/audit effect.
2. **Preset switching/endpoint ownership + add-only semantics** — the template now removes only what the preset itself added (duplicated-option bug fixed), is stable under repeated toggling, and keeps explicit operator selections intact; the pre-submit warning is truthful: server application of missing preset endpoints is ADD-ONLY (`_apply_admin_client_preset_endpoints`), never a refusal.
3. **Usability reorganization + structured safe errors + no-JS client create** — the form leads with the main flow (owner, intended client, provider/models, validity/budgets, delivery) and collapses advanced categories by default; every advanced editable field has adjacent plain-language help, programmer jargon is out of the primary labels, and a compact plain-language access summary sits before creation; refusals render a structured safe summary (operator sentence, clickable anchor per affected field, `aria-invalid` plus highlight, focus moved to the summary, containing collapsed group opened, entered NONSECRET values preserved, honest reference-ID fallback); the no-JS client create renders the 200 result page with the plaintext key.

No schema change, no migration, no preset-file/DATA byte change, no existing-key migration, no new framework.

## Audit and documentation impact

Canonical verification record updated (root-cause bullet corrected; drift-audit row 1 reworded; "229-b continuation" section). Operator docs: `docs/admin-usability.md` (section 21.1 plus new 21.5), `docs/client-compatibility-presets.md` (combined-client bindings and preset endpoints), `docs/cli-field-administration.md`, `docs/upgrade-runbook.md` (229-b: code/template-only), `docs/module-architecture.md`. Historical 229-a facts preserved as dated evidence and not relabeled current.

## Results (exact; mocked vs live)

Environment: owned disposable PostgreSQL container `slaif229b-pg` (postgres:16, 127.0.0.1:54412, DB `slaif229b_test` via `TEST_DATABASE_URL`), repo venv, Playwright Chromium against local uvicorn on a free loopback port. Providers and email MOCKED; no real inference, no real mail, no production DB.

- `tests/unit/test_key_create_client_use_presets.py` — **64 passed** (229-a: 39; combined-client composition, readiness negatives, add-only endpoint application).
- `tests/integration/test_admin_key_create_client_use_postgres.py` — **13 passed** (229-a: 7); reconfirmed at publication: 13 passed in 31.18 s, exit 0, against the same owned container.
- `tests/browser/test_admin_key_create_229b.py` (NEW, committed) — **8 passed**: main flow visible with advanced categories collapsed and the plain-language access summary (desktop and narrow viewport); preset-switching endpoint ownership with repeated-toggle stability; a missing preset endpoint's truthful pre-submit warning plus the server's add-only application with the final endpoint list shown on the confirmation page; a genuine refusal (invalid quota value) leaving no key/email/audit side effects; document-mode disabling (not hiding) of client choices; an ACTUAL no-JS Hermes create with the server-applied preset and the exact active pin; and the safe error state (anchors, `aria-invalid`, focus, collapsed group opened).
- Reused unchanged suites re-run once after the template-JS change, the eight-file GUI/unit suite — **620 passed** (`test_admin_key_create_routes`, `test_key_create_client_use_presets`, `test_admin_key_policy_207`, `test_admin_key_create_email_delivery_routes`, `test_admin_key_create_templates`, `test_admin_gui_completion_219`, `test_demo_web`, `test_admin_usability_inventory`).
- Doc guards (`test_documentation_inventory`, `test_documentation_contract_drift`, `test_documentation_asof`) — **44 passed**; `ruff check` on all changed source/test files — all checks passed; `git diff --check` — clean.
- Screenshots in the owned task directory (mode 700, for root visual review): `229b-create-ordinary-desktop.png`, `229b-create-ordinary-narrow.png`, `229b-create-client-presets.png`, `229b-create-doc-mode.png`, `229b-create-nojs-client-form.png`, `229b-create-error-state.png`, `229b-create-advanced-open.png`.
- Not run: no real provider traffic, no real email, no production DB, no full 128-worker harness. This objective makes no live-provider qualification claim; the qualified historical records remain the dated evidence.

## Corrections to prior claims

- The 229-a root-cause wording overclaimed: the original helper already pinned from the active installed module metadata; the frozen-revision equality guard was the sole defect. Corrected in the canonical record and the PR body.
- 229-a's "all seven requirements executed" described scope execution, not acceptance; ROOT's independent review reproduced the blocking defects this objective completes.
- ROOT read the secondary read-only audit AFTER the 229-a response; it was not relayed before publication.

## Deployment and migration conclusions

- Code/template-only change: no schema, no migration, no preset-file or DATA byte change, no existing-key migration, no key-material or quota change.
- Rollback: revert the implementation commit; no state revert is required (no persisted format or pin change for existing keys).

## Claims not made

- No CI-green claim (GitHub workflow results are root-owned and pending at publication).
- No browser/usability proof beyond the captured states and assertions above.
- No production request, deployment, or operator-database statement.
- No next objective activated; 229 terminal (review/merge) remains root-owned.
