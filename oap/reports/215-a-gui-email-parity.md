# OAP Coding-Agent Report — 215-a

## Work order
- Identifier: 215-a
- Work-order file: `oap/orders/215-a-gui-email-parity.md` (root-authored, committed unchanged)
- Numeric objective: 215
- PR mode: CREATE_NEW_PR (PR #371)

## Status
COMPLETE (implementation, verification, publication, and report-only commit done; final-SELF GitHub CI and the strategic review/merge gates remain pending per the OAP protocol and are root-owned. At report time the PR #371 checks on the implementation head show 7 SUCCESS / 3 IN_PROGRESS / 0 failed; no failure is known at report time.)

## Executive summary
Delivered G12 from `docs/MISSING_GUI_FUNCTIONALITY.md` on ONE new PR
(#371, branch `oap/215-gui-email-parity`, base verified remote `main`
`279f71a89fa6d41f34587ca300f1c6aaed815731`): complete email delivery
inspection, an explicit existing-delivery failed retry, attributable
enqueue intent, and a bounded two-stage reviewed SMTP test. The GUI reuses
the SAME shared surfaces the CLI uses - `validate_delivery_status`,
exact owner-email normalization, the shared finite latest-recorded-failure
projection, the shared Core
`EmailDeliveryService.get_key_email_delivery_sendability`, and the CLI's
extracted `email_key_enqueue_requested` intent-audit seam (CLI now
delegates to it with unchanged ordering, metadata, and defaults). The
explicit retry is a distinct failed-only route (required nonblank reason
bounded to 1024 UTF-8 bytes, confirmation, shared preflight, truthful
not-failed refusal); BOTH ordinary pending actions and the retry now
withhold a provided reason matching a known incoming opaque-auth alias
before any audit/SMTP/broker, and BOTH enqueue paths commit the shared
requested-intent audit durably BEFORE broker dispatch (recording failure
prevents dispatch; broker failure/lost ack is requested-but-unconfirmed,
never queued/sent success; the Celery payload remains exactly the existing
three UUIDs with deferred worker import). The bounded SMTP test uses the
existing `EmailService.send_email` primitive with server-configured
transport only (no browser transport overrides), a strict single
complete-mailbox validation, bounded escape-budgeted one-use signed review
token (15 minutes), durable one-use claim BEFORE the SMTP attempt under a
per-actor 3-attempts/60-seconds budget with a 30-second outer deadline,
honest outcomes (accepted = SMTP acceptance only; unconfirmed never
promises no-message), POST-only submission plus a safe no-send GET
recovery surface, and known-incoming-auth alias withholding from the
persisted user agent before persistence. No schema/migration/permission/
dependency change; the global metadata sanitizer, sender claim/decrypt/
consume/ambiguity/finalization law, and CLI output contracts are
unchanged. No merge performed. No installed/deployment/production/release
claim; the final 219 installed whole-GUI qualification remains mandatory.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 371 (NEW this turn)
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/371
- PR state at report time: OPEN
- PR title (exact, as ordered): Complete safe email inspection, retry and SMTP test controls.
- Base branch: main
- Base remote SHA: `279f71a89fa6d41f34587ca300f1c6aaed815731` (verified `main` at order preflight; tree `baad88bcc91e471ceb8beb50648a2a8f9cc7825b`)
- Head branch: oap/215-gui-email-parity
- Implementation head SHA: 438f8b381005cf69f055c1a277f8809bc2d5e32e
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified from GitHub after the report-only push)
- Implementation commits pushed before the report commit: exactly one - `438f8b381005cf69f055c1a277f8809bc2d5e32e` ("215-a: Complete safe email inspection, retry and SMTP test controls."), whose SOLE parent is base `main` `279f71a89fa6d41f34587ca300f1c6aaed815731` and which includes the root-authored 215-a order and `oap/active`
- Report commit first parent: `438f8b381005cf69f055c1a277f8809bc2d5e32e`
- Amended-branch disclosure (pre-PR, no external reference): the branch was force-updated once with `--force-with-lease` from `73ac005d4a59387ccf0b9168beb91752e7f43f24` to `438f8b381005cf69f055c1a277f8809bc2d5e32e` BEFORE the PR existed, solely to insert two missing blank-line separations between a heading and its preceding paragraph in `docs/upgrade-runbook.md` and `docs/verification/gui-cli-parity.md` (both source files lacked trailing newlines). No PR, CI run, or report ever referenced the superseded SHA; the remote PR carries only `438f8b38...` and this report commit.
- Merge performed: NO
- CI state at report time (2026-11-02T00:07:26Z, structured check-run API on implementation head): 10 total - SUCCESS: CodeQL, Analyze (python), Analyze (javascript-typescript), Analyze Python, Documentation hygiene, Docker Compose smoke, OpenAI-compatible E2E tests; IN_PROGRESS: Unit lint and migration head, PostgreSQL integration tests, Playwright browser smoke; 0 failed. Final-SELF CI completion, strategic review, and the guarded merge are pending and root-owned; this report does NOT claim CI green.

## Changes made
- `app/slaif_gateway/api/admin.py`: email list handler now validates status through the shared `validate_delivery_status` after blank/strip normalization (unsupported values - including the secret-lifecycle labels consumed/expired, which were never persisted delivery states - get a fixed no-echo "Invalid filter." refusal); additive EXACT `delivery_id` / `owner_id` / `owner_email_exact` filters; date bounds accepted as raw strings and parsed (`_parse_admin_email_datetime_filter`: blank/missing = unbounded, since the real HTML form submits blank date controls and framework `datetime` Query validation would 422 on blanks; nonblank parsed with `datetime.fromisoformat`, fixed no-echo refusal otherwise; naive treated as UTC; end-before-start refused) BEFORE limit/offset and carried through Previous/Next; recipient/owner address projections reuse the shared credential-shape withhold; the known incoming auth alias check of ALL signed facts runs immediately after verify/parse, before any render; top-level `workers.tasks_email` import removed (deferred dispatch via the existing `_enqueue` helper). `list_admin_keys` and other non-email pages untouched (verified by AST-vs-base comparison of changed existing functions; the two accidentally touched Keys lines were restored verbatim before this commit).
- `app/slaif_gateway/api/admin_email_operations.py` (NEW): focused router for the bounded SMTP test - prepare (strict single complete-mailbox validation via standard-library `email.headerregistry.Address` with nonempty username/domain and canonical target consistency; raw CR/LF/NUL in recipient/subject refused BEFORE strip/default; known credential shapes refused; subject <=255 UTF-8 bytes, body <=4096 UTF-8 bytes; bounded escape/UTF-8 worst-case budgeted one-use signed review token, 15-minute expiry), POST apply (signed facts are the only content; known incoming auth alias refusal immediately after verify; durable one-use claim - actor-bound, audit entity UUID derived from the nonce - committed BEFORE the bounded SMTP attempt through the existing `EmailService.send_email` with server-configured transport under a per-actor 3-attempts/60-seconds budget and 30-second outer deadline; honest accepted/unconfirmed/failed/unavailable outcomes; lost commit acknowledgement keeps the durable claim and the repeat is refused by it), and a safe NO-SEND GET recovery surface (fixed notice + link to a new test; no resend, no re-claim, no live token; a reload after the form POST can resubmit the consumed POST and the durable one-use claim refuses it truthfully). The handler withholds known incoming authentication aliases from the persisted user agent BEFORE persistence (same-input UTF-8-safe decode, fail closed).
- `app/slaif_gateway/api/admin_review_intent.py`: ONE bounded SMTP test intent purpose (closed facts, derived escape-budgeted size limits, actor/session/expiry binding); old purposes unchanged.
- `app/slaif_gateway/services/email_admin_operations.py` (NEW): narrow shared home for the extracted enqueue intent-audit operation (server actor, optional preserved reason, explicit retry intent; commit-before-dispatch) and the one-use SMTP claim/result orchestration.
- `app/slaif_gateway/services/email_inspection.py` + `app/slaif_gateway/schemas/email_inspection.py`: the shared finite latest-recorded-failure provenance (finite known code, action, recorded time; unknown/missing/unsafe codes project to `unavailable`, never inferred from prose) and the minimal shared GUI projection/query bridge over the EXISTING GUI repository query (CLI defaults/output unchanged; public GUI page-size ceiling 200 / 201 lookahead preserved; no N+1).
- `app/slaif_gateway/services/admin_activity_dashboard.py` + `app/slaif_gateway/schemas/admin_activity.py`: additive bounded list bridge (exact filters, status normalization, date-bounds normalization, recipient/owner credential-shape withholding, cap+1 honest `has_more`) over the existing list query; `AdminEmailDeliveryDetail` merged-failure projection repaired so a found audit failure renders exactly once (no duplicate kwargs).
- `app/slaif_gateway/services/admin_record_choices.py` + `app/slaif_gateway/api/admin_record_choices.py`: ONE closed `email_delivery` choice kind for the new delivery filter (latest 100 + older UUID search, minimal ID/status/time label; existing picker privacy/nonrotating-session behavior unchanged).
- `app/slaif_gateway/db/repositories/email.py` + `audit.py`: bounded shared read/intent query seams (exact delivery/owner/email filters, latest-exact-failure audit read, claimed-attempt lookups).
- `app/slaif_gateway/db/repositories/admin_users.py`: the directly necessary existing-row lock/claim seam for the SMTP test budget/idempotency (normal authentication/session behavior preserved).
- `app/slaif_gateway/cli/email.py`: delegation to the extracted shared validator/intent-audit operation with UNCHANGED CLI behavior, ordering, metadata, and defaults (no command redesign).
- `app/slaif_gateway/main.py`: composition of the new router only.
- `app/slaif_gateway/web/templates/email_deliveries/list.html`: canonical six-persisted-status dropdown (secret-lifecycle labels shown separately as secret lifecycle, never as delivery-state query values), inclusive UTC date controls with associated field help, exact-filter controls with actual IDs + help, credential-withheld recipient/owner columns.
- `app/slaif_gateway/web/templates/email_deliveries/detail.html`: shared finite latest-recorded-failure provenance (no raw legacy prose in the DOM), SAME Core sendability bridge (once per detail; button eligibility derived from `get_key_email_delivery_sendability`, not legacy re-derivation), the distinct failed-retry form (retry mode, required nonblank bounded reason with multibyte help, actual control IDs + `aria-describedby` help, truthful branch-specific copy distinguishing secret lifecycle from delivery state), and the truthful not-failed/not-applicable refusal for non-failed rows.
- `app/slaif_gateway/web/templates/email_operations/smtp_test.html`, `smtp_test_review.html` (NEW): bounded prepare/review/outcome pages - existing padded `action-panel` container, plain operator copy ("Will use the server-configured SMTP service..."), confirm checkbox with unique control ID + `aria-describedby` help, retriable missing-confirm KEEPS the valid one-use form, non-retryable outcomes hide it, plain-text body preview reusing the existing scroll-box class, "no gateway key is attached automatically; do not paste keys/passwords" guidance, and the safe GET recovery rendering.
- `app/slaif_gateway/web/templates/operations/index.html`: one useful entry to the SMTP test.
- Docs: `docs/MISSING_GUI_FUNCTIONALITY.md` (header delivery line + section 17 + Still-open update), `docs/admin-usability.md` (section 16, 16.1-16.5), `docs/cli-reference.md` (GUI-parity paragraph distinguishing the browser confirmation/review/budget WORKFLOWS wrapping the existing CLI `email send-pending-key --retry-failed --reason` and `email test` operations - CLI commands and output contracts unchanged), `docs/security-model.md` (bounded SMTP test and email action audit safety), `docs/upgrade-runbook.md` (215-a note: recreate/restart only, no schema migration, no Nginx change, no new env vars/dependencies, existing deliveries/secrets/audit untouched), `docs/verification/gui-cli-parity.md` (215-a section with evidence and broker/setup-deviation boundaries) and `docs/verification/README.md` (index entry).
- `oap/orders/215-a-gui-email-parity.md` (root-authored, committed UNCHANGED) and `oap/active` (now `215-a`).
- Tests: `tests/unit/test_admin_email_operations_215.py` (NEW, 1478 lines), `tests/integration/test_admin_email_operations_215_postgres.py` (NEW), `tests/browser/test_admin_email_operations_215.py` (NEW), plus canaries folded into the existing `tests/unit/test_admin_email_delivery_actions_routes.py`, `tests/unit/test_admin_activity_templates_safety.py`, and `tests/unit/test_admin_activity_dashboard_service.py`.

## Files changed
```text
M app/slaif_gateway/api/admin.py
A app/slaif_gateway/api/admin_email_operations.py
M app/slaif_gateway/api/admin_record_choices.py
M app/slaif_gateway/api/admin_review_intent.py
M app/slaif_gateway/cli/email.py
M app/slaif_gateway/db/repositories/admin_users.py
M app/slaif_gateway/db/repositories/audit.py
M app/slaif_gateway/db/repositories/email.py
M app/slaif_gateway/main.py
M app/slaif_gateway/schemas/admin_activity.py
M app/slaif_gateway/schemas/email_inspection.py
M app/slaif_gateway/services/admin_activity_dashboard.py
M app/slaif_gateway/services/admin_record_choices.py
A app/slaif_gateway/services/email_admin_operations.py
M app/slaif_gateway/services/email_inspection.py
M app/slaif_gateway/web/templates/email_deliveries/detail.html
M app/slaif_gateway/web/templates/email_deliveries/list.html
A app/slaif_gateway/web/templates/email_operations/smtp_test.html
A app/slaif_gateway/web/templates/email_operations/smtp_test_review.html
M app/slaif_gateway/web/templates/operations/index.html
M docs/MISSING_GUI_FUNCTIONALITY.md
M docs/admin-usability.md
M docs/cli-reference.md
M docs/security-model.md
M docs/upgrade-runbook.md
M docs/verification/README.md
M docs/verification/gui-cli-parity.md
M oap/active
A oap/orders/215-a-gui-email-parity.md
A tests/browser/test_admin_email_operations_215.py
A tests/integration/test_admin_email_operations_215_postgres.py
M tests/unit/test_admin_activity_dashboard_service.py
M tests/unit/test_admin_activity_templates_safety.py
M tests/unit/test_admin_email_delivery_actions_routes.py
A tests/unit/test_admin_email_operations_215.py
```
35 files changed, 7452 insertions(+), 91 deletions(-).

## Acceptance-criteria evidence

### Criterion 1: shared inspection and preserved list semantics
- Result: PASS
- The list status filter offers the six CANONICAL persisted delivery
  statuses only and validates with the SAME shared `validate_delivery_status`
  the CLI uses; unsupported values (including consumed/expired secret-
  lifecycle labels) are a fixed no-echo refusal, verified with genuine
  SQL results in the native layer (pending/failed work; consumed/expired
  refused) and in the focused unit layer. The legacy OR-within/AND-across
  substring filters, chips, latest-100 + older search, deterministic
  ordering, real cap+1 `has_more`, no-JS links, and page ordinals are
  preserved (the existing 214 pagination/formatting/accessibility is
  unchanged; the browser layer re-qualifies real picker selection
  semantics - hidden managed `rc-value` authority, ArrowDown+Enter, exact
  submitted `delivery_id`, exact TBODY). Additive EXACT
  `delivery_id`/`owner_id`/`owner_email_exact` filters use the shared
  normalization/equality and reach the SQL before limit/offset, carry
  through Previous/Next, and retain submitted values/chips. Date bounds
  are inclusive UTC (naive treated as UTC; end-before-start a fixed
  no-echo refusal; BLANK form controls normalize to unbounded so the real
  HTML form submit is always legal - the full-form blank-date regression
  is in the native layer). No N+1: the detail sendability bridge is
  called at most once per detail page. Recipient/owner projections reuse
  the shared credential-shape withhold so list metadata cannot expose
  complete credentials. CLI defaults/output unchanged (CLI `email
  inspect` commands untouched; only delegation in the enqueue-audit and
  reason-validation seams).

### Criterion 2: exact selected-delivery actions and audited dispatch
- Result: PASS
- Ordinary pending send-now/enqueue keep their existing one-page
  confirmation flows; the explicit retry-failed is a DISTINCT failed-only
  route with a required nonblank reason bounded to 1024 UTF-8 BYTES (the
  CLI's byte bound, extracted into the shared seam; a multibyte boundary
  case is covered), a confirmation checkbox, and the shared current Core
  preflight. A non-failed row receives a TRUTHFUL not-failed/not-applicable
  refusal (the failed-row redirect wording stays reserved); every refusal
  performs no SMTP. BOTH ordinary pending actions and the retry now
  withhold a PROVIDED reason matching a known incoming opaque-auth alias
  (pure `is_known_incoming_secret_alias`) before any audit/SMTP/broker,
  with actual-cookie canaries through valid auth/CSRF/eligible targets
  (asserted: no new intent/audit, no second dispatch, fixed safe
  feedback); missing/blank pending reasons remain accepted and the failed-
  only required rule is not applied to pending. The shared
  `email_key_enqueue_requested` intent audit (server actor, explicit retry
  intent, optional preserved reason, `retry_failed` flag, safe
  `one_time_reference_id`) commits durably BEFORE broker dispatch on BOTH
  enqueue paths; a recording failure prevents dispatch entirely (native
  fault seam: zero broker calls). The native layer proves
  durable-before-broker from INSIDE the dispatch stubs using SEPARATE
  fresh PostgreSQL sessions (the 214 threaded DB helper; no `asyncio.run`
  on the live ASGI loop). Broker failure/lost ack is requested-but-
  unconfirmed with a fixed safe message (no raw fault prose, no rollback
  promise, no queued/sent success). The Celery payload is exactly the
  existing three UUIDs; the worker import remains deferred. The native
  layer also covers: pending/failed/sending/sent and secret
  pending/expired/consumed/ambiguous/history states, controlled row-lock
  contention (real actor-lock contention, not auth/CSRF rejection),
  repeat POSTs following existing safe claim/history/idempotency (no
  duplicate secret delivery), pre-commit fault (no SMTP call, safe
  recording-unconfirmed) and real-commit-then-raise ack-loss (durable
  claim kept, repeat refused, no duplicate, no assumed rollback), and
  full mapped-field digests of a seeded small legal unrelated
  key/policy/usage/reservation sentinel allowing only the intentional
  delivery/secret/audit changes.

### Criterion 3: bounded SMTP test through the existing primitive
- Result: PASS
- The test uses `EmailService.send_email` as composed by the CLI
  `_send_test_email`, with the SERVER-configured host/port/TLS/auth/from
  (every transport field explicit in the fixtures; 127.0.0.1 loopback
  sink, no real auth, no TLS); no browser transport override is accepted.
  `ENABLE_EMAIL_DELIVERY` and configuration readiness are respected
  (disabled-settings app case). Recipient validation accepts ONE complete
  mailbox via standard-library `email.headerregistry.Address` with
  nonempty username/domain and canonical target consistency (the
  demonstrated `localonly` / `@example.invalid` / `a@example..invalid` /
  list-parser reinterpretation / group / trailing-syntax / raw CR/LF/NUL
  negatives are covered before strip/default); the canonical recipient is
  exactly what is signed and sent. Subject <=255 UTF-8 bytes, body <=4096
  UTF-8 bytes, no HTML/attachments. Known credential shapes and incoming
  auth aliases are refused immediately after verify, before any render or
  claim. The one-use review token is signed, 15-minute, actor/session-
  bound, and budgeted for JSON/UTF-8 worst-case escaping separately from
  raw field caps (astral code points cost 12 escaped bytes; exact bounded
  fixed JSON overhead; base64 cap `4*ceil(payload/3)` + separator +
  digest): a valid 4096-byte multiline/escaped body builds and verifies
  in an exact round-trip, and the overbound case is refused. The durable
  one-use claim (actor-bound, audit entity UUID from the nonce) commits
  BEFORE the SMTP attempt; a lost commit acknowledgement keeps the claim
  and the repeat is refused by it (native ack-loss seam). The per-actor
  3-attempts/60-seconds budget and 30-second outer deadline are honest
  (attempted/unconfirmed counted; timeout after dispatch = UNCONFIRMED,
  claim/budget stay consumed, no automatic retry) with a controlled
  timeout seam (no 30-second real-network wait). Outcomes are
  accepted (SMTP acceptance only - never verified inbox arrival),
  unconfirmed, failed, or unavailable. The persisted user agent withholds
  known incoming authentication aliases (UTF-8-safe same-input decode,
  fail closed, unaffected metadata preserved). The browser layer proves
  the real flow: prepare -> reviewed facts (verbatim) -> retriable
  missing-confirm keeps the one-use form -> confirm -> accepted with a
  REAL loopback sink message-count proof -> truthful reload (the actual
  method is observed: Chromium resubmitted the POST and the durable one-
  use claim refused it "already used"; no live token; sink unchanged) ->
  direct GET recovery 200 (no-send notice + link) -> fresh prepare page.

### Criterion 4: exact bounded paths and ergonomics
- Result: PASS
- All changes are inside the ordered exact bounded paths (see Files
  changed): NEW `api/admin_email_operations.py` focused router with
  `main.py` composition only; `api/admin.py` touched ONLY for email
  list/detail/send/enqueue bridges and navigation (verified against base
  by AST comparison of changed existing functions - `list_admin_keys`
  and every other non-email function byte-identical in behavior); the
  NEW `web/templates/email_operations/` templates plus the directly
  necessary `email_deliveries/` and `operations/index.html` changes;
  `cli/email.py` ONLY delegation; no models/migrations/schema changes;
  no theme/redesign (existing shell, pickers, sorter, and padding
  conventions reused). Every new/touched visible control has a unique
  ACTUAL control ID and associated field-specific help (units, blank/
  default, scope, consequences); operator copy is plain (no generic
  HMAC/transaction/authority walls). Desktop and narrow captures were
  taken under `/tmp/slaif215/` (`215a-desktop-list.png`,
  `215a-desktop-detail-failed.png`, `215a-desktop-detail-after-retry.png`,
  `215a-desktop-smtp-review.png`, `215a-narrow-list.png`,
  `215a-narrow-list-paged.png`, `215a-narrow-detail.png`,
  `215a-narrow-smtp-review.png`) and visually reviewed: list/detail shell
  and controls, SMTP review padding (existing `action-panel` container)
  and truthful "Will use..." copy, and narrow width containment were
  accepted.

### Criterion 5: proportionate verification and setup
- Result: PASS
- No new packages, helper agents, or infrastructure; the existing
  `/tmp/slaif192-coding-venv`, installed Chromium (chromium-1248), and the
  qualified fresh-owned PostgreSQL fixture (`owned_pg_url` re-exported
  from the 214 module) are reused; ONE focused SMTP sink is a STANDARD-
  LIBRARY loopback-only synthetic sink inside the 215 test modules - a
  LOCAL MOCK SMTP, explicitly NOT an inbox/provider/TLS qualification.
  One current JUnit receipt per necessary layer under `/tmp/slaif215`
  (below); unchanged modules were NOT rerun solely to manufacture
  receipts.

## Verification evidence
Receipts are SEPARATE and NON-ADDITIVE (overlaps stated, not summed):

- `/tmp/slaif215/unit-215a-affected.xml` - 114 tests, 0 failures, 0
  errors, 0 skipped, 27.988s, 2026-11-01T23:43:16Z, SHA256
  `9219f268aaea4684ae4087c3cc702d1fcfc09135c24fa19b045d39c1537d5acf` -
  the focused affected unit layer (`test_admin_email_operations_215.py`,
  `test_admin_email_delivery_actions_routes.py`,
  `test_admin_activity_templates_safety.py`, `test_admin_keys_routes.py`,
  `test_admin_list_filters_195.py`).
- `/tmp/slaif215/unit-215a.xml` - 290 tests, 0 failures, 0 errors, 0
  skipped, 64.097s, 2026-11-01T22:33:18Z, SHA256
  `be1c00cc827168a79681c6a6322e7368c5dbde8ea100271fb2afc9cf935f4e85` -
  the component unit layer, run BEFORE the final fixture-only test-file
  edits; all 20 changed app-source files predate that suite, so it is
  reused accepted and NOT rerun.
- Overlap (independently counted case IDs): the 290-test component layer
  and the 114-test affected layer share 61 case IDs; the 229 unchanged
  component cases plus 53 additional latest cases give 343 unique case
  IDs - NOT 404 unique/current-suite executions.
- `/tmp/slaif215/pg-215a.xml` - 23 tests, 0 failures, 0 errors, 0
  skipped, 13.872s, 2026-11-01T23:43:52Z, SHA256
  `c96630a7602f7372819fecede6a751bb6e1f7d4a52cd9c9d9050193e0b6e3c4b` -
  native owned-PostgreSQL HTTP qualification (states matrix, durable-
  before-broker inside-stub proofs, pre-commit and real-commit-then-
  raise fault seams, controlled row-lock contention, preservation
  sentinels, blank-date full-form regression, alias canaries).
- `/tmp/slaif215/browser-215a.xml` - 9 tests, 0 failures, 0 errors, 0
  skipped, 22.397s, 2026-11-01T23:51:50Z, SHA256
  `517c191c395abb21afa708487662892a5e3d0f59586c569edfea3e06ec958a23` -
  real-Chromium qualification (real uvicorn + owned PG; canonical
  controls, real picker semantics, retry-failed send-now with real sink
  message-count proof, no-JS missing-confirm -> confirm -> send, enqueue
  UI with recording stub at the existing seam - exact three-UUID payload,
  truthful queued/unconfirmed feedback, no real broker contact - the
  full SMTP flow with truthful reload + direct-GET recovery, keyboard/
  no-JS filter-preserving pagination, desktop + narrow captures).
- `/tmp/slaif215/gov-215a.xml` - 9 tests, 0 failures, 0 errors, 0
  skipped, 0.179s, 2026-11-02T00:01:59Z, SHA256
  `271aaa63ea918b21db33b8a28b22a2bdb5e1290339f535408d6f7f3cae142507` -
  OAP governance against the CURRENT 215-a order/active at final code.
- Static: scoped `ruff check` over all 22 changed Python files: clean;
  `py_compile` over all changed/new Python files: clean.

Commands (all single-process, no xdist workers, no HPC sharding; ambient
`DATABASE_URL`/`TEST_DATABASE_URL` cleared for every test process):

```text
/tmp/slaif192-coding-venv/bin/python -m pytest tests/unit/test_admin_email_operations_215.py tests/unit/test_admin_email_delivery_actions_routes.py tests/unit/test_admin_activity_templates_safety.py tests/unit/test_admin_keys_routes.py tests/unit/test_admin_list_filters_195.py -q -p no:cacheprovider --junitxml=/tmp/slaif215/unit-215a-affected.xml
/tmp/slaif192-coding-venv/bin/python -m pytest tests/integration/test_admin_email_operations_215_postgres.py -q -p no:cacheprovider --junitxml=/tmp/slaif215/pg-215a.xml
/tmp/slaif192-coding-venv/bin/python -m pytest tests/browser/test_admin_email_operations_215.py -m playwright -q -p no:cacheprovider --junitxml=/tmp/slaif215/browser-215a.xml
/tmp/slaif192-coding-venv/bin/python -m pytest tests/unit/test_oap_governance.py -q -p no:cacheprovider --junitxml=/tmp/slaif215/gov-215a.xml
/tmp/slaif192-coding-venv/bin/python -m ruff check <22 changed Python files>
```

## Environment status
- Redis: NOT used by any local qualification; the broker URL in settings
  stays inert. Broker boundaries stated exactly: the native owned-PG
  fixture default-denies live dispatch at BOTH enqueue helper bindings
  (each enqueue case installs an explicit recording/broken stub, and the
  unowned localhost:6379 is never contacted); in the browser fixture the
  enqueue UI case patches/restores the existing seam with recording/
  broken stubs (no real broker contact).
- Docker: available and used ONLY through the qualified fresh-owned
  PostgreSQL fixture (full container ID/owner, 127.0.0.1 loopback
  binding, and tmpfs verification before any SQL; only its own resource
  is cleaned).
- SMTP: loopback-only STANDARD-LIBRARY synthetic sink inside the 215 test
  modules - LOCAL MOCK SMTP, not an inbox/provider/TLS qualification;
  every transport field explicit (127.0.0.1 sink port, no real auth, no
  TLS); real SMTP acceptance proof is limited to the mock's
  message-count/`rcpt_to`/body assertions.
- DB isolation: `DATABASE_URL`/`TEST_DATABASE_URL` cleared for every test
  process; all qualification PostgreSQL state lives in fresh owned
  containers; no shared or ambient database is used by the accepted
  evidence.

## Setup deviations (preserved honestly; no reruns)
- Before the accepted qualification, one early probe (call
  `81215e8dc2d4c319`, 2026-11-01T21:03:25Z) attempted eight unowned
  localhost PostgreSQL connections on ports 5432/54330 using username
  guesses. The inspected output showed password prompts only - NO
  successful SELECT result and NO DDL/DML were observed - and ROOT
  stopped it; ALL subsequent qualification used fresh owned PostgreSQL
  fixtures only. This report therefore does NOT claim "no ambient DB
  attempts".
- Separately, the hash-only protected `uv.lock` was grepped for two
  installed dependency-name lines during setup; NO content change was
  observed, and the file remains untracked/protected - current state
  verified at report time: 405520 bytes, SHA256
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`
  (identical to the order-time value). This report therefore does NOT
  claim "no protected-file reads".

## Safety confirmations
- No merge performed; the coding agent never merges; strategic review
  and the guarded merge remain pending per the OAP protocol.
- No schema/migration, permission, dependency, or deployment change;
  `docs/database-schema.md` and the other contract documents are
  unchanged.
- No production, real-recipient, real-SMTP-account, provider, or Codex
  call; no real email sent; the only SMTP qualification is the labeled
  LOCAL MOCK SMTP loopback sink.
- No secrets in logs, audit, templates, or this report; the global
  metadata sanitizer is unchanged; the protected untracked files are
  byte-identical to their order-time values: `CODEX-SESSIONS.md` 7881
  bytes SHA256 `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
  `codex.sh` 492 bytes SHA256
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
  `uv.lock` 405520 bytes SHA256
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`.
- No reset/clean/stash; no unrelated worktree/catalog/config changes;
  the `.local-provider-catalog/` local artifacts are untouched.
- No release/tag/deployment claim of any kind; the only published release
  remains `v0.1.0-rc.1`.

## Documentation impact
`docs/MISSING_GUI_FUNCTIONALITY.md` (G12 delivered by 215-a; section 17
with the delivered scope and broker/setup boundaries; G14/G15/G17 remain
open), `docs/admin-usability.md` (section 16 operator walkthrough incl.
no-schema note), `docs/cli-reference.md` (GUI-parity paragraph: shared
surfaces plus the browser confirmation/review/budget WORKFLOWS wrapping
the existing CLI `email send-pending-key --retry-failed --reason` and
`email test` operations; CLI commands and output contracts unchanged),
`docs/security-model.md` (bounded SMTP test and email action audit
safety inside the Email And Celery section), `docs/upgrade-runbook.md`
(215-a: recreate/restart only, no schema migration, no Nginx change, no
new env vars/dependencies, existing deliveries/secrets/audit untouched),
`docs/verification/gui-cli-parity.md` (215-a section: scope, parity
contract, evidence, broker boundaries, setup deviations) and
`docs/verification/README.md` (index entry). No contract document
(`docs/database-schema.md`, `docs/rc2-feature-scope.md`,
`docs/compatibility-matrix.md`, provider/Responses contracts) is changed.

## Boundaries and honest limitations
- This report makes no final-code/full-GUI/installed/production claim
  beyond the recorded focused receipts; the SMTP proof is LOCAL MOCK
  SMTP only, and "accepted" means SMTP acceptance, never confirmed inbox
  arrival.
- Final-SELF GitHub CI, strategic review, and the guarded merge remain
  pending per the OAP protocol; at report time 7 of 10 checks on the
  implementation head are SUCCESS, 3 are IN_PROGRESS (Unit lint and
  migration head, PostgreSQL integration tests, Playwright browser
  smoke), and none has failed.
- The 215 objective is NOT resolved while PR #371 remains unresolved;
  the next numeric objective (216) is NOT activated; the whole-GUI goal
  stays ACTIVE through 219, and the final 219 installed whole-GUI
  qualification remains mandatory and unclaimed.
- The immutable 214-a/214-b orders/reports remain byte-for-byte
  unchanged and reachable in the PR/Git history.

I have ended this execution turn. The immutable report for the active
identifier is published, and every branch/commit/PR state claimed in that
report already exists on GitHub.
