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

## 208-b CI qualification and final-head chronology (objective 208, same PR, 2026-10-31)

208-b (same PR `oap/208-gui-key-clone`) qualifies the demonstrated
208-a final-head CI failures. The section above remains the 208-a
publication record; this section supersedes its pending-CI sentence
with the terminal A result and records the bounded B repair.

### Terminal A CI result (run 41243331544, head `4335ecb` A SELF)

- Unit, lint, and migration head (job `124661804858`): 1 FAILED,
  6687 PASS, 1 SKIPPED (the skip is not a pass). The failure is
  `tests/unit/test_main_app_structure.py::test_main_app_only_wires_app_and_routes`
  asserting the brittle source-line budget (`assert 87 < 84`): the
  new clone router's legitimate import/include/comment lines exceed
  the ceiling, while main still only composes the app.
- PostgreSQL integration (job `124661804846`): 10 FAILED, 524 PASS,
  9 SKIPPED. All 10 failures are in
  `tests/integration/test_admin_key_policy_207_postgres.py` with
  `duplicate key value violates unique constraint
  "uq_provider_configs_provider"`: CI collects the 208 clone module
  before the 207 policy module, and the 207 seed still created the
  DB-unique provider rows unconditionally (the earlier 207-then-208
  local coexist check could not see this order).
- The other 8 final-A checks (docs, Compose, browser, E2E, analyses,
  CodeQL) succeeded at that head.

### Bounded B repair (tests + one dead tuple; no product behavior change)

1. `tests/unit/test_main_app_structure.py`: the total-line ceiling is
   replaced by small standard-library AST structural checks of the
   main-as-composition contract: first-party imports (including
   `from slaif_gateway import ...` aliases treated as qualified
   module names) must stay outside the `services`/`db`/`workers`/
   `providers` layers; `include_router` must target the app
   instance; no inline route handlers (FastAPI and Starlette
   `route`/`websocket_route` decorator forms) and no direct handler
   registration (`add_api_route`, `add_route`,
   `add_websocket_route`, `add_api_websocket_route`). Ordinary new
   router imports/includes pass without any ceiling change, and a
   focused negative/positive control case pins the rejected shapes.
2. `app/slaif_gateway/api/admin_key_clone.py`: removes only the
   genuinely unused `_CLONE_FORM_FIELDS` tuple (demonstrated unused by
   repository search; form parameters, validations, and allowlists are
   unchanged).
3. `tests/integration/test_admin_key_policy_207_postgres.py`: the 207
   `_seed` provider/route creation becomes get-or-create on the
   DB-unique provider slugs and requested models (the same existing
   repository pattern the 208 seed already used), so both modules
   coexist in either collection order. No production law, state
   reset, or collection-order forcing.

### Focused B evidence (newly run)

- `tests/unit/test_main_app_structure.py`: 6 PASS, 0 skip (JUnit
  `unit-208b-3.xml`), including the new structural-guard control case.
- OAP governance: 9 PASS, 0 skip (JUnit `unit-208b-gov2.xml`) with
  the 208-b order committed byte-exact.
- 207/208 coexistence in BOTH collection orders on separate fresh
  qualified owned-PG fixtures: 14 distinct cases per order (10 + 4),
  28 executions total, 14 PASS / 0 fail / 0 skip each (JUnit
  `pg-208b-ciorder.xml` for the CI order 208-then-207 and
  `pg-208b-reverse.xml` for the reverse), each with exact-ID
  container cleanup.
- Ruff on the changed paths and `git diff --check` clean.

### Reused unchanged A evidence (not rerun)

The 208-a component proof stands as recorded above: 47 unit PASS
(`unit-208a-4.xml`), 4 owned-PG PASS (`pg-208a-1.xml`), 14 coexist
PASS (`pg-208a-coexist.xml`), 3 actual Chromium PASS
(`browser-208a-1.xml`); those suites are unaffected by the B changes
other than the two test files and the one dead tuple listed above.

### Final-head status and operator notes

GitHub CI on the B implementation head is pending at publication
(treated as pending, not pass); the A report remains immutable with
its pending-at-publication statement, and the terminal A failure is
recorded here. The 208-a operator/upgrade notes still apply: ordinary
API/assets rebuild and restart, no schema or existing-key migration,
no production action authorized. Strategic review and guarded merge
remain the root's gates.

## 209-a reviewed key batches (objective 209, new PR, 2026-11-01)

### Scope and GUI-CLI parity contract

Admin GUI G05 of `docs/MISSING_GUI_FUNCTIONALITY.md` (reviewed
changes to existing key sets). The GUI reuses the SAME qualified 203
core `KeyBatchService` plan/apply law (preview resolves exact UUIDs,
staleness revalidation under row locks, one caller-owned transaction,
one `update_key_configuration` audit per changed key, atomic
rollback) - there is no second policy engine, no GUI drift surface.
No database schema, table, migration, or runtime accounting change;
the record pickers (192/193), the redaction seam (207), and the
session/CSRF contexts are reused as well.

### Bounded implementation

`app/slaif_gateway/api/admin_key_batch.py` (focused router: form,
plan, apply), the batch-purpose token in
`app/slaif_gateway/api/admin_review_intent.py`, the router include in
`app/slaif_gateway/main.py`, the three `keys/batch_*.html` templates
(form / review / result), the batch entry link in `keys/list.html`,
`web/static/js/key-batch.js` (one composed disabled-state sync;
progressive enablement/disabling only - never value conversion), the
batch-opt-in `web/static/js/record-choices.js` changes (hydration cap
applied centrally to searches; omitted `selected` hydration on
non-empty queries) and the optional `help_id`/`hydrate_cap`
parameters of `_record_choice.html` (batch callers only; other
callers keep their exact markup), the asset registration, the `.field`
wrapper and `.config-json` containment stylesheet rules, and the
bounded 16 m `/admin/key-batch/` locations in BOTH shipped Nginx
configs plus the `deployment.md` operator note.

### Focused test evidence (local; actual CI chronology recorded below)

- **Fake-persistence ASGI/Jinja unit suite: 81 PASS / 0 skip** (JUnit
  `unit-209a-7.xml`; the module was green at 80 cases at
  `unit-209a-5.xml` and at 81 cases at `unit-209a-6.xml`, then
  re-verified after the in-order accessibility/hint corrections).
  Coverage: guided/advanced composition and the single-source law,
  list-mode allow-all/deny-all and credential-shaped refusals,
  selection overflow/malformed with the full-1000 accepted, review
  rendering (ordinals, raw ungrouped sort keys, M-token and
  money-string display, state-aware empty lists, excluded entries as
  real UUID/status, the five picker help links, apply-input help with
  the 512-UTF-8-byte bound and fenced acknowledgement), token
  round-trip plus expiry/actor/session/tamper/malformed/oversize
  refusals, apply flows (confirmation, reason, fenced, stale refusals
  with zero writes, canary absence), the actual near-8 MiB signed
  envelope through real ASGI urlencoded apply, the over-bound form
  refusal as a controlled fixed 400, and the full-1000 transport
  round-trip.
- **Owned-PostgreSQL integration: 6 PASS / 0 skip** (JUnit
  `pg-209a-1.xml`, 8.876 s, qualified loopback/tmpfs fixture, exact-ID
  container cleanup). Cohort-scope plan (107 selected over
  active+suspended; zero writes on preview), explicit 108-UUID plan
  with exact exclusions and 105 persisted changes (changed-key
  comparison allowing only the requested quotas plus `updated_at`;
  excluded and an unselected control key an unchanged value snapshot), 105
  actor-attributed audits, the SAME original reviewed token
  reapplied as `already_at_target`, direct-DB drift and status-change
  refusals with no-write snapshot proof, and an injected late per-key
  write failure rolling back ALL provisional updates and audits. The
  PG module seeds NO provider/route rows (quota-only batch); the
  browser fixture separately get-or-creates the two DB-unique
  provider slugs for the picker catalogs.
- **CI collection-order coexistence: 20 PASS / 0 skip** (JUnit
  `pg-209a-coexist-ci.xml`, 26.883 s: 6x209 + 4x208 + 10x207 in the
  CI order) on one session database; the reverse order reuses the
  208-b owned-PG proof. One CI-order coexistence satisfies this
  order.
- **Real Chromium on the owned fixture: 7 PASS / 0 skip, 32.655 s**
  (JUnit `browser-209a-3.xml`, exact container cleanup; actual
  uvicorn app, real stylesheet). Entry link plus safe initial
  disabled states (real composed sync), the populated transition
  regressions (stale allow-list values never ride along; guided<->
  advanced round trip; keys<->cohort scope change while advanced;
  inactive chip removal), the >100 multi-key selection with older
  search (no `selected` hydration on typed queries; the full 101
  selection submitted), the keyboard happy flow (combobox
  ArrowDown/Enter cohort selection, Space/type/Enter apply, 390px
  review with no document overflow and the apply control still
  reachable, independent persisted-DB and audit oracles: 105 cost
  caps persisted, 105 audits, then the no-JS flow's 105 request caps
  and 105 more audits), and the no-JS fallback flow through to the
  persisted change.
- **JS component root (separate, mocked lookup, no app auth/PG):** the
  populated-state regressions pass on the final
  `web/static/js/key-batch.js` SHA
  `5a1362620fb65a78a78630c3262197180a9651b1bb9104490c4e359a5f5867fd`;
  the durable native browser cases above cover the same states on the
  actual rendered page.
- **Static/governance receipts (publication gate):** the full
  `tests/unit/test_admin_usability_inventory.py` module: 119 PASS /
  0 skip (JUnit `unit-209a-inventory.xml`), and OAP governance:
  9 PASS / 0 skip (JUnit `unit-209a-gov.xml`) with the 209-a order
  byte-exact in the tree. Ruff clean on the changed Python paths,
  `scripts/check_documentation.py` reports `DOCUMENTATION_CHECK=OK`
  (135 files), and `git diff --check` is clean.

### Qualification chronology (honest failures)

- Browser run 1: 7 FAIL - all fixture/selector issues (the h1 is
  "Change Existing Keys", the multi picker has no `rc-open` button,
  hidden inputs need `state="attached"`, transition step (iv) must
  return to guided first, the cost formatter renders `5` not `5.00`).
  No product defect.
- Browser run 2: 3 PASS / 4 FAIL - the remaining root failure was the
  display assertion matching the literal `&rarr;` entity while the
  serialized page decodes it to the arrow; the other three cascaded
  from the happy Apply never executing. No product defect.
- Browser run 3: 7 PASS / 0 skip after the fixture corrections plus
  the in-order accessibility corrections (keyboard cohort selection,
  keyboard-only apply, the narrow-viewport review block, the
  visible-text display assertion).
- The in-order template corrections (one label per control, the
  picker `help_id` spans, the apply-input help, the M-token rate
  readout, the hint wording, the 512-UTF-8-byte reason bound) were
  re-verified by the unit module (`unit-209a-7.xml`) and the browser
  module (run 3 renders both corrected pages); the unchanged PG 6 /
  coexist 20 component proof is reused, not rerun.
- Pre-publication gate (root probe, closed exit 1): the inventory
  ordinal guard expected 25 sortable admin tables; the new batch
  review table is the 26th, and its tbody lacked the standard
  empty-state row. Same-order focused correction: the guard count
  25 -> 26 (assertions preserved) and the standard for-else
  empty-state row (`data-no-sort`, `colspan="8"`, unnumbered) in
  `batch_review.html`. The full inventory module then passed
  119/119 (`unit-209a-inventory.xml`); the empty branch never renders
  for a real plan (the core requires at least one selected key), so
  the unit 81 / browser 7 / PG 6 / coexist 20 receipts stand
  unchanged and were not rerun for this static correction.

### Transport bound (demonstrated defect and fix)

An 8 MiB canonical plan expands to 11,184,812 base64url characters
(~10.67 MiB) plus the digest/separator in the signed
`batch_review_intent` field. Starlette's default per-field cap (1 MiB)
refused the actual full-1000 apply before any gateway logic ran, and
Nginx's default 1 MiB `client_max_body_size` would refuse it in
transit. The fix is bounded to the batch surface: the APPLY route
parses its own form with envelope-sized headroom (no files, bounded
field count) BEFORE the framework auto-form parsing and maps both
bounded-parse failure forms to one fixed safe 400; both shipped Nginx
templates carry `client_max_body_size 16m` for the
`/admin/key-batch/` locations ONLY. No global body middleware,
storage, jobs, compression, or schema; every other route and limit is
unchanged. The near-8 MiB valid envelope is qualified through real
ASGI urlencoded apply (exactly one apply call, full strictly parsed
plan, all 1000 IDs) and the over-bound builder/API refusal is a
controlled fixed 400.

### Operator notes

Deploying 209 is an application upgrade: rebuild the API/assets image
and recreate/restart the API so the new batch code runs, together with
the reverse-proxy configuration from the shipped templates (or the
`location /admin/key-batch/` block added to a custom ingress) and
`nginx -t` + Nginx reload in the same maintenance window - a new app
behind an old proxy 413s large reviewed batches before they reach the
gateway. Editing only the proxy setting needs just `nginx -t` and a
reload. No schema migration, no existing-key change or rotation.

### Honesty and limitations

Component distinctions: the 81-case unit suite runs on synthetic fake
persistence (no real DB); the 6-case suite runs on the qualified owned
PostgreSQL; the 7-case browser suite runs the actual uvicorn app plus
the real stylesheet against the same owned fixture; the JS component
root used a mocked record-choices lookup without app auth/PG. No full
local matrix was rerun for this objective (the unchanged 207/208
component proof is reused, and one CI-order coexistence plus the
208-b reverse proof cover cross-module seeding). GitHub CI on the 209
implementation head is pending at publication (treated as pending, not
pass); strategic review and guarded merge remain the root's gates. No
production, security, compliance, or scale claim follows.

## 209-b CI qualification and factual-record correction (objective 209, same PR, 2026-11-01)

### Actual A IMPL CI failure (terminal)

A IMPL `2aaf11d2714ec7e24c732293f3ef7088a2b1ba7c` CI run
`41261553792`, unit job `124715694142`, completed FAILURE at
2026-11-01T01:36:04Z. The actual job log identifies exactly two
failures, both independently reproduced by root on the unchanged A SELF
(two cases / two failures, closed exit 1):

1. `tests/unit/test_documentation_contract_drift.py::
   test_external_tool_policy_contract_consumers_remain_allowlisted` -
   the new `app/slaif_gateway/api/admin_key_batch.py` imports the
   authoritative external-tool contract constant but was absent from
   the finite consumer allowlist.
2. `tests/unit/test_admin_slaif_design.py::
   test_table_wrappers_are_labeled_and_focusable` - actual 24 wrappers
   versus the historical expected 23; the added batch scroll region
   already carried its required `role="region"`, keyboard focus, and
   accessible label.

The A report's and the 209-a section's "no CI run exists on this head
yet / CI pending at publication" statement is SUPERSEDED by this actual
GitHub evidence, not rewritten: the A report remains immutable with its
pending-at-publication statement, and the terminal A failure is
recorded here.

### Factual corrections to the A-era record (superseding, not rewritten)

- The A-era chronology claim that the empty-state branch "never renders
  for a real plan (the core requires at least one selected key)" is
  FALSE: `KeyBatchService.plan` permits an empty cohort/status
  selection and the strict schema's `selected_count` minimum is 0. The
  standard empty-state row is the valid display for that outcome; no
  service or parser change was made or is needed.
- Membership-recheck precision: the core rechecks membership AFTER the
  last selected-key lock under the existing READ COMMITTED law; later
  joins are untouched. Nothing here implies serializability or a new
  lock guarantee.
- The A-era PG wording "an unchanged value snapshot" (real field-value
  snapshots, not physical DB byte equality) and the corrected unit
  receipt chronology (80 cases at `unit-209a-5.xml`, 81 cases at
  `unit-209a-6.xml` and `unit-209a-7.xml`) stand as corrected.

### Bounded B repair (tests only; no product bytes change from A)

1. `tests/unit/test_documentation_contract_drift.py`: the finite
   consumer allowlist gains the exact path
   `app/slaif_gateway/api/admin_key_batch.py` - a UI-gate consumer that
   reads `EXTERNAL_TOOL_FENCED` only to present and require the
   existing fresh apply-time acknowledgement when the reviewed input
   policy sets a fenced external-tool policy. The shared
   `KeyBatchService`/`KeyService` still own validation, current
   authorization, fences/holds and execution; this grants no runtime
   hosted-tool authority. Every existing consumer, the whole-tree
   scan, the operator-limit assertion, and the rejection of unlisted
   modules are preserved; no wildcard allowlist, skipped test, or
   contract duplication.
2. `tests/unit/test_admin_slaif_design.py`: the demonstrated wrapper
   count 23 -> 24 for the new batch scroll region. The per-wrapper
   `role="region"` / `tabindex="0"` / non-empty `aria-label`
   assertions and all other design tests are preserved; the product
   wrapper markup is unchanged (it was already correct).

### Focused B evidence (newly run)

- The two affected test modules (which include both failed cases) run
  once after the fixes: 27 PASS / 0 fail / 0 error / 0 skip, 5.016 s
  (JUnit `unit-209b-1.xml`).
- OAP governance: 9 PASS / 0 skip (JUnit `unit-209b-gov.xml`) with the
  209-b order committed byte-exact.
- Ruff clean on the current PR-changed Python files (small finite
  set); `scripts/check_documentation.py` reports
  `DOCUMENTATION_CHECK=OK`; `git diff --check` clean.

### Reused unchanged A evidence (not rerun)

The A component proof stands as recorded: 81 focused unit
(`unit-209a-7.xml`), 119 admin-usability inventory
(`unit-209a-inventory.xml`), 73 related 208/main-structure/actions
(`related-209a.xml`), 6 owned-PG (`pg-209a-1.xml`), 20 CI-order
coexist (`pg-209a-coexist-ci.xml`), 7 real Chromium
(`browser-209a-3.xml`), and the scoped root JS component probe
(`5a1362620fb65a78a78630c3262197180a9651b1bb9104490c4e359a5f5867fd`).
The B changes touch no product, proxy, CLI, service, schema, or
accounting bytes, so the negative/privacy/transaction evidence from A
remains accepted for the unchanged product code.

### Final-head status and operator notes

Final B-head GitHub CI is PENDING until actually green (skipped/
missing/pending is never pass); the A-era native proof remains scoped
as recorded, and the whole-GUI goal remains incomplete (G06-G18 open,
final installed 219 outstanding). The A operator notes still apply:
API/assets rebuild with API recreate/restart, the reverse-proxy
configuration from the shipped templates plus `nginx -t` and reload in
the same maintenance window (proxy-only edits need just the reload),
no schema migration and no existing-key change or rotation. Strategic
review and guarded merge remain the root's gates.

## 210-a reviewed route configuration and provider preparation (objective 210, new PR, 2026-11-01)

### Scope and GUI-CLI parity contract

G06 (reviewed route-capability changes) and G07 (provider preparation
and explicit clearing) of `docs/MISSING_GUI_FUNCTIONALITY.md`, delivered
on branch `oap/210-gui-provider-route` (created from accepted `main`
`32478e0`, the merged PR #365 head). The GUI reuses the SAME qualified
core: the shared `provider_route_configuration` orchestration (strict
reviewed-plan schema, fresh revalidation of route/provider identity and
context, deterministic FOR UPDATE locking, stale refusal, the no-op law,
and the merged-candidate validation including the configured-completion
zero-retry rule), `ModelRouteService` (the audited CRUD path - one
`model_route_updated` audit per changed route), `ProviderConfigService`
(prior-state capture, HTTP confirmation, credential reference only),
the record-choice infrastructure, and the review-intent token family.
No GUI policy engine, no second validator, no schema,
migration, model, CLI-semantics, worker, or accounting change. Route
CREATE's finite creation intent (Automatic / Prepare disabled / Enable
explicitly; legacy POSTs keep the enabled checkbox) and provider CREATE's
default-OFF enabled checkbox with one optional Notes are preparation
separations: provider status is never proof of backend authentication.

### Bounded implementation

New focused router `api/admin_provider_route_configuration.py` (GET
form / POST plan / POST apply; registered from `main.py` composition;
`admin.py` does not import it) over the route-purpose token extension of
`api/admin_review_intent.py` (HMAC-SHA256, actor + session + purpose,
15-minute expiry, 178,858-character encoded bound, and the 128 KiB
decoded canonical-plan bound enforced at BUILD and VERIFY; malformed
token formats are a fixed refusal before digest comparison). Bounded
`admin.py` changes: provider detail/form display projections, provider
create+edit known-shape refusals (the 199 CLI law) before any write,
legacy route-form refusal blanking/redaction, the route-creation intent
path (validated through `validate_route_creation_candidate` in the same
caller transaction before write), the entry link, and the small
`_admin_url_display_value` projection. Templates: three new
`routes/configuration_*.html`, touched `routes/{detail,edit,create}.html`
and `providers/{create,edit}.html`; progressive
`web/static/js/catalog-configuration.js` (the capability-source fieldset
hidden AND disabled by JS only; no-JS fully enabled; no value
conversion). A
bounded `completion_profile` choice kind (streaming `os.scandir`,
filters before stat, stop at 100, `bindings.json` excluded,
unsafe-mode/symlink/oversize refusals; configured profile directory
wired to initial render AND AJAX).

### Root-approved bounded shared-law exception (recorded with approval)

A demonstrated defect: the reviewed preview promised a null notes target
while the repository treated `notes=None` as preserve. Root approved the
exact bounded paths (`services/model_route_service.py`,
`db/repositories/routing.py`, `services/provider_route_configuration.py`
plus their unit tests; the 199 CLI PG module needed no change):
`update_model_route_metadata(..., clear_notes: bool = False)` writes
NULL only when explicitly requested (`notes=None` without it still
preserves), `update_model_route(..., clear_notes: bool = False)` refuses
the conflicting notes+clear combination, and
`execute_route_update_plan` passes `clear_notes=plan.notes is None` -
the plan's notes is the reviewed canonical target, applied as an
explicit clear (a no-op when already null; equality is checked first,
and the service captures the REAL prior notes in its single audit). No
schema/plan-version/permission/accounting change; the order bytes are
immutable. Evidence: `unit-clear-1.xml` (202 PASS), the native
clear-only PG case in `pg-210a-3.xml`, and `cli-pg-210a-1.xml` (31 PASS).

### Focused test evidence (local; GitHub CI pending at publication)

All JUnit files under `/tmp/slaif210/`; the final qualifying runs were
in managed foreground terminals (two early background PG launches were
diagnosed, found dead, and corrected rather than rerun blindly); owned
loopback/tmpfs PostgreSQL fixtures with exact-ID cleanup.

| Receipt | Scope | Result |
| --- | --- | --- |
| `unit-210a-3.xml` (latest; `unit-210a-2.xml` post-layout receipt reused for unchanged areas) | 210 unit module: form sources, leaf diff, tokens, boundaries, refusals | 58 PASS / 0 skip (24.033 s) |
| `choices-210a-1.xml` / `choices-210a-3.xml` | completion-profile lookup + final six tail cases | 74 PASS / 6 PASS |
| `unit-clear-1.xml` | 210 unit + `test_model_route_service` + `test_provider_route_configuration` after the shared-clear correction | 202 PASS / 0 skip (24.694 s) |
| `pg-210a-1.xml` | 10 native PG cases (chronology below) | 10 PASS / 0 skip (6.480 s) |
| `pg-210a-2.xml` | added real auth/CSRF denial case | 1 PASS (3.833 s) |
| `pg-210a-3.xml` | full 210 PG: preview read-only, exact apply + 1 audit, stale no-write, late-failure rollback, zero-diff no-op, provider create disabled / edit clear, creation intents, real auth/CSRF denial, native clear-only (plan TAMPER is unit evidence, not a native PG case) | 12 PASS / 0 skip (7.739 s) |
| `cli-pg-210a-1.xml` | 199 CLI PG module (affected by the execute-path change) | 31 PASS / 0 skip (36.378 s) |
| `browser-210a-1.xml` | real Chromium: entry/initial state + desktop/narrow captures, keyboard guided plan/apply with independent DB/audit oracles, JS source transitions, full-document replacement, no-JS fallback incl. notes clear, provider edit clear, creation intents, help associations | 8 PASS / 0 skip (21.267 s) |
| `affected-210a-1.xml` | main composition, legacy route form modules, consumer/doc drift, design/inventory, 9 OAP governance on the byte-exact order | 184 PASS / 0 skip (14.566 s) |
| `affected-210a-2.xml` | legacy provider form module incl. the three URL display canaries | 17 PASS / 0 skip (8.203 s) |
| `urlcanary-210a-2.xml` | focused URL canaries (supersedes `urlcanary-210a-1.xml`, 2 PASS pre-hardening) | 3 PASS / 0 skip (3.935 s) |
| `pathfix-210a-1.xml` | focused re-verification of the completion-profile path boundary (loader + choices modules) | 117 PASS / 0 skip (15.745 s) |
| `pathfix2-210a-1.xml` | FINAL completion-profile path-boundary re-verification (loader + choices modules; includes the root-containment guard and the separator-safe root-prefix tests) | 121 PASS / 0 skip (15.699 s) |
| `smoke-210a-1.xml` | focused re-verification of the repaired dashboard smoke case (owned PG, exact-ID cleanup) | 1 PASS / 0 skip (10.183 s) |

Scoped root component probes (mocked auth, no real DB/provider) are
reused: 11 pure review-helper checks (round-trip, actor/session/purpose,
expiry, digest tamper, cross-purpose denial, decoded 128 KiB refusal
inside wrapper slack), 8 completion-lookup metadata checks (bounded
opens, older hydration, `bindings.json` exclusion, unsafe-mode
refusals), 3 provider-detail projection checks, 2 provider create/edit
known-shape canaries (refusal before any service call), 8 URL-fix ASGI
refusal/recovery checks (https/ftp userinfo and malformed IPv6 across
create/edit, ordinary-URL recovery, retained projections, literal ENV
name, original row unchanged), and the AST audit that the seven
pre-existing review helpers are unchanged.

### Qualification chronology (honest failures)

- **PG fixture**: the first `pg-210a-1.xml` run was 10 tests / 2
  failures - the seed ENV names `210_SVC_KEY`/`210_MOD_KEY`/
  `210_NEW_KEY` start with digits and violate the existing ENV-name
  validator (a generic 400 blocked the intended validators). Corrected
  to `GUI210_*` names; the corrected module is the recorded 10 PASS
  receipt (the JUnit was overwritten; chronology preserved here).
- **PG final module**: the first `pg-210a-3.xml` run of the two new
  cases failed on an audit helper-key typo in the test (fixture-only -
  the audit dict keys are `old`/`new`, not `old_values`/`new_values`);
  the corrected module is the recorded 12 PASS receipt. The runner
  wrapper then raised a `NameError` on `child_exit` AFTER the tests
  and container cleanup had completed - a harness-only post-cleanup
  failure, distinct from the test result; the wrapper was corrected for
  later runs and the 12 PASS receipt was not rerun for it.
- **Legacy provider module**: the first `affected-210a-2.xml` run was
  14 / 1 failure - the pre-existing `_FakeSession` did not back the new
  caller-transaction locked read. Fixture-only backing added (directly
  affected behavior, authorized path); the module is the recorded 17
  PASS receipt after the URL canaries joined it.
- **Browser module (actual sequence)**: the first 2-case run failed 1
  case (42.688 s) - the Chat flag lives inside an intentionally
  collapsed disclosure, and the ordinary `select_option` was attempted
  on the control while it was still hidden; the fix opens the
  disclosure by keyboard first (focus the summary, Enter/Space) and
  only touches the flag once visible. The targeted rerun then failed
  (11.197 s) on an unsupported oracle - the result template does not
  render the audit reason, so the DB audit assertion is authoritative;
  corrected, the case passed (10.808 s). The first FULL 8-case run
  failed 4 cases (78.933 s), all fixture/oracle defects: the
  full-replacement raw-document expectation ignored the shared-
  normalized canonical defaults (stored state is the reviewed
  canonical target, so e.g. chat_text true -> true is correctly
  absent from the leaf diff); the no-JS notes label expected
  "No notes." where the template actually renders "(none)"; the
  provider redirect success check did not allow the `?message`
  query; and the route-creation fixture selected the requested model
  before its provider, whose picker parent change clears the
  dependent selection. Separately (setup correction, not one of the
  four test failures): the runner's unused outer owned PG was removed
  so the browser fixture is the sole container owner. The second FULL
  run failed 2 cases (21.927 s):
  ONE was a REAL shared persistence defect - the reviewed preview
  promised a null notes target while the repository treated
  `notes=None` as preserve - repaired through the root-approved
  bounded shared-law correction above, NOT a fixture fix; the other was
  test-side (the raw-plan `<details>` was read while closed). The final
  full run is the recorded 8 PASS receipt (21.267 s). No product
  message, message-flow, or validator was changed to fit selectors.
- **Demonstrated URL privacy edge and fix**: root reproduced (mocked
  auth, no real DB/provider) that a credential-bearing (userinfo) base
  URL is refused with 400 but the plaintext password remained in the
  error HTML - the generic known-shape redaction does not cover URL
  userinfo. The small field-specific `_admin_url_display_value`
  projection withholds credential-bearing URL values entirely on
  form/detail/review display (any userinfo, any scheme, including empty
  userinfo; malformed URLs withheld safely instead of re-raised, so a
  400 recovery page cannot become a 500), leaving ordinary URLs
  byte-identical and URL acceptance, canonical values, fingerprints,
  and stored data unchanged. Focused canaries:
  `urlcanary-210a-2.xml` (3 PASS) and the root's independent 8 checks;
  the two directly-affected unit modules were refreshed after each
  hardening (recorded receipts above).
- **Receipt supersession**: `unit-210a-2.xml` (58 PASS, post-layout),
  `urlcanary-210a-1.xml` (2 PASS, pre-hardening), and the intermediate
  14/16 PASS `affected-210a-2.xml` states were superseded by the
  recorded latest receipts as product/test code moved; the superseded
  states are described here, not rerun.

### CI chronology (actual, per head)

- **First IMPL head `edf201e3` - CodeQL aggregate FAILED** (2026-11-01T
  05:30:40Z) with three HIGH path-injection alerts
  (`modules/servers/completion_service/profiles.py:153`;
  `services/admin_record_choices.py:255,352`). Root SARIF review: the
  sources are submitted profile/selected IDs, not an HTTP-supplied
  directory; the existing fullmatch whitelist
  `[a-z0-9][a-z0-9-]{0,63}` excludes every path separator; no escape
  was demonstrated. Bounded same-order repair (commit `ebc12dac`, with
  the additionally approved paths
  `modules/servers/completion_service/profiles.py` and
  `tests/unit/test_completion_service.py`): AFTER the existing ID-law
  refusal, the final single root-relative filename is re-derived with
  `os.path.basename` at the loader join and both lookup joins (no raw
  `entry.path`), making the by-construction boundary explicit without
  relaxing it - the whitelist, streaming enumeration, 100 cap, file
  modes, and O_NOFOLLOW are unchanged; no suppression, dismissal,
  config change, or directory framework. Focused re-verification:
  `pathfix-210a-1.xml` (117 PASS / 0 skip; invalid components refused
  before any I/O, valid names unchanged). The follow-up CodeQL runs
  on the next heads (`bfe1ab43`, `784ed9c5`) STILL reported the same
  three HIGH alerts: the basename re-derivation alone was insufficient
  for the analysis (the SARIF still traced the submitted IDs through
  the basename join), so a further bounded guard was authorized.
- **CodeQL root-containment guard (commit `c32c6ca9`):** following the
  official CodeQL recommendation, the shared helper
  `profiles.contained_child` (used by the loader and by both
  enumeration/hydration joins) canonicalizes the TRUSTED ROOT only
  (`os.path.realpath`; the root's original absolute/non-symlink law is
  still checked first and unchanged), `os.path.normpath`s the joined
  validated filename, and requires the normalized candidate to start
  with the canonical root plus a separator BEFORE any I/O. The final
  file is never resolved and never opened through a symlink target:
  `O_NOFOLLOW`, symlink/mode/size refusal, streaming caps, and the
  pre-I/O ID-law rejection are all preserved. No directory framework,
  suppression, dismissal, or config change; same two approved modules
  plus `tests/unit/test_completion_service.py`. Focused re-verification:
  `pathfix2-210a-1.xml` (121 PASS / 0 skip, incl. inside-root and
  outside-root symlinked profile refusals and relative/symlinked root
  refusals).
- **Separator-safe root prefix (commit `cea28df1`, final CODE head):**
  `canonical_root + os.sep` builds `"//"` when the accepted root is
  `/` and would wrongly refuse `/profile.json`; the root prefix is now
  derived with `os.path.join(canonical_root, "")`, which keeps exactly
  one trailing separator (`/` itself at the root). The strict-child and
  separator-boundary requirements are unchanged; a pure helper
  assertion covers the `/` root without any filesystem write. Same
  focused suite: `pathfix2-210a-1.xml` (121 PASS / 0 skip).
- **First IMPL head `edf201e3` - browser job `124761536375` FAILED** on
  exactly one case: `tests/browser/test_admin_dashboard_smoke.py::
  test_admin_dashboard_browser_smoke` (line 487) - the new associated
  route-create metadata help had rephrased the established warning
  sentence the smoke asserts ("Runtime consumes it only for exact
  OpenAI Responses"). Same-order repair (commit `bfe1ab43`): the
  original sentence is restored verbatim inside the route-create
  metadata help, keeping the added field guidance and all
  hosted-tool limitations; no acceptance change or test weakening.
  Focused re-verification: `smoke-210a-1.xml` (1 PASS / 0 skip).
- **Placeholder correction (final IMPL commit):** the route-create
  capabilities textarea placeholder `{"vision": false}` names a group
  the shared `validate_capabilities_document` REFUSES; it is replaced
  by the valid RAW example `{"chat_completions": {"chat_text": true}}`
  (root-verified accepted) - the legacy editor takes the raw
  capability object, never the reviewed `schema_version` wrapper.
  Template hint only; IDs and behavior unchanged, no unrelated rerun.
- **Final CODE head `cea28df1` - CodeQL aggregate SUCCESS**
  (queried 2026-11-01T05:58:50Z), together with Unit/lint/migration,
  OpenAI-compatible E2E, Docker Compose smoke, documentation hygiene,
  and the three CodeQL analyze jobs all `completed/success` at the same
  timestamp; the Playwright browser smoke and PostgreSQL integration
  jobs were still `in_progress` at that timestamp (the same suites have
  local green receipts: `browser-210a-1.xml` 8 PASS, `pg-210a-3.xml`
  12 PASS, `smoke-210a-1.xml` 1 PASS). The final docs-only IMPL head's
  checks and the merge gate are root-owned; per-head check states are
  recorded in the immutable 210-a report (a failed or skipped job is
  never reported as pass).

### Operator notes

Deploying 210 is an application upgrade: rebuild the API/assets image
and recreate/restart the API so the new code runs. There is **no Nginx
change**: the signed route review envelope is bounded to ~175 KiB
(178,858 base64url characters), well inside the existing default
`client_max_body_size`, and no new location or allowance is introduced.
No database migration; existing keys and routes are untouched.
Installed completion profiles are a process-local cache: deploy the
profile files to the configured profile directory, then recreate/restart
the API so the process picks them up. See `deployment.md`.

### Honesty and limitations

This is local, commit-specific evidence on the qualified owned fixtures
and real Chromium: no real provider, mail, or upstream call; no
production access. The 207/208/209 component proof and the unchanged
CLI law are reused without rerun; the affected shared route-execute
path WAS requalified after the shared-clear correction (the 199 CLI PG
module, `cli-pg-210a-1.xml`, 31 PASS). GitHub CI had not yet run on
the 210 head when the first docs were committed; the FIRST IMPL head
actually FAILED the CodeQL aggregate (three HIGH path-injection
alerts) and one dashboard-smoke wording assertion; the basename
clarification alone did not clear the CodeQL flow, and both were
repaired by the bounded same-order commits recorded above
(chronology), ending in CodeQL aggregate SUCCESS on final CODE head
`cea28df1`. The final docs-only head's checked status is recorded in
the immutable 210-a report. Strategic
review and guarded merge remain the root's gates.

## 211-a GUI request diagnostics and process configuration (objective 211, new PR, 2026-11-01)

### Scope and GUI-CLI parity contract

G08 (content-free request diagnostics) and G16 (safe configuration,
profile and version inspection) of
`docs/MISSING_GUI_FUNCTIONALITY.md`, delivered on branch
`oap/211-gui-diagnostics-config` (created from accepted `main`
`f71f5799`, the merged PR #366 head). The GUI reuses the SAME qualified
core: `RequestDiagnosticsService` (status, bounded retained lookup with
explicit gateway/client/any namespaces, choice listing, and the
transactional expired cleanup with its single actor/reason/count audit),
the shared `configuration_inspection` 45-name allowlist (the shared
inspector gained explicit API-process-scope wording; the CLI defaults
and values are unchanged and re-qualified), and the record-choice
infrastructure (ONE kind-specific branch: the diagnostics picker POSTs
to a fixed private endpoint with the page's own non-rotating CSRF and
the live namespace; every other kind keeps the exact GET transport).
No schema, migration, permissions, capture activation, provider call,
accounting, worker, or CLI-semantics change. All seeded records are
synthetic, projected by the SHARED producer projection - no real
provider/Codex request is involved, and no installed-qualification or
deployment claim is made (final 219 remains required).

### Final evidence (accepted receipts)

| Receipt | Scope | Result |
| --- | --- | --- |
| `unit-211a-format-2.xml` | 211 unit module (typed found/ambiguity/overflow/unavailable, canaries, denials, cleanup service-call proofs, 45 allowlist, profile snapshot) | 34 PASS / 0 skip (15.281 s) |
| `unit-211a-usage-alias-1.xml` | usage-detail entry link + incoming-alias display withholding regression | 4 PASS / 0 skip (4.372 s) |
| `unit-211a-usage-alias-2.xml` | affected usage-rendering/numeric modules | 61 PASS / 0 skip (9.528 s) |
| `pg-211a-4.xml` | owned-PG module: retained rendering, ambiguity/namespace, expiry/disabled reads, choices cap/dedup/hydration, native auth/CSRF denials, bounded cleanup + single audit, late-failure rollback, zero-delete audit | 8 PASS / 0 skip (12.498 s) |
| `pg-211a-5.xml` | targeted re-qualification of the three strengthened read-only cases | 3 PASS / 0 skip (10.388 s) |
| `unit-211a-affected-1.xml` | affected 211-unit + SLAIF-design + usability-inventory + main-app-structure guards after the disclosure/no-store corrections | 173 PASS / 0 skip (18.469 s) |
| `browser-211a-8.xml` | actual Chromium (owned PG, sole container owner): login -> dashboard -> Operations -> diagnostics, keyboard picker lookup of the HTTP-200 stream failure, collision ambiguity + gateway resolve, pasted-credential canary (real handler via network capture; value in no URL/error body/page), existing kinds keep the GET lookup, usage-detail entry link with live-namespace POST evidence + same-page CSRF, no-JS lookup/validation recovery, process configuration + existing workflows, narrow/desktop captures | 7 PASS / 0 skip (18.807 s) |

Owned-container lifecycle was independently verified per run (labeled,
loopback, tmpfs; exact full ID removed; owner filter empty after).
Earlier preliminary states - the unit fixture-oracle corrections, the
PG encoding/oracle corrections, and the browser selector/oracle
corrections including one INTERRUPTED run (a Playwright page-bound
`Response.text()` stall; signalled to the exact pytest PID, exit 2, not
a pass, container cleaned) - were superseded by the receipts above and
are not catalogued here.

### Limits of this record

Synthetic fixture data only (no real provider/Codex request, no real
captured content); the browser privacy case proves the pasted value
never reaches a URL, error response, or rendered page through the real
handler; native PG proves retention/expiry/cleanup/audit/rollback
through authenticated HTTP; the installed whole-GUI qualification
(objective 219) and all deployment remain explicitly OUT of scope.

## 211-b Final-head browser CI qualification (objective 211, same PR,
2026-11-01)

The A final-head CI genuinely FAILED on the Playwright job (job
124809403688 of run 41293439505, 2026-11-01T09:36:22Z, 2 failed /
70 passed in 242.95s): both failures were stale exact nav-link
counts (14) in `tests/browser/test_admin_slaif_design.py`, while the
approved Operations entry intentionally grew the shared shell nav to
15 links. A was NOT all green, and B repairs no product behavior -
the 15-link nav is the accepted G08/G16 navigation.

B corrects ONLY those stale oracles: the two failing exact counts
plus one downstream 768-tablet count in the same no-JS case that the
first fix unblocked now expect 15, and both the normal and
no-JavaScript scenarios explicitly assert the ONE correctly named
Operations link to `/admin/operations` derived from the base
template (no arbitrary extra link, no weakened or dynamic count).
All other font-byte, theme/contrast, branding, current-page,
keyboard, responsive-overflow, table, and no-JS assertions and
fixtures are preserved; no product, template, JS, CSS, or
fixture-ownership change.

Newly run (local, synthetic): the TWO complete existing cases pass
on real Chromium with the qualified owned-PG fixture -
`browser-211b-1.xml` 2 PASS / 0 skip (16.829s), owned container
cleanup verified. Reused unchanged A evidence: unit 173/35, native
8 + overlap 3, browser 7, and the other 70 CI browser passes.


## 212-a GUI Codex compatibility management (objective 212, new PR, 2026-11-01)

### Scope and GUI-CLI parity contract

G10 (Codex policy-data inspection and existing-key migration) of
`docs/MISSING_GUI_FUNCTIONALITY.md`, delivered on branch
`oap/212-gui-codex-compatibility` (created from accepted `main`
`4d90d016`). The GUI reuses the SAME qualified Core:
`CodexQualificationService.inspect()` for the global readiness table,
`render_codex_profile` for the credential-free artifacts, the existing
route-detail artifact handlers, the shared reviewed
review/apply/stale-refusal orchestration (Core write law and default
CLI behavior unchanged; 212 adds only the optional expected-target
guard and read-only facts seam), and the existing
`_admin_attachment_context` read-only boundary. No schema, migration,
permissions, provider call, accounting, worker, or CLI-semantics
change. All seeded keys/providers/routes are synthetic; no real
provider/Codex request is involved; the final 219 installed
whole-GUI qualification remains required and is NOT claimed.

### Final evidence (accepted receipts)

| Receipt | Scope | Result |
| --- | --- | --- |
| `unit-212a-1.xml` | 212 unit module: finite option/edge law, reason law on the ORIGINAL string, signed-doc verification, review/apply dispatch, alias withholding (reason/from/tuples, apply-time), index projection withholding, preset exact-bytes/no-store/non-rotating download, denials | 44 PASS / 0 skip (19.592 s) SHA `1e6d52b0…` |
| `guards-212a-1.xml` | usability inventory (33 tables) + SLAIF design + main-app structure after the new templates | 139 PASS / 0 skip (5.638 s) |
| `cross-212a-1.xml` | affected 208 key-clone (48) + 210 provider/route configuration (59) modules unchanged behavior | 107 PASS / 0 skip (38.957 s) |
| `pg-212a-1.xml` | owned-PG ordered module (sole container owner), authenticated HTTP/TestClient (NOT the browser): review writes no key-policy/accounting/audit state, one-audit exact apply, exact-repeat no-op, rollback to the exact predecessor, ORIGINAL-token-after-a-different-authorized-action Already-at-target, non-target drift refusal, wrong-active-tuple refusal at apply, profile migrate-to-active + repeat no-op, LATE-AUDIT-failure rollback of policy and audit, retry-after-unconfirmed, native auth/CSRF denials - every refusal proves zero key-policy/accounting/domain/audit writes while normal authentication/session last-seen tracking is preserved | 12 PASS / 0 skip (9.830 s) |
| `catalog-212a-1.xml` | existing catalog-route module incl. the NEW route-artifact read-only regression (touch=False, no CSRF refresh, no-store on success and fixed errors, UUID/ready gates intact) | 9 PASS / 0 skip (6.100 s) |
| `browser-212a-2.xml` | actual Chromium (owned PG, sole owner): login -> Operations -> Compatibility index (entry, qualification row, exact preset identities, startup identity), key detail -> Compatibility entry, ready-route index row + route-detail Compatibility entry + credential-free no-store artifact downloads, keyboard module upgrade with same-page preset AND route-artifact downloads (form CSRF survives), DB oracles (exact tuple, one audit, full-row digest), persisted reload, browser-context HTTP repeat of the ORIGINAL token (Already at target), preset exact document, active profile migration, no-JS rollback, narrow/desktop captures | 8 PASS / 0 skip (19.256 s) |
| `unit-212a-visual-1.xml` | the same 44-case 212 unit module RECHECKED (not 88 distinct cases) after the display-only wide-table / short-State-label correction | 44 PASS / 0 skip (19.354 s) |
| `browser-212a-visual-1.xml` | visual-only overlapping recheck: the ONE existing narrow/desktop capture case for final images (not a ninth workflow case) | 1 PASS / 0 skip (10.257 s) |
| `root-cli-oap-212a.xml` | strategic-run: selected CLI wiring/import/safe-error nodes (module-mutation selector wiring, codex-CLI import isolation, migrate-key-profile bootstrap error) + full OAP governance | 19 PASS / 0 fail / 0 error / 0 skip (SHA `1544d250…`) |

The `root-cli-oap-212a.xml` run is a MOCKED CLI-runner wiring / import /
error proof, not an installed CLI or backend run.

The strategic model independently RAN scoped component probes (synthetic,
mocked auth/persistence - NOT native evidence): the review helper (11
pure probes incl. self-edge / tuple-mismatch / wrong-type / outer-extra
refusals), the alias guard (3 router probes: target alias at review,
source alias at review, target alias introduced only at apply), and the
index projection (2 probes: digest/name alias withheld across
text/attributes/hrefs, canonical preset unchanged). It also INDEPENDENTLY
REVIEWED (parsed, not rerun) the formal JUnit receipts above, including
the native 12 - it did not independently rerun that suite.

### In-order corrections (superseded states; product and test changes both occurred)

- The preliminary unit receipts failed with `NameError: Mapping
  undefined` in the NEW PRODUCT alias helper (a missing
  `collections.abc` import in `admin_compatibility.py`, not a
  fixture-only defect); after that product import fix the earlier
  38-PASS receipt is pre-alias-fix history, not final evidence.
- The first browser module runs failed on fixture/oracle defects
  observed for THIS objective: a trailing-slash link oracle, a Python
  `ElementHandle.value` assumption (the value attribute / `input_value`
  must be read instead), an unavailable upgrade repeat select (after
  v4->v5 the finite UI correctly offers rollback, not upgrade:v5), and
  a shipped-preset schema assumption (the current shipped presets are
  schema-2 documents with no top-level digest key); later states also
  corrected the preset bytes-vs-str/decode oracle and a dependent
  no-JS rollback state. Both earlier full-run states (4 failures; then
  3 failures over 7 tests) are superseded.
- The first stored-ready-route seed used provider kind `openai`, which
  the EXISTING `provider_configs` check constraint
  (openai_compatible/module) rejects: a fixture-only 8-ERROR state,
  corrected to the registered qwen38-27b 0.162 profile per the
  strategic order (single `/v1/responses` endpoint, client-local
  compaction, `codex_accounting` pricing metadata; verified
  `protocol_qualified` with empty reason codes by running the real
  service). No backend/schema change.
- The route Codex-profile artifact handler became a read-only
  attachment (no form-CSRF rotation, no-store on success and fixed
  errors) because the new global surface links those downloads; the
  bounded admin.py fix is a PRODUCT read-boundary change covered by the
  catalog receipt above.
- The index State cell was shortened to a "Protocol-qualified" label
  and both wide tables reuse the existing `.table-wide` / `.nowrap`
  classes (display-only; the 44-case unit recheck and 1-case browser
  capture recheck cover it).

### Preexisting observation (out of scope, no change made)

The registered OpenAI 0.147 qualification profile declares
`provider_kind="openai"`, which the stored-provider kind constraint
(openai_compatible/module) can never satisfy, so a v2-declared
gpt-5.6-sol route cannot reach protocol_qualified in a real database.
212-a's ready-route qualification therefore uses the registered
qwen38-27b 0.162 profile. This record makes no claim that the OpenAI
profile was repaired; it was not.

### Limits of this record

Synthetic fixture keys/providers/routes only (no real Codex or
provider request, no real DB beyond the owned disposable PostgreSQL in
the native/browser fixtures); browser evidence is real Chromium +
real uvicorn + real DB oracles, with browser-context HTTP steps
labeled as such (not UI clicks); mocked-auth probes are component
evidence, not native proof; the installed whole-GUI qualification
(objective 219) and all deployment remain explicitly OUT of scope.
Final-head GitHub CI status per head is recorded in the immutable
212-a report.

## 213-a GUI replay reference maintenance (objective 213, new PR,
2026-11-01)

### Scope and GUI-CLI parity contract

G09 (replay-reference inspection and extension) of
`docs/MISSING_GUI_FUNCTIONALITY.md`, delivered on branch
`oap/213-gui-replay-maintenance` (created from verified remote `main`
`abc08014`). The GUI reuses the SAME shared service the CLI uses
(`CodexReplayMaintenanceService.inspect_replay_references` /
`preview_replay_extend` / `apply_replay_extend`, the strict plan
schemas, and the repositories) inside a caller-owned transaction; the
controllers only bind the reviewed plan to the signed-in actor/session
through the existing HMAC review-intent pattern and enforce the GUI's
known-incoming-alias withholding. No schema, migration, permission,
adapter, request-acceptance, accounting, or replay-law change; no raw
replay inventory or content recovery, no expiry shortening, no key
migration or ownership transfer, no production calls. All seeded
keys/references are synthetic; no real provider/Codex request is
involved; the final 219 installed whole-GUI qualification remains
required and is NOT claimed.

### Final evidence (accepted receipts)

| Receipt | Scope | Result |
| --- | --- | --- |
| `unit-213a-1.xml` | 213 unit module: scope parsing/existence, time/TTL/default/expired controls, exact service invocation and read-only preview, strict plan envelope/types/unknowns/duplicates/caps, invalid auth/CSRF/confirmation, wrong actor/session/purpose/key/cohort, expired/tampered counts/TTL/reason/plan, fixed no-echo errors, incoming-alias canaries across every output/sign/apply boundary | 43 PASS / 0 skip (17.163 s) SHA `96af820b…` |
| `unit-guards-213a-1.xml` | the 43 above PLUS usability inventory, SLAIF design, and the 9 OAP governance tests on the exact activated order+active | 185 PASS / 0 skip (20.316 s) SHA `5565c61a…` (includes the 43, not 228 distinct) |
| `pg-213a-1.xml` | owned-PG ordered module (sole container owner): real admin login/CSRF and actual HTTP over the real app; inspection and preview prove NO domain/audit write; eligible/excluded synthetic retained references, original-age monotonic targets, explicit expired inclusion, same-key/finalized-ledger/HMAC eligibility; one session-actor/reason audit; exact reload/repeat with no duplicate write/audit; stale scope and changed-eligibility refusal; late fault after the real audit flush rolls back extension and audit together with retry; independent before/after oracle compares ALL non-expiry key/material/ledger/quota/reservation/replay-ownership fields and the ENTIRE expiry map | 11 PASS / 0 skip (14.131 s) SHA `c49c36de…` |
| `browser-213a-1.xml` | actual Chromium (owned PG, sole owner, real uvicorn, no route mocks): login -> Operations -> Replay maintenance index (three explicit scopes), bound key/cohort detail navigation, inspect with independent before/after oracles, preview -> confirm -> apply through the real UI with exact expiry-map/audit oracles, exact same-session repeat no-op, original displayed token surviving a real background read (browser-context POST), no-JS flow with recovery, desktop/narrow captures | 7 PASS / 0 skip (19.158 s) SHA `ae57bb6d…` |
| `unit-visual-213a-1.xml` | TARGETED post-visual-fix recheck (overlapping the 185, not new distinct totals): the 6 replay page/inspect unit cases rendering the changed templates (index combined Scope column, numeric Keys-in-scope, scope-page facets) plus the design and usability-inventory structural guards after the table-column change | 139 PASS / 0 skip (7.730 s) SHA `3862d3f8…` |
| `browser-213a-2.xml` | TARGETED post-visual-fix recheck (overlapping the accepted 7, not a ninth workflow): the existing inspect case 02 now submits the form with a REAL keyboard Enter and asserts the numeric Keys-in-scope render, and the existing captures case 07 exercises REAL keyboard focus + Space toggle of the review confirmation checkbox (toggled back before the capture; no apply) and adds the narrow POPULATED inspection capture | 2 PASS / 0 skip (11.691 s) SHA `4d637da4…` |

The strategic model independently RAN scoped component probes
(synthetic, no HTTP/auth/PG effects - NOT native evidence): 10 pure
controller/shared scope-parser probes (3 exact scopes; 7 conflicting/
mismatched/missing-kind refusals; scope-parser AST
`fc1199d1…`), 8 pure replay review-token probes, and 14 ASGI guard
probes. It also INDEPENDENTLY REVIEWED (parsed, not rerun) the formal
JUnit receipts above and visually reviewed the refreshed
desktop/narrow captures (visual gate passed on the refreshed set).

### In-order corrections (superseded states; product and test changes
both occurred)

- Pre-acceptance unit fixture corrections only (negative alias
  fixtures actually set the cookies; no fixture `int(bad)` before the
  HTTP call; the conflicting-scope ambiguity is preserved so the Core
  parser sees all populated IDs; invalid schema fields/types; short
  Unicode reason legality; HTML escaping/whitespace assertions). No
  Core change.
- Native fixture/oracle corrections only: an ORM
  `Column.key`/metadata collision, the full-key digest now exercises a
  nonempty legal 0149-v4 pin plus unrelated nested metadata sentinels
  (not only empty `{}`), JSONB datetime-string and comma-number
  expectations, the 07/08 full snapshot taken AFTER intentional
  external drift and BEFORE the refused apply with the full state
  compared immediately after apply before restore (no `updated_at`
  exclusion), and the entire expiry map compared against before plus
  the exact expected changes. No product/Core/accounting change.
- Browser fixture corrections only: the repeat reuses the ACTUAL
  browser context/session of the original apply (no second login or
  serialized-cookie artifact), absolute URLs for the context form
  POST, case 05 uses a REAL background private-POST inspect with the
  ORIGINAL displayed CSRF and then the unchanged visible UI
  confirm/apply, and the no-JS recovery link order. No weakened
  auth/session binding; no mocked backend success.
- Post-acceptance VISUAL corrections (root visual gate on the
  functional captures), all display/test-only: (1) the inspection
  "Keys in scope" projection renamed to `keys_count` because
  `summary.keys` collided with the `dict.keys` builtin in Jinja
  (numeric render now asserted); (2) the index navigation table
  combines label/link/note into ONE Scope column after the ordinal so
  the choices fit the narrow 390px layout; (3) the inspection
  identity/date cells reuse the existing `.table-wide` / `.col-key` /
  `.nowrap` classes inside the scroll wrappers; (4) the absent scope
  facet (cohort name on a key scope) stays absent instead of rendering
  a placeholder; (5) real keyboard evidence added to the same existing
  cases (Enter form submission in case 02; focus + Space checkbox
  toggle, restored, in case 07) and the narrow populated-inspection
  capture added to case 07. The targeted rechecks above cover these;
  the unchanged 185/native-11/full-7 flows were NOT rerun.
- Execution chronology note: the coding CLI hit its context window
  mid-visual-fix on 2026-11-01 and was recovered in the SAME
  CLI/pane/worktree as a continuation of the already-activated 213-a
  (the control OK was consumed ONCE at activation, 13:06 UTC; no
  resignal, no second reader, no model/profile/effort change).

### Reused unchanged evidence (not rerun)

The accepted objective-200/CLI concurrency and large-scope Core proofs
are reused unchanged (no 20k-row scale repetition); the unchanged
cross-purpose 208/210 consumer-guard stdout success is reused. The 9
OAP governance tests ran on the exact activated order+active inside
the accepted 185 receipt.

### Resource evidence

Every PostgreSQL run used a fresh owned, labeled, loopback-bound,
tmpfs-backed container created by the fixture and destroyed by the
fixture's exact-ID cleanup; the final targeted-capture container
(`20b0813f…`, owner `slaif185a-56d3ef…`) was independently verified
NotFound with owner_remaining 0 after the run. No Docker env/DSN
dump, no unowned container mutation.

### Limits of this record

Synthetic fixture keys/references only (no real Codex, provider, or
mail request; no real DB beyond the owned disposable PostgreSQL in the
native/browser fixtures). The 11-case native module is ONE ordered
scenario, not 11 independent workflows, and the 7-case browser module
is one ordered installation flow per case family; mocked-auth unit
probes are component evidence, not native proof. The installed
whole-GUI qualification (objective 219) and all deployment remain
explicitly OUT of scope. Final-head GitHub CI status is recorded in
the immutable 213-a report.
