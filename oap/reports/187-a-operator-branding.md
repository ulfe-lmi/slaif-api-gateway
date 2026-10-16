# OAP Execution Report — Objective 187-a: operator branding parity

Report status: IMMUTABLE (finalized at the exact implementation head
`2f86d78c23d386e1e1227bf271641b60d3158cc0`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first parent =
this implementation head; only this report path differs).

- Implementation head SHA: 2f86d78c23d386e1e1227bf271641b60d3158cc0
- Report publication commit: SELF

## 1. Work order and PR identity

- Work order: `oap/orders/187-a-operator-branding.md` (strategic-authored;
  committed unchanged by the activation commit); `oap/active` = `187-a`.
- PR: #325 `feat: add operator branding overrides` — the unique 187 PR
  (CREATE_NEW_PR):
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/325.
- Branch: `oap/187-operator-branding`.
- Base: `main` at `de75744f2c5a518a513a49a7b34582c87c5bbcbf` (186 merge).
- Activation commit: `849f873` (order + `oap/active` bytes unchanged).
- Commit chain on the branch: `de75744f` (base) → `849f873` (activation)
  → `abae4ed` (runtime: config, bounded reader, fixed asset routes,
  template integration) → `2f86d78` (tests, fixtures, overlay, docs, and
  the mobile default-logo fix).

## 2. What was implemented (R1–R6)

- R1: optional `SLAIF_BRANDING_DIR` (unset/blank = disabled); five fixed
  slots (`style.css`; `logo`, `logo-compact`, `favicon`, `hero` as
  `.svg`/`.png`), 256 KiB per file; unknown files ignored; ambiguous
  same-slot pairs fall back per slot. Same image, no rebuild.
- R2: five total public-before-login fixed routes
  `/admin/branding/{style.css,logo,logo-compact,favicon,hero}` serving
  valid override bytes or the packaged fallback (empty stylesheet /
  packaged logo); correct `Content-Type`, `Cache-Control: no-cache`,
  `X-Content-Type-Options: nosniff`; no authentication rights, session
  writes, or state; unregistered paths keep normal 404; `/v1` JSON/auth/
  error semantics unchanged.
- R3: per-request re-read/revalidation with no operator-asset cache
  (same-size/same-mtime replacements picked up); render-time discovery
  plus asset-time fallback; operator CSS loaded AFTER the packaged admin
  stylesheet on every admin browser template; wide logo with the compact
  replacement selected at the ≤480px breakpoint (scoped to
  `.branding-active` lockups so disabled deployments keep their packaged
  logo at every width); favicon on all browser templates with the
  packaged fallback always present; hero on the admin login page only
  (disabled/invalid hero keeps the current packaged login layout, no hero
  element).
- R4: reader security parity with the pinned reference — real (non-
  symlinked) directory, anchored no-follow component walk, `O_NOFOLLOW`/
  nonblocking regular-file reads, 256 KiB bounded reads, before/after
  identity checks, all FDs closed; symlink/root-swap/FIFO/IO-failure
  fallback without blocking workers; no directory creation/write/delete.
- R5: strict stdlib-only content validation — escape-free UTF-8 CSS
  without imports/resource functions/remote/data content; inert
  namespace-aware SVG allowlist (bounded depth/nodes/attrs, no
  scripts/events/remote refs); complete-framing CRC-validated
  noninterlaced 8-bit RGB/RGBA PNG (≤4096 per dimension, ≤1,048,576
  pixels, bounded zlib). No Pillow, no new decoder, no library.
- R6: `docker-compose.branding.yml` adds ONLY `SLAIF_BRANDING_DIR=/branding`
  and `./deploy/branding:/branding:ro` to the existing `api` service;
  verified merge on both development and production bases.

## 3. Exact paths changed (all within the order's permitted list)

- `app/slaif_gateway/config.py` — `SLAIF_BRANDING_DIR` setting only.
- `app/slaif_gateway/main.py` — branding router registration only
  (registered before the admin router).
- `app/slaif_gateway/api/branding.py` — new fixed routes.
- `app/slaif_gateway/web/branding.py`, `app/slaif_gateway/web/branding_png.py`
  — new shared validators/reader (adapted, Apache-2.0, see §7).
- `app/slaif_gateway/api/admin.py` — `_branding_context` context processor
  + `Jinja2Templates(context_processors=[...])` wiring only.
- `app/slaif_gateway/web/templates/_brand.html`, `base.html`, `login.html`,
  `dashboard.html` — presentation macro/hero/context integration; forms,
  actions, CSRF, and semantics retained.
- `app/slaif_gateway/web/static/css/admin.css` — minimal slot layout
  (`.brand-logo-compact`, scoped ≤480px switch, `.auth-hero`).
- `docker-compose.branding.yml` (new api-service-only overlay),
  `.env.example` (commented setting block), `README.md` (one task-table
  row; top branding untouched).
- Docs: `docs/branding.md` (new contract), `docs/configuration.md`,
  `docs/deployment.md`, `docs/security-model.md`, `INSTALL.md`,
  `docs/README.md` (index), `docs/verification/operator-branding.md`
  (new record) + single index entry in `docs/verification/README.md`.
- Tests: `tests/unit/test_branding.py`, `test_branding_png.py`,
  `test_admin_branding.py`, `test_config.py`,
  `test_production_compose_contract.py`,
  `tests/browser/test_admin_branding.py`,
  `tests/integration/test_branding_container.py`,
  `tests/fixtures/branding/**` (synthetic assets only).
- OAP: `oap/orders/187-a-operator-branding.md` + `oap/active` committed
  unchanged by the activation commit; this report only.
- The existing tracked `slaif-logo.svg` blob is unchanged; no migrations,
  dependencies, workflow, financial, provider, or auth-service changes.

## 4. Verification executed (exact commands and results)

All local runs on the implementation head bytes; venv
`/tmp/slaif-181c-strategic-venv` (Python 3.12), command-scoped
`LD_LIBRARY_PATH=/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/
x86_64-linux-gnu` for Chromium.

- Focused unit suites (one run): `pytest tests/unit/test_branding.py
  tests/unit/test_branding_png.py tests/unit/test_admin_branding.py
  tests/unit/test_config.py tests/unit/test_production_compose_contract.py
  tests/unit/test_documentation_inventory.py
  tests/unit/test_documentation_asof.py tests/unit/test_product_scope_docs.py
  -o addopts= -q` → 148 passed. Per-file: reader FD I/O 24; PNG framing 15;
  render-level 11 (6 new + 5 inherited packaged-logo); config 54 total
  (+2 new); compose contract 14 total (+1 new); documentation gates 30
  across the three doc test files.
- `scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=95`.
- `ruff check` on all changed Python → clean; `git diff --check` → clean.
- Browser (V2): `pytest tests/browser/test_admin_branding.py -o addopts= -q`
  → 3 passed (16.8s) with a real owned labeled loopback/tmpfs PostgreSQL
  per module run and explicit synthetic secrets: disabled defaults at
  1440×900 and computed visibility at 375px; all five slots with computed
  CSS/wide-compact selection, exact served bytes, and one actual
  authenticated owner-create mutation verified durable in PostgreSQL plus
  bad-CSRF refusal with state unchanged; live refresh including
  same-size/same-mtime and per-slot fallback. Observed and recorded: this
  headless engine did not issue the automatic favicon request
  (`FAVICON_AUTOMATIC_FETCH=false`); favicon integration is covered by the
  DOM link href/type plus explicit MIME/bytes/fallback checks. One
  pre-existing Alembic `path_separator` deprecation warning (unrelated).
- Container (V3): `pytest tests/integration/test_branding_container.py
  -o addopts= -q -s` — 4 passed. Strategic independent foreground
  rerun of the corrected fixture: 4/4 PASS in 87.2s
  (`independent-container-final.xml`); identity/cleanup record
  (`independent-container-identity.json`): nonroot `slaif` user, owner
  `slaif187a-072ae70721ab138e`, loopback host port 32941, exact created
  container `f1d4e9953af7...` and image `sha256:b1db1f8c9204...`, both
  removed by exact ID, post-teardown query confirmed both absent. Test-only
  bootstrap (synthetic `Settings`, uvicorn `lifespan="off"`, no DB/
  provider); image, container, read-only bind, and HTTP responses real.
- Compose merge (local evidence, not a unit test), exact command:
  `docker compose -f docker-compose.yml -f docker-compose.branding.yml
  --env-file /dev/null --no-env-resolution --no-interpolate config` (and
  the production-base equivalent): only the `api` service gains
  `SLAIF_BRANDING_DIR=/branding` plus the one `:ro` bind; all other
  services/networks/ports/secrets unchanged
  (`independent-compose-merge.json`).
- No provider/model/email/protected-credential access anywhere in this
  objective. No skip was treated as a pass. Full record with real-vs-
  mocked mapping: `docs/verification/operator-branding.md`.

## 5. GitHub CI state at publication (run 38980771822, head 2f86d78)

- PASS (8): Analyze (python), Analyze (javascript-typescript), CodeQL,
  Documentation hygiene, Docker Compose smoke, OpenAI-compatible E2E
  tests, Playwright browser smoke, Analyze Python.
- FAIL (1): `Unit, lint, and migration head` with exactly two failures:
  1. `tests/unit/test_oap_governance.py::test_active_identifier_resolves_
     exactly_one_matching_order` — the activated order's first line is
     `# OAP Work Order — 187-a: operator branding parity`, while the
     root-authored governance test requires exactly
     `# OAP Work Order — 187-a`. Strategic authoring deviation in the
     immutable activated order; per the strategic decision the order bytes
     are preserved as history and the test is not edited or weakened;
     the fix lands in the 187-b continuation on the same PR.
  2. `tests/unit/test_main_app_structure.py::test_main_app_only_wires_app_
     and_routes` — `app/slaif_gateway/main.py` is 72 lines; the
     root-authored structure test requires < 70 (the branding router
     registration added lines). Minimal no-logic trim lands in 187-b.
- PENDING at publication (1): `PostgreSQL integration tests` (still
  running when this report was finalized; preserved in CI history, not
  cancelled).

All final-head checks on the 187-b SELF are required before strategic
review/merge; nothing in this head is claimed green or mergeable.

## 6. Deviations and disclosed decisions

- The activated order's descriptive header suffix caused the governance
  failure above (strategic authoring; preserved as history per decision;
  187-b carries the exact canonical first line plus the minimal main.py
  trim). No coding-agent edit of the order or of the governance/structure
  tests was made.
- The ≤480px logo switch was scoped to `.branding-active` lockups after
  the runtime-checkpoint review found the default (disabled) deployment
  lost its logo on mobile; browser coverage includes the disabled 375px
  computed-visibility guard.
- Overlay/branding docs carry a project-identity note: operators whose
  stack uses an explicit Compose project name/profiles/env file must pass
  the same values when adding the overlay.
- Current logo-bearing surfaces are the admin login and dashboard pages;
  other admin pages share head styling and the favicon. A consistent
  shared header across all admin templates belongs to the later
  visual-design objective (188), not this one.

## 7. Code source attribution

The CSS/SVG validators and the bounded no-follow reader
(`app/slaif_gateway/web/branding.py`) and the PNG validator
(`app/slaif_gateway/web/branding_png.py`) are adapted from the SLAIF Asset
Reservation repository, pinned revision
`dad6e29d4f8e4fd941843b230474d35dafb69d1a`, published under the Apache
License 2.0; attribution is preserved in code docstrings and in
`docs/branding.md`.

## 8. Limitations and pending state

- The final-head check set is NOT all green at this head (see §5); the
  head is not mergeable as-is.
- Pending: the 187-b continuation on the same PR #325 (exact canonical
  order first line + minimal main.py trim), all final-head checks on the
  187-b SELF, strategic review, and the guarded merge. No release/tag,
  production, certification, or accounting guarantee is claimed.
- The headless Chromium favicon non-fetch observation is an engine
  behavior, not a product defect (explicit checks cover the routes).
