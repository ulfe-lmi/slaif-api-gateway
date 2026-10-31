# 2026-10-31 objective 207-a GUI key policy administration verification

Focused verification record for the 207-a admin GUI key-policy
administration change (G01-G03 of `docs/MISSING_GUI_FUNCTIONALITY.md`; PUBLISHED AS PARTIAL — the OAP governance format gate fails on the immutable order bytes, see below):
provider tri-state + advanced versioned configuration, existing-key
operational rate editor, and effective-policy inspection with
configuration-only "explain model access"). The GUI surfaces REUSE the
already-qualified shared services and projections; no database schema,
table, migration, client/server module, or sortable table was added.

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
  fetched before the form page is rendered because every admin page
  render refreshes the session CSRF token (existing admin design): a
  form page fetched before any other admin GET would carry a stale
  token. The empty-reason refusal block lifts the client-side
  `required` attribute first so the SERVER's fixed refusal, not native
  validation, is what is proven.
- **Test-side (readout whitespace):** the effective-policy rate readout
  renders each member as separate text nodes (`requests_per_window:`
  then, on the next line, `configured 7 (source: key)`), so the
  configuration-update assertion compares whitespace-normalized page
  text (`_flat`), exactly as the rate-editor case does. The persisted
  value itself is proven by the direct-DB oracle
  (`rate_requests == 7`).

## OAP governance format gate (UNRESOLVED on this head)

The activated immutable order
`oap/orders/207-a-gui-key-policy.md` (SHA256
`a3e959226d2429ccc7f2d4d62603bf2e779304ae9d444394eb42959c52b5bbd0`,
restored byte-exact from root's trusted preactivation copy) carries a
heading / PR-mode syntax that deviates from the durable governance
format used by orders 206-a through 206-d: line 1 is
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
`test_initial_round_declares_new_pr_and_one_objective_one_pr` fail on
the order format only; every other governance check passes. A
same-PR strategic continuation with a correctly formatted order is
required before any merge.

## Static and governance checks

- `ruff check` on all touched Python files (admin.py + the four 207
  test files + the updated oracles): clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `tests/unit/test_oap_governance.py`: 7 PASS, 2 FAIL, 0 skip — the two
  OAP governance FORMAT gates listed above fail on the restored
  immutable order bytes (recorded without waiver); the other seven
  governance checks pass.

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
 order bytes; the strategic same-PR continuation must resolve that
 before merge. No completion claim follows from this head.
- GitHub CI on the report head is pending at publication (treated as
  pending, not pass); strategic review and guarded merge are the root's
  gates.
