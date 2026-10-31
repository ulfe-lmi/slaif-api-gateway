# OAP Coding-Agent Report — 208-a

## Work order
- Identifier: 208-a
- Work-order file: `oap/orders/208-a-gui-key-clone.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `ca86edff0f72dc1d1dec56d13e7c6f964afc9f8740e29a3b6fbdf735ba96f297`)
- `oap/active` pointer: value `208-a` (5 bytes, no trailing newline),
  committed in IMPL; sha256
  `365e7d2a3c58e51eb1eac341348d79d2235d76c2f86fad31bb5e6ac4672ab933`
- Numeric objective: 208
- PR mode: CREATE_NEW_PR (PR 364 "Add reviewed key cloning to the
  admin GUI"; branch `oap/208-gui-key-clone`; base main at
  `09cbfb4795e279ef04e7a54f933afbeeaa7022b6` — the merged 207 head)
- Implementation head SHA (literal):
  `65ac0fd5543840383637d48fa71110cb9e3886a9` (implementation commit set:
  `f8d9af4e4d44e7167612824dd99ff17efcbefaad` product+tests+docs plus
  `65ac0fd5543840383637d48fa71110cb9e3886a9` verification index entry)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

ALL 208-a ORDER REQUIREMENTS IMPLEMENTED; FOCUSED LOCAL VERIFICATION
GREEN. The 208-a order is committed byte-exact and active; 9/9 OAP
governance checks pass on this head. GitHub CI on this head was IN
PROGRESS at publication (treated as pending, not pass); the merge gate
remains root-owned. No release/tag/deploy claim, and no completion
claim beyond the 208-a scope. No real provider, email, or production
traffic was involved (the SMTP failure path is a synthetic
monkeypatch).

## Delivered (per order requirement)

1. **Clone entry + guided form (requirement 1).** The key-detail page
   gains a bounded "Clone This Key" action panel (clone link + "Check a
   clone outcome" recovery link; all prior sections/actions unchanged).
   `/admin/keys/{id}/clone` shows the source public identity and a
   read-only core eligibility probe (`KeyCloneService.build_plan`
   against the source's own owner - the core decides; an unsupported
   source is refused honestly with a fixed controlled state and its
   policy is never reset or weakened), the existing latest-100 record
   pickers for the target owner (required) and cohort (optional; blank
   = no cohort) with the plain-text no-JS fallback, and exactly three
   validity modes: copy-source-expiry, positive whole duration from
   execution time (seconds/minutes/hours/days, service-bounded), or an
   explicit UTC window (end > start, end > now). Nothing is created on
   the form page.
2. **Review with the core, preview-only (requirement 2).** The form
   POST calls the core `build_plan` (no GUI policy engine, no mutation,
   no policy audit) and renders a readable canonical-policy summary
   (provider/model/endpoint tri-state wording, cost/token/request
   limits, WINDOW-AWARE rate counts, lazy throttling honoring the
   explicit mode, live-burn, external-tool, and a NEUTRAL null-
   Responses readout — no blanket "disabled" claim), the reviewed
   target/validity/delivery summary, the operation UUID and
   fingerprints, and the optional raw non-secret plan/policy JSON in
   `<details>`. Apply requires the explicit confirmation checkbox, a
   bounded nonblank reason (server-side refusal before mutation or
   audit; masked through the existing redaction seam before storage),
   the session-derived actor, CSRF, and - when the copied policy is
   fenced external-tool - a FRESH fenced checkbox (never copied from
   the source key). The review page never shows key material.
3. **Review-intent binding (requirement 3; decision 2).** The review
   state is a purpose-bound HMAC-SHA256 token over the strict plan plus
   the acting admin user ID, admin session ID, a short expiry, and the
   delivery mode, keyed with the existing `ADMIN_SESSION_SECRET`.
   Apply verifies, before ANY mutation: token format (a digest that is
   not exactly 64 lowercase hex characters - including non-ASCII input
   - is a fixed controlled refusal BEFORE any constant-time
   comparison), the constant-time HMAC, the purpose/actor/session
   binding, the expiry, and a STRICT re-parse of the embedded plan;
   the plan's source must match the URL path. Bounded DECODED plan
   bytes (the core 128KiB limit the strict parser alone does not
   enforce) AND the final encoded token size are enforced at build and
   verify, with the full core-supported plan scope still building
   within the documented overhead. The hidden JSON/fingerprint is an
   authority only in the verified form; the token carries no
   gateway-key, replay, or provider secret; the SAME reviewed plan is
   executed (never a regenerated operation UUID).
4. **Delivery bound before confirmation (requirement 4).** The channel
   (none / pending / send-now / enqueue) is bound at review and
   revalidated against the existing readiness rules at apply; the
   delivery preconditions are re-derived from the VERIFIED TOKEN, so a
   mutable apply field can never change the reviewed channel. All
   mutations commit in the caller-owned transaction; dispatch happens
   only AFTER commit; a post-commit channel failure renders "Created
   With Delivery Failure" with the stable target/secret/delivery IDs
   and an explicit "A second clone is NOT needed" recovery path (never
   a request for a second clone). The generated key is displayed at
   most once (none/pending channels) in a private no-store result
   page; already-applied outcomes never decrypt or redisplay.
5. **Read-only outcome recovery (requirement 5).**
   `/admin/keys/{id}/clone/receipts?operation=` inspects the committed
   receipt by source + operation through the new READ-ONLY
   `find_clone_receipt` projection: created (with stable IDs and
   fingerprints), not-found ("NOTHING is assumed"), ambiguous (fixed
   safe state), and malformed (repository-matching receipts missing
   required identity members are `key_clone_receipt_malformed`, never a
   claimed completed clone). It works after the review state expired or
   the result page was lost; the operation input is redacted before
   redisplay while ordinary misspelled UUIDs keep their useful fixed
   error; the view never creates, mutates, or assumes anything.
6. **Target law (requirement 6).** `execute_plan` reuses the qualified
   core law unchanged: locked source revalidation with fresh
   fingerprint/policy comparison (stale plans refused), deduplication
   on the operation UUID BEFORE creation, independent key material and
   identity, zero usage and reservations, its own replay ownership,
   the committed receipt, and the audited `gateway_key_cloned` row.
   Source and unrelated rows are untouched (proven by before/after
   row snapshots).

### Bounded changed paths (exact)

- `app/slaif_gateway/api/admin_key_clone.py` (NEW focused router:
  form / review / apply / receipts)
- `app/slaif_gateway/api/admin_review_intent.py` (NEW purpose-bound
  review-intent token: build/verify, bounded sizes, controlled
  format refusals)
- `app/slaif_gateway/services/key_clone_service.py` (read-only
  `find_clone_receipt` projection + `KeyCloneReceiptProjection` +
  `KeyCloneReceiptMalformedError`; no change to build/execute/dedup/
  fingerprint/receipt law)
- `app/slaif_gateway/main.py` (router include only)
- `app/slaif_gateway/web/templates/keys/clone_form.html`,
  `clone_review.html`, `clone_result.html`, `clone_recovery.html`
  (NEW); `detail.html` (bounded action panel)
- `app/slaif_gateway/web/static/js/key-clone.js` (NEW progressive
  validity-mode enablement; never converts/scales values) +
  `app/slaif_gateway/web/assets.py` (registration)
- Tests: `tests/unit/test_admin_key_clone_208.py` (NEW, 47 cases),
  `tests/integration/test_admin_key_clone_208_postgres.py` (NEW, 4
  cases), `tests/browser/test_admin_key_clone_208.py` (NEW, 3 cases)
- Docs: `docs/MISSING_GUI_FUNCTIONALITY.md` (header line, G04 status,
  section 10), `docs/admin-usability.md` (section 9),
  `docs/verification/gui-cli-parity.md` (208-a section),
  `docs/security-model.md` (focused subsection),
  `docs/verification/README.md` (index entry)
- OAP: `oap/orders/208-a-gui-key-clone.md` (exact bytes),
  `oap/active` (`208-a`)

No schema, migration, model, CLI, worker, or runtime-accounting
change.

## Focused evidence (local; GitHub CI pending)

Layer: native unit (ASGI app with the existing fake-session seams; no
DB, no server, no real provider/mail).

- `tests/unit/test_admin_key_clone_208.py`: 47 PASS, 0 skip (JUnit
  `unit-208a-4.xml`): intent round-trip, expiry at the boundary, wrong
  actor/session/secret, tamper, malformed formats (incl. the
  controlled non-ASCII digest refusal before comparison), builder
  decoded-plan bound (hypothetical oversized document refused) and
  final-token bound, the full core-supported scope still building,
  vanished-source controlled 404 on the form AND the re-render path,
  ineligible/secret-shaped source refusals with no token issued,
  apply confirmation/reason bounds (blank/513 refused), forged
  delivery field ignored (channel bound at review), fenced
  confirmation required/accepted, one-time plaintext exactly once
  with no-store headers, already-applied without redisplay/duplicate
  audit, post-commit send-now failure (synthetic `EmailError`)
  rendering "Created With Delivery Failure" with stable IDs and no
  plaintext, read-only recovery (created / not-found / ambiguous /
  malformed incl. the two-ID-only malformed receipt) with the
  recovery operation-input canary redaction and ordinary UUID errors
  preserved, the window-aware rate readout (10s window labeled by the
  window; minute default keeps the per-minute grammar), the lazy
  reject/wait mode controls, and the neutral null-Responses readout
  (no blanket "disabled" claim).

Layer: actual owned, labeled, loopback-bound, tmpfs-backed
PostgreSQL 16 container (same qualified fixture generator), real
schema/migrations, real ASGI app through `TestClient` (no browser);
exact created container removed on teardown (verified in the runner
output).

- `tests/integration/test_admin_key_clone_208_postgres.py`: 4 PASS,
  0 skip (JUnit `pg-208a-1.xml`): faithful canonical clone to an
  ALTERNATE owner + cohort (the target controls are proven persisted,
  not ignored): policy columns and metadata blocks equal the source,
  exact 3601s window (non-minute, exact persisted timedelta), zero
  usage/reservations, independent token hash/public ID, receipt
  identity (operation UUID equal to the reviewed operation, source/
  target IDs, target owner/cohort, status created, fingerprints),
  source and unrelated-key snapshots unchanged (policy rows and
  one-time-secret rows), exact-repeat returning already-applied with
  no second key/audit/plaintext and unchanged target, stale (post-
  review source validity change) and tampered-token refusals proven
  by AFTER-change state snapshots and audit counts, committed clone
  with a post-commit SMTP failure (synthetic monkeypatch) showing
  "Created With Delivery Failure" plus the persisted pending delivery
  and its recovery, suspended-source form/review controlled states
  (no 500), and the send-now precondition refusal when delivery is
  disabled.
- 207/208 coexistence: the 208 seed is get-or-create on the
  DB-unique provider slugs (the existing repository pattern, as in
  `test_cli_key_clone_postgres.py`), so the 207 and 208 modules pass
  together on one session database: 14 PASS, 0 skip (JUnit
  `pg-208a-coexist.xml`).

Layer: real Chromium on the owned fixture (Playwright sync API,
uvicorn app, real stylesheet); exact created container removed on
teardown.

- `tests/browser/test_admin_key_clone_208.py`: 3 PASS, 0 skip (JUnit
  `browser-208a-1.xml`): key-detail clone entry with the preserved
  ordinary panels; guided form with the record pickers driven and a
  3601s duration; review page with the window-aware 10s rate readout
  ("30 requests, 0.01M tokens per 10s window", no per-minute label),
  the neutral null-Responses readout, and no key material;
  keyboard-only apply (focus + Space to confirm, typed reason, Enter
  to submit) with no-store response headers; one-time result asserted
  from HTML only (the plaintext page is NEVER screenshotted);
  persisted-target oracles (policy fidelity, zero usage, receipt
  identity equal to the reviewed operation, exact window, audit
  count, source unchanged); exact-repeat via the same still-valid
  token through a form POST (already-applied, recorded target, no
  second key/audit/plaintext); recovery created/not-found views; the
  no-JS typed-UUID fallback carried through to the persisted no-
  cohort target (with its own audit/receipt proof); and a
  narrow-viewport (768px) review capture. Focused screenshots
  (synthetic data only, no key/session/secret cells) under
  `/tmp/slaif208/`.

A throwaway fake-persistence probe (`/tmp/slaif208/probe_routes.py`,
not in the repository) exercised the full route surface during
qualification; all probes passed. It is execution state, not
evidence of record.

## Static and governance checks

- `ruff check` on all touched/new Python files: clean.
- `git diff --check`: clean.
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK
  files=135`.
- `tests/unit/test_oap_governance.py`: 9 PASS, 0 skip (JUnit
  `governance-208a.xml`) with the 208-a order bytes committed and
  `oap/active=208-a`.

## CI chronology

- PR 364 head `65ac0fd5543840383637d48fa71110cb9e3886a9` (IMPL) pushed
  and verified as the PR head before report publication.
- At publication the run was in progress: "Documentation hygiene"
  PASS; "Unit, lint, and migration head", "PostgreSQL integration
  tests", "Playwright browser smoke", "OpenAI-compatible E2E tests",
  "Docker Compose smoke", and the CodeQL analyses PENDING. Pending is
  recorded as pending, not pass; root's final-head checks and review
  gate the merge.

## Privacy invariants

- The review-intent token is never echoed in errors, logs, or
  recovery output; its digest is format-checked (exactly 64 lowercase
  hex) before any constant-time comparison, and non-ASCII or malformed
  digests are fixed controlled refusals.
- The generated key is displayed at most once (none/pending channels)
  in a private no-store page; send-now/enqueue results and
  already-applied outcomes never show or decrypt it.
- Reasons and the recovery operation input pass through the existing
  redaction seam before retention/redisplay; ordinary useful values
  are preserved.
- Test assertions over generated/credential-shaped values compute
  booleans first and assert fixed labels only; the browser result
  page carrying the one-time plaintext is never screenshotted.
- No gateway-key, replay, or provider secret is carried in the token,
  the templates, or the recovery view; the seeded fixtures use
  synthetic values only.

## Deployment

A normal rebuild/restart of the API assets. **No schema migration, no
model change, no CLI/worker change, no policy mass-update.**
Historical keys are untouched; cloning is an explicit two-step
operator action that creates a NEW key with independent material,
identity, zero usage and reservations, and its own replay ownership.

## Documentation

- `docs/MISSING_GUI_FUNCTIONALITY.md`: header delivery line (G04
  delivered by 208-a; G05-G18 remain open), "Still open" updated, new
  section 10 "Delivery status (objective 208-a)".
- `docs/admin-usability.md`: new section 9 (navigation, review readout
  semantics incl. the window-aware rate line and the neutral null-
  Responses wording, safety/error behavior, no-JS and narrow
  behavior, upgrade notes).
- `docs/verification/gui-cli-parity.md`: new "208-a reviewed key
  cloning" section (GUI-to-CLI mapping, focused evidence per layer,
  static/governance checks, honesty and limitations).
- `docs/security-model.md`: new focused subsection "Reviewed key
  cloning and review-intent state (objective 208)" (token law, core
  execution law reuse, one-time delivery, read-only recovery,
  refusal states).
- `docs/verification/README.md`: 208-a index entry (207 entries
  preserved).

## Pending and honest limitations

- GitHub CI on the report head: PENDING at publication (treated as
  pending, not pass); root's final-head checks and guarded merge gate
  this PR.
- The unit renders are fake-session ASGI renders (no DB); the owned-
  PG cases are the real-schema proof; the Chromium cases are the
  actual-page proof. No real provider, email, or production traffic is
  involved (the SMTP failure is a synthetic monkeypatch); no release
  or production claim follows.
- The GUI parity is at the shared-code level: the same
  `KeyCloneService` build/execute law and the same strict plan schema
  as the CLI clone commands. The core concurrency/rollback/replay
  proofs are component evidence from the qualified 196-205 core/CLI
  objective records and are not re-run here; the CLI itself is not
  re-qualified by this PR.
- The review-intent token is a bounded browser-session review-state
  adapter (short expiry; actor/session/source/delivery bound); it is
  not a signing framework. The recovery view is read-only and never
  creates or assumes an outcome.
- JUnit XML files and screenshots live in the execution workdir
  (`/tmp/slaif208/`), not in the repository.
