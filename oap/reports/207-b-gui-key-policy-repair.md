# OAP Coding-Agent Report — 207-b

## Work order
- Identifier: 207-b
- Work-order file: `oap/orders/207-b-gui-key-policy-repair.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `216bdaa14db2cded4ecae7e3b1158e36a2276f1f05a8ca493e8db76b69cd81b7`)
- `oap/active` pointer: value `207-b` (5 bytes, no trailing newline),
  committed in IMPL; sha256
  `34a1afb8e086c51be421220a1f1acc7c348d1afb3fad7fe19114cb6ffbd9e3da`
- Numeric objective: 207
- PR mode: AMEND_EXISTING_PR (PR 363 "Complete GUI key policy and
  rate administration"; branch `oap/207-gui-key-policy`; base main at
  `67604ad6970ff8486e0a9905fdb87ffd37060bd2`; the SAME unique
  objective-207 PR as 207-a — no second PR was opened)
- Implementation head SHA (literal):
  `59b2561db6eb3ce214da715bb8dadff41402bc3f`
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

ALL 207-b ORDER REQUIREMENTS IMPLEMENTED; FOCUSED LOCAL VERIFICATION
GREEN. The 207-a history remains immutable and PARTIAL (FORMAT-
GATE-FAILED on the immutable 207-a order bytes, reported without
waiver in its own report); with the correctly formatted 207-b order
now committed and active, the two A-era format gates pass on this head
(9/9 OAP governance). GitHub CI on this head was IN PROGRESS at
publication (treated as pending, not pass); the A-head CI failures are
all repaired in this head with the local evidence below. Strategic
review and guarded merge remain root-owned. No release/tag/deploy
claim, and no completion claim beyond the 207-b scope.

## Repairs delivered (per order requirement)

1. **Protected new/touched key-form error output and retained values
   (requirement 1), scoped by value kind** using the existing
   redaction rules (recognized shapes plus configured accepted key
   prefixes; no redesign, no DOM/Jinja redactor, no capture):
   - credential-shaped MODEL identifiers in the create (guided AND
     document), policy, and configuration policy inputs are refused
     with a fixed safe message BEFORE the shared validators (whose
     safe message embeds the rejected model and was the (a) leak);
   - reasons and the other retained form values (the malformed-JSON
     (b) and numeric-rate (c) leak paths) are MASKED in every
     retained surface — re-rendered form, flash/error text, audit
     note, and failure logs — and a valid change with a
     credential-shaped reason still succeeds, stored and redisplayed
     masked;
   - the explain-model-access action keeps sending the ORIGINAL input
     to the UNCHANGED shared classifier and masks only the retained
     re-displayed form values.
   Rejected raw JSON is never retained; useful ordinary values and
   HTML escaping are preserved; the legitimate one-time plaintext
   creation result is unchanged and intentional.
2. **Configuration download authenticates WITHOUT rotating form CSRF
   (requirement 2).** `download_admin_key_configuration` now uses a
   read-only `_admin_attachment_context` (same real session
   validation, active/expired/revoked checks, login-cookie behavior)
   that does NOT refresh the stored CSRF; mutation CSRF,
   authorization, and the page render/session design are unchanged.
   The browser case was rewritten to the order's required chronology:
   load detail -> download the same-page attachment -> edit through
   the SAME still-displayed form/token (no reload, page.goto, token
   swap, or injected token); the A-era "download before render"
   workaround is removed.
3. **Bounded reasons on the new/touched mutations (requirement 3).**
   Key create (guided and document), policy update, rate edit, and
   configuration update enforce server-side nonblank / at-most-512-
   Unicode-character reasons (`_admin_bounded_reason`, using the
   existing schema constant `MAX_KEY_CONFIGURATION_REASON_LENGTH`),
   with the fixed safe refusal BEFORE mutation or audit, and matching
   `maxlength` plus visible field help. This is a GUI-side seam
   bound: the constant was previously unused and the UNCHANGED CLI is
   not claimed to enforce it. Exactly 512 valid / 513 refused and
   Unicode character behavior are asserted; credential-shaped
   reasons are masked like every other value. Legacy operations,
   CLI/service contracts, and schema are untouched.
4. **Qualified real document-mode creation and actual-control visuals
   (requirement 4).** NEW browser case: guided policy checkboxes
   reset to off in document mode (JS law), one strict version-1
   document as the single policy source, 200 result page with the
   intentional one-time plaintext key rendered exactly once
   (booleans-only assertion — the generated value is never printed),
   then navigate away before any capture; persisted canonical state
   proven by direct-DB oracle (providers `["openai"]`, models
   `["gpt-test"]`, endpoints `["/v1/chat/completions"]`, cost
   `5.000000000`, rate 3/15s, inherited concurrency/tokens) AND by
   the canonical `configuration.json` export; provider tri-state
   mutual exclusion re-verified intact afterward. Screenshots are now
   FOCUSED element captures of the actual new controls (create
   policy-source section, create provider controls, document-mode
   create form, effective-policy readout, rate editor, explain
   panel, plus 480px narrow captures including the rate editor),
   because the A-era whole-page captures showed only the page-top
   identity.
5. **Preserved accepted 207 functionality and architecture
   (requirement 5).** Null/unrestricted vs `[]`/deny-all vs selected
   providers, disabled-provider preservation, no-mode empty fail-
   closed, strict 64 KiB canonical JSON and exact Decimals,
   absence/null/`[]` semantics, bound-module guard, positive rate
   controls/no-op/set/clear with nested `window_seconds`
   preservation, read-only configuration-only explain and effective
   reports, one-time creation result, and legacy lazy throttling are
   all preserved by the unchanged component proof plus the B
   regressions. No request acceptance, tool/route permission,
   accounting, quota, replay, or credential authority changes;
   PostgreSQL remains authoritative; no provider/SMTP calls.

## Exact changed paths (16, IMPL)

Product (207 key handlers/rendering and focused session helper only):
- `app/slaif_gateway/api/admin.py` — the four B repairs above at the
  touched seams (model-shape guards; redacted retained form/flash/
  audit/log values; `_admin_attachment_context`; `_admin_bounded_
  reason` + field wiring). No service-contract, schema, migration,
  auth, or accounting change.
- `app/slaif_gateway/web/templates/keys/create.html` — reason
  `maxlength=512` + `create-reason-help` field help/aria.
- `app/slaif_gateway/web/templates/keys/detail.html` — reason
  `maxlength=512` + field help on the policy/rate/config forms;
  effective-policy rate/quotas and rate-editor source summary now
  render token quantities in M (exact count in `title`) with request
  counts in plain `num`; Responses profile `</dd>` placement fixed.

Tests (existing 207 files + minimal directly affected oracles):
- `tests/unit/test_admin_key_policy_207.py` (+16 B cases on the 49 A
  cases)
- `tests/integration/test_admin_key_policy_207_postgres.py` (+3 B
  cases)
- `tests/browser/test_admin_key_policy_207.py` (+1 document-mode
  create case; same-page download chronology; focused element
  screenshots; reason-help assertion)
- `tests/browser/test_admin_numeric_display_206.py` (locator
  disambiguates the new "Rate limits" readout row from the legacy
  summary)
- `tests/integration/test_admin_key_create_postgres.py` and
  `tests/integration/test_admin_key_email_delivery_postgres.py`
  (create payloads given the explicit `allow_all_providers: "true"`
  — the A CI 400-vs-200 fixture omissions)
- `tests/unit/test_admin_key_create_email_delivery_routes.py` (same
  fixture correction for the unit seam)

Docs and OAP state:
- `docs/verification/gui-cli-parity.md` (single living record: A
  history preserved as written; 207-b repair round appended; A-era
  "download before render" workaround marked superseded; A-era
  claims that reasons were bounded / all canaries covered corrected)
- `docs/admin-usability.md` (section 8 now 207-a + 207-b)
- `docs/MISSING_GUI_FUNCTIONALITY.md` (section 9 repaired-by-207-b
  subsection; delivery line updated)
- `docs/verification/README.md` (new 207-b index entry)
- `oap/orders/207-b-gui-key-policy-repair.md` (exact bytes)
- `oap/active` (`207-b`)

Preserved immutable: `oap/orders/207-a-gui-key-policy.md` (sha256
`a3e959226d2429ccc7f2d4d62603bf2e779304ae9d444394eb42959c52b5bbd0`),
`oap/reports/207-a-gui-key-policy.md` (sha256
`318f825ffb73fe826839037297bb4cc8c33d3fb6bc7200b8692da4b5abcad412`),
all earlier orders/reports, and the OAP governance tests (unedited).
NOT committed (protected/ignored, unchanged): `CODEX-SESSIONS.md`,
`codex.sh`, `.local-provider-catalog/`, `.codex/`, and all other
unrelated state. No reset/clean/stash was used.

## Requirement proof (native / mocked / real distinctions)

- Unit layer (fake-session ASGI; no DB, no server, no real
  provider/mail): the three repaired leak paths with recognized
  synthetic canaries and ordinary-value controls; a full plausible
  key-shape canary (43-char secret; plausibility verified with the
  accepted-prefix parser); `allowed_models: null` as a legal explicit
  clear; 512-valid / 513-refused with no mutation on refusal and
  Unicode character behavior; explain display masking with the
  classifier receiving the original input; stateful CSRF download
  without rotation.
- Owned-PostgreSQL layer (real owned, labeled, loopback-bound,
  tmpfs-backed PostgreSQL 16 container; real schema/migrations; real
  ASGI app through TestClient; exact container removed on teardown):
  same-page download does not rotate the page CSRF (detail ->
  attachment -> same-form edit 303); 512/513 bound with no
  mutation/audit on refusal (audit-count baseline, since the shared
  module seed persists across the file); document-create canary
  refusal without persistence.
- Actual-page layer (real Chromium + real uvicorn + real stylesheet
  on the same owned PostgreSQL): strict document-mode create
  (persisted canonical state + export); detail -> download -> SAME
  still-displayed form edit; focused element screenshots of the new
  controls; no-JS fallback and narrow layout preserved.

## Focused test evidence (local; GitHub CI pending)

207-b (this head; JUnit in the execution workdir `/tmp/slaif207/`,
not committed):
- Unit: `tests/unit/test_admin_key_policy_207.py` 65 PASS, 0 skip
  (`unit-b-4.xml`; 49 A + 16 B). Directly affected existing unit
  suites (key-create routes, key-create email-delivery routes, OAP
  governance): 101 PASS, 0 skip (`unit-b-1.xml`).
- Owned-PostgreSQL: 12 PASS, 0 fail / 0 error / 0 skip
  (`pg-b-1.xml`; 7 A + 3 B + 2 directly-affected A PG fixtures).
- Browser: full 207 suite 7 PASS, 0 fail / 0 error / 0 skip
  (`browser-207b-1.xml`); the two cases touched after first green
  (one-time-result opaque-boolean assertion; 480px rate-editor
  capture) rerun 2 PASS (`browser-207b-pair-1.xml`); affected 206
  numeric-display case 1 PASS (`browser-207b-206-1.xml`). The other
  five 207 browser cases are component evidence for the unchanged
  flows (overlapping runs are not summed).
- OAP governance: 9 PASS, 0 skip (`gov-b-1.xml`) with the formatted
  207-b order and `oap/active=207-b`.
- Static: `ruff check` on all touched Python files clean; `git diff
  --check` clean; `scripts/check_documentation.py`
  `DOCUMENTATION_CHECK=OK files=135`.

207-a (reused component proof, NOT rerun; immutable report
`oap/reports/207-a-gui-key-policy.md`): 49 new unit + 168 combined
unit + 282 affected unit PASS, 7 owned-PostgreSQL PASS, 6 actual
Chromium/owned-PG PASS.

## CI chronology (A head -> B head)

- A head `f0f5d13` (207-a SELF), CI run 41229112374, all failures
  routine and now repaired in this head with the local evidence
  above: unit job (7 failures: the 2 known A governance-FORMAT
  cases + 5 email-delivery route cases whose fixtures omitted the
  now-explicit provider mode), PostgreSQL job 124619365455 (2
  failures: `test_admin_key_create_form_postgres` and
  `test_admin_key_email_delivery_modes_postgres`, 400-vs-200, same
  fixture omission; 525 passed / 9 skipped), browser job 124619365533
  (1 failure: the 206 numeric-display case whose "Rate limits"
  locator matched the new readout row AND the legacy summary). The
  format-gate failures are resolved by the formatted 207-b order
  itself; the fixture and locator failures by the minimal
  in-order corrections. A history stays recorded as it was.
- B head `59b2561` (this IMPL): CI run 41234140436 and CodeQL
  41234140445 were in_progress at publication (PENDING, not pass);
  strategic verification owns the final-head result.

## Privacy / authorization / accounting / replay invariants

- Scoped credential protection (no broader claim): model-shape
  refusal before the shared validators on the policy inputs;
  masking (never refusal) of credential-shaped reasons/retained
  values, with a valid masked change still succeeding; the explain
  classifier unchanged on the original input with only the retained
  display masked. Recognized shapes appear nowhere in responses,
  flash, logs, audit notes, or exports (asserted).
- The attachment is the service's allowlisted projection only:
  policy fields, never identity/secret/environment; `attachment`
  with `Cache-Control: no-store`; and it no longer rotates the form
  CSRF (asserted statefully). Mutation CSRF, session, and
  authorization are unchanged; unauthenticated and invalid-CSRF
  requests are still refused before any service call.
- Rate/policy/configuration edits never touch usage counters,
  reservations, key material, status, validity, or replay/module
  binding (row-snapshot assertions); explain/inspections never
  write (audit-trail assertions); the 513 refusal performs no
  mutation and no audit write (baseline assertions).
- No schema, table, migration, client/server module, provider-
  transport, admission/accounting/replay, or catalog change; no new
  framework, dependency, or logger.

## Deployment / upgrade guidance

Normal rebuild/restart of the API assets picks up the code and static
assets. There is NO schema migration and NO policy mass-update.
Historical deny-all keys stay deny-all and stored allow-lists keep
their values. Operator-visible behavior changes: (1) an empty
provider selection with no mode checked FAILS CLOSED (207-a); (2) a
reason longer than 512 characters on a new/touched key mutation is
refused with a fixed message (no mutation, no audit row), and the
affected fields show `maxlength=512` plus visible help; (3) the
configuration download no longer invalidates the still-displayed
form token. No deploy was performed.

## Documentation impact

- `docs/verification/gui-cli-parity.md`: the single living record now
  carries the A history as written plus the 207-b repair round
  (demonstrated gaps, scoped repairs, focused evidence, static/gov
  checks, corrected status); the A-era "download before render"
  workaround is marked superseded; the earlier claims that reasons
  were bounded and all canaries were covered are explicitly
  corrected.
- `docs/admin-usability.md`: section 8 is now "207-a + 207-b"
  (scoped credential protection, non-rotating download, GUI-side
  reason bound, upgrade notes).
- `docs/MISSING_GUI_FUNCTIONALITY.md`: section 9 gains the
  "Repaired by 207-b" subsection; G04-G18 remain open.
- `docs/verification/README.md`: new 207-b index entry (207-a entry
  preserved).

## Pending and honest limitations

- GitHub CI on the report head: PENDING at publication (treated as
  pending, not pass); root's final-head checks and review gate the
  merge.
- The unit renders are fake-session ASGI renders (no DB); the owned-
  PG cases are the real-schema proof; the Chromium cases are the
  actual-page proof. No real provider, email, or production traffic
  is involved.
- The GUI parity is at the shared-code level (same parser, same
  `KeyService` operations, same inspection/explain projections as the
  CLI); the CLI itself is not re-qualified here. The 512 reason
  bound is GUI-side; the unchanged CLI is not claimed to enforce it.
- JUnit XML files and screenshots live in the execution workdir
  (`/tmp/slaif207/`), not in the repository.
- The 207-a report remains immutable and PARTIAL; nothing in this
  report rewrites or supersedes A's recorded state.
