# 2026-11-27 — Key creation uses active client profiles and explains its choices

OAP objective 229 (five continuations on the same PR #403: 229-a, 229-b,
229-c, 229-d, 229-e). CURRENT end state (229-e, 2026-11-27): the
229-d GUI feature state below, with the demonstrated final-CI failures
of the 229-d head repaired — the shared key-creation result template now
renders with a safe default pin context for every legitimate caller (a
real product regression: template creation returned 500), and the test
suite is portable again (test-owned screenshot directory, wall-clock
relative test key, and browser tests operating the current native
request-speed disclosure, including no-JS) — as recorded in the 229-e
section below. The 229-d end state (as of that continuation) was: the admin GUI
key-creation form shows a plain-language access summary that tracks the
CURRENT visible choices (client setup, models, providers, endpoints
including the effective preset union, lifetime limits, validity, and the
delivery effect) — including the primary widget path, where Add/Remove
selections in the policy selector's real available/selected lists and the
server-side search selection now update the summary immediately through a
shared post-mutation notification — and is withheld with an explanation
when scripts are disabled; the one-time secret and delivery text states
the real show-once / copy-before-leaving / no-later-retrieval behavior and
matches the actual email workflow, with the failed/queued-email recovery
truth (check the Email delivery result, use the existing retry only when
it is permitted, rotate or reissue the key if delivery is ambiguous or the
secret is unavailable); invalid numeric inputs pinpoint ONLY the actually
invalid control with the field's real units and exact blank/zero/default
behavior; and every editable advanced control has its own adjacent plain-
language help with accessible `aria-describedby` relationships. The 229-a,
229-b, 229-c, and 229-d sections below are historical continuations of this
same objective, preserved as dated evidence; where a later continuation
supersedes an earlier description, the latest one governs.

## Root cause

A deployment that bound a newer Codex compatibility profile through
`CODEX_COMPATIBILITY_PROFILE_FILE` (for example the packaged
`codex-0.167.1`, module `codex-0.162-responses-v1`, DATA revision 16) could
NOT create a Codex key at all:

- `_validated_admin_qwen_codex_policy` compared the frozen qualification
  profile's recorded `client_module_version` (e.g. `"8"` in
  `QWEN38_CODEX_PROFILE`) against the installed module's
  `module.module_version` and failed the request whenever the deployment had
  promoted a newer revision, even though the stable executable module ID
  had not changed.
- Correction (229-b, after ROOT source verification of the pre-229-a
  code): the ORIGINAL helper already built the pin from the ACTIVE
  installed module metadata — `client_module_metadata(module)` reads the
  snapshot bound into this process at bootstrap — so the defect was ONLY
  the frozen-revision equality gate above, not the pin source. The 229-a
  fix replaces the gate with a stable module-ID check and routes the pin
  through the shared `active_client_module_facts` accessor.

The frozen qualification revision is EVIDENCE (the DATA snapshot a route was
qualified against), not a runtime equality gate. The runtime gate is the
stable executable module ID; the pin must come from the active snapshot.

## Four concepts kept distinct

1. **Stable executable module ID** — e.g. `codex-0.162-responses-v1`.
   Never renamed or substituted; it does not encode the CLI version.
2. **Active installed DATA** — revision + canonical digest + CLI provenance
   of the profile bound once at bootstrap
   (`bind_codex_0162_client_module`), exposed through
   `slaif_gateway.modules.clients.registry.active_client_module_facts`.
3. **Frozen qualification profiles/evidence** — the per-route qualification
   records in `services/codex_profile_registry.py` /
   `services/codex_qualification.py` (including their recorded
   `client_module_version`).
4. **Route/key capabilities** — the independent `codex_*` route gates and
   key `responses_policy` capabilities that authorize behavior.

## Current shared-source / data-flow design

- `modules/clients/registry.py`
  - `ActiveClientModuleFacts` + `active_client_module_facts(module_id)`:
    one accessor for the active identity. Responses registry is consulted
    first, then the agent-chat registry; `.pin` is the exact
    `{id, version, fixture_sha256}` triple; provenance comes from the bound
    `.profile` (or `policy_spec.provenance`) and is used for DISPLAY, never
    for qualification.
- `api/admin.py` (key-creation POST)
  - Four client-use checkboxes (`client_use_codex`,
    `client_use_opencode_chat`, `client_use_opencode_responses`,
    `client_use_hermes`), each with a "What is this for?" help panel.
  - `_validate_admin_client_use_selection`: fail-closed conflict rules —
    client-use + advanced configuration document, client-use +
    trusted calibration, a second Chat-family binding, a second
    Responses-family binding, advanced historical Codex sections +
    client-use. Each error names the fields and the form re-renders with
    every entered value preserved plus a diagnostic reference ID.
  - Codex choice: the checkbox is the confirmation on the existing
    `_validated_admin_qwen_codex_policy` path. The gate is now a stable
    module-ID match between the selected frozen profiles and
    `active_client_module_facts(CODEX_0162_CLIENT_MODULE_ID)`; the returned
    policy builds the pin from the ACTIVE snapshot (revision/digest of the
    bound DATA), while route readiness still comes from
    `CodexQualificationService.inspect()` and the frozen profiles' gates.
  - OpenCode (Chat) / Hermes: chat preset from the agent-chat registry's
    active facts; requires the `/v1/chat/completions` endpoint on the key.
  - OpenCode (Responses): `_validated_admin_opencode_responses_policy` —
    explicit models + providers (no allow-all), the `/v1/responses`
    endpoint, and an enabled exact `/v1/responses` route with ALL four
    OpenCode Responses gates True for every selected model × provider pair
    (fail closed otherwise, no dead-end grants).
  - `_safe_client_module_pins` renders the created key's pins on the result
    page ("Responses client module" / "Chat client module" lines);
    `_safe_codex_responses_policy_summary` keeps an acceptable-pin list
    (a list, not a set) for the Codex summary.
- `api/admin_compatibility.py` / `api/demo_admin_compatibility.py`
  - The compatibility dashboard's Codex module column now reads
    `<module> v<active> (qualified v<frozen>)`, keeping the active runtime
    identity and the frozen qualification evidence visibly distinct.
- `web/templates/keys/create.html`, `create_result.html`,
  `web/static/css/admin.css`
  - Client-use section with per-choice help, an endpoint preselect
    convenience (the server rechecks every grant), a clearly labeled
    "Advanced: historical Codex key modes" disclosure, and result-page pin
    lines.

## Drift audit findings

| # | Location / caller | Classification | Disposition |
|---|-------------------|----------------|-------------|
| 1 | `api/admin.py` `_validated_admin_qwen_codex_policy` (frozen `profile.client_module_version != module.module_version` equality gate against the active installed module) | CONFIRMED_RUNTIME_DEFECT | FIXED: stable-ID check only; the pin was already built from active module metadata (229-b correction of the earlier "frozen pin inputs" overclaim) |
| 2 | `api/admin_compatibility.py`, `api/demo_admin_compatibility.py` module column (frozen revision displayed as the current module) | CONFIRMED (misleading current label) | FIXED: "active vN (qualified vM)" |
| 3 | `api/admin.py` codex-protocol-pilot branch; `services/codex_profile_registry.py` frozen 0.147 `OPENAI_CODEX_PROFILE` | INTENTIONAL_HISTORICAL_FROZEN | PRESERVED: the pilot and 0.147 records remain frozen qualification evidence; the historical section is labeled as such in the GUI |
| 4 | `services/key_template_service.py` (hardcoded frozen `CODEX_0147_CLIENT_MODULE` pin check) | INTENTIONAL_HISTORICAL_FROZEN | PRESERVED + DOCUMENTED: key templates intentionally pin the 0.147 qualification; templates do not offer the client-use choices, so this is a known GUI/template gap, not a defect |
| 5 | `api/admin_key_batch.py`, `api/admin_key_clone.py` (carry `responses_policy` / `chat_client_module` metadata without Codex client-use checkboxes) | GUI difference | DOCUMENTED: batch/clone manage the raw policy metadata and have no client-use presets; no behavior change |
| 6 | `keys/create.html` `guidedPolicyControls` script (does not uncheck historical Codex checkboxes when switching to document mode) | Pre-existing client-side gap | DOCUMENTED: the server-side conflict rule (client-use + configuration document) is the authoritative boundary; the JS only hides guided policy controls |
| 7 | `modules/clients/codex_0162.py` stale "(revision 3)" docstring lines | UNRESOLVED / UNRELATED | DOCUMENTED only: cosmetic comment staleness in module docstrings; no runtime effect; left unchanged in this order |

Frozen fixture/digest evidence was NOT altered to make any check pass.

## Field-help / UX coverage

- Every client-use checkbox has an inline "What is this for?" disclosure
  explaining what the preset grants and what it does not.
- Checking a client preselects its unambiguous endpoint(s) and shows a
  summary line; the UI states that the server rechecks every grant.
- The historical Codex sections sit in one disclosure titled
  "Advanced: historical Codex key modes" and cannot be combined with
  client-use (server-enforced).
- Errors render a `role="alert"` flash with a diagnostic reference ID; all
  entered values (owner, validity, policy lists, checkboxes) are preserved
  for correction.
- No-JS fallback: the owner/cohort record choices degrade to plain inputs
  and the manual policy strings panel is the primary policy editor; the form
  still creates keys server-side (verified in the browser smoke).
- All new controls are keyboard reachable (checkboxes toggle with Space;
  the record-choice and manual panels are native form controls).

## Verification results (exact)

Environment: owned disposable PostgreSQL
(`slaif229-tmp-pg`, port 54399, DB `slaif229_test`,
`TEST_DATABASE_URL=postgresql+asyncpg://postgres:229tmp@127.0.0.1:54399/slaif229_test`),
repo venv, Playwright Chromium against a local uvicorn on
127.0.0.1:18400. Providers and email are MOCKED; no real inference, no real
mail, no production `DATABASE_URL`.

- `tests/unit/test_key_create_client_use_presets.py` — **39 passed** in
  2.24s (active facts incl. chat fallback and unknown-id fail-closed; all
  five conflict rules and allowed combinations; chat preset endpoint/pin;
  gate predicate truthy-vs-True; `_safe_client_module_pins`; summary
  accepts an active pin and rejects a stale digest; Qwen policy with
  monkeypatched rev-16 active facts → pin == active identity, module-ID
  mismatch rejected, not-ready route rejected, exact-endpoint rule,
  allow-all rejected).
- `tests/integration/test_admin_key_create_client_use_postgres.py` —
  **7 passed** in 17.84s (GUI POSTs persist the EXACT active pin in
  `metadata_json` for chat/Hermes/OpenCode-Responses; result page shows the
  pin labels; conflict 400 leaves 0 keys / 0 email / 0
  `gateway_key_created` audits with values preserved; gateless route 400;
  rev-16 and synthetic rev-17 GUI creates in isolated subprocesses pin the
  active identity while the QWEN38 frozen profile records v8).
- Browser smoke (Playwright, real styles + JS, disposable PG seed):
  **PASSED**. States captured under the owned task directory as
  `229-browser-ordinary.png`, `229-browser-client-use.png`,
  `229-browser-advanced.png`, `229-browser-error.png`,
  `229-browser-result.png` (mode 700). Verified: ordinary unchecked state;
  client-use endpoint preselect (summary + manual + selected list);
  advanced disclosure; conflict error flash with preserved values and
  diagnostic reference ID; keyboard focus/Space toggling; a corrected
  resubmission that creates the key; no-JS fallback create with the plain
  owner input.
- Stage-2 functional GUI smoke (TestClient, mocked provider/email):
  **12 cases passed** (ordinary-key regression; OpenCode-Chat pin
  `opencode-1.19.3-chat-v1 v1`; Hermes pin `hermes-0.22.5-chat-v1 v2`;
  chat-family conflict 400 pre-effects; Codex preset pin
  `codex-0.162-responses-v1 v8` under the packaged default;
  responses-family conflict; missing-route fail-closed; OpenCode-Responses
  pin `opencode-1.19.3-responses-v1 v1` with all four capabilities;
  advanced + client-use conflict; legacy `qwen_codex` regression; combined
  chat + responses on one provider).
- `ruff check` on all changed source and test files: **All checks passed**.
  (`ruff format --check` drift in `api/admin.py` is pre-existing at the
  base HEAD; CI runs `ruff check`.)
- `git diff --check`: clean.
- Not run: no real provider traffic, no real email, no production DB, no
  full 128-worker harness; CI workflow results are reported by the OAP
  publication record, not claimed here.

## Limitations

- The browser smoke exercises ONE synthetic scenario (one owner, one
  provider, one route) per state; it is form-level proof, not a full admin
  UX audit.
- Key templates, batch import, and clone intentionally keep their frozen /
  raw-metadata behavior (findings 4–5); the client-use presets exist only
  on the interactive create form.
- No existing-key migration: keys created with explicit pins keep those
  pins; a pin that no longer matches the installed DATA fails closed at
  request time instead of being silently rewritten. Operators migrate
  deliberately through the audited CLI workflow, as before.
- Document (configuration-JSON) mode and client-use are mutually exclusive
  by server rule; the client-side script does not uncheck the historical
  Codex boxes in document mode (finding 6) — the server boundary is the
  guarantee.
- Historical records (including 228-c OpenCode Responses qualification and
  the accepted 227 Hermes/OpenCode Chat native loops) are preserved as
  dated evidence and are not relabeled current by this change.

## 229-b continuation (2026-11-27, same PR #403)

### What 229-a's "all seven requirements executed" did not cover

The 229-a report's "all seven requirements executed" described scope
execution, not acceptance. ROOT's independent review reproduced blocking
defects in the advertised end state; 229-b completes them:

1. **Broken advertised combinations** — the Qwen Codex helper accepted
   only the exact endpoint pair `/v1/models` + `/v1/responses`, so the
   advertised Codex+Hermes and Codex+OpenCode-Chat combined keys could not
   be created. Now each enabled client's required endpoints are present in
   the composed policy (the operator's explicit lists plus the preset
   union, extras governed by the deliberate requested policy) and the
   shared readiness path validates the combination. Real PostgreSQL GUI
   creates for BOTH combinations persist the exact active pins with no
   extra privileges; OpenCode Responses+Chat, same-family conflicts, and
   ordinary/legacy behavior are retained.
2. **Preset switching retained invisible endpoints** — unchecking a client
   left its preset-owned endpoint in the selected pane (a duplicated-option
   bug), so Hermes to Codex after unchecking Hermes failed over an
   invisible Chat endpoint. The template now removes only what the preset
   itself added, keeps explicit operator selections intact, and is stable
   under repeated toggling (browser regressions).
3. **Readiness that did not prove usability** — the Chat preset checked
   endpoint presence only and the OpenCode Responses preset checked raw
   gate booleans. A shared local readiness check now resolves the selected
   models/providers the way the live resolver would (selected enabled
   providers and routes, actual route selection, streaming requirement,
   registered client/server pair, active pricing) and fails safely BEFORE
   any key/email/audit effect.
4. **Incomplete usability reorganization** — the form now leads with the
   main flow (owner, intended client, chosen provider/models,
   validity/budgets, delivery) and collapses the advanced categories by
   default; every advanced editable field has adjacent plain-language help
   (what it controls, when to change it, what blank/zero does, an example);
   programmer jargon is out of the primary labels (Redis to "Request speed
   controls", fences to "Provider-run tools and their cost risk",
   live-burn to "Stopping long responses early"); a compact plain-language
   access summary (client setup, models, providers, endpoints, lifetime
   limits, delivery effect) sits before creation.
5. **Unstructured errors** — refusals render a structured safe summary:
   the operator sentence, a clickable anchor per affected field,
   `aria-invalid` plus highlight on the flagged controls, focus moved to
   the summary, the containing collapsed group opened, entered NONSECRET
   values preserved, and an honest reference-ID fallback for unknown
   failures. Validation refusals (no key/email side effect) are
   distinguished from post-creation delivery outcomes.

Honesty notes: ROOT read the secondary read-only audit after the 229-a
response; it was not relayed before publication. The root-cause overclaim
in this file's first section is corrected above: the original helper
already pinned from the active installed module metadata, and the
frozen-revision equality guard was the sole defect.

### 229-b evidence (exact)

Environment: owned disposable PostgreSQL container `slaif229b-pg`
(postgres:16, 127.0.0.1:54412, DB `slaif229b_test`), repo venv, Playwright
Chromium against local uvicorn on a free loopback port. Providers and email
are MOCKED; no real inference, no real mail, no production `DATABASE_URL`.

- `tests/unit/test_key_create_client_use_presets.py` — **64 passed**
  (extended in 229-b from 229-a's 39: combined-client composition,
  readiness negatives, add-only endpoint application).
- `tests/integration/test_admin_key_create_client_use_postgres.py` —
  **13 passed** (extended in 229-b from 229-a's 7: real PG GUI
  combined-client creates under active rev16, readiness failures with zero
  key/email/audit side effects, disabled/unregistered provider negatives).
- `tests/browser/test_admin_key_create_229b.py` (NEW, committed) —
  **8 passed**: main flow visible with advanced categories collapsed and
  the plain-language access summary (desktop and narrow viewport); preset
  switching endpoint ownership with repeated-toggle stability; a missing
  preset endpoint's truthful pre-submit warning plus the server's add-only
  application with the final endpoint list shown on the confirmation page;
  a genuine refusal (invalid quota value) leaving no key/email/audit side
  effects; document-mode disabling (not hiding) of client choices with
  deliberate guided return; an ACTUAL no-JS Hermes create with the
  server-applied preset and the exact active pin; and the safe error state
  (anchors, `aria-invalid`, focus, collapsed group opened). Screenshots in
  the owned task directory: `229b-create-ordinary-desktop.png`,
  `229b-create-ordinary-narrow.png`, `229b-create-client-presets.png`,
  `229b-create-doc-mode.png`, `229b-create-nojs-client-form.png`,
  `229b-create-error-state.png`, `229b-create-advanced-open.png`.
- Reused unchanged suites re-run once after the template-JS change, the
  eight-file GUI/unit suite: **620 passed** (`test_admin_key_create_routes`,
  `test_key_create_client_use_presets`, `test_admin_key_policy_207`,
  `test_admin_key_create_email_delivery_routes`,
  `test_admin_key_create_templates`, `test_admin_gui_completion_219`,
  `test_demo_web`, `test_admin_usability_inventory`).
- Doc guards `test_documentation_inventory`,
  `test_documentation_contract_drift`, `test_documentation_asof` —
  **44 passed**; `ruff check` on all changed source/test files — all checks
  passed; `git diff --check` — clean.
- Not run: no real provider traffic, no real email, no production DB, no
  full 128-worker harness. This continuation makes no live-provider
  qualification claim; the qualified historical records remain the dated
  evidence.

## 229-c continuation (2026-11-27, same PR #403)

### What ROOT's independent review of 229-b still blocked

1. **Stale live summary** — the `.access-summary` rendered only
   server-side at form load and stayed at the initial defaults while the
   operator changed client, model, provider, lifetime limits, validity, or
   delivery before submit.
2. **Delivery truth** — the summary said "No email; the key stays available
   in the dashboard", which is false: with no email the key is shown in the
   browser ONCE and cannot be retrieved later; the email-mode text also had
   to match the actual send-now/enqueue workflow without promising delivery
   before it happens.
3. **Numeric errors flagged every speed control** — the numeric catch
   re-parsed groups and marked ALL four speed controls for a single
   requests=`abc`; a then-committed browser assertion codified that
   mistake.
4. **Per-field help not actually finished** — advanced fields still showed
   group paragraphs and programmer text (for example "Redis counters
   separate from PostgreSQL hard quota limits") instead of the reviewed
   copy next to EACH editable control.

### 229-c implementation (form, focused helpers, template, tests, docs)

1. **Live summary** — the summary recomputes client-side from the current
   form state on every relevant change (including the effective preset
   endpoint union) using safe text rendering; it is informational only and
   server validation remains authoritative. Under no-JS the summary is
   withheld with an explanation that the entered fields govern, and the
   accepted no-JS create path and final result are unchanged. Two real
   template bugs were caught by the new browser tests and fixed: the JSON
   data script was HTML-escaped by Jinja (breaking `JSON.parse`) and is now
   emitted unescaped with `</` escaping, and the delivery row read the
   policy-source select instead of the delivery select.
2. **One-time/delivery truth** — the "after creation" row states the real
   behavior per mode: no email, the key is shown in the browser once, copy
   it before leaving, no later retrieval (the one-time warning is displayed
   for that mode); send-now/enqueue, the owner email is the delivery
   channel and the browser plaintext is suppressed (the email warning is
   displayed instead). No successful delivery is promised before it
   happens.
3. **Pinpoint numeric failures** — `_locate_key_create_numeric_failures`
   reports typed field/call-site context so ONLY the actually invalid
   control is flagged and valid blank fields stay valid (parser acceptance
   law unchanged); `KEY_CREATE_NUMERIC_FIELD_REMEDIES` gives each field its
   real units and exact blank/zero/default behavior (blank lifetime quota =
   no total ceiling; blank speed values = the shown deployment defaults;
   blank queue bounds = the shown defaults; zero invalid for positive
   limits, valid for the existing safety-margin controls). The entered
   NONSECRET value is preserved, the containing group opens and focus moves
   to the field, single-field details anchor to that control while
   multi-field details keep an empty anchor, and unknown failures get an
   honest safe fallback with a reference ID instead of raw exception text,
   reusing the existing settings-aware redaction.
4. **Per-control plain-language help** — every editable advanced control
   carries its own adjacent plain-language help with accessible
   `aria-describedby` relationships (the former group-level
   `create-limits-help` / `create-rate-limit-help` paragraphs are replaced
   by per-field help); raw Redis/null/schema/fence/capability-ID vocabulary
   and source names moved into optional Technical details; the copy was
   checked against the runtime (counting-window semantics, margin threshold
   direction) and relabeled honestly (the old "Margins are positive safety
   cushions" wording replaced by signed-margin text, mode relabels,
   "Allowed provider tools" legend); all advanced functions remain
   available.

### 229-c evidence (exact)

Environment: owned disposable PostgreSQL (module fixture, self-
tearing-down), repo venv, Playwright Chromium against local uvicorn on a
free loopback port. Providers and email MOCKED; no real inference, no real
mail, no production `DATABASE_URL`.

- `tests/browser/test_admin_key_create_229b.py` — **12 passed** (27.43 s):
  the eight 229-b tests (one corrected: the invalid requests=`abc` case
  now asserts ONLY the flagged control, the per-field remedy with real
  units and default behavior, the preserved nonsecret value, then
  correction and successful issuance) plus four NEW tests —
  `test_live_access_summary_reflects_current_choices` (row values track the
  current choices, including the preset endpoints),
  `test_delivery_one_time_warnings_track_mode` (one-time warning for the
  no-email mode, email warning for send-now, "No browser plaintext"),
  `test_advanced_per_field_help_relationships` (four opened advanced
  groups, four help ids, four `aria-describedby` references, jargon out of
  the primary help), and `test_nojs_withholds_stale_live_summary`
  (summary withheld with an explanation, no stale defaults displayed).
- Reused unchanged suites re-run once after the template/JS change, the
  eight-file GUI/unit suite — **556 passed** (230.98 s)
  (`test_admin_key_create_routes`, `test_key_create_client_use_presets`,
  `test_admin_key_policy_207`, `test_admin_key_create_email_delivery_routes`,
  `test_admin_key_create_templates`, `test_admin_gui_completion_219`,
  `test_demo_web`, `test_admin_usability_inventory`), including
  `test_admin_key_create_routes.py` 39 passed with the corrected
  `test_create_numeric_error_flags_only_the_invalid_control`.
- REUSED unchanged (not re-run): `test_admin_key_create_client_use_postgres.py`
  13 passed, the rev16/17 GUI pin and readiness evidence, and 229-b's
  then-620 eight-file count (historical, not summed with the current 556).
- Fixture corrections in this continuation (assertions that encoded the old
  behavior): `test_admin_key_create_229b.py` (four falsely highlighted
  speed controls → the single flagged control),
  `test_admin_key_create_templates.py` (stale summary copy, per-field help
  ids, per-field ceiling wording), `test_key_create_client_use_presets.py`
  (detail anchoring: a single field anchors the control, multiple fields
  keep an empty anchor), `test_admin_key_policy_207.py` (per-field help
  ids; the rate-limit help lives in a collapsed group and must be opened
  before asserting its text).
- Doc guards `test_documentation_inventory`,
  `test_documentation_contract_drift`, `test_documentation_asof` —
  **44 passed**; `ruff check` on all changed Python files — all checks
  passed; `git diff --check` — clean.
- Screenshots in the owned task directory (for root review):
  `229c-create-summary-live.png`, `229c-create-one-field-error.png`,
  `229c-create-advanced-help.png`.
- Not run: no real provider traffic, no real email, no production DB, no
  full 128-worker harness; this continuation makes no live-provider
  qualification claim.

## 229-d continuation (2026-11-27, same PR #403)

Two bounded defects, both reproduced by root on the 229-c state:

1. **Widget-path summary staleness (real browser blocker).** The policy
   selector's primary interaction — selecting in the real available list
   and pressing "Add selected ->", selecting in the selected list and
   pressing "<- Remove selected", and choosing a server-side search
   result — sets the manual textarea programmatically, and no DOM `input`
   event fires. The 229-c live summary listened only for `input`/`change`
   on the manual controls, so after a widget Add/Remove/search selection
   the submitted value was correct but the visible summary stayed stale
   (e.g. "Models: None yet" while the textarea already held the token).
   Fix (code + template only): `policy-selector.js` now dispatches one
   shared `slaif:policy-manual-synced` CustomEvent from
   `syncManualFromSelected` — the single helper behind Add, Remove, and
   the search `choose()` path — after every programmatic manual sync, and
   the key-creation summary IIFE subscribes to that event and refreshes.
   No observers, no polling, no framework; listeners only read form
   state, so the event cannot recurse. Preset endpoint ownership,
   document mode, and manual typing (real `input` events) are untouched.
2. **Email recovery copy overstated the one-way rule.** The create-form
   delivery warning/help and the server delivery summary texts said a
   failed/queued email's key "cannot be resent" universally. The actual
   law in `email_delivery_service.py`: the one-time secret is consumed
   only after SMTP success; a failed safe attempt may still hold the
   unconsumed secret; the existing retry-failed flow retries ONLY what
   sendability permits (sent, sending, ambiguous, consumed, and expired
   secrets are never retried). The copy now says: check the Email
   delivery result, use the existing retry action only when it is
   permitted, and rotate or reissue the key if delivery is ambiguous or
   the secret is unavailable. Text-only; no workflow, endpoint, or
   sendability change.

A test-only finding (no source change): in the Playwright fixture, the
browser scrolls a freshly focused multi-select into view during
mousedown, and Playwright's fixed-coordinate mouseup then lands on the
pre-scroll position, so the click gesture — and its `change` event — does
not complete on the option even though the option is selected. The new
test therefore keeps each widget select fully in view before option
clicks, the same posture a real operator uses.

Evidence (this continuation):
- `tests/browser/test_admin_key_create_229b.py` — **13 passed** (31.47 s),
  adding `test_policy_selector_widgets_update_live_summary`: a real
  endpoint Add via the widgets, a server-side model search selection, a
  model Add via the available list + Add button, a model Remove via the
  selected list + Remove button, a provider Add/Remove cycle, and a
  preset-endpoint Remove with Hermes ownership surviving — each step
  asserting BOTH the submitted manual value and the visible summary row.
  Screenshot `229d-create-summary-widget-path.png` in the owned task
  directory.
- Reused unchanged suites re-run once after the template/JS change, the
  eight-file GUI/unit suite — **556 passed** (229.83 s)
  (`test_admin_key_create_routes`, `test_key_create_client_use_presets`,
  `test_admin_key_policy_207`, `test_admin_key_create_email_delivery_routes`,
  `test_admin_key_create_templates`, `test_admin_gui_completion_219`,
  `test_demo_web`, `test_admin_usability_inventory`).
- `test_admin_key_create_routes.py` + `test_admin_key_create_templates.py`
  — **47 passed** (19.04 s), with the new assertions that the create
  template carries the recovery wording ("check the Email delivery
  result", "only when it is permitted", "rotate or reissue the key") and
  no longer claims "the key cannot be resent".
- REUSED unchanged (not re-run): `test_admin_key_create_client_use_postgres.py`
  13 passed, the rev16/17 GUI pin and readiness evidence, the email
  sendability/retry integration coverage, and the security/accounting
  suites.
- Doc guards `test_documentation_inventory`,
  `test_documentation_contract_drift`, `test_documentation_asof` —
  **44 passed**; `ruff check` on all changed Python files — all checks
  passed; `git diff --check` — clean.
- Changed files: `app/slaif_gateway/api/admin.py` (delivery summary
  texts), `app/slaif_gateway/web/templates/keys/create.html` (summary
  subscription + delivery wording),
  `app/slaif_gateway/web/static/js/policy-selector.js` (shared
  post-mutation notification), `tests/browser/test_admin_key_create_229b.py`,
  `tests/unit/test_admin_key_create_templates.py`, and the docs named in
  the commit.
- Not run: no real provider traffic, no real email, no production DB, no
  full 128-worker harness; this continuation makes no live-provider
  qualification claim.

## 229-e continuation (2026-11-27, same PR #403)

Final-CI repair on the 229-d head, from root's exact-head CI run
46064198175 (implementation 4cc0b2d5, report SELF 7f4eec9c). Exactly two
jobs failed: unit/lint job 140725539904 — **2 failed, 8943 passed, 1
skipped** — and browser job 140725539535 — **11 failed, 134 passed**.
PostgreSQL, E2E, Docker, documentation, both security workflows, and the
CodeQL aggregate PASSED; main was unchanged; PR #403 was
ready/unmerged/no auto-merge. One failure was a real shared-template
product regression; the other three were fixture, portability, and
test-alignment issues in tests only. No redesign, no schema, preset/DATA,
migration, existing-key/permissions/quotas, or request-runtime change.

1. **Shared create-result template regression (product code).**
   `tests/unit/test_admin_keys_routes.py::test_create_key_from_template_creates_one_key_result`
   POSTed the template-create path and got 500: Jinja `UndefinedError:
   'client_module_pins' is undefined`. The shared
   `keys/create_result.html` gained the optional pin explanation in
   229-b, but only the NATIVE create caller supplied
   `client_module_pins`; the template-create caller did not. Fix (code +
   template only): the template now defaults the variable to `{}` before
   first use, and the template caller passes
   `_safe_client_module_pins(...)` derived from the stored template
   snapshot's `responses_policy` (chat is never pinned by template
   creation, so `None`). No key or template metadata is changed; native
   creation still shows the correct pin facts, and template creation
   renders successfully. New regressions in
   `tests/unit/test_admin_key_create_templates.py`: the result template
   renders WITHOUT any pin context (no fabricated pin facts), and it
   shows the stored Responses pin (id, `v8`, digest prefix, no chat row)
   when present.
2. **Portable browser screenshot artifacts (test portability).** Nine
   failures in `tests/browser/test_admin_key_create_229b.py` tried to
   write the personal path `/home/janezp/codex-work/slaif-229-task`,
   which does not exist on the CI runner. Replaced with a session-scoped
   `artifact_dir` fixture: a pytest temporary directory (0700) by
   default — no setup, no personal home, no privileged permission, no
   repository write — with an explicit test-only `SLAIF_229B_ARTIFACT_DIR`
   override for operator-owned local provenance. ALL ten screenshot call
   sites (helper and direct full-page/element screenshots) route through
   the fixture. No skips, no catch-and-ignore, no CI-side `/home/janezp`
   creation; the existing private screenshots in the owned task directory
   stay as review provenance.
3. **Date-dependent unit fixture (test clock).**
   `tests/unit/test_cli_keys_effective_policy.py::test_policy_effective_json_shape`
   built its fixture key around a hardcoded `NOW = 2026-10-28`; with
   `valid_until = NOW + 30 days`, the key genuinely expired on
   2026-11-27, and the code correctly reported `expired` where the test
   expected active. The production expiry/authorization logic is correct
   and untouched. Fix: the test clock is now wall-clock relative
   (`datetime.now(UTC)`), so the fixture key is valid from shortly before
   the run until 30 days after the run against the same clock the
   inspection checks. Expired/future-key negative behavior stays covered
   by `tests/unit/test_key_policy_inspection.py`, which drives the
   injected `now` seam of `build_key_policy_inspection` directly.
4. **Lazy-throttling browser alignment (test fixture).** Two failures in
   `tests/browser/test_admin_lazy_throttling.py` after the intentional
   229-c layout/help changes. (a) The old literal combined ceiling
   sentence no longer exists on the create form; the test now asserts
   the ACTUAL per-field help ceilings ("the operator ceiling of 120
   seconds", "the operator ceiling of 16") that 229-c renders. (b) The
   lazy-throttling fields live inside the new native
   "Request speed controls" `<details>` disclosure (closed by default);
   both tests now open it by clicking its summary — a browser built-in,
   so the no-JS context works without any script. The full wait
   create → detail → update → back-to-reject flow, the persisted wait
   policy, the escaped invalid-bounds redisplay, and the no-JS create
   all still execute and assert exactly as before; no waiting/ceiling/
   security assertion was weakened, and no hidden control is forced open
   with JS. No product regression was exposed once the tests could reach
   the controls.

Evidence (this continuation):
- `tests/unit/test_cli_keys_effective_policy.py` +
  `tests/unit/test_admin_keys_routes.py` — **56 passed** (30.01 s),
  including the previously failing template-create node and the
  relative-clock `test_policy_effective_json_shape`.
- `tests/unit/test_admin_key_create_templates.py` — **10 passed** (5.33
  s) with the two new result-template regressions.
- `tests/browser/test_admin_key_create_229b.py` (13) +
  `tests/browser/test_admin_lazy_throttling.py` (3) — **16 passed**
  (45.26 s) against the owned disposable PostgreSQL and actual
  Chromium; all 10 creation screenshots verified inside the test-owned
  0700 temporary artifacts directory, and the old owned task directory
  untouched.
- `ruff check` on all changed Python files — all checks passed;
  `git diff --check` — clean; doc guards
  (`test_documentation_inventory`, `test_documentation_contract_drift`,
  `test_documentation_asof`) — **44 passed**.
- REUSED unchanged (not re-run): `test_admin_key_create_client_use_postgres.py`
  13 passed (its line-476 "Responses client module" assertion already
  proves the native pin-facts display), the rev16/17 GUI pin and
  readiness evidence, the email sendability/retry integration coverage,
  and the security/accounting suites.
- Not run yet: the broad CI rerun on the new final head is the remaining
  required gate (root-owned); no real provider traffic, no real email,
  no production DB, no full 128-worker harness in this continuation.
- Operator notes: none affected — the shared-template fix changes no
  operator-visible text or workflow beyond rendering the already-existing
  pin explanation for every legitimate create-result caller.
