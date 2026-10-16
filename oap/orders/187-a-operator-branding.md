# OAP Work Order — 187-a: operator branding parity

## Objective, authority and business reason

Implement the SAME optional operator-branding capabilities as SLAIF Asset
Reservation, adapted to FastAPI/Jinja. Human explicitly requests all stages via
coding agent/OAP and final SLAIF design. This objective delivers full branding
functionality; subsequent188 delivers the packaged SLAIF visual design. Do not
stop at config/helpers: working browser+deployment integration is acceptance.

PR mode: `CREATE_NEW_PR`
Repository: ulfe-lmi/slaif-api-gateway
Base: main at de75744f2c5a518a513a49a7b34582c87c5bbcbf
Branch: oap/187-operator-branding
Title: feat: add operator branding overrides

## Verified state and current contracts

186 PR324 MERGED2026-10-16T18:36:13Z asde75744f. Accepted SELF8167871 firstparent
be8a3bb, reportSHA256e91330604734d6cc584fa5567dc79a4f65c70fce125963131e1e1dfa95767090.
All actual main checks SUCCESS (including later Dependabot check additions).
Only unrelatedDependabot319 open; no187 PR. Ruleset23580289 deletion/nonFF,
no bypass; only releasev0.1.0-rc.1. Local186 SELF, only CODEX-SESSIONS.md/codex.sh
untracked. Preserve these and .codex/.local-provider-catalog/unrelated resources.
Sole coding agent pane%9/PID2075296; existingcontrolwaiter58242 verified.

Read applicable AGENTS hierarchy, coding OAP, compact strategic OAP/architecture,
workorders/BRANDING-EXECUTION-PLAN.md and this order; live configuration/security/
deployment/readme/admin-branding contracts and current tests. No fullarch/archive
load absent concrete unresolved detail. AGENTS preserves README top SLAIF logo
and link; do not change that header or its local asset in this objective.

Reference immutable snapshot:
/home/janezp/codex-supervision/slaif-api-gateway/review-artifacts/branding-reference-dad6e29d
Repository ulfe-lmi/slaif-asset-reservation revisiondad6e29d4f8e4fd941843b230474d35dafb69d1a.
Read docs/branding.md, docs/ux/visual-design.md, pure validation/read code and
reference tests, manifest and LICENSE. Prefer adapting reviewed stdlib validators
and reader rather than inventing broader machinery. Keep attribution/license
notices for reused code; no Django dependency or wholesale test-fixture copy.
Only pinned public reference GET via gh is allowed; no provider/model calls.

## Exact permitted paths

- app/slaif_gateway/config.py (optional SLAIF_BRANDING_DIR setting only)
- app/slaif_gateway/main.py (router registration/context wiring only)
- app/slaif_gateway/api/branding.py (new fixed routes)
- app/slaif_gateway/web/branding.py, branding_png.py (new shared helpers)
- app/slaif_gateway/api/admin.py (template context processor/import wiring only;
  no domain/session/financial/mutation behavior edits)
- app/slaif_gateway/web/templates/**/*.html (branding/context/hero/error-shell
  presentation only, retain forms/actions/CSRF and semantics)
- app/slaif_gateway/web/static/css/admin.css (minimal slot layout only; final
  palette/typography redesign belongs188)
- docker-compose.branding.yml (new api-service-only overlay)
- .env.example
- README.md (one navigation entry, preserve top branding)
- INSTALL.md, docs/README.md, docs/configuration.md, docs/deployment.md,
  docs/security-model.md, docs/branding.md (new)
- tests/unit/test_branding.py, test_branding_png.py (new),
  test_admin_branding.py, test_config.py, test_production_compose_contract.py
- tests/browser/test_admin_branding.py (new)
- tests/integration/test_branding_container.py (new optional exact-owned fixture)
- tests/fixtures/branding/** (new synthetic assets, no private data)
- docs/verification/operator-branding.md and docs/verification/README.md (single
  new record/index entry only)
OAP: this order/oap/active and unique187-a report. Existing SVG bytes unchanged.
Any additional path needs strategic scope decision BEFORE edit. No migrations,
dependencies/workflow/financial/provider/authservices changes authorized.

## Functional requirements

R1 Optional environment SLAIF_BRANDING_DIR unset/blank means disabled. Same image,
no rebuild. Five fixed slots: style.css; logo.svg|png; logo-compact.svg|png;
favicon.svg|png; hero.svg|png. Max256KiB perfile. Unknown files ignored; ambiguous
same-slot alternatives fall back independently. Product identity stays SLAIF
API Gateway; no user uploads or browser editor, templates/code are not overridable.

R2 Fixed public-before-login routes, preferably /admin/branding/{FIXED_SLOT}
so existing Nginx /admin proxy works unchanged. Route choices are registered
fixed literals, never arbitrary paths/file parameters/listing. Known slot serves
valid bytes or safe fallback200: empty CSS or packaged logo. MIME correct,
Cache-Control:no-cache, X-Content-Type-Options:nosniff on each branding response.
No private path/content in logs/errors. No authentication rights or session writes
from requesting public assets. Unknown paths keep normal404; API JSON untouched.

R3 Same live refresh semantics: re-read/revalidate each request, no operatorasset
cache; same-size/same-mtime replacements picked up. Render-time discovery plus
asset-time fallback makes deletion/invalidity between HTML and asset request safe.
CSS loaded AFTER packaged styles on every existing browser template; logo wide,
compact<=480px, favicon all browser templates, hero on admin login. Integrate
via shared context/macros with small changes; do not create new anonymous business
pages or replace existing API/nonHTML error contracts. Existing standalone HTML
error surfaces, if any, share branding; otherwise document that limitation rather
than inventing generic error architecture. Preserve existing inline error pages.

R4 Reader security parity: real directory, no symlink in any ancestor or leaf,
anchored directory descriptors reused for slot reads, nofollow/nonblocking opens,
regular files only, bounded read, before/after identity checks, close all FDs.
Root/ancestor/file swaps, FIFO/specialfiles and IO failures fall back, cannot block
worker or read external target. No directory creation/write or deletion byapp.
Use existing reference mechanism; do not build filesystem service/framework.

R5 Content parity: conservative strictUTF8 CSS rejects escapes/malformedcomments,
imports/resource functions/remote/data/active constructs even with comments or
spacing; ordinary selectors/variables/media rules allowed. SVG namespace-aware
wellformed inert allowlist/bounded depth/nodes/attrs, reject scripts/events/remote
resources/DOCTYPE/PIs/comments/unknown constructs as reference. PNG only complete
CRC-valid bounded noninterlaced8bitRGB/RGBA, <=4096eachdim and1048576pixels,
bounded zlib, no trailing/truncated/unknownchunks. No Pillow/newdecoder/library.
Do not claim merely checking signature is validation. Invalid slot cannot break
login/other slots. This is trusted operator input, not hostile upload acceptance.

R6 Overlay only adds SLAIF_BRANDING_DIR=/branding and read-only
./deploy/branding:/branding:ro to EXISTING api service. Both development and
production compose merge correctly; preserve existing project identity/ports/
services/networks/secrets/user/read-onlyroot. Document precreate directory,
permissions for existing appUID, onlypublicassets in mount. No actualproduction
invocation or broad compose-down. Header/favicon assets work through current
/admin proxy path. Existing built-in visuals remain default until188.

## Acceptance and focused verification

V1 Unit real temporary files and real FD IO: disabled/missing/valid/per-slot/
ambiguous/unknown; all5routes/fallback/MIME/cache/nosniff; CSS/SVG/PNG positives
and negativeformats; path traversal rejected; symlinkroot/ancestor/leaf; identity
change; noFDleak; rootrebind and file-toFIFO swap bounded child-process evidence;
newcontent same-size/mtime; deletionafterrender fallback. No global monkeypatch
that makes security negative silently test a fake implementation.
V2 Render and nativeChromium: disableddefaults; allslots using alternate fixture;
CSS last/computed visible change; compact desktop/mobile selection; validPNG and
SVG; favicon+loginhero; mutation/reload withoutrestart, same-size/mtime; removal/
invalidfile fallsback; unauthassetrequests don't expose protected pages; existing
login/session/CSRF and at least one adminform still function. Use syntheticaccounts,
realapp/nativebrowser. Separate staticrenderunit vs actualauthentication evidence.
V3 Compose qualification: parse combined dev and production configs safely WITHOUT
printing secret values. Verify only intendedapi env/mount delta and :ro. Run
ONEnew owned labeled loopback local application container same image with override
read-only mount (nonroot; representative productionshape); show mounted fileupdate
pickedup/no rebuild, appcannotwrite mount, defaultsifinvalid. No live provider/DB
needed for asset/login render iflifespan can be safely test-disabled; if DBneeded
use NEW owned syntheticPG and explicitURLs, not shared/envfallback. Record exact
what was real/mocked. Test fixture creates/removes ONLY exactIDs with ownerlabel,
no names-onlycleanup, no shared volumes/containers. Failedsetup cannot delete
uncreatedresources. No Docker daemon/system configuration change.
V4 Focused affected unit/config/admin/context/compose tests, browser above,
documentation checker, Ruff, diffcheck. No entire local matrix. Final GitHub
checks on exact SELF required. No skip treated aspass. Browser runtime/venv reuse
allowed: /tmp/slaif-181c-strategic-venv; command-scopedLD_LIBRARY_PATH
/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu.
OwnedPG/Redisfixture from objective185 may be imported/reused if needed unchanged,
but never use ambientDATABASE_URL or sharedTEST_DATABASE_URL destructively.

## Documentation, boundaries and publication

Docs give complete slot/env/overlay/reload/fallback/format/security/troubleshooting
contract, actualsupportedbrowser/error surfaces and comparison to pinnedreference.
Explain trustedoperatorCSS can alter presentation; not enduser permissions. New
verification record maps precise executed tests, real/mocked, limits, code source
attribution. No production/certification/accounting guarantee invented. Existing
PostgreSQL quota/fences/auth/CSRF/provider credentials/content policies unchanged.
No actualmodel/provider/email calls, protectedcredentials/productionread orwrite,
release/tag/deploy; pinned publicsourceGET and ownedsynthetic localtests permitted.

Coding agent owns Git: branchfrom verifiedmain preservinguserchanges, uniquePR187,
commit/push unchanged strategic order+active, final accuratePRbody. Never merge or
auto-merge. Report includes literal Implementation head SHA: <fullSHA> and
Report publication commit: SELF, exact paths/docsimpact/commands/results/skips/
limitations/deviations. Publish report-onlySELF firstparent=implementation, only
report differs, pushandverifyremotePRhead before responseFIFO exactOK once; then
attach sole control waiter. Strategic model independently reviews/merges after
all final gates. No188activation bycoder. Do not rewrite message.txt or oldreports.
