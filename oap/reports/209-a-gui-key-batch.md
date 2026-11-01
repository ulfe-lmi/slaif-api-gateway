# OAP Coding-Agent Report — 209-a

## Work order
- Identifier: 209-a
- Work-order file: `oap/orders/209-a-gui-key-batch.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `e16fe3c2fc951136723ea7373293f94031bab8c50111d7aa0337907f5f7d6c5b`,
  18,960 bytes)
- `oap/active` pointer: value `209-a` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 209
- PR mode: CREATE_NEW_PR (PR 365 "Add reviewed atomic key batch
  changes to the admin GUI"; branch `oap/209-gui-key-batch`; base main
  at `a4ed3ae68851ecbe0cb6862106abc287f3d6af55`, the merge of PR 364)
- Implementation head SHA (literal):
  `2aaf11d2714ec7e24c732293f3ef7088a2b1ba7c` (single implementation
  commit on top of base main)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

209-a COMPLETE; FOCUSED LOCAL VERIFICATION GREEN. The G05 reviewed
key-batch surface is delivered on the SAME qualified 203 core
`KeyBatchService` law with no schema, migration, CLI, worker, or
runtime-accounting change; the demonstrated transport defect (the
~10.67 MiB signed envelope vs the 1 MiB per-field/admin-body defaults)
is fixed bounded to the batch surface. GitHub CI on this head is
PENDING at publication (treated as pending, not pass). The merge gate
remains root-owned. No release/tag/deploy claim, and no completion
claim beyond the 209-a scope: the full GUI goal remains broader (G06-G18
of `docs/MISSING_GUI_FUNCTIONALITY.md` stay open, and the whole-GUI
qualification remains later work). No real provider, email, or
production traffic was involved.

## Delivered (per order requirement)

1. **Entry (requirement 1).** The key list (`/admin/keys`) gains
   exactly ONE "Change existing keys" link to the new
   `/admin/key-batch` page (discovered, clearly separate, h1
   "Change Existing Keys"). All prior list behavior is unchanged; the
   entry link renders exactly once.
2. **Shared record pickers (requirement 2).** Cohort and key-UUID
   selection reuse the existing searchable latest-100/older-search
   record pickers (plain-text no-JS fallbacks). The batch key picker is
   batch-opt-in capped: the hydration cap is applied centrally to
   searches and `selected` hydration is omitted on non-empty queries,
   so a typed query cannot fill all 100 result slots and evict the
   older match; the FULL selection (proven at 101 = 100 initial + 1
   older) is what submits. Other pickers/callers are unchanged.
3. **Guided + advanced input (requirement 3).** ONE input source: the
   guided controls (lifetime cost/token/request quotas with
   unchanged/set/clear; the four rate members - three counts plus the
   window; provider/model/endpoint list modes; lazy throttling; chat
   live-burn margins) or the advanced strict version-1 configuration
   document. "Leave unchanged" omits, "Clear" sends explicit null, a
   value is used only with "Set", zero is a real zero. Exactly one
   selection source and one input source per submission; with
   JavaScript a single composed sync disables (and therefore omits
   from the submission) every non-selected control, so a mode switch
   can never send a stale subordinate value; the server enforces every
   single-source law for every submission including no-JS.
4. **Plan law (requirement 4).** POST plan calls
   `KeyBatchService.plan` in one caller-owned transaction: no
   mutation and no policy audit at plan time; the EXACT non-secret
   plan renders (every selected key with readable before/after,
   excluded-by-status entries for explicit scope, submitted policy
   summary, raw plan JSON as optional detail). At apply, any drift in
   membership, status, or configuration refuses the WHOLE batch with a
   fixed 400 and zero writes/zero new audits.
5. **Full 1000 / 8 MiB transport (requirement 5).** Full 1,000-key
   plans are supported end to end (transport round-trip qualified).
   The signed review envelope expands an 8 MiB canonical plan to
   11,184,812 base64url characters (~10.67 MiB); Starlette's default
   1 MiB per-field cap refused the actual full-1000 apply before any
   gateway logic ran (demonstrated defect). Bounded fix: the APPLY
   route parses its own form with envelope-sized headroom (no files,
   bounded field count) BEFORE the framework auto-form parsing and
   maps both bounded-parse failure forms to one fixed safe 400; every
   other route and global limit is unchanged. Both shipped Nginx
   configs (`nginx/production.conf`,
   `deploy/nginx/slaif-api-gateway.conf`) add
   `client_max_body_size 16m` for the `/admin/key-batch/` locations
   ONLY (derived headroom; all other proxy behavior unchanged), and
   `docs/deployment.md` carries the operator note. The near-8 MiB
   valid envelope is qualified through real ASGI urlencoded apply
   (actual request-body byte count, exactly one apply call, full
   strictly parsed plan, all 1,000 IDs), and the over-bound
   builder/API refusal is a controlled fixed 400.
6. **Purpose-bound review state (requirement 6).** The review token is
   an HMAC-SHA256 purpose-209/batch-bound signed state over the
   entire strict plan plus the acting admin user and session, a
   15-minute expiry, and bounded encoded size. Apply verifies format,
   the constant-time HMAC, purpose/actor/session, expiry, and strictly
   re-parses the embedded plan BEFORE any mutation; a mutable apply
   field can never change the reviewed plan; the token is never
   retained on the result page (pages are no-store).
7. **Apply gates (requirement 7).** Apply requires fresh valid admin
   auth, CSRF, the explicit reviewed-scope confirmation checkbox, a
   bounded nonblank audit reason (at most 512 UTF-8 bytes, the stored
   core bound - multibyte text uses more than one byte per character;
   masked through the existing redaction seam before storage), and the
   session-derived actor. A plan that explicitly sets a fenced
   external-tool policy requires the fresh fenced checkbox, including
   a repeat of the same reviewed operation.
8. **Core state/membership revalidation (requirement 8).** The core's
   deterministic locks and per-key revalidation are reused unchanged:
   the apply re-derives every selected key under the row locks; a
   set that currently equals the target is the ordinary no-write
   `already_at_target` repeat (present-state equality, not a
   historical receipt); one caller-owned transaction rolls back ALL
   keys and ALL provisional audits on any late per-key failure; every
   changed key gets its own `update_key_configuration` audit with the
   actor and the bounded reason.
9. **Honest outcomes, safe IDs (requirement 9).** Applied /
   already-at-target / no-change outcomes render with safe exact IDs
   and counts; the review and result pages are private no-store and
   never show key material (synthetic token-hash markers asserted
   absent from every rendered page).
10. **Shell/theme/ergonomics (requirement 10).** The SLAIF shell,
    local fonts/theme, and stacked-group ergonomics are preserved:
    the shared sortable table convention (raw ungrouped sort keys,
    grouped/M display, field-specific null labels) inside a labeled,
    keyboard-focusable `.table-wrap` scroll region with the standard
    empty-state row; one label per control (no label wraps two
    controls, no nested picker labels); each batch picker's visible
    field references its own help span; the apply inputs reference
    meaningful linked help (reason purpose + 512-UTF-8-byte bound +
    fresh fenced acknowledgement + ordinary-repeat semantics); the
    390 px review has no document overflow and the apply control
    stays reachable.
11. **No rotation on non-page reads (requirement 11).** Record-choice
    lookups, downloads, and status reads are read-only: they never
    rotate or mutate the current form state, keys, or key material;
    the form re-renders keep the operator's in-progress values, and a
    rejected planning re-render blanks the advanced document before
    redisplay (no credential-shaped value retained).

## Exact changed paths (IMPL vs base main `a4ed3ae`)

- `app/slaif_gateway/api/admin_key_batch.py` (NEW: focused router -
  form, plan, apply, bounded self form-parsing, readable review
  helpers)
- `app/slaif_gateway/api/admin_review_intent.py` (batch-purpose
  token build/verify + size bounds)
- `app/slaif_gateway/main.py` (router include)
- `app/slaif_gateway/web/assets.py` (asset registration)
- `app/slaif_gateway/web/static/js/key-batch.js` (NEW: one composed
  disabled-state sync; progressive enablement only - never value
  conversion)
- `app/slaif_gateway/web/static/js/record-choices.js` (batch-opt-in
  hydration cap applied centrally; omitted `selected` hydration on
  non-empty queries)
- `app/slaif_gateway/web/templates/_record_choice.html` (optional
  `help_id`/`hydrate_cap` parameters; batch callers only)
- `app/slaif_gateway/web/templates/keys/list.html` (entry link)
- `app/slaif_gateway/web/templates/keys/batch_form.html` (NEW)
- `app/slaif_gateway/web/templates/keys/batch_review.html` (NEW)
- `app/slaif_gateway/web/templates/keys/batch_result.html` (NEW)
- `app/slaif_gateway/web/static/css/admin.css` (`.field` wrapper;
  `.config-json` scroll containment)
- `nginx/production.conf`, `deploy/nginx/slaif-api-gateway.conf`
  (16 m batch locations ONLY)
- `docs/deployment.md` (operator note incl. the application-upgrade
  vs proxy-only distinction)
- `docs/security-model.md`, `docs/admin-usability.md` (section 10),
  `docs/MISSING_GUI_FUNCTIONALITY.md` (section 11),
  `docs/cli-field-administration.md` (pointer),
  `docs/verification/README.md` (index entry),
  `docs/verification/gui-cli-parity.md` (209-a living-record section)
- `oap/orders/209-a-gui-key-batch.md` (byte-exact order),
  `oap/active` (pointer)
- `tests/unit/test_admin_key_batch_209.py` (NEW: 81 cases)
- `tests/unit/test_admin_usability_inventory.py` (ordinal guard 25 ->
  26 for the new sortable table; assertions preserved)
- `tests/integration/test_admin_key_batch_209_postgres.py` (NEW:
  6 cases)
- `tests/browser/test_admin_key_batch_209.py` (NEW: 7 cases)

## Focused evidence (local; GitHub CI pending)

- **Unit: 81 PASS / 0 skip** (JUnit `unit-209a-7.xml`; the module was
  green at 80 cases at `unit-209a-5.xml` and at 81 cases at
  `unit-209a-6.xml`, then re-verified after the in-order
  accessibility/hint corrections). Fake-persistence ASGI/Jinja:
  composition + single-source law, list-mode allow-all/deny-all and
  credential-shaped refusals, selection overflow/malformed with the
  full-1000 accepted, review rendering (ordinals, raw ungrouped sort
  keys, M-token and money-string display, state-aware empty lists,
  excluded entries as real UUID/status, the five picker help links,
  apply-input help), token round-trip + expiry/actor/session/tamper/
  malformed/oversize refusals, apply flows (confirmation, reason,
  fenced, stale refusals with zero writes, canary absence), the
  actual near-8 MiB signed envelope through real ASGI urlencoded
  apply, the over-bound controlled fixed 400, and the full-1000
  transport round-trip.
- **Owned PostgreSQL: 6 PASS / 0 skip** (JUnit `pg-209a-1.xml`,
  8.876 s; qualified loopback/tmpfs fixture; exact-ID container
  cleanup, none left). Cohort-scope plan (107 selected over
  active+suspended; zero preview writes), explicit 108-UUID plan with
  exact exclusions and 105 persisted changes (changed-key comparison
  allowing only the requested quotas plus `updated_at`; excluded and
  an unselected control key an unchanged value snapshot), 105
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
- **Real Chromium / owned PG: 7 PASS / 0 skip, 32.655 s** (JUnit
  `browser-209a-3.xml`; actual uvicorn app, real stylesheet; exact
  container cleanup). Entry + safe initial disabled states (real
  composed sync); the populated transition regressions (stale
  allow-list values never ride along; guided<->advanced round trip;
  keys<->cohort scope change while advanced; inactive chip removal);
  >100 multi-key selection with older search (no `selected`
  hydration on typed queries; the full 101 selection submitted); the
  keyboard happy flow (combobox ArrowDown/Enter cohort selection,
  Space/type/Enter apply, 390 px review with no document overflow and
  the apply control reachable, independent persisted-DB and audit
  oracles); and the no-JS fallback flow through to the persisted
  change. Focused screenshots (synthetic data only) under
  /tmp/slaif209/.
- **JS component root (separate, mocked lookup, no app auth/PG):** the
  populated-state regressions pass on the final
  `web/static/js/key-batch.js` SHA
  `5a1362620fb65a78a78630c3262197180a9651b1bb9104490c4e359a5f5867fd`;
  the durable native browser cases cover the same states on the
  actual rendered page.
- **Admin-usability inventory: 119 PASS / 0 skip** (JUnit
  `unit-209a-inventory.xml`), including the ordinal guard updated for
  the 26th sortable table plus the standard empty-state row.

## Static and governance checks

- `tests/unit/test_oap_governance.py`: 9 PASS / 0 skip (JUnit
  `unit-209a-gov.xml`) with the 209-a order byte-exact and
  `oap/active=209-a`.
- Ruff clean on all seven changed Python paths;
  `scripts/check_documentation.py` reports `DOCUMENTATION_CHECK=OK`
  (135 files); `git diff --check` clean.

## CI chronology

- No GitHub CI run exists on this 209 head yet; CI at publication is
  PENDING (treated as pending, not pass) and is the normal required
  final-head gate.
- Local browser chronology (honest): run 1 7 FAIL (all
  fixture/selector issues - the h1 text, the multi picker's open
  affordance, hidden-input wait states, the transition step's input
  mode, the formatter's `5` vs raw `5.00`; no product defect); run 2
  3 PASS / 4 FAIL (root cause: the display assertion matched the
  literal `&rarr;` entity while the serialized page decodes it to the
  arrow; the other three cascaded from the happy Apply never
  executing; no product defect); run 3 7 PASS / 0 skip after the
  fixture corrections plus the in-order accessibility corrections.
- Pre-publication gate (root probe, closed exit 1): the inventory
  ordinal guard expected 25 sortable admin tables; the new batch
  review table is the 26th and its tbody lacked the standard
  empty-state row. Same-order focused correction (guard count 25 ->
  26, assertions preserved; standard for-else empty-state row,
  `data-no-sort`/`colspan="8"`/unnumbered) then passed the full
  inventory module 119/119. The empty branch never renders for a real
  plan (the core requires at least one selected key), so the unit 81
  / browser 7 / PG 6 / coexist 20 receipts stand unchanged and were
  not rerun for this static correction.

## Privacy invariants

- The review and result pages never carry generated key material;
  synthetic token-hash markers are asserted absent (booleans only)
  from every rendered page in the browser suite, and the result page
  never retains the signed review token.
- The audit reason is masked through the existing redaction seam
  before storage; credential-shaped form values are refused or
  redacted by the existing seam, and a rejected advanced-document
  re-render blanks the document before redisplay.
- Canary assertions compute booleans first and assert fixed labels;
  no canary or full output is echoed in any failure representation.
- No gateway/provider secrets appear in logs, tests, screenshots, or
  this report; screenshots contain synthetic fixture data only.
- The operator request-capture facility, email delivery, and replay
  ownership are untouched by this surface.

## Deployment

Deploying 209 is an application upgrade plus a proxy update in the
SAME maintenance window: rebuild the API/assets image and
recreate/restart the API so the new batch code runs, and update the
reverse-proxy configuration from the shipped templates (or add the
`location /admin/key-batch/` block to a custom ingress), then
`nginx -t` and reload Nginx - a new app behind an old proxy 413s
large reviewed batches before they reach the gateway. Editing only
the proxy setting needs just `nginx -t` and a reload. No database
migration, no existing-key change or rotation. The exact additional
paths and scope reason: an 8 MiB reviewed plan expands to ~10.67 MiB
in the signed envelope (11,184,812 base64url characters plus
digest/separator), which exceeds the admin default 1 MiB body limit;
the 16 m allowance is derived headroom applied ONLY to the new batch
locations in `nginx/production.conf` and
`deploy/nginx/slaif-api-gateway.conf`, with the operator note in
`docs/deployment.md`.

## Documentation

- `docs/MISSING_GUI_FUNCTIONALITY.md` section 11 (delivery status:
  G05 delivered; honest limits; G06-G18 open), header updated.
- `docs/admin-usability.md` section 10 (navigation, form semantics,
  review/apply readout, upgrade notes).
- `docs/verification/gui-cli-parity.md` 209-a section (living record:
  parity contract, bounded implementation, focused evidence with
  hashes, honest chronology, transport bound, operator notes,
  limitations).
- `docs/verification/README.md` index entry (newest first).
- `docs/cli-field-administration.md` pointer note on the 203 batch
  row (GUI equivalent; no CLI change).
- `docs/security-model.md` 209 batch section; `docs/deployment.md`
  batch transport/operator note.

## Pending and honest limitations

- GitHub CI on the 209 implementation head is PENDING at publication;
  the final-head CI result and strategic review/merge remain the
  root's gates. No merge was performed by the coding agent.
- Component scope distinctions: the 81-case unit suite runs on
  synthetic fake persistence (no real DB); the 6-case suite runs on
  the qualified owned PostgreSQL; the 7-case browser suite runs the
  actual uvicorn app plus the real stylesheet against the same owned
  fixture; the JS component root used a mocked record-choices lookup
  without app auth/PG. The unchanged 207/208 component proof is
  reused, not rerun; no full local matrix was run for this objective.
- The full GUI goal remains broader than G05: G06-G18 stay open, and
  the final whole-GUI qualification is later work.
- No production, security, compliance, provider-behavior, or scale
  claim follows from this report.
