# OAP 224-i — immutable final report (report-only SELF)

* Objective: 224 (demo web), PR #383 `oap/224-demo-web` (AMEND_EXISTING_PR).
* Order: `oap/orders/224-i-core-forms-and-routes-read-pages.md`,
  SHA256 `ff823500871c94b68f3d8b8c679ab0efdda9e680e17841030a7812dad9205fcc`
  (identifier-only first line, as required by the unchanged governance test).
* Activation commit: `c65495cc` (order + `oap/active=224-i`).
* Implementation commit (sole parent of this SELF): `8f677b99`,
  tree `c9d05e66cf19e66402ce5b0acdd0544a0d1c9b1d`.
* This report is the sole diff of the SELF commit; no other file changes.

## 1. What this round implemented (bounded 224-i scope)

The closed 224-e/224-f default-deny demo gate admits, for GET/HEAD only,
one more CLOSED set of EXISTING read pages, each handler source-audited to
need only the verified copy, fixed packaged data and safe demo display
settings (copy-bound DB reads through the request-local sessionmaker; no
ambient files, no provider credentials, no source/owner DB, no provider
call, no GET-time mutation):

* `/admin/routes` list and `/admin/routes/{uuid}` detail (canonical
  lowercase 8-4-4-4-12 UUID, exactly one trailing segment);
* the twelve fixed core form GETs: `/admin/keys/create`,
  `/admin/keys/bulk-import`, `/admin/owners/new`,
  `/admin/institutions/new`, `/admin/cohorts/new`,
  `/admin/providers/new`, `/admin/routes/new`, `/admin/routes/import`,
  `/admin/pricing/new`, `/admin/pricing/import`, `/admin/fx/new`,
  `/admin/fx/import`;
* the seven canonical-UUID edit forms
  `/admin/{owners,institutions,cohorts,providers,routes,pricing,fx}/{uuid}/edit`
  (keys and templates have NO edit forms and stay 404);
* `/admin/providers/{uuid}/discover` as a read-only FORM GET (its POST
  preview remains the uniform 204 no-op).

Positive shapes only — no prefix or arbitrary-suffix passthrough; unknown,
extra-segment, malformed or action GETs stay 404. Every form's POST/PUT/
PATCH/DELETE handlers remain cut to the uniform quiet 204 no-op BEFORE
routing and body parsing (demo sign-out remains the sole explicit
exception).

Demo-mode presentation (normal administrator rendering unchanged):

* the demo nav gains `Routes` between Providers and Pricing (thirteen
  sections, matching the normal nav order);
* the create/import/edit links the 224-f/g demo conditionals hid (their
  targets were 404 then) are shown again in demo mode now that the targets
  are admitted; links whose targets stay gated (key batch, reports,
  operations) remain hidden;
* the four data-ingest forms (key bulk-import; routes/pricing/FX import
  preview) carry one concise local no-op hint above the preview submit, on
  top of the persistent banner (the strategic review narrowed the hint set
  from every form template to the ingest forms);
* route detail in demo mode: the still-404 "Reviewed configuration change"
  and "Codex compatibility" links are hidden; `render_codex_profile` is
  skipped ENTIRELY (unit-asserted never called) and a one-line read-only
  hint replaces the artifact block — the demo host cannot forward `/v1`,
  so a profile built from the neutral `localhost:8000/v1` base URL would be
  misleading; the inline TOML blocks are not rendered in demo mode;
* the routes list uses the shared `rows_shown_label` helper
  (singular/plural: "1 row shown").

The three genuinely unused 224-g declarations `_DEMO_RUN_ID_RE`,
`_DEMO_JOB_ID_RE`, `_DEMO_UPLOAD_BASENAME` were removed from
`services/demo_web_worker.py`; the closed per-copy display-name law
(`_DEMO_RUN`/`_DEMO_JOB`/preset/brand-slot components) is unchanged.

## 2. Diff scope (implementation commit `8f677b99`, 26 files)

* `app/slaif_gateway/api/demo_admin_gate.py` — admission law
  (`ADMITTED_FORM_PATHS`, `ADMITTED_EDIT_FAMILY_PREFIXES`, routes in the
  list/detail closed sets, discover branch, comment/docstring updates).
* `app/slaif_gateway/api/admin.py` — demo nav (Routes) and the
  route-detail demo codex-artifact skip.
* `app/slaif_gateway/services/demo_web_worker.py` — the three unused
  declarations only.
* 20 directly affected core templates: link re-shows for newly admitted
  targets (keys/institutions/owners/cohorts/providers/pricing/fx
  list+detail, dashboard create link), the four ingest-form hints, and
  `routes/detail.html` / `routes/list.html` demo-safe presentation and
  row label.
* `tests/unit/test_demo_web.py`,
  `tests/integration/test_demo_web_admin_gate_postgres.py`,
  `docs/demo-admin.md`.

No settings/CLI, no schema/migration, no file-display reader expansion, no
body downloads, no admission of the still-gated families. No
source/ordinary DB, provider adapter, `/v1`, Compose/Nginx or production
file-mount changes.

## 3. Verification (all local, venv, `-p no:warnings`)

| Check | Result |
| --- | --- |
| `tests/unit/test_demo_web.py` | 106 passed (was 104; +2 new tests) |
| `tests/unit/test_oap_governance.py` (UNCHANGED, vs active 224-i) | 9 passed |
| `tests/unit/test_demo_web_worker.py` | 59 passed |
| `tests/unit/test_admin_usability_inventory.py` | 126 passed |
| `tests/unit/test_documentation_inventory.py` | 16 passed |
| Owned PG 16 e2e `test_e2e_admin_gate_two_sessions_distinct_copies` | 1 passed |
| Real-Chromium `test_browser_smoke_demo_copy_pages` | 1 passed |
| Scoped Ruff (repo policy E4/E7/E9/F) on the 5 changed Python files | clean |
| `git diff --check` | clean |
| Protected untracked `CODEX-SESSIONS.md` / `codex.sh` / `uv.lock` | hashes unchanged (`5ae1d77c…` / `66eda802…` / `d3d0e80d…`), still untracked |

Synthetic/mocked vs real: the unit gate tests exercise the real gate and
templates against a fake facade (no DB); the unit codex-skip test drives
the REAL `admin_route_detail` handler with a monkeypatched service scope
and an explode-if-called `render_codex_profile`. The PG e2e and browser
smoke run on the owned PostgreSQL 16 pair with the REAL worker chain
(221/222/223), the REAL reader role, real logins and two concurrent
sessions on distinct copies.

New/updated focused evidence:

* Admission law: every 224-i positive shape 303 (admitted, no session);
  unknown/extra/malformed/action GETs 404; keys/templates edits denied;
  edit middle-segment UUID variants (uppercase, no-dash, trailing slash,
  extra segment) denied; discover only on providers.
* No-store: an admitted form GET (`/admin/keys/create`) carries
  `private, no-store` through the central guard.
* Demo nav: thirteen sections including Routes; normal rendering keeps the
  full nav, no banner.
* Route detail (unit): demo HTML carries the hint and NO
  `localhost:8000` URL, NO `codex-profile` download links, NO artifact
  section and NO profile TOML; `render_codex_profile` is asserted never
  called in demo mode; normal mode still renders links + TOML.
* Owned PG (real reader role, two sessions, distinct copies): routes list
  rendered row count equals the copied `model_routes` count; route detail
  renders 200 with banner/no-store and shows the COPIED fictionalized
  provider `base_url`/`api_key_env_var` (joined source/copy on the
  preserved provider slug; row ID remapped and URL/env-name asserted to
  differ) with the raw SOURCE URL/env-name ABSENT; all twelve form GETs,
  all seven edit forms and the discover form render 200/no-store; the
  still-gated GETs (keys/templates edit, route configuration,
  codex-profile download, exports, operations, reports) stay 404; the
  whole read/POST/logout phase leaves the source and BOTH copies
  unchanged (`model_routes` added to the invariance set); sign-out,
  wrong-CSRf refusal and the distinct-copy (marker) proofs are unchanged
  from 224-e/f evidence and re-passed in this run.
* Real Chromium: the new Routes nav link is visible and follows to the
  list (ephemeral desktop-layout screenshot saved to a run-owned /tmp
  path: `/tmp/slaif-224i-browser-routes-699733-8545bba413.png` — never
  committed, not in ordinary application logs); a route detail row opens;
  the cohorts create form renders and its operational submit returns the
  quiet 204 no-op with the rendered cohort row count unchanged; banner,
  packaged CSS/JS, sorting and CSRF sign-out re-passed.

## 4. Hosted CI and review state (honest)

* 224-h exact head (`1dd60875`), run 43449802443 — terminal: ONE FAILURE,
  `Unit, lint, and migration head` (NOT CodeQL), failed solely at
  `tests/unit/test_oap_governance.py::test_active_identifier_resolves_exactly_one_matching_order`:
  the immutable root-authored 224-h order's first line carries the
  `: close verified display-publication gaps` title suffix while the test
  requires the identifier alone. The other CI jobs all SUCCESS
  (PostgreSQL integration tests completed SUCCESS; E2E, browser, docs,
  Compose, CodeQL-side checks green). The test reads ONLY the CURRENT
  active order; this identifier-only 224-i order recovers it — proven
  locally 9/9 (section 3) and expected green at this head.
* 224-g CI correction (this report only; the immutable 224-h report is
  not amended): the 224-h report's "6 of 7 jobs SUCCESS" for the 224-g
  head (`434b5143`) is a miscount — it counted the separate CodeQL
  umbrella check as a CI job. The actual CI workflow run 43438704480 had
  SIX jobs: FIVE successful (OpenAI-compatible E2E, Documentation
  hygiene, Playwright browser smoke, PostgreSQL integration, Docker
  Compose smoke) and ONE failed job named "Unit, lint, and migration
  head" (55 expected vs 56 sortable-table inventory; 7714 passed, 1
  skipped) — the direct fixture correction landed in 224-h. The
  separate CodeQL workflows (umbrella + python/javascript analyses) were
  SUCCESS. No CodeQL check failed at either head.
* Review threads: three unresolved `github-code-quality` threads on PR383
  are the true 224-g findings — unused globals `_DEMO_RUN_ID_RE`,
  `_DEMO_JOB_ID_RE`, `_DEMO_UPLOAD_BASENAME` in
  `services/demo_web_worker.py`. All three declarations are removed by
  this diff; root resolves the threads after confirming the final diff.
  No other unresolved threads are introduced by this round's diff.
* PR #383 remains OPEN, base `d3762e51`; the coding agent never merges.

## 5. Process note (accuracy, self-reported)

During preparation, a `git add -A` briefly staged the protected untracked
files `CODEX-SESSIONS.md`, `codex.sh`, `uv.lock`. They were reset from the
index IMMEDIATELY and BEFORE the implementation commit; commit `8f677b99`
excludes them (root independently verified) and their SHA256 values are
unchanged; they were never pushed or otherwise exposed. This violated the
order's "never stage" process instruction even though corrected in time.
The report-only SELF commit was staged with an explicit path only.

## 6. Docs and limitations

`docs/demo-admin.md` documents the 224-i coverage, form semantics,
route-detail demo-safe presentation, the remaining 404 families, and the
evidence above.

Limitations: the demo stage remains INCOMPLETE — operations (all
subpaths), reports, catalog, compatibility, branding, process-configuration,
OpenAI-assisted, accounts, key batch/clone (incl. keys/templates edit
forms), route configuration-change and codex-profile downloads, exports,
and all file-backed admin panels stay default-denied/unmounted (panel
wiring is a later 224 suffix on top of the 224-g publication). The demo
remains default-off and NOT usable for company demonstrations; objective
225 is the installed acceptance gate. No TLS guarantee for the demo
transport; no new OAP signal, branch, PR, merge or release.
