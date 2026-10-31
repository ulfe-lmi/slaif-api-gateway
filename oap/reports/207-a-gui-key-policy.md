# OAP Coding-Agent Report — 207-a

## Work order
- Identifier: 207-a
- Work-order file: `oap/orders/207-a-gui-key-policy.md`
  (committed with its EXACT original strategic-authored bytes in IMPL;
  sha256
  `a3e959226d2429ccc7f2d4d62603bf2e779304ae9d444394eb42959c52b5bbd0`;
  the file was restored byte-exact from root's trusted preactivation
  copy after an interrupted publication attempt had briefly staged a
  non-conforming header edit — that edit is NOT in this commit)
- `oap/active` pointer: value `207-a` (5 bytes, no trailing newline),
  committed in IMPL; sha256
  `f35dac328657739d4491a7a36715cfba3e0296f034655e2cebb20bc039b82e49`
- Numeric objective: 207
- PR mode: NEW_OBJECTIVE_NEW_PR per the order's own text (exactly ONE
  new objective-207 PR against `main`; base main at
  `67604ad6970ff8486e0a9905fdb87ffd37060bd2`; branch
  `oap/207-gui-key-policy`)
- Implementation head SHA (literal):
  `27a5f0a00d629bed32f9f0733d175e6a48034390`
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

PARTIAL (FORMAT-GATE-FAILED). The G01-G03 product work and the focused
product evidence below are complete and green. However, this head
FAILS two OAP governance format gates because the immutable activated
order bytes use a heading / PR-mode syntax that deviates from the
durable governance format (see "OAP governance format gate" below).
Per the strategic recovery decision, the activated order is published
with its exact original bytes, the governance tests were NOT loosened,
and the failures are reported without waiver. A same-PR strategic
continuation with a correctly formatted order is required before any
merge. GitHub CI on this head is PENDING at publication (treated as
pending, not pass). Strategic review and guarded merge are root-owned.
This is NOT a release/tag/deploy claim and NO completion claim follows
from this head.

## OAP governance format gate (failed on this head, reported)

`tests/unit/test_oap_governance.py`: 7 PASS / 2 FAIL, 0 skip, run on
the restored original order bytes (JUnit `gov-207a-restored.xml` in
the execution workdir, not committed).

The two failures are order-FORMAT gates only; no substantive
instruction is involved:

1. `test_active_identifier_resolves_exactly_one_matching_order`: the
   order's line 1 is `# OAP Work Order 207-a — GUI key policy, rate
   overrides and effective inspection`; the durable gate (satisfied by
   orders 206-a through 206-d) requires exactly
   `# OAP Work Order — 207-a`.
2. `test_initial_round_declares_new_pr_and_one_objective_one_pr`: the
   round declares the new-PR mode as prose (`PR mode:
   NEW_OBJECTIVE_NEW_PR.`) instead of a standalone
   `PR mode: CREATE_NEW_PR` line.

Root's recovery records this as a root-authored heading/PR-mode
clerical syntax error. The coding agent did not edit the activated
order or the governance tests, and makes no completion claim on this
head until the canonical same-PR continuation resolves the format
gate.

## Exact changed paths (21, IMPL)

Product (G01-G03 surfaces only):
- `app/slaif_gateway/api/admin.py` — new routes
  `POST /admin/keys/{id}/rate-limits`,
  `GET /admin/keys/{id}/configuration.json`,
  `POST /admin/keys/{id}/configuration`,
  `POST /admin/keys/{id}/explain-route`; tri-state parse/prefill and
  guided-vs-document policy-source handling on the create and
  policy-update paths; fixed safe errors (rejected documents never
  retained in the re-rendered form, flash, logs, or audit). No
  service-contract, schema, migration, auth, or accounting change.
- `app/slaif_gateway/web/templates/keys/_policy_selector.html`
- `app/slaif_gateway/web/templates/keys/create.html`
- `app/slaif_gateway/web/templates/keys/detail.html`
- `app/slaif_gateway/web/static/js/policy-selector.js`
- `app/slaif_gateway/web/static/css/admin.css` (minimal field-card
  additions)

Tests (new):
- `tests/unit/test_admin_key_policy_207.py` (49 cases)
- `tests/integration/test_admin_key_policy_207_postgres.py` (7 cases)
- `tests/browser/test_admin_key_policy_207.py` (6 cases)

Tests (updated oracles, minimal, no weakened assertions):
- `tests/unit/test_admin_usability_inventory.py`
- `tests/unit/test_admin_key_create_routes.py`
- `tests/unit/test_admin_key_create_templates.py`
- `tests/unit/test_admin_key_actions_routes.py`
- `tests/unit/test_admin_table_rows_194.py` (comment)

Docs and OAP state:
- `docs/MISSING_GUI_FUNCTIONALITY.md` (new; human-requested analysis +
  section 9 delivery status for G01-G03 only)
- `docs/admin-usability.md` (new section 8 + pointer)
- `docs/verification/gui-cli-parity.md` (new single verification
  record)
- `docs/verification/README.md` (index entry)
- `docs/README.md` (two-line navigation)
- `oap/orders/207-a-gui-key-policy.md` (exact original bytes)
- `oap/active` (`207-a`)

NOT committed (protected/ignored, unchanged): `CODEX-SESSIONS.md`,
`codex.sh`, `.local-provider-catalog/`, `.codex/`, and all other
unrelated state.

## Requirement proof (native / mocked / real distinctions)

Requirement 1 — provider fidelity (create + existing-key edits):
- Unit (fake-session ASGI, no DB): tri-state parse law (allow-all /
  selected / deny-all, both-modes refusal, empty-without-mode fail
  closed, unknown-slug and credential-shaped-slug refusal), deny-all
  `[]` persistence, allow-all `null` persistence, disabled-provider
  preservation, unknown-provider refusal (in
  `test_admin_key_policy_207.py`).
- Owned PostgreSQL 16 (real schema, TestClient): tri-state round-trips
  including `[]` and disabled-provider preservation.
- Actual Chromium/owned PG: three creates persisted through the real
  form (allow-all default, allow-list, deny-all), empty-selection
  fail-closed refusal on an existing key, disabled-provider
  preservation with the `slug | manual entry` label, adding a
  provider; no-JS fail-closed submit.

Requirement 2 — strict version-1 configuration in the GUI:
- Unit: document-mode create (missing document, document+guided-policy
  refusal, Codex-preset refusal, trusted-calibration deny-all refusal,
  success building the shared input, error re-render scrubbing the
  document), configuration POST refusals (missing reason / missing
  confirmation / empty / malformed JSON / duplicate key / unknown
  field / missing schema version / empty object) WITHOUT echo of a
  credential-shaped canary, success payload, safe service-error
  message; download headers + exact 9-dp Decimal rendering + 409 on
  export failure.
- Owned PG: export/update round-trip (allowlisted projection headers,
  partial update, unknown-field refusal without echo).
- Actual Chromium: allowlisted export as a private no-store attachment
  (forbidden fields absent), a canonical `requests_per_minute` partial
  update with sibling/allow-list preservation proven by the direct-DB
  oracle (`rate_requests == 7`), the unknown-field canary refused with
  fixed message, no echo, and an emptied re-rendered textarea, plus
  the confirmation and reason refusals.

Requirement 3 — existing-key rate editor:
- Unit: compose law (set/clear, 1-per-10s + concurrency 1, zero /
  blank / unknown-action refusal, no-op detection, prefill), route
  (unauthenticated redirect, invalid CSRF before service, missing
  reason, no-op refusal, set/clear payloads with the session actor,
  zero refusal with the fixed message, 404).
- Owned PG: set 1/10s + concurrency 1, zero/no-op refusals, clear with
  sibling preservation, audit actor/reason.
- Actual Chromium: prefill of the stored 500, zero and no-op refusals,
  set 1/10s + concurrency 1 with the configured/source/effective
  readout, isolation snapshot of untouched members, clear with sibling
  preservation. Usage, reservations, identities, validity, and key
  material are untouched (snapshot assertions).

Requirement 4 — effective inspection + explain:
- Unit: shared-report render with the EXACT shared kwargs
  (`requested_model`, `endpoint`), unauthenticated redirect, 503 fixed
  message on inspection-context failure.
- Owned PG: resolved / blocked / not-evaluated with the audit trail
  and the FULL key-row snapshot unchanged (inspections never write).
- Actual Chromium: resolved, unknown-model blocked, cross-provider
  blocked, and the audit-trail invariant (snapshot taken after the
  login, which itself audits `admin_login_succeeded`; the explain
  POSTs add zero rows).

Requirement 5 — ergonomics / field help:
- Actual Chromium: the five field-help anchors present and non-empty
  with matching `aria-describedby`; grouped sections; narrow 480px
  layout with no horizontal overflow; legacy lazy-throttling and
  lifecycle controls still usable; no-JS server form fallback
  (plain-text owner field, manual provider textarea in the collapsed
  disclosure).

Requirement 6 — table law:
- No new `<table>` element was introduced (the rate editor and
  inspection blocks are grouped field cards); `policy-selector.js`
  table-sort behavior untouched.

Verification negatives (per the order): authentication, wrong/missing
CSRF, missing confirmation/reason, malformed identifiers, 404 targets,
secret-shaped canaries in rejected JSON/fields with no complete canary
in response/log/audit/export, HTML escaping, no-store and unauthorized
export denial, 503 explain unavailability — all covered by the unit /
owned-PG / browser cases above.

## Focused test evidence (local; GitHub CI pending)

Layer: native unit (fake-session ASGI; no DB, no server, no real
provider/mail).
- `tests/unit/test_admin_key_policy_207.py` (NEW): 49 PASS, 0 skip
  (JUnit `unit-207.xml`).
- 207-unit + updated usability inventory combined: 168 PASS, 0 skip
  (JUnit `unit-207c.xml`).
- Directly affected existing admin suites (key create
  routes/templates, key actions routes, 194 table rows, usability
  inventory, and the other touched oracles): 282 PASS, 0 skip (JUnit
  `affected2.xml`).

Layer: owned, labeled, loopback-bound, tmpfs-backed PostgreSQL 16
container (existing fixture generator), real schema/migrations, real
ASGI app through TestClient; exact created container removed on
teardown (verified absent).
- `tests/integration/test_admin_key_policy_207_postgres.py` (NEW):
  7 PASS, 0 fail / 0 error / 0 skip (JUnit `pg-207a-1.xml`).

Layer: actual Chromium on the same owned PostgreSQL with a real
uvicorn app and real stylesheet.
- `tests/browser/test_admin_key_policy_207.py` (NEW): 6 PASS, 0
  fail / 0 error / 0 skip (JUnit `browser-207a-7.xml`, 23.742 s).
- Screenshots (synthetic fixture data only, no key/session/secret
  cells), in the execution workdir `/tmp/slaif207/` (not committed):
  `key-create-form-desktop.png`, `key-detail-effective-policy.png`,
  `key-detail-rate-editor.png`, `key-explain-report.png`,
  `key-detail-narrow.png`.

Static and governance (actual results on this tree):
- `ruff check` on all touched Python files: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK`.
- `tests/unit/test_oap_governance.py`: 7 PASS / 2 FAIL — the two
  FORMAT gates described above, on the immutable order bytes, recorded
  without waiver.

## Privacy / authorization / accounting / replay invariants

- Fixed safe errors only: a rejected configuration document is never
  retained in the re-rendered form, flash, logs, or audit; credential-
  shaped canaries appear nowhere in responses, logs, audit notes, or
  exports (asserted).
- Downloads are the service's allowlisted projection only: policy
  fields, never identity/secret/environment; `attachment` with
  `Cache-Control: no-store` and a `slaif-key-configuration-
  <public_key_id>.json` filename (asserted).
- All mutations go through the existing session/CSRF contexts with the
  session as actor; reasons are bounded nonblank; confirmations are
  explicit checkboxes; unauthenticated and invalid-CSRF requests are
  refused before any service call (asserted).
- Rate edits, policy edits, and configuration updates never touch
  usage counters, reservations, key material, status, validity, or
  replay/module binding (row-snapshot assertions in the owned-PG
  cases); explain/inspections never write (audit-trail and snapshot
  assertions).
- No schema, table, migration, client/server module, provider-
  transport, admission/accounting/replay, or catalog change.

## Deployment / upgrade guidance

Normal rebuild/restart of the API assets picks up the code and static
assets. There is NO schema migration and NO policy mass-update.
Historical deny-all keys stay deny-all and stored allow-lists keep
their values. The operator-visible behavior change: a POST that leaves
the provider selection empty with no mode checked now FAILS CLOSED
instead of silently meaning unrestricted — creating an unrestricted
key requires the explicit "Allow all enabled providers" mode (the
guided default). No deploy was performed.

## Documentation impact

- `docs/MISSING_GUI_FUNCTIONALITY.md`: new section 9 records the
  G01-G03 delivery status and explicitly lists G04-G18 as still open;
  historical findings preserved as written at the baseline.
- `docs/admin-usability.md`: new section 8 documents the key-policy
  administration surfaces (tri-state semantics, advanced document
  semantics/non-goals, rate units/inheritance/no-op law,
  configuration-only explanations, privacy/authorization/help
  patterns, upgrade notes).
- `docs/verification/gui-cli-parity.md` + index entry: the single
  incremental verification record for this GUI round.
- `docs/README.md`: two-line navigation addition.

## Defects found and fixed during qualification (provenance)

Two product defects and four test-side harness issues surfaced only on
the real-page layer and were fixed within this order (full detail in
`docs/verification/gui-cli-parity.md`):
- Product: the create page's document-mode script unconditionally
  unchecked every guided policy checkbox on load (missing
  document-mode guard); now guarded.
- Product: the explain form select was named `explain_endpoint` while
  the handler/CLI paths read `endpoint`; template select renamed.
- Test-side: status-pill CSS uppercasing (raw DOM text compared);
  canonical config member name (`requests_per_minute`) in the test
  document; post-login audit snapshot + export-before-form-page CSRF
  chronology + lifting the client-side `required` attribute so the
  server's fixed refusal is proven; whitespace-normalized readout
  assertion.

## Pending and honest limitations

- OAP governance FORMAT gate: 2 FAIL on the immutable order bytes
  (above). UNRESOLVED; strategic same-PR continuation required before
  merge. No completion claim.
- GitHub CI on the report head: PENDING at publication (treated as
  pending, not pass).
- The unit renders are fake-session ASGI renders (no DB); the owned-PG
  cases are the real-schema proof; the Chromium cases are the
  actual-page proof. No real provider, email, or production traffic is
  involved.
- The GUI parity is at the shared-code level (same parser, same
  `KeyService` operations, same inspection/explain projections as the
  CLI); the CLI itself is not re-qualified here (covered by the
  197-204 CLI records).
- JUnit XML files and screenshots live in the execution workdir
  (`/tmp/slaif207/`), not in the repository.
- This head must NOT be merged: the strategic continuation (correctly
  formatted order, same PR) plus root's review of the actual product
  defects and all final-head checks gate the merge.
