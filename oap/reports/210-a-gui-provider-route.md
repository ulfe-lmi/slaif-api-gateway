# OAP Coding-Agent Report — 210-a

## Work order
- Identifier: 210-a
- Work-order file: `oap/orders/210-a-gui-provider-route.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `45c72d9dbb1276c860ae08d2bfcd38dc912074719f60a2d330ac14ebdba8eab6`,
  24,574 bytes)
- `oap/active` pointer: value `210-a` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 210
- PR mode: CREATE_NEW_PR (PR 366 "Add reviewed route changes and
  provider preparation to the admin GUI"; branch
  `oap/210-gui-provider-route`; base main at
  `32478e0aa16c5a51ac7657f6b5863a107f2d9dcd`, the merge of PR 365)
- Implementation head SHA (literal):
  `19b47cf1c961ea762952309a82e3451abc2b9765` (nine implementation
  commits on top of base main: `0b0247da` the GUI surfaces; `edf201e3`
  the CLI field-administration pointer copy correction; `ebc12dac` the
  completion-profile path-boundary clarification; `bfe1ab43` the
  restored dashboard-smoke warning sentence; `784ed9c5` the valid raw
  capabilities placeholder plus the actual CI chronology in the living
  record; `c32c6ca9` the CodeQL root-containment guard; `cea28df1`
  the separator-safe root prefix correction - the final CODE head;
  `9c9102d1` the living record of the containment fix and actual CI
  results; `19b47cf1` the browser-chronology prose correction - the
  last two commits are documentation-only)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

210-a COMPLETE; FOCUSED LOCAL VERIFICATION GREEN. The G06 reviewed
route-configuration workflow and the G07 provider preparation surfaces
are delivered on the SAME qualified core `provider_route_configuration`
orchestration, `ModelRouteService`, and `ProviderConfigService` - no
schema, migration, model, CLI-semantics, worker, or runtime-accounting
change. One demonstrated shared persistence defect (reviewed null notes
target vs repository preserve) was repaired through a root-approved
bounded shared-law correction (exact scope below). The FIRST IMPL head
actually failed GitHub CI in two bounded places - the CodeQL aggregate
(three HIGH path-injection alerts, for which root's SARIF review found
no demonstrated escape) and one dashboard-smoke wording assertion. The
basename clarification alone did not clear the CodeQL flow, so a
further bounded root-containment guard (plus the separator-safe root-
prefix correction) was authorized and landed; the per-head chronology
ends with CodeQL aggregate SUCCESS on final CODE head `cea28df1`, and
is recorded in the CI section below. The merge
gate remains root-owned; no merge, release, tag, or deploy was
performed. No real provider, email, or production traffic was involved.
No completion claim beyond 210 scope: the full GUI goal remains broader
(G08-G18 of `docs/MISSING_GUI_FUNCTIONALITY.md` stay open).

## Delivered (per order requirement)

1. **Preserved full editing + clearly labelled reviewed action
   (requirement 1).** Provider slug/status edits, route full editing,
   record detail/list, discovery/setup (including the explicit LAN HTTP
   acknowledgement), public alias mapping, imports, and explicit
   activation controls are unchanged. The reviewed flow is additional,
   entered from the route detail page ("Reviewed configuration
   change") through the longer target-bound path
   `/admin/routes/{route_id}/configuration` - no dynamic
   `/routes/{route_id}` collision, no replacement of any full editor.
2. **Guided route edits on the actual closed schema (requirement 2).**
   The Match/Target scalars (requested model + match type, endpoint,
   provider, upstream model, priority) and the notes intent work
   independently; "Keep current" omits (omission preserves), false and
   zero remain explicit where valid, and there is no invented null-clear
   on fields whose Core does not support one. The route's ENABLED state
   is deliberately preserved by the preview (enable/disable stay on the
   existing status actions). Pickers use the known kinds (provider
   references the existing provider slug, including disabled records,
   for preparation; the target route is an exact UUID, not a model
   alias), with safe current/older choices and no-JS entries.
3. **Practical partial capabilities + distinct complete replacement
   (requirement 3).** The guided leaves are the actual CapabilityPatch
   leaves (codex_limits, media_input_estimation, the closed
   Chat/Responses boolean leaves as 51 tri-state flags grouped in
   accessible native disclosures, and the completion-service selector
   exactly `{"version":1,"profile":"installed-profile-id"}`); omitted
   leaves preserve deep siblings; numeric leaves are positive whole
   numbers against the shared route ceilings. The capability source is
   ONE choice - unchanged / guided partial / the explicit advanced
   COMPLETE strict version-1 document (`schema_version: 1` plus
   `capabilities`, at most 64 KiB via `parse_capabilities_file`),
   labelled distinctly from the working legacy raw capability-object
   editor; the two are never merged and the same complete-candidate
   validator and shared normalizer make preview equal stored state. The
   completion selector reuses the loader and the configured
   operator-owned directory through a bounded picker (streaming
   `os.scandir`, filters before stat, stop at 100 eligible,
   `bindings.json` excluded, unsafe-mode/symlink/oversize refusals,
   selected older IDs hydrated on demand, configured directory wired to
   initial render AND AJAX); no file/path input, no profile editor, no
   hot-reload promise - profiles remain process-cached.
4. **Reviewed exact target/canonical state before execution
   (requirement 4).** The preview calls the shared orchestration with
   the actual installation's external-tool ceilings and completion
   profile directory, resolves the PROPOSED destination provider, and
   seals the route UUID, full route state/enabled fingerprint,
   destination provider UUID, and provider context (kind / base URL /
   credential ENV-var NAME / timeout / retries). The review renders
   meaningful readable per-leaf differences (token leaves as M tokens
   plus the exact raw count; capability states; the non-secret
   external-tool and transport-contract values) plus the exact
   non-secret JSON as optional detail. The preview is read-only with
   zero policy writes/audits/provider calls. The canonical plan is
   strictly re-parsed with the 128 KiB bound BEFORE any rendering or
   HMAC construction and AGAIN at apply; unadministerable legacy state
   is refused safely without altering fingerprints or reviewed data.
5. **Bounded owned review and atomic apply (requirement 5).** A
   distinct route-configuration purpose HMAC-SHA256 token binds the
   entire plan, the acting admin user and session, the exact route
   target, and a bounded 15-minute lifetime (encoded bound 178,858
   characters); the clone/batch token APIs are preserved and the new
   purpose is cross-denied. Wrong purpose, actor/session/route, expiry,
   tamper, malformed/non-ASCII digest, oversize, or strict-plan
   refusal all fail with fixed safe errors before any mutation
   (malformed formats are refused BEFORE digest comparison). A valid
   signature is reviewed data, never authority. Apply requires a fresh
   valid admin session, CSRF, the explicit confirmation checkbox, and a
   nonblank bounded audit reason (at most 512 Unicode characters - a
   GUI-side seam bound; the unchanged CLI is not claimed to enforce
   it); the server derives the actor. The SAME plan executes in ONE
   caller-owned transaction with Core-owned deterministic
   route-then-provider locking and fresh revalidation; any
   route/provider-context drift refuses all writes/audits, a repeated
   effective route update is stale, and a fresh zero-diff plan is the
   no-write/no-audit no-op. Every changed route gets its
   `model_route_updated` audit (actor + reason); unrelated rows, keys,
   pricing, usage, holds/fences, replay ownership, and module bindings
   are preserved. Display/enabled-only provider edits remain outside
   the context digest and are never labelled readiness.
6. **Provider notes and preparation parity (requirement 6).** Provider
   EDIT shows current notes read-only with preserve/replace/clear; a
   BLANK replacement KEEPS current notes (replacing is not an implicit
   clear), and the explicit clear flows the `clear_notes` intent
   through the shared audited service - the REAL prior notes are
   captured, one audit shows real old value -> real new null, with no
   direct pre-clear and no second audit. The full edit takes the 199
   administrative row lock in the caller transaction before the
   service prior-state capture, and slug/status editing is unchanged.
   ROUTE CREATE carries the finite creation intent (Automatic /
   Prepare disabled / Enable explicitly) as the sole new-UI activation
   control: automatic keeps the enabled default for a basic
   empty-capabilities route, a supplied complete-capabilities document
   prepares the route DISABLED without an extra mode change, and
   explicit enable activates; legacy POSTs with no intent keep the
   existing enabled-checkbox semantics, and basic-route creation is not
   disabled. PROVIDER CREATE defaults the enabled checkbox OFF (an
   explicit check enables) with one plainly labeled optional Notes.
   Enabled never proves provider authentication, health, or
   compatibility.
7. **Secret protection, recovery, and field help (requirement 7).**
   The established known-shape credential refusal (the 199 CLI law)
   runs BEFORE any new provider write (create and full edit); provider
   detail, form re-display, and route-review contexts project the
   touched retained free-form values; the route-form refusal
   re-render blanks the advanced capabilities bytes and projects the
   retained values; ENV-variable NAMES are never masked. A demonstrated
   edge was repaired in-order: credential-bearing (userinfo) URL values
   are now withheld entirely on form/detail/review display (any
   userinfo, any scheme, including empty userinfo; malformed URLs
   withheld safely instead of re-raised, so a 400 recovery page cannot
   become a 500), leaving ordinary URLs byte-identical and URL
   acceptance, canonical values, fingerprints, and stored data
   unchanged. Every touched/new editable or choice control carries
   associated, individually linked help (purpose, raw token/frame
   units, ceiling context, omission/keep/clear meanings, bounds,
   scope); configuration validation is labelled as not being
   admission/pricing/provider-health or live-model proof. Labels wrap
   one control, help IDs are unique, and `aria-describedby` sits on the
   actual inputs (including the picker help links via the optional
   record-choice `help_id`; other callers unchanged). The client JS
   only manages progressive active/inactive state (the capability
   source fieldsets hidden AND disabled; no value conversion; stale
   managed hidden values cannot resubmit), and keyboard and no-JS
   paths succeed through to the persisted change. The review table
   uses the standard ordinal-first sortable layout with raw typed sort
   keys, the standard empty-state row, and a labelled keyboard-
   focusable table-wrap inside the packaged theme.

## Root-approved bounded shared-law exception (exact scope)

A demonstrated defect: the reviewed preview promised a null notes
target while the repository treated `notes=None` as preserve. Root
approved the exact bounded paths (`services/model_route_service.py`,
`db/repositories/routing.py`, `services/provider_route_configuration.py`
plus their unit tests; the 199 CLI PG module needed no change):
`update_model_route_metadata(..., clear_notes: bool = False)` writes
NULL only when explicitly requested (`notes=None` WITHOUT it still
preserves); `update_model_route(..., clear_notes: bool = False)`
refuses the conflicting notes+clear combination; and
`execute_route_update_plan` passes `clear_notes=plan.notes is None` -
the plan's notes is the reviewed canonical target, applied as an
explicit clear (a no-op when already null; equality is checked first,
and the service captures the REAL prior notes in its single audit).
No schema/plan-version/permission/accounting change; the order bytes
are immutable. The shared fix applies to the CLI as well (requalified,
31 PASS). Evidence: `unit-clear-1.xml` (202 PASS), the native
clear-only case in `pg-210a-3.xml`, and `cli-pg-210a-1.xml` (31 PASS).

## Exact changed paths (IMPL vs base main `32478e0`)

- `app/slaif_gateway/api/admin_provider_route_configuration.py` (NEW:
  focused router - GET form / POST plan / POST apply; readable review
  helpers; `_provider_context_readable` projection)
- `app/slaif_gateway/api/admin_review_intent.py` (route-purpose token
  build/verify; strict reparse + 128 KiB decoded canonical-plan bound
  at build AND verify; malformed-format fixed refusal before digest
  comparison; the seven pre-existing review helpers unchanged)
- `app/slaif_gateway/main.py` (router include; composition only)
- `app/slaif_gateway/api/admin.py` (bounded: provider detail/form
  display projections, provider create+edit known-shape refusals
  before any write, legacy route-form refusal blanking/redaction,
  route-creation intent path validated in the same caller transaction,
  the entry link, `_admin_url_display_value`, and the provider
  create/edit notes-intent wiring)
- `app/slaif_gateway/services/admin_record_choices.py` (NEW bounded
  `completion_profile` kind: streaming `os.scandir` enumeration,
  filters before stat, 100 cap, `bindings.json` excluded, unsafe-mode
  refusals; basename-derived root-relative joins after the ID-law
  refusal, proven by the shared containment check to stay inside the
  canonicalized trusted root before any I/O)
- `app/slaif_gateway/api/admin_record_choices.py` (kinds registration)
- `app/slaif_gateway/services/model_route_service.py`
  (root-approved `clear_notes` flow)
- `app/slaif_gateway/db/repositories/routing.py` (root-approved
  `clear_notes` repository law)
- `app/slaif_gateway/services/provider_route_configuration.py`
  (root-approved `clear_notes=plan.notes is None` in the executor)
- `app/slaif_gateway/modules/servers/completion_service/profiles.py`
  (root-approved: basename-derived join plus the shared
  `contained_child` root-containment guard - trusted root only
  canonicalized, joined candidate normalized and required to start
  with the canonical root plus a separator, separator-safe at the `/`
  root, final file never resolved; loader law unchanged)
- `app/slaif_gateway/web/assets.py` (asset registration)
- `app/slaif_gateway/web/static/js/catalog-configuration.js` (NEW:
  progressive source/leaf state sync only - never value conversion)
- `app/slaif_gateway/web/templates/routes/configuration_form.html`
  (NEW), `configuration_review.html` (NEW), `configuration_result.html`
  (NEW)
- `app/slaif_gateway/web/templates/routes/detail.html` (entry link),
  `routes/edit.html`, `routes/create.html` (creation intent; metadata
  help incl. the restored established sentence; valid raw
  capabilities placeholder), `providers/create.html` (default-OFF
  enabled; one optional Notes), `providers/edit.html` (read-only
  current notes; preserve/replace/clear)
- `docs/MISSING_GUI_FUNCTIONALITY.md` (section 12 + header/tables/
  still-open), `docs/admin-usability.md` (section 11),
  `docs/cli-field-administration.md` (GUI pointer),
  `docs/deployment.md` (210 operator note),
  `docs/verification/README.md` (index entry),
  `docs/verification/gui-cli-parity.md` (210-a living record incl. the
  actual CI chronology)
- `oap/orders/210-a-gui-provider-route.md` (byte-exact order),
  `oap/active` (pointer)
- `tests/unit/test_admin_provider_route_configuration_210.py` (NEW:
  58 cases), `tests/integration/test_admin_provider_route_configuration_210_postgres.py`
  (NEW: 12 cases), `tests/browser/test_admin_provider_route_configuration_210.py`
  (NEW: 8 cases)
- `tests/unit/test_completion_service.py` (root-approved: loader
  invalid-component before-I/O refusals, valid-name identity,
  containment-predicate and separator-safe `/`-root assertions,
  inside/outside-root symlinked profile refusals, relative/symlinked
  root refusals),
  `tests/unit/test_admin_record_choices.py` (completion-profile cases
  incl. invalid selected components),
  `tests/unit/test_admin_provider_config_actions_routes.py` (directly
  affected: locked-read fixture backing + the three URL display
  canaries), `tests/unit/test_admin_slaif_design.py` /
  `tests/unit/test_admin_usability_inventory.py` (registrations for
  the new table/scroll region; assertions preserved),
  `tests/unit/test_documentation_contract_drift.py` (consumer
  registration), `tests/unit/test_model_route_service.py` /
  `tests/unit/test_provider_route_configuration.py` (root-approved
  focused clear cases)

## Focused evidence (local)

All JUnit files under `/tmp/slaif210/`; the final qualifying runs were
in managed foreground terminals; owned loopback/tmpfs PostgreSQL
fixtures with exact-ID cleanup (none left).

- **210 unit module: 58 PASS / 0 skip** (`unit-210a-3.xml`, 24.033 s,
  latest after the URL hardening; the post-layout
  `unit-210a-2.xml` 58 PASS receipt reused for unchanged areas).
  Fake-persistence ASGI/Jinja: capability-source law and scalar
  independence, leaf diff rendering (M + exact raw counts; external-
  tool/transport values; state-aware labels), completion-profile
  picker wiring, token round-trip plus purpose/actor/session/expiry/
  tamper/non-ASCII/oversize/decoded-128-KiB-inside-wrapper-slack
  refusals, complete-document 64 KiB bound, canonical-plan 128 KiB
  refusal before rendering/signing, apply flows (confirmation,
  512-character reason, CSRF, stale/zero-diff, canary absence),
  provider create/edit canaries, creation-intent laws, help
  associations, and table/empty-state structure.
- **Completion-profile lookup: 74 PASS / 0 skip**
  (`choices-210a-1.xml`, 15.216 s) plus the final six
  completion-profile tail cases re-qualified after the last test-file
  patch (`choices-210a-3.xml`, 6 PASS / 0 skip, 2.449 s).
- **Shared-clear-affected modules: 202 PASS / 0 skip**
  (`unit-clear-1.xml`, 24.694 s: the 58-case 210 unit module +
  `test_model_route_service` + `test_provider_route_configuration`).
- **Owned PostgreSQL: 10 PASS / 0 skip** (`pg-210a-1.xml`, 6.480 s;
  chronology: first run 10/2 failures from digit-leading seed ENV
  names violating the existing ENV-name validator, corrected to
  `GUI210_*`; the JUnit was overwritten, chronology preserved) and
  **12 PASS / 0 skip** (`pg-210a-3.xml`, 7.739 s: preview read-only,
  exact apply + 1 audit, stale no-write, late-failure rollback,
  zero-diff no-op, provider create disabled / edit clear,
  route-creation intents with zero-retries refusal, real auth/CSRF
  denial, native clear-only; the first run of the two new cases
  failed on an audit helper-key typo in the test - fixture-only - and
  the runner wrapper's `NameError` occurred AFTER tests and cleanup,
  harness-only). Plan TAMPER is unit evidence, not a native PG case.
- **Added denial case: 1 PASS** (`pg-210a-2.xml`, 3.833 s; real
  login/session/CSRF: missing cookie 303 and wrong CSRF 400 before any
  route/audit change).
- **Affected 199 CLI PG module (requalified after the shared execute-
  path change): 31 PASS / 0 skip** (`cli-pg-210a-1.xml`, 36.378 s).
- **Real Chromium / owned PG: 8 PASS / 0 skip, 21.267 s**
  (`browser-210a-1.xml`; actual uvicorn app, real stylesheet; exact
  container cleanup). Entry link + safe initial states (desktop and
  narrow captures), the keyboard guided plan/apply flow (disclosure
  opened by keyboard; independent persisted-DB and audit oracles), the
  JS capability-source transitions (stale inactive values never submit
  after a round trip), the full-document replacement (shared-
  normalized canonical state; raw JSON read only after opening the
  disclosure by keyboard), the no-JS fallback through to the persisted
  change (including notes clear via the shared fix), the provider edit
  notes clear (redirect query; all other fields exact), the
  route-creation intents (provider before the dependent model;
  expect-response with safe error inspection), and the help-
  association resolution. The honest browser chronology (2 cases/1
  hidden-Chat failure 42.688 s; targeted 11.197 s unsupported
  result-reason oracle then 10.808 s pass; full 8/4 fixture/oracle
  failures 78.933 s - raw-document expectation ignored canonical
  defaults, no-JS notes label ("No notes." vs actual "(none)"),
  provider redirect `?message` query, and provider-before-model
  fixture ordering (the unused outer PG removal was a separate setup
  correction); full 8/2 - ONE the REAL shared notes-
  clear persistence defect repaired through the root-approved
  exception, the other a closed-disclosure test read - 21.927 s; final
  8 PASS) is in the living record. Focused screenshots (synthetic
  data only, no result-page or token captures) under /tmp/slaif210/.
- **Affected main/legacy/consumer/design/governance: 184 PASS / 0
  skip** (`affected-210a-1.xml`, 14.566 s: main composition, legacy
  route form modules, consumer/doc drift, design/inventory
  registrations, and the 9 OAP governance cases on the byte-exact
  order).
- **Legacy provider form module: 17 PASS / 0 skip**
  (`affected-210a-2.xml`, 8.203 s; first run 14/1 - the pre-existing
  `_FakeSession` did not back the new caller-transaction locked read;
  fixture-only backing in the authorized path - then the three URL
  display canaries joined).
- **URL display canaries: 3 PASS / 0 skip** (`urlcanary-210a-2.xml`,
  3.935 s; supersedes `urlcanary-210a-1.xml`, 2 PASS pre-hardening):
  https/ftp userinfo refusals with no writes and no echo, ordinary-
  URL recovery byte-identical, malformed IPv6 withheld safely, ftp
  userinfo withheld; root independently ran 8 ASGI refusal/recovery
  checks (mocked auth, no real DB/provider).
- **Completion-profile path-boundary re-verification: 117 PASS / 0
  skip** (`pathfix-210a-1.xml`, 15.745 s: the loader and choice
  modules after the basename clarification; invalid components refused
  before any I/O, valid names unchanged).
- **Completion-profile path-boundary FINAL re-verification: 121 PASS /
  0 skip** (`pathfix2-210a-1.xml`, 15.699 s: the loader and choice
  modules after the root-containment guard and the separator-safe
  root-prefix correction; adds the containment-predicate and `/`-root
  pure assertions, inside-root and outside-root symlinked profile
  refusals, relative/symlinked root refusals; invalid components still
  refused before any I/O, valid names unchanged).
- **Dashboard smoke re-verification: 1 PASS / 0 skip**
  (`smoke-210a-1.xml`, 10.183 s; the exact failed CI case after the
  wording restoration, owned container lifecycle verified and cleaned).
- **Scoped root component probes (reused, mocked auth, no real
  DB/provider):** 11 pure review-helper checks, 8 completion-lookup
  metadata checks, 3 provider-detail projection checks, 2 provider
  create/edit known-shape canaries, 8 URL-fix checks, and the AST
  audit that the seven pre-existing review helpers are unchanged.

## Static and governance checks

- `tests/unit/test_oap_governance.py`: 9 PASS / 0 skip (within
  `affected-210a-1.xml`) with the 210-a order byte-exact and
  `oap/active=210-a`.
- Ruff clean on every changed Python path (re-run after each
  product/test change, including the final commits).
- `scripts/check_documentation.py`: `DOCUMENTATION_CHECK=OK` (135
  files), re-run after every docs change;
  `tests/unit/test_documentation_contract_drift.py`: 15 PASS / 0 skip
  (`docdrift-210a-3.xml`, latest after the final docs-only commits,
  `f7364ba446f02dda06d9bf6f0540c4e64e166b278c102e89eed8214cb63f8d29`;
  supersedes `docdrift-210a-2.xml` and `-1`).
- `git diff --check` clean.

## CI chronology (per head, actual)

- **IMPL head `edf201e3` (first head): CodeQL aggregate FAILED**
  (2026-11-01T05:30:40Z) with three HIGH path-injection alerts
  (`modules/servers/completion_service/profiles.py:153`;
  `services/admin_record_choices.py:255,352`). Root SARIF review: the
  sources are submitted profile/selected IDs, not an HTTP-supplied
  directory; the existing fullmatch whitelist
  `[a-z0-9][a-z0-9-]{0,63}` excludes path separators; no escape
  demonstrated. Bounded same-order repair (`ebc12dac`, with the
  additionally approved paths
  `app/slaif_gateway/modules/servers/completion_service/profiles.py`
  and `tests/unit/test_completion_service.py`): AFTER the existing
  ID-law refusal, the final single root-relative filename is re-derived
  with `os.path.basename` at the loader join and both lookup joins
  (no raw `entry.path`), making the by-construction boundary explicit
  without relaxing it - whitelist, streaming enumeration, 100 cap,
  file modes, and O_NOFOLLOW unchanged; no suppression, dismissal,
  config change, or directory framework. Focused re-verification:
  `pathfix-210a-1.xml` (117 PASS / 0 skip). The follow-up CodeQL runs
  on the next heads (`bfe1ab43`, `784ed9c5`) STILL reported the same
  three HIGH alerts - the basename re-derivation alone was insufficient
  for the analysis (the SARIF still traced the submitted IDs through
  the basename join) - so a further bounded guard was authorized.
- **IMPL head `edf201e3`: browser job `124761536375` FAILED** on
  exactly one case: `tests/browser/test_admin_dashboard_smoke.py::
  test_admin_dashboard_browser_smoke` (line 487) - the new associated
  route-create metadata help had rephrased the established warning
  sentence the smoke asserts ("Runtime consumes it only for exact
  OpenAI Responses"). Same-order repair (`bfe1ab43`): the original
  sentence restored verbatim inside the route-create metadata help,
  keeping the added field guidance and all hosted-tool limitations; no
  acceptance change or test weakening. Focused re-verification:
  `smoke-210a-1.xml` (1 PASS / 0 skip).
- **IMPL head `c32c6ca9` (CodeQL root-containment guard):** following
  the official CodeQL recommendation, the shared helper
  `profiles.contained_child` (loader join, enumeration join, hydration
  join) canonicalizes the TRUSTED ROOT only (`os.path.realpath`; the
  root's original absolute/non-symlink law is still checked first and
  unchanged), `os.path.normpath`s the joined validated filename, and
  requires the normalized candidate to start with the canonical root
  plus a separator BEFORE any I/O. The final file is never resolved
  and never opened through a symlink target: O_NOFOLLOW,
  symlink/mode/size refusal, streaming caps, and the pre-I/O ID-law
  rejection are all preserved. No directory framework, suppression,
  dismissal, or config change. Focused re-verification:
  `pathfix2-210a-1.xml` (121 PASS / 0 skip).
- **IMPL head `cea28df1` (separator-safe root prefix; final CODE
  head):** `canonical_root + os.sep` builds `"//"` when the accepted
  root is `/` and would wrongly refuse `/profile.json`; the root
  prefix is now derived with `os.path.join(canonical_root, "")`
  (exactly one trailing separator; `/` itself at the root). Strict-
  child and separator-boundary requirements unchanged; a pure helper
  assertion covers the `/` root without any filesystem write. Same
  focused suite: 121 PASS / 0 skip. Actual checks queried
  2026-11-01T05:58:50Z: **CodeQL aggregate `completed/success`**, with
  Unit/lint/migration, OpenAI-compatible E2E, Docker Compose smoke,
  documentation hygiene, and the three CodeQL analyze jobs all
  `completed/success` at the same timestamp; the Playwright browser
  smoke and PostgreSQL integration jobs were still `in_progress` at
  that timestamp (the same suites have local green receipts:
  `browser-210a-1.xml` 8 PASS, `pg-210a-3.xml` 12 PASS,
  `smoke-210a-1.xml` 1 PASS).
- **IMPL head `19b47cf1` (final, docs-only):** `9c9102d1` recorded
  the containment fix and the actual CI results in the living record;
  `19b47cf1` corrected the browser-chronology prose there. Both are
  documentation-only - no code, test, or behavior difference from
  final CODE head `cea28df1`. Checks as actually queried at
  publication (2026-11-01T06:04:35Z): only the CodeQL analyze jobs
  were started (two `in_progress`, one `queued`); the remaining
  checks were not yet scheduled at that timestamp. Root owns the
  final-head checks and the merge gate; a failed or skipped job is
  never reported as pass.

## Privacy invariants

- The review and result pages never carry the signed token or
  generated key material; the result page is no-store and a synthetic
  token-hash marker is asserted absent (booleans only) from every
  rendered page in the browser suite.
- The audit reason is masked through the existing redaction seam
  before storage; credential-shaped form values are refused before any
  write (create and full edit) or redacted by the existing seam;
  refused advanced-document bytes are blanked before redisplay.
- Credential-bearing (userinfo) URL values are withheld entirely on
  form/detail/review display; ordinary URLs pass through byte-
  identical; URL acceptance, canonical values, fingerprints, and
  stored data are unchanged; ENV-variable NAMES are never masked and
  provider key values are never resolved or displayed.
- Canary assertions compute booleans first and assert fixed labels; no
  canary or full output is echoed in any failure representation; no
  gateway/provider secrets appear in logs, tests, screenshots, or this
  report (screenshots contain synthetic fixture data only).
- The operator request-capture facility, email delivery, and replay
  ownership are untouched by this surface.

## Deployment

Deploying 210 is an application upgrade ONLY: rebuild the API/assets
image and recreate/restart the API so the new code runs. There is NO
Nginx change: the signed route review envelope is bounded to ~175 KiB
(178,858 base64url characters), well inside the existing default
`client_max_body_size`, and no new location or allowance is
introduced. No database migration; existing keys and routes are
untouched. Installed completion-service profiles are a process-local
cache: deploy the profile files to the configured profile directory,
then recreate/restart the API so the process picks them up. The
operator note is in `docs/deployment.md`.

## Documentation

- `docs/MISSING_GUI_FUNCTIONALITY.md` section 12 (compact delivery
  status: G06/G07 delivered; shared-clear note; G08-G18 open; links),
  plus the header delivery update, the provider/routes table rows, and
  the three "Still open" sections.
- `docs/admin-usability.md` section 11 (navigation; form semantics -
  scalars/notes independent of the capability source; review/apply;
  route-create intent vs provider-create default; upgrade notes).
- `docs/verification/gui-cli-parity.md` 210-a section (living record:
  parity contract, bounded implementation, focused evidence with
  hashes, honest qualification chronology, root-approved exception,
  the ACTUAL per-head CI chronology, operator notes, limitations).
- `docs/verification/README.md` index entry (newest first).
- `docs/cli-field-administration.md` GUI pointer on the 199
  provider/route parity section (route creation carries the finite
  intent; provider creation defaults disabled; CLI commands and schema
  unchanged; the shared notes-clear fix applies to the CLI as well).
- `docs/deployment.md` 210 operator note (application upgrade only;
  no Nginx change; no migration; process-cached profiles).

## Pending and honest limitations

- Check states are recorded per actual head above. At publication
  (2026-11-01T06:04:35Z) the final docs-only IMPL head `19b47cf1` had
  only just begun its check run (CodeQL analyze jobs two
  `in_progress`, one `queued`; the other checks not yet scheduled) -
  pending is recorded as pending, never as pass. The final-head
  checks, strategic review, and guarded merge remain the root's
  gates. The code head `cea28df1`'s CodeQL aggregate is
  `completed/success` (2026-11-01T05:58:50Z), with Unit/lint/migration,
  E2E, Compose smoke, documentation hygiene, and the analyze jobs all
  success at that timestamp; its browser and PostgreSQL integration
  jobs were still `in_progress` at that query and are covered locally
  by the green receipts listed above.
- Component scope distinctions: the 58-case unit suite runs on
  synthetic fake persistence (no real DB); the PG suites run on the
  qualified owned PostgreSQL; the 8-case browser suite runs the actual
  uvicorn app plus the real stylesheet against the same owned fixture;
  the scoped root component probes used mocked auth/lookups without
  app auth/PG. The 207/208/209 component proof and the unchanged CLI
  law are reused, not rerun; the affected shared route-execute path WAS
  requalified (31 CLI PG PASS); no full local matrix was run.
- The full GUI goal remains broader than G06/G07: G08-G18 stay open,
  and the final whole-GUI qualification (219) is later work.
- No production, security, compliance, provider-behavior, or scale
  claim follows from this objective.
