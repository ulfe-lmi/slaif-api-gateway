# OAP Report — 229-d (final): model-picker summary event path and email recovery copy — execution complete

## Status

- Objective: 229-d (`oap/active` working-tree bytes `229-d`, sha256 `c888d69e7aba0508f0eaf2771c80f6350107e85e87cfb12e2853d774db47a1fd`, committed byte-unchanged in this PR); order `oap/orders/229-d-key-creation-final-widget-path.md` (sha256 `cb53764ab1307293f1ac676b143d431f8332b20a4961ad63fd26ecba96255561`), committed with the objective.
- PR: #403 (same PR; created by 229-a, amended by 229-b, 229-c and 229-d), branch `oap/229-key-creation-active-profiles`, base `main` at `f1feec6bca0fd55f83d78c5badef2ab0b13ee304`; PR kept as a DRAFT; no auto-merge; the coding agent never merges.
- RESULT: **PASS** — both advertised end-states (the live access summary tracks the primary widget path: Add/Remove and server-search selections; the email recovery copy matches the actual retry-failed/sendability law) are implemented and re-proven (below); the remaining delivery (CI gates, root review, guarded merge, actual-main verification) is root-owned and pending.
- No production certification, release, tag, or security/compliance claim. No provider traffic, no real email, no production `DATABASE_URL` at any point.

## Identification

Implementation head SHA: 4cc0b2d5fba2a0106031e6839a03cf50292a2438

Report publication commit: SELF

- PR #403 head at publication: the implementation head `4cc0b2d5` (verified via GitHub before this report commit: head sha `4cc0b2d5fba2a0106031e6839a03cf50292a2438`, draft, open).
- Canonical record: `docs/verification/2026-11-27-key-creation-active-profiles.md` (top status paragraph replaced with the 229-d current end state; new "229-d continuation" section; 229-a/229-b/229-c sections preserved as historical continuations).
- Unrelated untracked local files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) preserved; they are not part of this PR.

## Implementation (two defect families; code/template-only)

1. **Widget-path summary staleness (root-reproduced real browser blocker)** — the policy selector's primary interaction (selecting in the real available list + "Add selected ->", selected list + "<- Remove selected", server-side search choice) sets the manual textarea programmatically, so no DOM `input` event fired and the visible live summary stayed stale (e.g. "Models: None yet" while the textarea already held the token) even though the submitted value was correct. Fix: `policy-selector.js` dispatches one shared `slaif:policy-manual-synced` CustomEvent from `syncManualFromSelected` — the single helper behind Add, Remove, and the search `choose()` path — after every programmatic manual sync; the key-creation summary IIFE subscribes and refreshes. No observers, no polling, no framework; listeners only read form state, so the event cannot recurse. Preset endpoint ownership, document mode, and manual typing (real `input` events) are untouched.
2. **Email recovery copy overstated the one-way rule** — the create-form delivery warning/help and the server delivery summary texts said a failed/queued email's key "cannot be resent" universally. The actual law in `email_delivery_service.py`: the one-time secret is consumed only after SMTP success; a failed safe attempt may still hold the unconsumed secret; the existing retry-failed flow retries ONLY what sendability permits (sent, sending, ambiguous, consumed, expired secrets are never retried). The copy now says: check the Email delivery result, use the existing retry action only when it is permitted, and rotate or reissue the key if delivery is ambiguous or the secret is unavailable. Text-only; no workflow, endpoint, or sendability change.

Test-only finding (no source change): in the Playwright fixture, the browser scrolls a freshly focused multi-select into view during mousedown and Playwright's fixed-coordinate mouseup then lands on the pre-scroll position, so the click gesture and its `change` event do not complete on the option even though the option is selected (verified with event-level tracing; a bare-page control with the select in view fires `change` normally). The new test keeps each widget select fully in view before option clicks, the posture a real operator uses.

No schema change, no migration, no preset-file/DATA byte change, no existing-key migration, no new framework.

## Audit and documentation impact

Canonical verification record: top paragraph replaced with the current 229-d end state (229-a/b/c sections preserved as historical continuations, not relabeled) plus the "229-d continuation" section. Operator docs: `docs/admin-usability.md` (section 21.6 updated: widget-path coverage of the live summary; email recovery law in the delivery-truth bullet), `docs/upgrade-runbook.md` (229-d code/template-only note).

## Results (exact; mocked vs live)

Environment: owned disposable PostgreSQL (module fixture, self-tearing-down), repo venv, Playwright Chromium against local uvicorn on a free loopback port. Providers and email MOCKED; no real inference, no real mail, no production DB.

- `tests/browser/test_admin_key_create_229b.py` — **13 passed** (31.47 s): the twelve prior tests (unchanged) plus ONE new test, `test_policy_selector_widgets_update_live_summary`: real endpoint Add via the widgets, server-side model search selection, model Add via available list + Add button, model Remove via selected list + Remove button, provider Add/Remove cycle, and a preset-endpoint Remove with Hermes ownership surviving — each step asserting BOTH the submitted manual value and the visible summary row.
- Reused unchanged suites re-run once after the template/JS change, the eight-file GUI/unit suite — **556 passed** (229.83 s) (`test_admin_key_create_routes`, `test_key_create_client_use_presets`, `test_admin_key_policy_207`, `test_admin_key_create_email_delivery_routes`, `test_admin_key_create_templates`, `test_admin_gui_completion_219`, `test_demo_web`, `test_admin_usability_inventory`).
- `test_admin_key_create_routes.py` + `test_admin_key_create_templates.py` — **47 passed** (19.04 s), with the new assertions that the create template carries the recovery wording ("check the Email delivery result", "only when it is permitted", "rotate or reissue the key") and no longer claims "the key cannot be resent".
- REUSED unchanged (not re-run): `test_admin_key_create_client_use_postgres.py` 13 passed, the rev16/17 GUI pin and readiness evidence, the email sendability/retry integration coverage, and the security/accounting suites.
- Doc guards (`test_documentation_inventory`, `test_documentation_contract_drift`, `test_documentation_asof`) — **44 passed**; `ruff check` on all changed Python files — all checks passed; `git diff --check` — clean.
- Screenshot in the owned task directory (for root review): `229d-create-summary-widget-path.png`.
- Not run: no real provider traffic, no real email, no production DB, no full 128-worker harness; no live-provider qualification claim.

## Deployment and migration conclusions

- Code/template-only change: no schema, no migration, no preset-file or DATA byte change, no existing-key migration, no key-material or quota change.
- Rollback: revert the implementation commit; no state revert is required (no persisted format or pin change for existing keys).

## Claims not made

- No CI-green claim (GitHub workflow results are root-owned and pending at publication).
- No browser/usability proof beyond the captured states and assertions above; no claim that the Playwright focus-scroll artifact affects real-user pointer gestures.
- No email-delivery claim beyond the copied text and the unchanged sendability workflow; no real email sent.
- No production request, deployment, or operator-database statement.
- No next objective activated; 229 terminal (review/merge) remains root-owned.
