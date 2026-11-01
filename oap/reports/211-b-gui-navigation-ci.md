# OAP Coding-Agent Report — 211-b

## Work order
- Identifier: 211-b
- Work-order file: `oap/orders/211-b-gui-navigation-ci.md`
  (committed with its EXACT strategic-authored bytes in IMPL; sha256
  `7f4b9dd1ec0490aca3a4fb70b3d436dbf1520e8a1e71c44702d85f404343cea5`,
  8,682 bytes)
- `oap/active` pointer: value `211-b` (5 bytes, no trailing newline),
  committed in IMPL
- Numeric objective: 211
- PR mode: AMEND_EXISTING_PR (PR 367; branch
  `oap/211-gui-diagnostics-config`; base = existing PR head
  `27082a43774d19fdd4b7ae4b9144316356d8157c`, the A SELF)
- Implementation head SHA (literal): `0b253cb02e934f791f390f1ddbd6c2de579c0913`
  (one 211-b commit on top of the A SELF)
- Report publication commit: SELF (this report is the ONLY difference
  between SELF and IMPL; SELF's first parent is IMPL)

## Status

211-b COMPLETE; the TWO focused browser cases are GREEN locally. B
repairs the demonstrated final-head Playwright CI blocker on the SAME
211 PR 367: two legacy exact nav-link counts (14) that are stale
against the intentional, approved 15-link Operations navigation. This
is a bounded test-oracle correction - B changes NO product, template,
JS, CSS, or fixture-ownership bytes from A, and the A report
(`oap/reports/211-a-gui-diagnostics-config.md`) remains immutable.

## A final-head CI failure (demonstrated, terminal)

Playwright job `124809403688` of CI run `41293439505` FAILED at
2026-11-01T09:36:22Z: 2 failed / 70 passed in 242.95s. Both failures
were `tests/browser/test_admin_slaif_design.py`:
- `test_design_default_theme_shell_fonts_navigation_and_tables`
  (line 395): `assert nav.count() == 14`, actual 15;
- `test_design_no_javascript_navigation_usable` (line 548):
  `assert page.locator('#admin-nav a').count() == 14`, actual 15.

The 15th link is the approved Operations entry (G08/G16 navigation).
All other A final-head checks were SUCCESS; the A run was terminated
at 2026-11-01T09:42:51Z, CANCELLING the still-running PostgreSQL
integration job (not a pass; never treated as one). A was NOT all
green.

## Bounded B repair (tests + one doc addendum)

- The two failing exact counts, plus the downstream 768-tablet count
  in the same no-JS case that the first fix unblocked, now expect 15.
- Both the normal and no-JavaScript scenarios explicitly assert the
  ONE correctly named Operations link: `#admin-nav a[href='/admin/operations']`
  with count exactly 1 and accessible text "Operations", derived from
  the accepted base template (no arbitrary extra link, no weakened
  `>=14`, no dynamic DOM self-count).
- All other font-byte, theme/contrast, logo/branding, current-page,
  keyboard, responsive-overflow, table, and no-JS assertions and
  fixtures are preserved.
- Concise 211-b addendum appended to
  `docs/verification/gui-cli-parity.md` (previous history preserved;
  no new document or inventory).

## Exact changed paths (B IMPL vs A SELF `27082a43`)

- `tests/browser/test_admin_slaif_design.py` - three exact nav counts
  14 -> 15 (two failing + one unblocked downstream) and two explicit
  Operations-link assertions (one per scenario).
- `docs/verification/gui-cli-parity.md` - 211-b addendum only.
- `oap/active` (`211-a` -> `211-b`), `oap/orders/211-b-gui-navigation-ci.md`
  (root-authored bytes committed unchanged).

No other path differs; all A orders, reports, and product bytes are
preserved.

## Focused B evidence (local, /tmp/slaif211)

| Receipt | Result | Scope |
| --- | --- | --- |
| `browser-211b-1.xml` | 2 PASS / 0 fail, error, skip (16.829s), sha256 prefix `074b1d28` | the TWO complete existing browser cases on real Chromium with the qualified owned-PG fixture (child pytest exit 0; exact owned container cleaned - owner filter empty): `test_design_default_theme_shell_fonts_navigation_and_tables` (10.455s) and `test_design_no_javascript_navigation_usable` (3.928s) |
| `unit-211b-1.xml` | 24 PASS / 0 skip (1.573s), sha256 prefix `c7a78ed1` | 9 OAP governance tests on the EXACT B order + active, and the documentation contract drift checker (run after the doc addendum) |

- Scoped Ruff on the touched test: clean.
- `git diff --check`: clean.
- Synthetic data only: real app over real HTTP, real Chromium, owned
  disposable PostgreSQL; no real credentials, provider calls, or email.

## Reused unchanged A evidence (not rerun)

B changes no product bytes, no fixture ownership, and no other test,
so the accepted A receipts remain valid: unit 34 / 4 / 61 / 173
(overlapping 34 + 133) / 133, native owned-PG 8 distinct + 3
overlapping rechecks, real Chromium 7, and the final 35 (CLI
configuration-inspection defaults + OAP governance + doc drift). The
other 70 CI browser passes on the A head cover every browser case
except the two corrected here.

## CI chronology (per head, actual)

- A head `27082a43`: SUCCESS - Unit, lint, and migration head; Analyze
  Python; Analyze (python); Analyze (javascript-typescript); CodeQL
  aggregate; OpenAI-compatible E2E; Docker Compose smoke;
  Documentation hygiene. FAILED - Playwright browser smoke (the two
  stale counts above). CANCELLED - PostgreSQL integration (the A run
  was terminated at 2026-11-01T09:42:51Z; not a pass).
- B IMPL head `0b253cb0` (queried at report publication,
  2026-11-01T09:43:16Z): SUCCESS - Analyze (javascript-typescript);
  Documentation hygiene. IN PROGRESS - Unit/lint/migration,
  PostgreSQL integration, OpenAI-compatible E2E, Playwright browser
  smoke, CodeQL Analyze (python), Analyze Python, Docker Compose
  smoke. Pending and in-progress checks are NOT reported as passed;
  the B final-head CI is a normal required gate, root-owned.

## Limits and preserved state

- B repairs no product behavior: the 15-link nav is the accepted A
  navigation; no new operator action, schema upgrade, or operator
  setting is introduced; the normal API/assets upgrade facts remain
  those of A.
- A order/report/protected bytes intact: `CODEX-SESSIONS.md`
  `5ae1d77c17a367e86ef725a8f9d25aba3464b24f22fba77fd2808377f8c7feda`,
  `codex.sh`
  `66eda80258f6a4f13b88a9fe2ad5a69b9e7df226a4e503f57b35b6c6f03e1247`,
  untracked `uv.lock`
  `d3d0e80db77da56e41795c619875ac14b5d25427d5169a7c9d2c8dee45b3b5b6`
  (all verified at publication; none committed).
- No deploy, release, tag, or production mutation by B.

## Documentation

Only the living verification record gained a concise 211-b addendum
(no new documents, inventories, or fixture history).

Documentation updated: docs/verification/gui-cli-parity.md
