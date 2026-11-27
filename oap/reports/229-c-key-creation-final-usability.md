# OAP Report — 229-c (final usability): live key summary, one-time delivery truth, pinpoint numeric errors, per-field help — execution complete

## Status

- Objective: 229-c (`oap/active` working-tree bytes `229-c`, sha256 `b52f7f27c0a0c6e25c22475484f097bd12dc0c51b0a804750bee57e660ce10f7`, committed byte-unchanged in this PR); order `oap/orders/229-c-key-creation-final-usability.md` (sha256 `4c105a70f2b5cabd020bb65786abbe88863e23f0d703e281e0c9fa0cc007ecfb`), committed with the objective.
- PR: #403 (same PR; created by 229-a, amended by 229-b and 229-c), branch `oap/229-key-creation-active-profiles`, base `main` at `f1feec6bca0fd55f83d78c5badef2ab0b13ee304`; PR kept as a DRAFT; no auto-merge; the coding agent never merges.
- RESULT: **PASS** — the four advertised end-states (truthful live summary while editing, one-time secret/delivery truth, pinpoint bad-numeric identification, per-control plain-language help) are implemented and re-proven (below); the remaining delivery (CI gates, root review, guarded merge, actual-main verification) is root-owned and pending.
- No production certification, release, tag, or security/compliance claim. No provider traffic, no real email, no production `DATABASE_URL` at any point.

## Identification

Implementation head SHA: 9eea3146c04432144746c8194086be940520291b

Report publication commit: SELF

- PR #403 head at publication: the implementation head `9eea3146` (verified via GitHub before this report commit: head sha `9eea3146c04432144746c8194086be940520291b`, draft, open).
- Canonical record: `docs/verification/2026-11-27-key-creation-active-profiles.md` (top status paragraph replaced with the 229-c current end state; new "229-c continuation" section; 229-a/229-b sections preserved as historical continuations).
- Unrelated untracked local files (`CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`) preserved; they are not part of this PR.

## Implementation (four defect families; code/template-only)

1. **Truthful live summary** — the access summary recomputes client-side from the current form state on every relevant change (client setup, models, providers, endpoints including the effective preset union, lifetime limits, validity, delivery effect) with safe text rendering; informational only, server validation remains authoritative; under no-JS the summary is withheld with an explanation instead of showing stale initial defaults (accepted no-JS create path and final result unchanged). Two real template bugs fixed along the way: the Jinja HTML-escaped JSON data script (now unescaped with `</` escaping) and the delivery row reading the policy-source select instead of the delivery select.
2. **One-time secret/delivery truth** — the "after creation" row states the real behavior per mode (no email: shown in the browser ONCE, copy it before leaving, no later retrieval, warning displayed; send-now/enqueue: owner email is the delivery channel and the browser plaintext is suppressed, email warning displayed); no successful delivery is promised before it happens.
3. **Pinpoint numeric inputs** — typed field/call-site context (`_locate_key_create_numeric_failures`) flags ONLY the actually invalid control, valid blanks never marked; `KEY_CREATE_NUMERIC_FIELD_REMEDIES` gives each field real units and exact blank/zero/default behavior (blank lifetime quota = no total ceiling; blank speed values = shown deployment defaults; blank queue bounds = shown defaults; zero invalid for positive limits, valid for the safety-margin controls); nonsecret values preserved, group opened, field focused, honest safe fallback for unknown failures, existing settings-aware redaction reused.
4. **Per-control plain-language help** — each editable advanced control has its own adjacent plain-language help with accessible `aria-describedby` relationships (group-level `create-limits-help`/`create-rate-limit-help` paragraphs replaced by per-field help); raw Redis/null/schema/fence/capability-ID vocabulary and source names moved to optional Technical details; copy checked against runtime semantics (counting-window, margin direction) and relabeled honestly; all advanced functions kept.

No schema change, no migration, no preset-file/DATA byte change, no existing-key migration, no new framework.

## Audit and documentation impact

Canonical verification record: top paragraph replaced with the current 229-c end state (229-a/b sections preserved as historical continuations, not relabeled) plus the "229-c continuation" section. Operator docs: `docs/admin-usability.md` (new section 21.6), `docs/upgrade-runbook.md` (229-c code/template-only note).

## Results (exact; mocked vs live)

Environment: owned disposable PostgreSQL (module fixture, self-tearing-down), repo venv, Playwright Chromium against local uvicorn on a free loopback port. Providers and email MOCKED; no real inference, no real mail, no production DB.

- `tests/browser/test_admin_key_create_229b.py` — **12 passed** (27.43 s): the eight 229-b tests (one corrected: only the invalid control flagged, per-field remedy with real units and default behavior, preserved nonsecret value, correction, successful issuance) plus four NEW tests (live summary reflects current choices; delivery one-time warnings track the selected mode; advanced per-field help relationships and text; no-JS withholding of the stale live summary).
- Reused unchanged suites re-run once after the template/JS change, the eight-file GUI/unit suite — **556 passed** (230.98 s), including `test_admin_key_create_routes.py` 39 passed with the corrected single-flagged-control assertion.
- REUSED unchanged (not re-run): `test_admin_key_create_client_use_postgres.py` 13 passed, rev16/17 GUI pin/readiness evidence; 229-b's then-620 eight-file count is historical and not summed with the current 556.
- Fixture corrections in this continuation: `test_admin_key_create_229b.py`, `test_admin_key_create_templates.py`, `test_key_create_client_use_presets.py`, `test_admin_key_policy_207.py` (assertions that encoded the old behavior).
- Doc guards (`test_documentation_inventory`, `test_documentation_contract_drift`, `test_documentation_asof`) — **44 passed**; `ruff check` on all changed Python files — all checks passed; `git diff --check` — clean.
- Screenshots in the owned task directory (for root review): `229c-create-summary-live.png`, `229c-create-one-field-error.png`, `229c-create-advanced-help.png`.
- Not run: no real provider traffic, no real email, no production DB, no full 128-worker harness; no live-provider qualification claim.

## Corrections to prior claims

- The 229-b access-summary and per-field-help claims described the rendered form at initial state; the live recomputation, no-JS withholding, and per-control (not group-level) help are what 229-c proves.
- The 229-b-era browser assertion expecting four speed controls flagged for one invalid value codified the defect; it now asserts only the invalid control is flagged.
- The stale summary line "No email; the key stays available in the dashboard" is false; the real one-time reveal behavior is now stated.

## Deployment and migration conclusions

- Code/template-only change: no schema, no migration, no preset-file or DATA byte change, no existing-key migration, no key-material or quota change.
- Rollback: revert the implementation commit; no state revert is required (no persisted format or pin change for existing keys).

## Claims not made

- No CI-green claim (GitHub workflow results are root-owned and pending at publication).
- No browser/usability proof beyond the captured states and assertions above.
- No production request, deployment, or operator-database statement.
- No next objective activated; 229 terminal (review/merge) remains root-owned.
