# OAP Coding-Agent Report — 212-a

## Work order
- Identifier: 212-a
- Work-order file: `oap/orders/212-a-gui-codex-compatibility.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `0a3ce9c1a6fe74203bd6ac980f0efd992125c19b809920ac15cb16d0584714d2`,
  21,889 bytes)
- `oap/active` pointer: value `212-a` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 212
- PR mode: CREATE_NEW_PR (PR 368 "Add reviewed Codex compatibility
  management to the admin GUI"; branch
  `oap/212-gui-codex-compatibility`; base main at
  `4d90d016b82568b1f5be0f4ff10750661ae0e618`, the merge commit of PR
  #367 (211))
- Implementation head SHA (literal): `9643aa3b31b63bcf322fa0d0cc870e296fc9495e`
  (one implementation commit on top of base main)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

212-a COMPLETE; FOCUSED LOCAL VERIFICATION GREEN. G10 (Codex
policy-data inspection and existing-key migration) is delivered on the
EXISTING qualified Core: `CodexQualificationService.inspect()`,
`render_codex_profile`, the existing route-detail artifact handlers,
the shared reviewed review/apply/stale-refusal orchestration, and the
existing `_admin_attachment_context` read-only boundary. Core write law
and default CLI behavior are unchanged: the shared orchestration
gains only the OPTIONAL expected-target guard and a read-only facts
seam. No schema, migration, permission, API-request-acceptance,
provider-call, accounting, worker, or CLI-semantics change. No shared-
law redesign was required. Every root review finding was a routine
correction within the same order's allowed paths; the ONE root-approved
bounded shared-handler context fix (the route Codex-profile artifact
read boundary, below) is recorded precisely here. No deploy, release,
tag, or production mutation was performed. The coding agent does not
merge.

## Delivered (per order)

1. **Operations / Codex Compatibility** surface with three entries
   (Operations index card, key-detail link, route-detail "Codex
   compatibility" line):
   - **Choose a key** entry (the existing key workflow owns
     selection);
   - **Registered Codex qualification** table: one row per declared
     Codex route with readiness state (ready rows show the short
     "Protocol-qualified" label; not-ready rows keep their
     withheld-safe badge text), model, provider, endpoint, route link,
     named profile, client-module identity, and exact reasons;
     canonical credential-free artifact links on ready rows only
     (base fragment only when the profile is not self-contained; model
     catalog only when the profile ships one);
   - **API startup data identity**: the validated 0.162 snapshot this
     API process adopted (module, revision, digest, provenance);
   - **Validated shipped presets**: bounded safe facts with exact
     identity strings, an authenticated exact-document inspect page,
     and a private no-store export of the exact validated bytes.
2. **Per-key binding page**: exact stored (module ID, data version,
   fixture SHA-256) tuple; ONE finite operation selector legal for
   THIS pin (module upgrade/rollback; data-profile migration to the
   API's active profile or the approved frozen 0.162 tuples); 8-200
   printable-ASCII audit reason saved verbatim; dry-run review of the
   exact source/target identities (15-minute preview); explicit
   confirmation; one audited apply; the exact repeat of an applied
   token is a safe no-op ("Already at target", no new audit, no row
   change); rollback offered from the target pin. Refusals (stale,
   tampered, drifted, wrong-active-tuple) write no
   key-policy/accounting/domain/audit state (normal
   authentication/session last-seen tracking is preserved).
   There is NO automatic key migration; host-file deployment and
   activation remain separately controlled operator steps.
3. **Read boundary fix (root-approved, bounded)**: the existing route
   Codex-profile artifact handler now authenticates via the existing
   `_admin_attachment_context(request, touch=False)` (no form-CSRF
   rotation; a backwards-compatible `touch=` keyword was added, old
   default behavior preserved) and marks success AND fixed-error/auth
   responses no-store via the existing `_set_no_store_headers`. All
   existing gates (dashboard flag, UUID parse, session auth, catalog
   lookup, ready/profile check, base-URL render, artifact dispatch)
   and response bytes are preserved. Covered by the new
   catalog-route regression (`catalog-212a-1.xml`).
4. **Privacy**: known incoming authentication aliases and
   credential-shaped values are refused/withheld across ALL review
   facts (reason, from-fields, BOTH source/target tuples), apply-time
   recheck, index/projection display, and hrefs; canonical preset and
   export bytes are never rewritten; ENV variable NAMES remain
   literal.

## Exact changed paths (IMPL vs base main `4d90d016`)

```text
M	app/slaif_gateway/api/admin.py
A	app/slaif_gateway/api/admin_compatibility.py
M	app/slaif_gateway/api/admin_review_intent.py
M	app/slaif_gateway/main.py
M	app/slaif_gateway/services/codex_module_upgrade.py
A	app/slaif_gateway/web/templates/compatibility/index.html
A	app/slaif_gateway/web/templates/compatibility/key.html
A	app/slaif_gateway/web/templates/compatibility/migration_review.html
A	app/slaif_gateway/web/templates/compatibility/preset.html
M	app/slaif_gateway/web/templates/keys/detail.html
M	app/slaif_gateway/web/templates/operations/index.html
M	app/slaif_gateway/web/templates/routes/detail.html
M	docs/MISSING_GUI_FUNCTIONALITY.md
M	docs/admin-usability.md
M	docs/client-compatibility-presets.md
M	docs/verification/README.md
M	docs/verification/gui-cli-parity.md
M	oap/active
A	oap/orders/212-a-gui-codex-compatibility.md
A	tests/browser/test_admin_compatibility_212.py
A	tests/integration/test_admin_compatibility_212_postgres.py
M	tests/unit/test_admin_catalog_routes.py
A	tests/unit/test_admin_compatibility_212.py
M	tests/unit/test_admin_key_clone_208.py
M	tests/unit/test_admin_provider_route_configuration_210.py
M	tests/unit/test_admin_slaif_design.py
M	tests/unit/test_admin_usability_inventory.py
```

## Focused evidence (local, /tmp/slaif212)

Final qualifying receipts (all JUnit-parsed; PG/browser runs used the
qualified owned-PG fixture as sole container owner with exact-ID
cleanup verified - owner filter empty after; synthetic data only):

| Receipt | Result | Scope |
| --- | --- | --- |
| `unit-212a-1.xml` | 44 PASS / 0 skip (19.592s) SHA `1e6d52b0…` | 212 unit module: finite option/edge law, reason law on the ORIGINAL string, signed-doc verification, review/apply dispatch, alias withholding (reason/from/tuples, apply-time), index projection withholding, preset exact-bytes/no-store/non-rotating download, denials |
| `guards-212a-1.xml` | 139 PASS / 0 skip (5.638s) SHA `ffefa090…` | usability inventory (33 tables) + SLAIF design + main-app structure after the new templates |
| `cross-212a-1.xml` | 107 PASS / 0 skip (38.957s) SHA `d9710e62…` | affected 208 key-clone (48) + 210 provider/route configuration (59) modules, unchanged behavior |
| `pg-212a-1.xml` | 12 PASS / 0 skip (9.830s) SHA `f5f93e64…` | owned-PG ordered module, authenticated HTTP/TestClient (NOT the browser): review writes no key-policy/accounting/audit state, one-audit exact apply, exact-repeat no-op, rollback to the exact predecessor, ORIGINAL-token-after-a-different-authorized-action Already-at-target, non-target drift refusal, wrong-active-tuple refusal, profile migrate-to-active + repeat no-op, LATE-AUDIT-failure rollback of policy and audit, retry-after-unconfirmed, native auth/CSRF denials (refusals prove zero key-policy/accounting/domain/audit writes while normal session last-seen tracking is preserved) |
| `catalog-212a-1.xml` | 9 PASS / 0 skip (6.100s) SHA `9b86b357…` | existing catalog-route module incl. the NEW route-artifact read-only regression (touch=False, no CSRF refresh, no-store on success and fixed errors, UUID/ready gates intact) |
| `browser-212a-2.xml` | 8 PASS / 0 skip (19.256s) SHA `8e28f687…` | actual Chromium (owned PG, sole owner): login -> Operations -> Compatibility index (entry, ready qualification row, exact preset identities, startup identity), key detail -> Compatibility entry, ready-route index row + route-detail Compatibility entry + credential-free no-store artifact downloads, keyboard module upgrade with same-page preset AND route-artifact downloads (form CSRF survives both), independent DB oracles (exact tuple, one audit, full-row stability digest), persisted reload, browser-context HTTP repeat of the ORIGINAL token (Already at target), preset exact document, active profile migration, no-JS rollback, narrow/desktop captures |
| `unit-212a-visual-1.xml` | 44 PASS / 0 skip (19.354s) SHA `902c9324…` | the SAME 44-case unit module rechecked (not 88 distinct cases) after the display-only wide-table / short-State-label correction |
| `browser-212a-visual-1.xml` | 1 PASS / 0 skip (10.257s) SHA `d2f46b88…` | visual-only overlapping recheck: the ONE existing narrow/desktop capture case for final images (not a ninth workflow case) |
| `drift-212a-1.xml` | 15 PASS / 0 skip SHA `5af8c723…` | documentation contract drift after the doc edits |
| `root-cli-oap-212a.xml` | 19 PASS / 0 fail / 0 error / 0 skip SHA `1544d250…` | strategic run: selected CLI wiring/import/safe-error nodes (module-mutation selector wiring 8 cases, codex-CLI import isolation, migrate-key-profile bootstrap error) + full OAP governance (9); MOCKED CLI-runner wiring/import/error proof, not an installed CLI or backend run |

Full receipt sha256: unit-212a-1
`1e6d52b09bcdb77c6641017c62f41c6cc5f31e0df377d8d7580d511373cbffd8`;
guards-212a-1
`ffefa090d90906deded84a3f2f6a8cbbdfddeb91d72327c9b630ef039ea39ef5`;
cross-212a-1 `d9710e628c93285c5376fb24e4fb748eac6180be7262a4dd0319e220b1961da0`;
pg-212a-1 `f5f93e644c440865cfd0de4accd43cff0d31db024f7ac3f344cf77cbfdbc45d2`;
catalog-212a-1
`9b86b357fb9fc33270a9af16bea3e07d7d1a1ec9f8df98024676e12b4e1a02fe`;
browser-212a-2
`8e28f68700cdd054ffe4805a1b66a9d57aff54ac2ee7fcb8a1cafdb3456ba702`;
unit-212a-visual-1
`902c93243964facb66407c1d5cf1d16fee3e2a5cee091ed76766859b6716d8ce`;
browser-212a-visual-1
`d2f46b88f013acc4c6b3f08cfd29d7f54cd1a70a4c8b54d29926ab213f3270ea`;
drift-212a-1
`5af8c723677373d62b656c23d68ddf05ff7bd748458c389a8d00e0e6587dddfb`;
root-cli-oap-212a
`1544d250d0487422f28f821fbb60406aff4505afa99e7a441c05e6dd7c399c01`.

The strategic model independently RAN scoped component probes
(synthetic, mocked auth/persistence - NOT native evidence): the review
helper (11 pure probes incl. self-edge / tuple-mismatch / wrong-type /
outer-extra refusals), the alias guard (3 router probes: target alias
at review, source alias at review, target alias introduced only at
apply), and the index projection (2 probes: digest/name alias withheld
across text/attributes/hrefs, canonical preset unchanged). It also
independently REVIEWED (parsed, not rerun) the formal JUnit receipts
above, including the native 12, and accepted the desktop/narrow
visuals.

Honest chronology (brief): preliminary wip unit receipts failed with
`NameError: Mapping undefined` in the NEW PRODUCT alias helper (a
missing `collections.abc` import in `admin_compatibility.py`, not a
fixture-only defect); the 38-PASS receipt predates that fix and is
history, not final evidence. The first browser module runs failed on
fixture/oracle defects (trailing-slash link oracle, a Python
`ElementHandle.value` assumption, an unavailable upgrade repeat select
the finite UI correctly no longer offers, and shipped-preset schema
assumptions - the shipped presets are schema-2 documents with no
top-level digest key; later states also corrected a preset
bytes-vs-str oracle and a dependent no-JS rollback state); both earlier
full-run states (4 failures; then 3 failures over 7 tests) are
superseded. The first stored-ready-route seed used provider kind
`openai`, which the EXISTING `provider_configs` check constraint
(openai_compatible/module) rejects - a fixture-only 8-ERROR state,
corrected per the strategic order to the registered qwen38-27b 0.162
profile (verified `protocol_qualified` with empty reason codes by
running the real service). A final scoped lint cleanup after the
receipts removed unused imports / an f-string prefix / one unused
local in the touched files only (no logic change); final-head CI
covers it.

## CI chronology (per head, actual)

IMPL head `9643aa3b` (queried at report publication,
2026-11-01T12:32:21Z): SUCCESS - CodeQL (aggregate), Documentation
hygiene, Docker Compose smoke, Analyze (javascript-typescript);
IN PROGRESS - Unit, lint, and migration head; PostgreSQL integration
tests; OpenAI-compatible E2E tests; Playwright browser smoke; Analyze
Python; Analyze (python). Pending and in-progress checks are NOT
reported as passed; they are root-owned final-head gates. The
report-only SELF head's checks run after its push and are likewise
root-owned.

## Privacy invariants

- Known incoming authentication aliases and credential-shaped values
  are refused as review input (reason, from-fields, both
  source/target tuples) and withheld from review rendering, apply
  (rechecked before Core/audit), index/projection display, and hrefs;
  ENV variable NAMES remain literal; no key, route, provider, or
  ledger row is mutated by a refusal.
- Canonical preset documents and route artifact bytes are exported
  exactly as validated - never rewritten; if display masking were
  required the canonical export refuses rather than mutating bytes.
- Preset exports and route Codex-profile artifacts are private
  no-store attachments that do not rotate a displayed form's CSRF.
- The compatibility GUI is read-only except the reviewed, signed,
  confirmed, audited per-key migration; it exposes no request-capture
  control, no provider credentials, no environment dump, and no
  server paths.

## Deployment

Deploying 212 is an application upgrade ONLY: rebuild the API/assets
image and recreate/restart the API so the new code runs. No Nginx
change and no database schema migration; no existing key, route, or
profile change or rotation follows. "Active" profile migration always
resolves the snapshot THIS API process adopted at startup: to migrate
to a newer host file, restart to adopt it, then run a fresh
review/migration; worker target drift still refuses. NO deployment was
performed by this objective. See `docs/deployment.md`.

## Documentation

Living docs updated (operator navigation, semantics, upgrade and
restart scope; compact proof/limits in the living verification record;
no duplicate inventories): `docs/MISSING_GUI_FUNCTIONALITY.md` (G10
delivered; G09, G11-G15 and G17-G18 remain open; final 219 still
required), `docs/admin-usability.md` (section 13 operator
walkthrough), `docs/verification/gui-cli-parity.md` (212-a living
record incl. the preexisting OpenAI-profile provider_kind constraint
observation and honest chronology), `docs/verification/README.md`,
`docs/client-compatibility-presets.md` (GUI pointer; CLI commands and
schema unchanged).

Documentation updated: docs/MISSING_GUI_FUNCTIONALITY.md, docs/admin-usability.md, docs/client-compatibility-presets.md, docs/verification/README.md, docs/verification/gui-cli-parity.md

## Pending and honest limitations

- G09, G11-G15 and G17-G18 remain open; the entire GUI goal stays
  active through objective 219, and the FINAL 219 installed whole-GUI
  qualification and the remaining stages are NOT complete here.
- All qualification evidence is synthetic: owned disposable
  PostgreSQL and Playwright Chromium with synthetic
  credentials/IDs; no real provider/Codex request, no installed
  transcript, no installed whole-GUI qualification.
- PREEXISTING, OUT OF SCOPE (no change made): the registered OpenAI
  0.147 qualification profile declares `provider_kind="openai"`, which
  the stored-provider kind constraint (openai_compatible/module) can
  never satisfy, so a v2-declared gpt-5.6-sol route cannot reach
  protocol_qualified in a real database; 212-a's ready-route
  qualification uses the registered qwen38-27b 0.162 profile. This
  report makes no claim that the OpenAI profile was repaired; it was
  not.
- At report publication, six IMPL-head CI jobs were still in progress;
  final-head checks, strategic review, merge, and main verification
  are root-owned. The coding agent performs no merge or auto-merge.
- Preliminary superseded runs are referenced once above and in the
  living record; they are not catalogued and are not evidence.
