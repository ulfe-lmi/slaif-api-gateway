# 2026-10-25 Objective 193-a admin visual consolidation verification

Bounded verification record for Objective 193-a (approved admin visual
consolidation and hyperlink table sorting): the shared visual
foundations, hyperlink table-sort headers, the integrated record-choice
control appearance, and the deterministic local asset-revision URLs.
Synthetic data only (owned temporary PostgreSQL, native Chromium, real
authenticated admin HTTP against a local uvicorn app); no real
provider/model/email/production claim.

## Scope of the change (what this record covers)

- `web/static/css/admin.css` — shared tokens (control/button radii),
  top-anchored `.page-shell`, unified 42px control geometry, unified
  label (13px/600 muted) / value (14px/400) typography, top-aligned
  filter bars with downward-expanding chips, hyperlink sort-header
  styles (`.ts-link`/`.ts-indicator`, neutral U+2195 before first
  click, accent up/down markers after), the integrated `.rc-*`
  control (arrow inside the border, compact clear, chips below),
  grouped dashboard styles, centered header actions, and a
  token-driven decorative arrow for native single dropdowns
  (`select:not([multiple]):not([size])`; multiple/size listboxes keep
  the native box).
- `web/static/js/table-sort.js` — header controls are real focusable
  text hyperlinks (`<a class="ts-link" href="#ts-sort">`, local
  fragment, no network); click and native Enter activate; Space does
  not (link semantics); `aria-sort` and indicator-space semantics
  unchanged; comparison logic unchanged.
- `web/static/js/record-choices.js` — `.rc-js` enhancement class; a
  single selected value remains a chip while the integrated box keeps
  a blank search prompt (managed hidden field stays the scalar form
  authority); no-JS behavior unchanged.
- `web/templates/_record_choice.html` — integrated markup (arrow
  inside the box; multi static chevron); default visible prompt for
  blank boxes ("Search or select…") with explicit caller
  placeholders preserved. All EXISTING classes and data-* hooks are
  preserved (record-choices.js and the no-JS fallback keep their exact
  behavior); 193-a ADDED the visual wrapper classes `rc-main` /
  `rc-main-multi`, `rc-js` (set by the script at enhancement), and the
  chevron spans — no existing class or data-* was renamed or
  removed.
- `web/templates/base.html`, `dashboard.html`, and 57 other
  list/detail/form templates (60 modified templates in total,
  including the `_record_choice.html` macro above) — asset-revision
  URL wiring (base + keys create/detail extra scripts), and the
  grouped dashboard (product heading, three destination groups,
  primary action). Sign-out keeps its real CSRF-protected POST
  `<button>`; it is only styled as a plain text link (not an actual
  hyperlink).
- `web/assets.py` (new) + one `templates.env.globals` registration in
  `api/admin.py` — fixed-allowlist, content-digest (`?v=sha256[:16]`)
  local asset revision URLs; no remote service/cache/SW/DB/build.
- `services/catalog_refresh/rendering.py` — the report's fixed style
  carries the hyperlink-header look; `<main id="ts-sort">` is the
  local fragment target for the report's hyperlink sort headers
  (internal-link audit requires resolving ids). The report still
  embeds the EXACT CURRENT shared `table-sort.js` source through the
  same byte-exact loader (single-source-of-truth law retained, asserted
  by tests); the shared source itself changed in 193-a (button ->
  hyperlink headers), so the embedded bytes changed WITH it.
- Tests: new `tests/browser/test_admin_visual_screenshots.py` (A1),
  new `tests/unit/test_admin_assets.py`, and repaired oracles in the
  existing usability/branding/design/report browser suites and
  design/template unit suites (selectors and expectations, no
  assertion weakening). `tests/browser/test_admin_lazy_throttling.py`
  was NOT modified in 193 (its record-choice helper repair is a 192-a
  change); it is run unchanged and passes against the 193 source.

## Focused unit evidence

Command (venv `/tmp/slaif192-coding-venv`, `PYTHONPATH=app`):

```
python -m pytest tests/unit/test_oap_governance.py \
  tests/unit/test_admin_usability_inventory.py \
  tests/unit/test_admin_branding.py tests/unit/test_branding.py \
  tests/unit/test_branding_png.py tests/unit/test_admin_assets.py \
  tests/unit/test_admin_slaif_design.py tests/unit/test_admin_record_choices.py \
  tests/unit/test_admin_key_create_templates.py \
  tests/unit/test_admin_key_actions_templates.py \
  tests/unit/test_admin_key_create_routes.py \
  tests/unit/test_catalog_refresh_report.py \
  tests/unit/test_catalog_refresh_source_evidence.py \
  tests/unit/catalog_report_script_audit.py \
  --junit-xml=... -p no:cacheprovider -q
```

Result: **401 passed, 0 failed, 0 errors, 0 skipped** (JUnit
`/tmp/slaif193/final-unit-affected.xml`; real exit 0). Includes the
asset-revision unit proofs (deterministic/sensitive digest, all seven
allowlisted names map to the exact digest of the bundled bytes,
changed-bytes/changed-URL and stable-bytes/stable-URL via a logical
name mapping, unknown/traversal names rejected, login page emits the
exact versioned URLs and static serves them byte-equal, unknown
static names 404), the 102-field/34-template inventory with the
raw-reference guard, the record-choice macro serialization, and the
catalog-report fixed-script/security unit suite.

## Focused browser evidence (native Chromium 156, real app, owned PG16)

The A1, usability, branding/design, and lazy-throttling suites run
against the real rendered admin (real uvicorn app on an owned
loopback/tmpfs PostgreSQL 16 fixture, seeded synthetic data, real
stylesheet and JS; no forced clicks; no test-only CSS). The report
suite is different by design: it opens the generated per-case
`REVIEW.html` files from disk offline (no PG, no admin app) and audits
the self-contained contract:


| Suite | JUnit | Result |
| --- | --- | --- |
| `tests/browser/test_admin_visual_screenshots.py` (A1: dashboard + keys list at 1440/1600/768/390, top-anchored panel, no overflow, unified 42px/14px/400 + 13px/600 geometry, link headers, default prompt, chip grow-down + restore) | `final-a1.xml` | 9 passed, 0 failed |
| `tests/browser/test_admin_usability.py` (192-a regressions: hyperlink sorting where click and Enter activate and Space does NOT toggle, record-choice batch/older search/keyboard/mouse, dependent clear, physical keystrokes, import tables) | `final-usability.xml` | 9 passed, 0 failed |
| `tests/browser/test_admin_branding.py` + `tests/browser/test_admin_slaif_design.py` (branding order/override, default + alternate theme contrast incl. transparent secondary links measured against their effective opaque surface, named regions, 768/375 surfaces) | `final-branding-design.xml` | 7 passed, 0 failed |
| `tests/browser/test_catalog_refresh_report.py` — OFFLINE file-based: the generated per-case `REVIEW.html` files (13 cases) opened from disk, no PG/admin app; offline hyperlink sorting plus the exact fixed-script/security/internal-link audit | `final-report-lazy.xml` (shared) | 2 passed, 0 failed |
| `tests/browser/test_admin_lazy_throttling.py` — real app/PG: key create through the JS dropdown selection and the no-JS raw-fill path, plus throttle behavior | `final-report-lazy.xml` (shared) | 3 passed, 0 failed |

(Counts and exit codes parsed from the JUnit files; real pytest exit
0 for every run.)

## A1 screenshot evidence

Full-page screenshots of the real authenticated dashboard and keys
list (synthetic records; the keys table shows opaque prefix + public
id only — no one-time plaintext cells, CSRF values, or cookies are
read or screenshotted):

- `/tmp/slaif193/screenshots/dashboard-{desktop-1440,desktop-1600,tablet-768,narrow-390}.png`
- `/tmp/slaif193/screenshots/keys-{desktop-1440,desktop-1600,tablet-768,narrow-390}.png`
- `/tmp/slaif193/screenshots/keys-chips-selected-desktop-1440.png`
  (selected-chip state: chip row below the controls, primary control
  tops unchanged, table moved down)

## Honest boundaries

- No full local suite / 128-worker matrix was run for this objective;
  standard CI supplies the broad matrix at the PR head.
- The A1 grow-down proof covers the real keys filter bar (owner
  picker); the other pages share the same top-aligned filter-bar CSS.
- The native-select arrow is decorative and token-driven; native
  select behavior/keyboard/options are unchanged, and multiple/size
  listboxes (policy dual-lists) intentionally keep the native box.
- No schema, migration, model, quota, accounting, provider,
  Responses, transport, or dependency changes; `api/admin.py` gained
  exactly the assets import plus the one `templates.env.globals`
  registration; `services/key_import.py` is untouched.
