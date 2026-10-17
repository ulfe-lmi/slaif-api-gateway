# SLAIF visual design (admin interface)

> **Status:** Current — implemented in the packaged admin web surface
> **Audience:** Operators, maintainers, and UI reviewers
> **Boundary:** RC-beta; the design is presentation only and changes no
> permission, quota, accounting, or API behavior

This page documents the packaged SLAIF visual design applied to the admin
interface: palette, typography, layout, accessibility behavior, and the
relationship to the optional operator branding overlay.

## Palette

The packaged theme uses the SLAIF cream/teal/lime palette. Presentation
tokens are defined once in `app/slaif_gateway/web/static/css/admin.css`
and consumed by the class rules, so an operator stylesheet that overrides
either the canonical token or the retained alias changes the same
consumer.

| Token | Value | Role |
|-------|-------|------|
| `--background` (alias `--bg`) | `#fbfbf9` | Page background (cream) |
| `--surface` (alias `--panel`) | `#ffffff` | Cards, controls, secondary buttons |
| `--text` | `#23312f` | Body text |
| `--heading` | `#16302e` | Headings |
| `--muted` | `#52625e` | Secondary text |
| `--accent` | `#086c86` | Primary buttons, links, focus outlines (teal) |
| `--accent-dark` | `#07576b` | Primary hover |
| `--border` | `#d5e0d8` | Rules and card borders |
| `--lime` | `#a3cc32` | Highlight accent: success-flash, policy-selector intro, and summary-card borders |
| `--pale-blue` | `#c8e1e8` | Nav current/hover, secondary hover |
| `--footer-background` | `#edf4ef` | Footer band |
| `--danger` / `--danger-dark` | `#a32a30` / `#801d23` | Danger controls |
| `--error-bg` / `--error-text` | `#fff2ef` / `#8f1b1b` | Flash error surfaces |

Coordinated foreground/background pairs keep readable contrast at 4.5:1 or
better in the packaged theme: primary buttons use `--button-fg: #ffffff` on
`--accent`, secondary buttons use `--secondary-fg: var(--accent)` on
`--secondary-bg: var(--surface)`, and form controls use `--text` on
`--control-bg: var(--surface)`. Status pills carry their own
`--pill-*` pair tokens.

## Typography

Two local, open-licensed faces are packaged and served from
`/admin/static/fonts/` (no external font requests):

| File | Font | Use | SHA-256 |
|------|------|-----|---------|
| `Roboto.ttf` | Roboto | Body text, controls, nav | `d7598e12c5dbef095ff8272cfc55da0250bd07fbdecbac8a530b9b277872a134` |
| `RobotoCondensed.ttf` | Roboto Condensed | Headings and the brand lockup | `dace262afcee68a5276f200d8026c57221735c0118ab5fda8c2c0d3dc409a8d0` |
| `roboto-OFL.txt` | License (OFL 1.1) | Roboto license text | `061402327a96aadb0bfb694a960ed289ecd38d383e396243831ab81feb109c41` |
| `robotocondensed-OFL.txt` | License (OFL 1.1) | Roboto Condensed license text | `0e4cc6ece88573545be2ed25835363662a6182ba4a4c1b5c8feda52add30e8a6` |

Both families are published under the SIL Open Font License 1.1. The
packaged font and license copies come from the objective's pinned asset
reservation, which carries the recorded Google Fonts provenance
(`google/fonts` revision
`6e8069ff8ba3dab2a397fb30e7fbd243aba9b57a`). The `@font-face` rules are
packaged with the stylesheet, so the admin pages never depend on a public
font CDN.

## Shared shell

Every admin browser template renders the same shared shell:

- **Header**: the SLAIF brand lockup (wide logo with packaged fallback,
  honoring the operator branding slots), and, for signed-in sessions, a
  section navigation with fourteen links (Dashboard, Keys, Owners,
  Institutions, Cohorts, Providers, Routes, Pricing, Templates, FX, Usage,
  Audit, Email, OpenAI). The active section carries `aria-current="page"`.
- **Compact keyboard menu**: below 768px, when JavaScript is available,
  the section navigation collapses behind a Menu button. The button is
  keyboard-operable, exposes `aria-expanded`, closes on Escape with focus
  returned to the button, and closes when a link is chosen.
- **No-JS behavior**: without JavaScript the `nav-ready` class is never
  added, so the navigation stays a plain wrapping list that remains visible
  and usable at all viewports; the Menu button stays hidden.
- **Skip link**: a visually hidden "Skip to content" link targets
  `#admin-main` for keyboard users.
- **Footer**: the SLAIF API Gateway identity band.

Breakpoints: 960px (form/filter grids relax), 640px (headers, filter bars,
and form grids collapse to single columns), 480px (the branding compact
logo slot becomes active where provided).

### Labeled table regions

Data tables are wrapped in a named, keyboard-focusable scroll region
(`<div class="table-wrap" role="region" tabindex="0" aria-label="…">`).
The label names the data set (for example "Gateway keys"), the region is
the keyboard-focusable scroll surface for wide tables, and the native
`<table>` markup itself is unchanged.

### Error surfaces

Admin HTML routes that fail with 400/404/503 render a branded standalone
error page (status line, status text, the exact pre-existing message, and a
return link to the admin console). Unauthenticated visitors still redirect
to login instead of seeing an error page. The `/v1` JSON error contract is
untouched: machine clients still receive OpenAI-shaped JSON errors.

## Operator branding relationship

The optional operator branding overlay (see [Operator
branding](branding.md)) is unchanged: the same slots (`style.css`, `logo`,
`logo-compact`, `favicon`, `hero`), the same strict validation and
fallback behavior, and the same "presentation only" boundary. The operator
stylesheet loads after the packaged stylesheet and can retoken the whole
shell; the packaged theme above is what renders when no valid overlay is
supplied. The visual design objective completes the shared visible header
and lockup across all admin templates; the hero slot remains login-page
only.

## Verification

Dated native-browser and unit evidence for this design, including the
default and alternate theme checks, viewports, and the real-vs-mocked
qualification boundary, is recorded in
[SLAIF visual design verification](verification/slaif-visual-design.md).
