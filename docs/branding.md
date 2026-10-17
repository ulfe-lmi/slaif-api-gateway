# Operator branding (optional, same image, no rebuild)

> **Status:** Current — implemented in the admin web surface
> **Audience:** Operators deploying SLAIF API Gateway
> **Boundary:** RC-beta; branding is presentation only, not a permission change

Appearance overrides are optional and off by default. Operators can supply
local CSS and images through a read-only directory without rebuilding the
application image.

## What it changes

The packaged SLAIF identity remains the default on every browser surface.
When enabled, an operator directory may supply, per slot, at most one file
that replaces the corresponding default:

| Slot | File names (one per slot) | Formats | Max size | Where it appears |
|------|---------------------------|---------|----------|------------------|
| `style.css` | `style.css` | CSS (strict UTF-8) | 256 KiB | Loaded AFTER the built-in admin stylesheet on every admin browser template |
| `logo` | `logo.svg` / `logo.png` | inert image | 256 KiB | Wide-viewport lockup in the shared header on all admin browser pages |
| `logo-compact` | `logo-compact.svg` / `logo-compact.png` | inert image | 256 KiB | Shared header on all admin browser pages on narrow viewports (≤ 480 px), replacing the wide lockup |
| `favicon` | `favicon.svg` / `favicon.png` | inert image | 256 KiB | Browser tab icon on all admin browser templates |
| `hero` | `hero.svg` / `hero.png` | inert image | 256 KiB | Top of the admin login page only |

Slots are fixed: there is no request-selected file name, no directory
listing, and no way to address a path. Unknown files in the directory are
ignored. Two files for the same slot are ambiguous: that slot falls back
(closed failure), and the other slots are unaffected.

Branding assets are available before login. Keep credentials and private
data out of this directory.

The product identity remains **SLAIF API Gateway** on all surfaces;
branding changes imagery and presentation only.

### Current logo-bearing surfaces

Since Objective 188, every admin browser template renders the shared
header lockup: the admin **login** page and all signed-in pages
(dashboard, keys, owners, institutions, cohorts, providers, routes,
pricing, templates, FX, usage, audit, email delivery, and
OpenAI-assisted) carry the same header with the brand lockup and section
navigation. The wide/compact logo slots and the packaged fallback apply
on those surfaces; on narrow viewports (≤ 480 px) a valid
`logo-compact` slot replaces the wide lockup. The login hero slot
applies to the admin login page only; when branding is disabled or the
hero slot is invalid, the login page keeps its packaged layout (no hero
element is rendered).

See [SLAIF visual design](visual-design.md) for the packaged theme these
surfaces render when no valid operator overlay is supplied.

## Enabling it

The application reads the `SLAIF_BRANDING_DIR` environment variable
(default: unset or blank = disabled). The shipped overlay
(`docker-compose.branding.yml`) adds it together with a bounded read-only
mount of the existing `api` service — no rebuild, no new service, network,
port, database, proxy, privilege, or runtime change:

```bash
install -d -m 755 deploy/branding
# add at most one file per slot (see the table above)

# local development:
docker compose -f docker-compose.yml -f docker-compose.branding.yml up -d

# production-shaped deployment:
docker compose -f docker-compose.production.yml -f docker-compose.branding.yml up -d
```

The overlay sets `SLAIF_BRANDING_DIR=/branding` and mounts
`./deploy/branding:/branding:ro`.

**Preserve your existing project identity.** If your stack was started
with an explicit Compose project name (`-p` / `COMPOSE_PROJECT_NAME`),
profiles, or an env file, pass the same values when adding this overlay;
the examples above assume the default project name and can launch a
different project for installs that used `-p`.

- **Precreate the directory** before starting the stack; the application
  never creates, replaces, or deletes it.
- **Permissions:** the directory must be readable by the application user
  (the `slaif` user in the image). In the production compose the api
  container starts as root and drops privileges, so the host directory must
  be world- or group-readable accordingly.
- **Public assets only:** the mount is served over HTTP before login. Never
  place credentials, keys, exports, or private data in `deploy/branding`.

## Refresh and cache semantics

- **Server side:** each request re-stats the directory and the slot file;
  every slot is read and validated again without an operator-asset cache.
  Content changes are picked up even when size and modification time stay
  the same. Editing or replacing a file takes effect on the next page load;
  no container restart, rebuild, or re-deploy is required (and restarting
  the same image is harmless).
- **Browser side:** `/admin/branding/*` responses carry `Cache-Control:
  no-cache`, so the browser revalidates on every navigation; a plain page
  reload shows updated assets without a hard refresh.
- **Static defaults:** packaged assets (including the fallback logo) are
  served by the normal static pipeline and cache as usual.

## Fallback and failure behavior

- **Disabled, missing directory, empty directory, absent slot file, or
  invalid file:** that slot uses the packaged default — the override
  stylesheet link is simply not emitted, and image slots fall back to the
  packaged logo. One invalid asset never breaks login, administration, or
  any other slot.
- **`/admin/branding/*` endpoints are total:** they return the override
  bytes when the slot is currently valid and the packaged fallback
  otherwise (empty stylesheet for `style.css`, the packaged logo for image
  slots). They never return 404 or 500 for a registered slot, so a page
  that referenced an override at render time never shows a broken
  subresource even if the file disappears before the subresource request.
  Unregistered paths keep the normal 404 behavior.
- Rejections are silent: no file path or content is logged or rendered in
  errors.

## Security boundaries

Overrides are **trusted operator inputs only** — they are never uploads and
never derived from private data. The mechanism enforces:

- **Directory:** must be a real directory (a symlinked directory is
  refused). Only single-level, fixed slot file names are ever opened.
- **File access:** every directory component is opened with no-follow
  semantics from the filesystem root. Files are opened relative to the
  verified directory descriptor, with `O_NOFOLLOW` and non-blocking mode.
  Only regular files within the size limit are read. File identity is
  checked before and after the bounded read; changes and I/O failures fall
  back safely. A directory swap cannot redirect a read, and a FIFO swap
  cannot block an application worker.
- **Image formats:** PNG must be non-interlaced, 8-bit RGB/RGBA with
  complete chunk framing, checksums, and valid bounded scanlines (at most
  1,048,576 pixels and 4096 pixels in either dimension). Ancillary PNG
  chunks, palette/grayscale modes, JPEG, and WebP are not supported; export
  a plain RGB/RGBA PNG or use SVG. SVG must be a well-formed, **static,
  inert** document: only an allowlist of geometry/paint/text elements and
  attributes (plus `data-*`), the SVG namespace only, at most 32 levels and
  2048 nodes, no processing instructions, DOCTYPE, or comments, no scripts,
  no event handlers, no `<image>`, `<use>`, `<a>`, `<style>`, filters, or
  animation, no `xlink:href`, no remote or `data:` references, and `url()`
  limited to local `#fragment` gradient/clip references. HTML, active SVG,
  and unknown MIME content are rejected.
- **CSS:** strict UTF-8 without backslash escapes or malformed comments.
  Imports, resource functions (`url`, `image-set`, `image`, `src`), data
  URIs, and active content are rejected, including comment/whitespace
  variants. Ordinary selectors, CSS variables, and media rules remain
  available. Branding images use the fixed slots rather than CSS resource
  URLs.
- **Responses:** correct `Content-Type` per slot plus
  `X-Content-Type-Options: nosniff`; no server-side template or code
  execution is involved in serving an override.
- **No rights, no state:** requesting a branding asset grants no
  authentication, writes no session, and is not audited. Existing
  authentication, CSRF, quota, accounting, audit, and provider-credential
  behavior is unchanged.

## Limits and troubleshooting

- Max 256 KiB per file; five slots (≤ 1.25 MiB total) per deployment.
- The branding mount is read-only with both Compose files; the application
  cannot write to it.
- If a slot silently keeps its default, the file was rejected: check the
  name (exact slot + allowed extension), that only one file uses that slot,
  the format (the SVG and PNG rules above are strict), the size, and that
  it is a regular file (not a symlink or special file). No rejection detail
  is intentionally logged.
- The favicon should be square and small (16–64 px) for predictable tab
  rendering; the logo should be legible at the header height; the hero
  scales to a 18rem maximum width with its own aspect ratio.
- Operator CSS can alter the presentation of admin pages (colors, spacing,
  typography) but cannot change form actions, authentication, or data.

## Packaged logo

- File: `app/slaif_gateway/web/static/img/slaif-logo.svg` (7,351 bytes)
- SHA-256: `0760613aca18ace80d559686e98ec640f9f85caa163c5338c28e73b57b9c7a08`
- The SVG source contains no scripts, external or remote references, or
  embedded raster payloads — only vector identity-mark geometry.

The file is served as a local static asset; no browser surface hotlinks the
logo at runtime.

## Code provenance

The content validators (`css_is_valid`, `svg_is_valid`, `png_is_valid`) and
the bounded no-follow directory reader in `app/slaif_gateway/web/branding.py`
and `app/slaif_gateway/web/branding_png.py` are adapted from the SLAIF Asset
Reservation repository, pinned revision
`dad6e29d4f8e4fd941843b230474d35dafb69d1a`, published under the Apache
License 2.0. That reference is the basis for the format rules above; this
repository preserves the attribution and adds no new decoder or
filesystem framework.
