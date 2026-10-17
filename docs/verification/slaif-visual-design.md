# SLAIF visual design — verification record

> **Date:** 2026-10-17
> **Commit:** the Objective-188-a implementation head published on its
> pull request (SHA recorded in the immutable OAP report for 188-a)
> **Scope:** packaged admin visual design (theme, typography, shared
> shell, named table regions, error surfaces) and the unchanged operator
> branding overlay
> **Environment:** owned loopback PostgreSQL 16 container (labeled,
> tmpfs-backed, exact-ID cleanup), uvicorn on a free 127.0.0.1 port,
> native Playwright Chromium, synthetic HMAC/encryption/session secrets,
> no ambient database or host environment values

This record describes what the bounded 188-a runs actually proved. It is
commit-specific evidence, not certification of later commits, production
fitness, security, or scale.

## What ran

### Unit (packaged design contract)

`pytest tests/unit -k "admin or branding or main_app or oap or documentation"`
→ **551 passed, 0 failed** (2026-10-17, owned environment). The twelve
design-specific unit tests in
`tests/unit/test_admin_slaif_design.py` prove:

- packaged font assets match the pinned SHA-256 values and OFL notices;
- `@font-face` rules are local with no external font sources;
- the CSS exposes the contract tokens plus the retained `--bg`/`--panel`
  aliases at their consumers;
- default-theme text/control pairs meet a computed 4.5:1 contrast floor;
- the login page renders the shared shell without section navigation, and
  authenticated pages render the fourteen-link nav with
  `aria-current="page"`;
- `navigation.js` is served locally;
- admin error pages preserve status, exact message, and the shared shell,
  and Jinja-escape message data;
- all 23 table wrappers carry `role="region"`, `tabindex="0"`, and a
  non-empty `aria-label`;
- templates/CSS/JS reference no external asset URLs;
- the `/v1` JSON error contract is unchanged by the HTML error surface.

### Native browser (real app, owned PostgreSQL)

`pytest tests/browser/test_admin_slaif_design.py` → **4 passed, 0 failed**
in one focused run (2026-10-17). All four cases run the real uvicorn
application against an owned, labeled, loopback-bound PostgreSQL container
with real admin login, real HTTP, and real Chromium rendering. The upstream
provider layer is never invoked (no provider calls, no real keys).

1. **Default theme** — login (1440 and 375, anonymous) with exact
   cream/teal computed palette, both font faces loaded and byte-exact
   SHA-256 over HTTP, shared shell (lockup, footer, skip link), no
   horizontal overflow; dashboard at 375 with a long synthetic admin
   identity string (wraps, no overflow) and at 1440 (fourteen-link nav,
   `aria-current`); keys list at 1440 with the named focusable
   `role="region"` table region and computed primary/secondary/select
   contrast pairs ≥ 4.5:1; key detail (safe metadata, no plaintext) and
   provider list review surfaces; 768 tablet (inline nav, no toggle,
   keyboard-focused table region, real `ArrowRight` keyboard scroll with a
   bounded wait when the table overflows); 375 keys (compact keyboard menu:
   Enter expands with `aria-expanded="true"`, Escape closes and returns
   focus); 375 key-create form (action panels and every control contained
   inside the card).
2. **No-JS navigation** — with JavaScript disabled: no `nav-ready` class,
   toggle hidden, the wrapping nav visible and usable at 375 (plain form
   login, link navigation) and at 768, no overflow.
3. **Alternate operator theme** — operator CSS loads after the packaged
   stylesheet and wins; navy/gold computed body/heading; scoped
   primary/secondary/select control pairs computed at the actual controls
   with contrast ≥ 4.5:1 and body text ≥ 4.5:1 against the page surface;
   real mobile login at 375; 768 tablet (inline nav, no toggle); 375
   compact logo slot replacing the wide logo.
4. **Error surfaces and form flow** — authenticated branded 404 and 400
   with exact pre-existing messages on the shared surface; anonymous
   redirect proven in a fresh browser context (no session leakage);
   owner-create server-side validation refusal (`Owner email must be
   valid`, exact flash element, no row written); valid owner create with
   reason and CSRF (one row written); bad-CSRF refusal (400,
   `Invalid CSRF token.`, no row written); `/v1/chat/completions` still
   returns 401 OpenAI-shaped JSON.

### Inherited browser regressions

After each layout correction, the previously qualified browser modules
were rerun with their presentation locators and style expectations
updated for the new theme (the assertion semantics — real owned-PG
state, auth/CSRF flows, live refresh, fallback, and no-JS negatives —
are retained): `tests/browser/test_admin_branding.py` and
`tests/browser/test_admin_lazy_throttling.py` → **6 passed, 0 failed**
(2026-10-17, final rerun after the key-create containment fix). These
cover the 187 branding slots/live-refresh/fallback and the 185
lazy-throttling key-create/policy/reject/audit/no-JS flows under the new
theme.

## Product layout defects found and fixed in this objective

Independent 375/768 probing against the real application found three
narrow-viewport layout defects, each fixed in the packaged stylesheet
(presentation only) and pinned by a browser assertion:

1. 375px dashboard: a long admin identity line forced horizontal overflow
   (`.brand-copy` min-content). Fixed with `min-width: 0` on
   `.dashboard-header` flex children and `overflow-wrap: anywhere` on the
   identity block. Regression: 375 dashboard overflow check with a long
   synthetic email.
2. 768px five-field filter bars (keys/pricing/routes): the 130px column
   minimums overflowed the page. Fixed by relaxing the filter-bar tracks
   to `minmax(0, 1fr)` below 960px. Regression: 768 keys overflow check.
3. 375px key-create card: action panels (driven by long select options)
   exceeded the card while the page did not overflow. Fixed with an
   explicit `minmax(0, 1fr)` form column and `min-width: 0` on form
   children. Regression: 375 key-create panel/control containment
   assertions (page-level overflow checks alone cannot catch this).

## Real vs mocked

| Boundary | Kind |
|----------|------|
| PostgreSQL | Real owned container, real migrations, real rows |
| Admin auth / session / CSRF | Real (synthetic secrets, real login) |
| HTTP / rendering | Real uvicorn + native Chromium |
| Font bytes | Real HTTP fetch, SHA-256 pinned |
| Upstream providers | Not invoked in any of these runs |
| Unit render tests | Rendered templates with mocked service/repository boundaries where the test targets presentation |

## Screenshots

The focused browser run produced sixteen review images (per-test unique
output directories), copied to the strategic review directory as
`agent-design-*.png`: default login 1440/375, dashboard 1440/375, keys
1440/768/375, key-create 375, key detail 1440, providers 1440, alternate
login 1440/375, alternate keys 768/375, error 404 1440, and the owner
validation-error surface. Screenshots contain no one-time keys,
passwords, CSRF values, or provider material (login images are captured
before form fill; no key-result screens are captured).

## Slot × surface parity (closed in this objective)

Source coverage (structural audit of the checked-in tree, root
`template-parity-audit.json`): all 68 admin HTML files comprise 65 full
pages that inherit the shared `base.html`, plus the `_brand` and
`_policy_selector` partials. The shared base head loads the packaged
stylesheet and then the operator `style.css` **last**, the shared icon
link (favicon slot), and the branding macro with context that renders
the shared header lockup (logo / logo-compact slots) on every page; the
nav script loads in the body. The `hero` slot is the one exception to
that inheritance: it renders in the login page body only. Cells below
cite the actually measured cases; "shared base" cells rest on that
template inheritance plus the measured header behavior, not on per-page
screenshots.

| Slot | Login | Dashboard | Signed-in section pages | Admin error surface |
|------|-------|-----------|-------------------------|---------------------|
| `style.css` (operator override loaded last) | Measured (alt login 1440/375: operator CSS after the packaged CSS, computed body/heading) | Shared base (not measured on this page) | Measured through the keys pages (alt 1440/768/375) | Shared base (default theme measured in the 404 case) |
| `logo` | Measured (alt login 1440: override src) | Shared base (same header macro; not measured on this page) | Measured (alt keys 768/375; default keys 1440/768/375) | Default packaged fallback measured (404 case) |
| `logo-compact` | Shared base (alt 375 login captured; display asserted on the alt keys page) | Shared base | Measured (alt keys 375: src, display, visibility) | Shared base |
| `favicon` | 187 record (DOM link + HTTP MIME/bytes/fallback) | Shared base | Shared base | Shared base |
| `hero` | 187 record (login-body slot: DOM/bytes, live refresh, fallback; shared reader) | Not rendered (login-body slot) | Not rendered | Not rendered |

Viewports 375/768/1440 are covered per case above for both themes.
Deployment parity: development and production Compose serve the same
image and the same asset/template routes; the 187 record verified the
compose merge on both bases, and this objective changes no compose or
Dockerfile bytes. No further objective extends or re-audits this
surface set.

## Deviations

- An unnecessary full `tests/unit` matrix run was started for extra
  thoroughness after the focused affected-case selection had already
  passed, and was stopped before completion. It is not a pass and is
  not cited as evidence anywhere in this record; the focused unit
  selections above are the unit evidence.

## Limitations and pending items

- This record does not cover a production deployment, a release, or any
  security certification; the product remains RC-beta.
- The final-SELF GitHub matrix for the implementation head, strategic
  review, and the guarded merge remain pending at the time of writing;
  they are not claimed here.
- The hero branding slot remains login-page only (by design).
