# 2026-10-31 objective 207 GUI key policy administration verification (207-a + 207-b)

Focused verification record for the 207 admin GUI key-policy
administration change (G01-G03 of `docs/MISSING_GUI_FUNCTIONALITY.md`):
provider tri-state + advanced versioned configuration, existing-key
operational rate editor, and effective-policy inspection with
configuration-only "explain model access"). The GUI surfaces REUSE the
already-qualified shared services and projections; no database schema,
table, migration, client/server module, or sortable table was added.

The 207-a record below is preserved as written at its publication (it
was PUBLISHED AS PARTIAL — the OAP governance format gate failed on
the immutable 207-a order bytes, see the A-era section below).
207-b (same PR363) repaired the demonstrated privacy, same-page
download, and reason-bound gaps in those same surfaces; the
"207-b repair round" section below supersedes the A-era claims where
they conflict.

## Scope and GUI-CLI parity contract

The whole point of 207-a is that the admin GUI cannot drift from the
CLI: each new surface calls the SAME shared code the CLI calls.

- **G01 provider tri-state + advanced configuration.** Key creation and
  existing-key policy edits express exactly one of: allow-all
  (unrestricted, stored `null`), an explicit allow-list (stored list;
  disabled or older stored providers preserved on save), or deny-all
  (stored `[]`, explicit). Neither-mode + empty selection fails closed.
  The create page additionally accepts one advanced version-1
  configuration document and the key detail page applies one - both
  through the SAME strict `key_configuration` parser, bounds, and
  presence-aware canonical semantics as the CLI
  `keys policy update --policy-file` (omitted preserves; `null` vs `[]`
  distinct; exact 9-dp Decimal handling; unknown/duplicate fields and
  >64 KB documents refused). The detail page serves the SAME allowlisted
  canonical export the CLI renders, as a private no-store attachment.
- **G02 rate editor.** The per-member editor (requests per window,
  tokens per window, concurrency, window seconds; leave-unchanged / set
  / clear) applies the SAME positive-integer law, zero-is-not-a-value,
  clear-to-inherit, and no-op refusal as the CLI
  `keys set-rate-limits`, through the same audited `KeyService`
  operation.
- **G03 inspection + explain.** The key detail renders the shared
  `build_key_policy_inspection` projection (configured/effective/source
  per control, provider state, quotas, lazy throttling, Redis-disabled
  caveat) and the "Explain Model Access" form reuses the exact shared
  `explain_model_route_access` projection of the CLI
  `keys policy explain-route` (`resolved` / `blocked` / `not-evaluated`
  verdicts, blockers, bounds, not-evaluated states, bounded route
  examination). Both are configuration-only: no authentication as the
  key, no admission/quota/pricing check, no counter reset, no provider
  call, no writes.

Ergonomics (order requirement 5): every touched control carries
`aria-describedby` field help; new blocks are grouped field cards, and
no new `<table>` element was introduced.

## Implementation

- `app/slaif_gateway/api/admin.py`: new routes
  `POST /admin/keys/{id}/rate-limits`, `GET /admin/keys/{id}/
  configuration.json`, `POST /admin/keys/{id}/configuration`,
  `POST /admin/keys/{id}/explain-route`; tri-state parsing/prefill and
  policy-source (guided vs one version-1 document) handling on the
  create and policy-update paths; fixed safe errors only (a rejected
  document is never retained in the re-rendered form, flash, logs, or
  audit). No service-contract, schema, migration, auth, or accounting
  change.
- `app/slaif_gateway/web/templates/keys/{_policy_selector,create,
  detail}.html`: the tri-state controls, the policy-source section, the
  effective-policy readout, the rate editor, the explain panel, and the
  advanced configuration section; all with field help and no new tables.
- `app/slaif_gateway/web/static/js/policy-selector.js`: provider mode
  mutual exclusion, selection-grid locking, and the document-mode reset
  of guided POLICY controls only (guarded so guided-mode explicit
  defaults are preserved; identity fields always stay guided).
- `app/slaif_gateway/web/static/css/admin.css`: minimal additions for
  the new field cards (existing card/typography patterns).

## Focused test evidence (local; GitHub CI pending)

Layer: native unit (ASGI app with the existing fake-session seams; no
DB, no server, no real provider/mail).

- `tests/unit/test_admin_key_policy_207.py` (NEW): 49 PASS, 0 skip
  (JUnit `unit-207.xml`). Covers: the tri-state parse law (allow-all /
  selected / deny-all, both-modes refusal, empty-without-mode fail-
  closed, unknown-slug and credential-shaped-slug refusal); form
  prefill; the rate-policy compose law (set/clear, 1-per-10s +
  concurrency 1, zero/blank/unknown-action refusal, no-op detection,
  prefill); the rate-limit route (unauthenticated redirect, invalid
  CSRF before service, missing reason, no-op refusal, set/clear
  payloads with the session actor, zero refusal with the fixed
  message, 404); the configuration download (unauthenticated, headers +
  exact 9-dp decimals, export-error 409); the configuration POST
  (missing reason/confirmation/empty/malformed/duplicate-key/unknown-
  field/missing-schema-version/empty-object refusals WITHOUT echo of a
  credential-shaped canary, success payload, safe service-error
  message); the explain route (unauthenticated, shared-report render
  with the exact shared kwargs, 503 fixed message on context failure);
  the existing-key policy-update tri-state persistence (both-modes,
  fail-closed, deny-all `[]`, allow-all `null`, disabled-provider
  preservation, unknown-provider refusal); and the create document mode
  (missing document, document+guided-policy refusal, Codex-preset
  refusal, trusted-calibration deny-all refusal, success building the
  shared input, error re-render scrubbing the document).
- `tests/unit/test_admin_usability_inventory.py` (updated): the new
  detail-page select fields are inventoried; combined 207-unit +
  inventory run 168 PASS, 0 skip (JUnit `unit-207b.xml` /
  `unit-207c.xml`).
- Directly affected existing admin suites (key create routes/templates,
  key actions routes, 194 table rows, usability inventory, and the
  other touched oracles): 282 PASS, 0 skip (JUnit `affected2.xml`).

Layer: actual owned, labeled, loopback-bound, tmpfs-backed PostgreSQL 16
container (fixture generator from
`tests/integration/test_lazy_throttling_postgres_redis.py`), real
schema/migrations, real ASGI app through `TestClient` (no browser);
exact created container removed on teardown.

- `tests/integration/test_admin_key_policy_207_postgres.py` (NEW):
  7 PASS, 0 fail / 0 error / 0 skip (JUnit `pg-207a-1.xml`). Covers the
  tri-state persistence against the real schema (including deny-all
  `[]` and disabled-provider preservation), the rate editor
  (set 1/10s + concurrency 1, zero/no-op refusals, clear with sibling
  preservation), the configuration export/update round-trip (allowlisted
  projection headers, partial update, unknown-field refusal without
  echo), and the explain route (resolved/blocked/not-evaluated with the
  audit trail and the full key-row snapshot unchanged: inspections
  never write).

Layer: actual Chromium on the same owned PostgreSQL with a real uvicorn
app and real stylesheet (real HTTP admin pages end to end).

- `tests/browser/test_admin_key_policy_207.py` (NEW): 6 PASS, 0
  fail / 0 error / 0 skip (JUnit `browser-207a-7.xml`). (1) Create form:
  the five field-help anchors present and non-empty with matching
  `aria-describedby`, the JS provider-mode mutual exclusion, and three
  creates persisted through the real form (allow-all default,
  allow-list, deny-all). (2) Existing-key policy: empty-selection
  fail-closed refusal, disabled-provider preservation with the
  `slug | manual entry` label, and adding a provider. (3) Rate editor:
  prefill of the stored 500, zero and no-op refusals, set 1/10s +
  concurrency 1 with the configured/source/effective readout, isolation
  snapshot of untouched members, and clear with sibling preservation.
  (4) Configuration: allowlisted export as a private no-store
  attachment (forbidden fields absent), a canonical
  `requests_per_minute` partial update with sibling/allow-list
  preservation, an unknown-field credential-shaped canary refused with
  fixed message, no echo, and an emptied re-rendered textarea, plus the
  confirmation and reason refusals. (5) Explain: resolved, unknown-
  model blocked, cross-provider blocked, and the audit-trail invariant
  (snapshot taken after the login, which itself audits
  `admin_login_succeeded`; the explain POSTs add zero rows). (6) No-JS
  fallback: plain-text owner field, manual provider textarea inside the
  collapsed disclosure, fail-closed policy submit, legacy lazy-
  throttling controls still usable, and the narrow 480px layout with no
  horizontal overflow.
- Screenshots (synthetic fixture data only, no key/session/secret
  cells): `/tmp/slaif207/key-create-form-desktop.png`,
  `/tmp/slaif207/key-detail-effective-policy.png`,
  `/tmp/slaif207/key-detail-rate-editor.png`,
  `/tmp/slaif207/key-explain-report.png`,
  `/tmp/slaif207/key-detail-narrow.png`.

## Defects found and fixed during qualification (provenance)

Two product defects and four test-side issues surfaced only on the
real-page layer and were fixed in this same order:

- **Product (create page script):** the document-mode inline script
  unconditionally unchecked every guided policy checkbox (including
  `allow_all_providers`) on load, so a guided create submitted the
  allow-all mode as off. The uncheck loop is now guarded to document
  mode only; guided-mode explicit defaults are preserved, and no-JS and
  JS guided creates express the same state (server law unchanged).
- **Product (explain form field name):** the explain select was named
  `explain_endpoint` while the handler (and the CLI/ASGI paths) read
  `endpoint`, so the real browser page always explained an empty
  endpoint (`not-evaluated`). The template select is now `endpoint`;
  the unit/integration oracles already posted `endpoint` directly and
  are unchanged in meaning.
- **Test-side (verdict rendering):** `.status-pill` CSS uppercases the
  verdict text, so the assertions compare the raw DOM text
  (`text_content().strip()`) instead of the rendered text.
- **Test-side (canonical member name):** the configuration update
  document used the rate-EDITOR display suffix `requests_per_window`;
  the strict version-1 schema member is `requests_per_minute`. The
  test document uses the canonical name; the page readout still shows
  the display name.
- **Test-side (audit snapshot + CSRF chronology):** the explain audit
  snapshot now happens after the login (login audits
  `admin_login_succeeded`), and the configuration export download is
  fetched BEFORE the form page was rendered — a workaround for the
  defect that the attachment GET rotated the stored CSRF token (every
  admin page render refreshes it, but the read-only attachment must
  not): a form page fetched before any other admin GET would carry a
  stale token. **Superseded by 207-b:** the attachment now
  authenticates through a non-rotating context, and the browser case
  loads the detail page FIRST, downloads, then edits the SAME
  still-displayed form. The empty-reason refusal block lifts the
  client-side `required` attribute first so the SERVER's fixed
  refusal, not native validation, is what is proven.
- **Test-side (readout whitespace):** the effective-policy rate readout
  renders each member as separate text nodes (`requests_per_window:`
  then, on the next line, `configured 7 (source: key)`), so the
  configuration-update assertion compares whitespace-normalized page
  text (`_flat`), exactly as the rate-editor case does. The persisted
  value itself is proven by the direct-DB oracle
  (`rate_requests == 7`).

## 207-b repair round (same PR363, 2026-10-31)

207-b (correctly formatted, now the active order on the same PR)
repaired three demonstrated gaps in the 207-a surfaces. The 207-a
report remains immutable; this section corrects the earlier claims
that reasons were bounded and that all canaries were covered.

### Demonstrated gaps (root probes: real ASGI/Jinja, synthetic canaries)

- **Credential-shaped values leaked into 400 HTML.** Three cases
  returned the COMPLETE synthetic canary: (a) an otherwise-valid
  version-1 `allowed_models` list carrying a canary reached the real
  shared `validate_gateway_key_policy`, whose safe message embeds
  the rejected model; (b) malformed JSON plus a canary in the reason;
  (c) a canary in a numeric rate input.
- **Same-page download rotated the form CSRF.** The attachment
  authenticated through `_admin_page_context`, which refreshes the
  stored CSRF while the displayed page keeps its old form token:
  detail 200, attachment 200, same-page old-token POST 400
  InvalidCSRF; fresh-token control 303. The A-era browser case
  avoided this by downloading before the page render.
- **Reasons unbounded on the new/touched mutations.** A valid
  fresh-token rate POST with a 513-character reason reached the
  service and 303'd; the 512 schema constant existed but was unused
  on these seams.

### Repairs (GUI seams only; no core/schema/service/CLI change)

- **Credential-shape guards at the touched seams, scoped by value
  kind** (recognized through the existing redaction rules, including
  configured accepted key prefixes; no redesign): (1) credential-
  shaped MODELS in the create (guided and document), policy, and
  configuration `allowed_models` are refused with a fixed safe
  message BEFORE the shared validators, whose safe message would
  otherwise embed the rejected model in the 400 HTML; (2) reasons
  and the other retained form values are MASKED — a valid change
  with a credential-shaped reason still succeeds, stored and
  redisplayed masked; (3) the explain-model-access action keeps
  sending the ORIGINAL input to the unchanged shared classifier and
  masks only the retained re-displayed form values. Masking covers
  the re-rendered form, flash/error text, the audit note, and
  failure logs; useful ordinary values are preserved unchanged, and
  no DOM/Jinja redactor, capture, or classifier change was added.
- **Non-rotating attachment authentication.**
  `download_admin_key_configuration` uses a read-only
  `_admin_attachment_context` (the same real session validation,
  active/expired/revoked checks, and login-cookie behavior) that
  does NOT refresh the stored CSRF; mutation CSRF, authorization,
  and the page render/session design are unchanged.
- **GUI-side reason bound.** The four new/touched mutation seams
  apply a server-side nonblank / at-most-512-Unicode-character bound
  (`_admin_bounded_reason`, matching the existing schema constant)
  with the fixed safe refusal BEFORE mutation or audit, and the
  fields carry `maxlength` plus visible help that agree with the
  server law; credential-shaped reasons are masked exactly like
  every other retained value. This bound is a GUI-side seam bound:
  the schema constant was previously unused and the unchanged CLI is
  NOT claimed to enforce it; no legacy operation, CLI/service
  contract, or schema was altered to introduce it.

### 207-b focused evidence (local; GitHub CI pending)

Layer: native unit (ASGI app with the existing fake-session seams; no
DB, no server, no real provider/mail).

- `tests/unit/test_admin_key_policy_207.py`: 65 PASS, 0 skip
  (JUnit `unit-b-4.xml`; the 49 A cases plus 16 B cases). The new
  cases cover the three repaired leak paths with recognized
  synthetic canaries (document-mode create canary model, guided
  create canary model, policy canary, configuration canary) with
  fixed safe refusals and no echo in HTML, flash, logs, or audit; a
  full plausible-key-shape canary (43-char secret, verified with the
  accepted-prefix parser); `allowed_models: null` as a legal explicit
  clear; the 512-valid / 513-refused bound with no mutation on
  refusal (rate, configuration, policy, create) and Unicode
  character behavior; the explain form re-display masking with the
  shared classifier still receiving the original input; and the
  stateful CSRF download without rotation.
- Directly affected existing unit suites (key-create routes,
  key-create email-delivery routes, OAP governance): 101 PASS, 0
  skip (JUnit `unit-b-1.xml`). The email-delivery route fixtures
  omitted the now-explicit provider mode and were given
  `allow_all_providers="true"` (unrestricted) — a fixture
  correction, not a behavior change.

Layer: actual owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL 16 container (same fixture generator), real
schema/migrations, real ASGI app through `TestClient` (no browser);
exact created container removed on teardown.

- `tests/integration/test_admin_key_policy_207_postgres.py` plus the
  directly affected A PG oracles: 12 PASS, 0 fail / 0 error / 0
  skip (JUnit `pg-b-1.xml`). New: the same-page download does not
  rotate the page CSRF (detail -> attachment -> same-form edit
  303), the 512/513 reason bound with no mutation/audit on refusal
  (audit-count baseline, because the shared module seed persists
  across the file), and the document-create canary-model refusal
  without persistence. The two A CI PG fixtures (create form,
  email-delivery modes) received the same explicit
  `allow_all_providers: "true"` fixture correction.

Layer: actual Chromium on the same owned PostgreSQL with a real
uvicorn app and real stylesheet (real HTTP admin pages end to end).

- `tests/browser/test_admin_key_policy_207.py`: 7 PASS, 0 fail / 0
  error / 0 skip (JUnit `browser-207b-1.xml`). NEW: strict
  document-mode create — the guided policy checkboxes reset to off,
  the version-1 document is the single policy source, the one-time
  plaintext result renders exactly once (booleans-only assertion),
  and the persisted state is verified by direct-DB oracle plus the
  canonical `configuration.json` export (providers/models/
  endpoints/cost/exact rate window), with the provider tri-state
  still intact afterward. CHANGED: the configuration case now loads
  the detail page FIRST, downloads the same-page attachment, and
  then edits through the SAME still-displayed form/token (no
  reload, page.goto, or token swap) — the A-era "download first"
  workaround is removed. FOCUSED: screenshots are now element
  captures of the actual new controls (create policy-source and
  provider sections, document-mode create form, effective-policy
  readout, rate editor, explain panel, plus 480px narrow captures
  including the rate editor), because whole-page captures showed
  only the page-top identity.
- The two cases touched after that first green (one-time-result
  opaque-boolean assertion; 480px rate-editor capture) reran to 2
  PASS (JUnit `browser-207b-pair-1.xml`); the other five 207 browser
  cases are component evidence for the unchanged flows, and the
  privacy/CSRF/reason repairs are additionally covered by the unit
  and PG layers above.
- The affected 206 numeric-display case
  (`test_admin_numeric_display_206.py::
  test_key_detail_live_burn_zero_and_raw_inputs`), whose locator now
  disambiguates the new "Rate limits" readout row from the legacy
  summary (direct-child Policy heading inside the detail section):
  1 PASS (JUnit `browser-207b-206-1.xml`).
- Screenshots (synthetic fixture data only, no key/session/secret
  cells): `/tmp/slaif207/key-create-policy-source.png`,
  `/tmp/slaif207/key-create-provider-controls.png`,
  `/tmp/slaif207/key-create-document-mode.png`,
  `/tmp/slaif207/key-detail-effective-policy.png`,
  `/tmp/slaif207/key-detail-rate-editor.png`,
  `/tmp/slaif207/key-explain-report.png`,
  `/tmp/slaif207/key-detail-narrow.png`,
  `/tmp/slaif207/key-detail-narrow-policy.png`,
  `/tmp/slaif207/key-detail-narrow-rate-editor.png`.

### 207-b static and governance checks

- `ruff check` on all touched Python files: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `tests/unit/test_oap_governance.py`: 9 PASS, 0 skip with the
  correctly formatted 207-b order and `oap/active=207-b` committed —
  the two A-era format gates no longer fail on the 207-b head.

## OAP governance format gate (207-a head; resolved by the 207-b order)

The activated immutable order
`oap/orders/207-a-gui-key-policy.md` (SHA256
`a3e959226d2429ccc7f2d4d62603bf2e779304ae9d444394eb42959c52b5bbd0`,
restored byte-exact from root's trusted preactivation copy) carried a
heading / PR-mode syntax that deviates from the durable governance
format used by orders 206-a through 206-d: line 1 was
`# OAP Work Order 207-a — GUI key policy, rate overrides and effective
inspection` instead of the required `# OAP Work Order — 207-a`, and
the round declares the new-PR mode as prose
(`PR mode: NEW_OBJECTIVE_NEW_PR.`) instead of the standalone
`PR mode: CREATE_NEW_PR` line the initial-round gate requires. Per the
strategic recovery decision, the activated input is published with its
exact original bytes and the governance tests were NOT loosened; this
clerical format issue is reported, not fixed. Consequence on this
head: `tests/unit/test_oap_governance.py` is 7 PASS / 2 FAIL —
`test_active_identifier_resolves_exactly_one_matching_order` and
`test_initial_round_declares_new_pr_and_one_objective_one_pr` failed on
the order format only; every other governance check passed. That
state is historical: with the correctly formatted 207-b order
committed and active, all nine governance checks pass on the 207-b
head (see the 207-b static and governance checks above).

## Static and governance checks

- `ruff check` on all touched Python files (admin.py + the four 207
  test files + the updated oracles): clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `tests/unit/test_oap_governance.py`: 7 PASS, 2 FAIL, 0 skip — the two
  OAP governance FORMAT gates listed above fail on the restored
  immutable order bytes (recorded without waiver, 207-a head); the
  other seven governance checks pass.

## Honesty and limitations

- The unit renders are fake-session ASGI renders (no DB); the owned-PG
  integration cases are the real-schema proof and the Chromium cases are
  the actual-page proof. No real provider, email, or production traffic
  is involved; no release claim.
- The GUI parity is at the shared-code level: the same parser, the same
  `KeyService` operation, and the same inspection/explain projections as
  the CLI. This record does not re-qualify the CLI itself (covered by
  the 197-204 CLI objective records).
- The configuration export is a projection: it carries policy only,
  never identity, never secrets, never server environment. Historical
  keys are untouched by this change (no migration, no mass update);
  deny-all keys stay deny-all and allow-lists keep their values. The
  operator-visible behavior change: an empty provider selection with no
  mode checked now fails closed instead of silently meaning
  unrestricted.
- Overall status is PARTIAL (FORMAT-GATE-FAILED): the product work and
 the focused product evidence above are complete and green, but this
 head fails the two OAP governance format gates on the immutable
 order bytes; the strategic same-PR continuation (207-b) has since
 resolved that on the same PR. No completion claim followed from the
 207-a head.
- GitHub CI on the report head is pending at publication (treated as
  pending, not pass); strategic review and guarded merge are the root's
  gates.
- Status on the 207-b head: the 207-a PARTIAL (FORMAT-GATE-FAILED)
  state is historical; the active order is the correctly formatted
  207-b, all nine governance checks pass, and the focused 207-b
  evidence above is green. GitHub CI on the 207-b report head is
  pending at publication (treated as pending, not pass).

## 208-a reviewed key cloning (objective 208, new PR, 2026-10-31)

208-a delivers G04 (faithful standard-key cloning) in the admin GUI by
reusing the already-qualified core `KeyCloneService` (reviewed-plan
build/execute, dedup, fingerprint revalidation, receipt, one-time
delivery) and the existing GUI seams (session/CSRF contexts, record
pickers, redaction, no-store headers). No schema, migration, model,
CLI, worker, or runtime-accounting change; the core's concurrency,
rollback, dedup, and replay laws are component evidence from the
qualified core/CLI rounds and are not re-run here.

### GUI-to-CLI mapping

| GUI surface | Reused core/CLI law |
| --- | --- |
| Guided clone form (source eligibility, target owner/cohort, three validity modes, delivery select) | `KeyCloneService.build_plan` (core decides eligibility; no GUI policy engine) |
| Review page (readable canonical policy, operation identity, signed intent) | strict `parse_clone_plan_document` plan; new purpose-bound review-intent token (HMAC-SHA256 over plan + actor/session/expiry/delivery) |
| Apply (confirm + bounded reason + fresh fenced checkbox when required) | `KeyCloneService.execute_plan` in the caller-owned transaction; dedup-first; fresh fingerprint/policy/public ID/expiry |
| One-time result (plaintext at most once, no-store; delivery after commit; "Created With Delivery Failure" recovery state) | existing one-time-secret / email-delivery services; post-commit dispatch only |
| Outcome recovery by source + operation | new READ-ONLY `find_clone_receipt` projection (created / not-found / ambiguous / malformed safe states) |

### Focused evidence (local; GitHub CI pending)

Layer: native unit (ASGI app with the existing fake-session seams; no
DB, no server, no real provider/mail).

- `tests/unit/test_admin_key_clone_208.py`: 47 PASS, 0 skip (JUnit
  `unit-208a-4.xml`). Coverage: intent round-trip, expiry at the
  boundary, wrong actor/session/secret, tamper, malformed formats
  (including the controlled non-ASCII digest refusal before
  comparison), builder decoded-plan and final-token size bounds with
  the full core-supported scope still building, controlled 404 for a
  vanished source (form AND re-render path), ineligible/secret-shaped
  source refusals with no token issued, apply confirmation/reason
  bounds (blank/513 refused), forged delivery field ignored (channel
  bound at review), fenced confirmation required/accepted,
  one-time plaintext exactly once with no-store headers,
  already-applied without redisplay or duplicate audit, post-commit
  send-now failure (synthetic `EmailError`) rendering "Created With
  Delivery Failure" with stable IDs and no plaintext, read-only
  recovery (created / not-found / ambiguous / malformed, including the
  two-ID-only malformed receipt) and the recovery operation-input
  canary redaction with ordinary UUID errors preserved, plus the
  window-aware rate readout (10s window labeled by the window; minute
  default keeps the per-minute grammar) and the lazy reject/wait mode
  controls.

Layer: actual owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL 16 container (same fixture generator), real
schema/migrations, real ASGI app through `TestClient` (no browser);
exact created container removed on teardown.

- `tests/integration/test_admin_key_clone_208_postgres.py`: 4 PASS,
  0 skip (JUnit `pg-208a-1.xml`). Faithful canonical clone to an
  ALTERNATE owner + cohort (the target controls are proven persisted,
  not ignored): policy columns and metadata blocks equal the source,
  exact 3601s window (non-minute, exact persisted timedelta), zero
  usage/reservations, independent token hash/public ID, receipt
  identity (operation UUID equal to the reviewed operation, source/
  target IDs, status created), source and unrelated-key snapshots
  unchanged, exact-repeat returning already-applied with no second
  key/audit/plaintext, stale (post-review source validity change) and
  tampered-token refusals proven by AFTER-change state snapshots and
  audit counts, committed clone with a post-commit SMTP failure
  (synthetic monkeypatch) showing "Created With Delivery Failure"
  plus the persisted pending delivery and recovery, suspended-source
  form/review controlled states, and the send-now precondition
  refusal when delivery is disabled.
- 207/208 coexistence: the 208 seed is get-or-create on the
  DB-unique provider slugs (existing repository pattern), so the 207
  and 208 modules pass together on one session database (14 PASS, 0
  skip; JUnit `pg-208a-coexist.xml`).

Layer: real Chromium on the owned fixture (Playwright sync, uvicorn
app, real stylesheet); exact created container removed on teardown.

- `tests/browser/test_admin_key_clone_208.py`: 3 PASS, 0 skip (JUnit
  `browser-208a-1.xml`). Key-detail clone entry with the preserved
  ordinary panels; guided form with the record pickers driven and a
  3601s duration; review page with the window-aware 10s rate readout
  and no key material; keyboard-only apply (focus/Space to confirm,
  typed reason, Enter to submit); one-time result asserted from HTML
  only (the plaintext page is NEVER screenshotted); persisted-target
  oracles (policy fidelity, zero usage, receipt, exact window, audit
  count, source unchanged); exact-repeat via the same still-valid
  token through a form POST; recovery created/not-found views; the
  no-JS typed-UUID fallback carried through to the persisted
  no-cohort target; and a narrow-viewport (768px) review capture.
  Focused screenshots (synthetic data only, no key/session/secret
  cells) under `/tmp/slaif208/`.

### Static and governance checks

- `ruff check` on all touched/new Python files: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `tests/unit/test_oap_governance.py`: 9 PASS, 0 skip.

### Honesty and limitations

- The unit renders are fake-session ASGI renders (no DB); the
  owned-PG cases are the real-schema proof and the Chromium cases are
  the actual-page proof. No real provider, email, or production
  traffic is involved (the SMTP failure is a synthetic monkeypatch);
  no release or production claim follows.
- The GUI parity is at the shared-code level: the same
  `KeyCloneService` build/execute law and the same strict plan schema
  as the CLI clone commands; this record does not re-qualify the CLI
  or the core concurrency/rollback/replay proofs (qualified in the
  196-205 core/CLI objective records).
- The review-intent token is a browser-session review-state adapter
  (bounded size, short expiry, actor/session/source/delivery bound);
  it is not a signing framework and carries no gateway-key, replay,
  or provider secret. The recovery view is read-only and never
  creates or assumes an outcome.
- Historical keys are untouched (no migration, no mass update);
  cloning is an explicit two-step operator action creating a NEW key
  with independent material, identity, zero usage and reservations,
  and its own replay ownership.
- GitHub CI on the 208-a report head is pending at publication
  (treated as pending, not pass); strategic review and guarded merge
  are the root's gates.
