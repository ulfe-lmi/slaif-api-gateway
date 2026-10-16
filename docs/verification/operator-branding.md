# Operator Branding Verification

> **Status:** Current objective 187-a verification record
> **Boundary:** Focused real-boundary evidence plus final-head GitHub CI; no broad local matrix is claimed

## Scope verified in this objective

- Optional `SLAIF_BRANDING_DIR` (unset/blank = disabled) with five fixed
  slots (`style.css`; `logo`, `logo-compact`, `favicon`, `hero` as
  `.svg`/`.png`), 256 KiB per file, unknown files ignored, ambiguous
  same-slot pairs falling back per slot.
- Five total public-before-login routes
  `/admin/branding/{style.css,logo,logo-compact,favicon,hero}` serving
  valid override bytes or the packaged fallback (empty stylesheet /
  packaged logo), with `Cache-Control: no-cache` and
  `X-Content-Type-Options: nosniff`; no authentication rights, session
  writes, or state from asset requests; unregistered paths keep normal
  404; `/v1` JSON/auth semantics unchanged.
- Render integration via a shared Jinja context processor resolved from
  each application instance's settings (isolated `create_app` instances):
  operator CSS loaded AFTER the packaged admin stylesheet on every admin
  browser template; wide logo with the compact replacement selected at the
  ≤ 480px breakpoint; favicon on all browser templates (packaged fallback
  always present); hero on the admin login page only (disabled/invalid hero
  keeps the current packaged login layout, no hero element).
- Live refresh: per-request re-read/revalidation with no operator-asset
  cache; same-size/same-mtime replacements picked up; per-slot fallback on
  removal/invalidity.
- Reader security parity with the pinned reference: no-follow anchored
  directory walk, `O_NOFOLLOW`/nonblocking regular-file reads, 256 KiB
  bounded reads, before/after identity checks, all FDs closed;
  symlink/root-swap/FIFO/IO-failure fallback without blocking workers.
- Strict stdlib-only content validation: escape-free UTF-8 CSS without
  imports/resource functions/remote/data content; inert namespace-aware
  SVG allowlist (bounded depth/nodes/attrs, no scripts/events/remote
  refs); complete-framing CRC-validated noninterlaced 8-bit RGB/RGBA PNG
  (≤ 4096 per dimension, ≤ 1,048,576 pixels, bounded zlib).
- Compose overlay (`docker-compose.branding.yml`): adds ONLY
  `SLAIF_BRANDING_DIR=/branding` and the `./deploy/branding:/branding:ro`
  bind to the existing `api` service, merging on both development and
  production bases.

## Newly executed evidence (objective 187-a)

### Unit: real temporary files and real FD I/O (V1)

- `tests/unit/test_branding.py` — 24 PASS: disabled/missing/valid/
  per-slot/ambiguous/unknown slots; all five routes with fallback bytes,
  MIME, `no-cache`, `nosniff`; exact override bytes; CSS exact-cap;
  symlink file/directory/ancestor; root-swap; FIFO swap with bounded
  real child-process evidence (nonblocking opens asserted); read-error
  isolation; identity-change fallback; no FD leak (±2 descriptors over
  200 resolutions); same-size/same-mtime revalidation; removed-after-
  render fallback; traversal and foreign-name non-leak; two separately
  created app instances stay isolated; `/v1` JSON error contract
  unchanged.
- `tests/unit/test_branding_png.py` — 15 PASS: RGB/RGBA positives,
  boundary dimensions/pixels, and single-mutation negatives (bad
  signature/truncation, second/misplaced IHDR, bad CRC, CRC-valid
  unknown ancillary chunk, IDAT before IHDR, IDAT after IEND, IEND with
  payload/trailing bytes, invalid scanline filter, short/long scanlines,
  trailing compressed bytes, 16-bit, interlaced, oversized), plus
  multi-IDAT concatenation acceptance. Each negative mutates exactly one
  named condition of a verified-valid control.
- `tests/unit/test_admin_branding.py` — 11 PASS (5 inherited packaged-
  logo render tests + 6 new): disabled default markup exact; enabled all-
  override markup with CSS-after-packaged ordering; per-slot fallback;
  independent compact fallback; dashboard override render; CSRF error
  page re-render unaffected by branding.
- `tests/unit/test_config.py` — +2 (setting defaults blank/disabled; env
  loading; blank means disabled at the settings level); 54 PASS total.
- `tests/unit/test_production_compose_contract.py` — +1 static overlay
  contract (exactly one `api` service, exactly the one env entry and one
  `:ro` bind, no other deltas); 14 PASS total.
- Documentation gates: `test_documentation_inventory` (all settings
  named, 13 PASS), `test_documentation_asof`, `test_product_scope_docs`
  PASS; `scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK
  files=95`; `ruff check` clean on all changed Python; `git diff
  --check` clean.

### Browser: native Chromium, actual owned PostgreSQL, real app (V2)

`tests/browser/test_admin_branding.py` — 3 PASS (one fresh owned labeled
loopback/tmpfs PostgreSQL per module run, exact-ID cleanup; explicit
synthetic HMAC/one-time/session secrets; no ambient environment):

1. `test_admin_branding_disabled_defaults_and_public_assets` — disabled/
   unset defaults at 1440×900 (packaged logo visible, no compact/hero/
   CSS link, packaged favicon, packaged body background), computed
   visibility of the packaged logo at the 375px mobile breakpoint
   (regression guard for the scoped hide rule), total public asset
   responses (exact fallback bytes, MIME, headers, no `Set-Cookie`,
   unknown slot 404), and CSRF-protected login plus the authenticated
   dashboard.
2. `test_admin_branding_enabled_all_slots_desktop_and_mobile` — all five
   slots with the synthetic `custom` fixture: operator CSS loaded after
   and winning over the packaged stylesheet (computed body/h1 changes),
   wide visible / compact hidden on desktop and the inverse at 375px by
   computed visibility, hero and favicon overrides, served bytes exactly
   equal to the fixture bytes, observed subresource requests, working
   login, and one ACTUAL authenticated admin form mutation (owner
   create) verified durable in PostgreSQL, plus a bad-CSRF attempt
   refused with state unchanged. Favicon note: this headless engine did
   not issue the automatic tab-icon request during the run (recorded,
   not forced); favicon integration is covered by the DOM link
   href/type plus the explicit MIME/bytes/fallback checks.
3. `test_admin_branding_live_refresh_and_fallback` — changed file
   picked up on reload without restart; same-size/same-mtime replacement
   picked up; stylesheet removal restores the packaged default; invalid
   logo falls back per slot while the valid compact PNG override stays.

The module emits one pre-existing Alembic `path_separator` deprecation
warning (unrelated to branding). The three cases were independently
re-verified by the strategic side (all PASS).

### Integration: one owned labeled application container (V3)

`tests/integration/test_branding_container.py` — 4 PASS. One fresh image
built from the repository (owner-labeled at build time), one owned
labeled container (create → record exact ID → start) with the read-only
`/branding` bind, verified nonroot user, loopback-only port publish, and
exact created IDs on both resources. Test-only bootstrap with explicit
synthetic `Settings` and uvicorn `lifespan="off"` (no database engine, no
provider). Real evidence: image build, container, mount, HTTP responses,
and mounted-file updates:

1. `test_container_serves_override_and_renders_login` — override CSS
   bytes + headers (no `Set-Cookie`) and the login page rendering the
   branding lockup/hero/CSS/favicon overrides.
2. `test_container_mounted_update_picked_up_without_restart` — host-side
   file update served by the running container without restart, then
   restored.
3. `test_container_app_cannot_write_mount` — in-container write to the
   read-only mount refused; no file appears host-side.
4. `test_container_invalid_slot_falls_back_to_packaged` — invalid SVG
   falls back to the packaged logo byte-for-byte; the valid compact slot
   is unaffected; the login page shows the packaged fallback src.

Cleanup removes only the exact created container ID (owner label
re-verified before removal; `NotFound` treated as already removed) and
the exact built image ID (owner label re-verified; non-forced removal),
and never touches unrelated containers or images. The strategic side
independently re-ran the module in a foreground tracked session: 4/4
PASS in 87.2s (JUnit: `independent-container-final.xml`); the captured
identity record shows the nonroot `slaif` user, owner
`slaif187a-072ae70721ab138e`, loopback host port 32941, exact created
container `f1d4e9953af7...` and image `sha256:b1db1f8c9204...`, both
removed by exact ID (`removed:f1d4e9953af7` /
`removed:sha256:b1db1f8c9204`), with a post-teardown query confirming
both exact resources absent.

### Deployment compose merge (local evidence, not a unit test)

The exact executed command (and the production-base equivalent with
`docker-compose.production.yml`) is:

```bash
docker compose --env-file /dev/null -p slaif187-review \
    -f docker-compose.yml -f docker-compose.branding.yml \
    config --no-env-resolution --no-interpolate --format json
```

The merged output shows only the `api` service gaining
`SLAIF_BRANDING_DIR=/branding` plus the one `./deploy/branding:/branding:ro`
bind; all other services, networks, ports, secrets, and fields are
unchanged (independent artifact:
`review-artifacts/187-a-review/independent-compose-merge.json`).

## Real vs mocked

- **Real:** Docker image build and container (V3), owned PostgreSQL for
  the browser cases, native Chromium rendering/interaction, all unit FD
  I/O against real temporary filesystems, Compose merge parsing of the
  actual compose files, the packaged logo asset, and every HTTP response
  asserted.
- **Test-only / mocked:** the V3 container bootstrap (synthetic settings,
  lifespan off) and the synthetic key material used to seed one admin
  user. The UNIT render tests in `test_admin_branding.py` additionally use
  the shared `_app`/`_settings` harness of `test_admin_routes` with a fake
  sessionmaker and monkeypatched admin-session/CSRF service methods, so
  their login/dashboard markup assertions do not exercise real
  authentication or a database; the actual authenticated browser proof
  (real login form, real owned PostgreSQL, real session) is the separate
  V2 evidence above. No
  model/provider/email/protected-credential access occurred anywhere in
  this objective.
- No skip was treated as a pass; no live provider, model, or email call
  was made.

## 187-b structural CI closure (same PR, continuation round)

The 187-a final-head unit CI failed exactly two root-authored structural
checks (see the 187-a report, §5), both closed by the 187-b continuation
on the same PR without any executable change:

- `app/slaif_gateway/main.py` is trimmed from 72 to 68 lines by removing
  only explanatory comments and one redundant blank line; router
  registration order, settings, lifespan, middleware, and error-handler
  wiring are untouched. Proof of equivalence against the 187-a
  implementation head `2f86d78` bytes: the normalized AST dump
  (`ast.dump(..., annotate_fields=True, include_attributes=False)`) is
  byte-identical, and for every code object (3 total) the raw instruction
  stream (`co_code`), non-code constants, `co_names`, `co_varnames`, and
  `co_freevars` are identical — only line-number tables moved. The
  focused pair `pytest tests/unit/test_oap_governance.py
  tests/unit/test_main_app_structure.py -o addopts= -q` passes 14/14
  with the existing exact-header and <70 assertions unchanged.
- The activated 187-a order's descriptive header suffix was preserved as
  immutable history (strategic authoring deviation); the 187-b order
  carries the exact canonical first line required by the governance
  check. No governance or structure test was edited or weakened.

All other qualified runtime/browser/container source hashes match
`qualified-source-hashes.json` byte-for-byte (main.py is the only
changed file); the packaged SVG blob, the 187-a order and report, and
all prior evidence remain unchanged.

## Code provenance

`app/slaif_gateway/web/branding.py` (CSS/SVG validation and the bounded
reader) and `app/slaif_gateway/web/branding_png.py` (PNG validation) are
adapted from the SLAIF Asset Reservation repository, pinned revision
`dad6e29d4f8e4fd941843b230474d35dafb69d1a`, Apache License 2.0; see
[Operator branding](../branding.md#code-provenance).

## Limitations and pending state

- The visible logo lockup is currently on the admin login and dashboard
  pages; other admin pages share head styling and the favicon. A
  consistent shared header across all admin templates is a later
  visual-design objective, not this one.
- The headless Chromium favicon non-fetch observation is an engine
  behavior, not a product defect; the favicon routes/links are fully
  covered by explicit checks.
- Final-head GitHub checks on the report (SELF) commit, strategic review,
  and the guarded merge remain pending and are not claimed here.
