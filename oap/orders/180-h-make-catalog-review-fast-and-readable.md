# OAP Work Order — 180-h

PR mode: AMEND_EXISTING_PR

## Objective and reason

Finish the operator-facing presentation of the offline catalog review foundation:
one self-contained REVIEW.html that a busy administrator can assess in30–60seconds,
with all detailed evidence available inside the same file. Put state, deterministic
gates, completeness, important changes and FX where the reader sees them first.
Fix the remaining expanded/print overflow and current-facing evidence wording.
This is a presentation/truth correction on the SAME PR317, not another validation
or filesystem redesign.

The full human goal remains one refresh command -> one trustworthy report -> one
explicitly confirmed audited apply command. Objective180 is its offline foundation.
Live OpenAI/OpenRouter/ECB retrieval, isolated Codex research, atomic historical
price/FX supersession and final wrappers remain subsequent numeric objectives after
180 is accepted and resolved. Do not reduce scope to offline tooling, claim the
whole workflow complete, build a new dashboard, or pre-activate181.

## Verified state and strategic disposition

Fresh GitHub/transcript reconciliation on2026-09-22:

- Repository ulfe-lmi/slaif-api-gateway. Main
  b1e6ef0a49d7e5ab6376f6344290f58ff844e671.
- Unique open PR317, base main, branch oap/180-catalog-refresh-bundle-review;
  MERGEABLE/CLEAN, no requested changes in recorded reviews.
- Starting PR/report head e65e5678b45046375a2e326ec24ceb15077a5e48.
- Its sole changed file is oap/reports/180-g-harden-catalog-filesystem-and-sealing.md;
  first parent / implementation07a75f96437e8059d8c8f92d9015e9eb23893641.
- Prior activationf9ce74320b2c066f1921784de114910c85851263; order hash
  c4a72d964276efe8d00de34461d7586d047a70881a101dcd32fa253965663695.
- Sole helper38607 returned exact RESPONSE_OK_EXACT and exit0; it is CLOSED.
  Prior active180-g. Clean shared worktree. Never reuse that helper or start
  a reader for the completed round.
- All10 implementation AND report-head GitHub checks completed/success.
- Strategy independently ran291 focused tests on exact07a75f9 (33.92s, exit0;
  stable hashes compared to Git objects), documentation checkerOK files91 and
  clean diff-check. All10 implementation paths allowed. No database/provider/
  deployment/dependency changes inG.
- Strategic acceptance: G's corrected bounded reads, protected mutation namespaces,
  retained lifecycle handles, exact key checks, no-clobber publication, authenticated
  captured-byte replay and safe errors are accepted within the documented Linux,
  operator-owned namespace scope. Report overstatements below are NOT accepted
  as proof. Preserve the immutable G report; correct them here/current docs.
- Main ruleset protects deletion/non-fast-forward. Only published release remains
  v0.1.0-rc.1. No merge/tag/release authority transfers to the coding agent.

## Exact allowed paths

- app/slaif_gateway/services/catalog_refresh/rendering.py
- app/slaif_gateway/schemas/catalog_refresh.py (RENDERER_VERSION constant only;
  increment180.4 to180.5; no other schema/policy/capability behavior changes)
- app/slaif_gateway/services/catalog_refresh/validation.py (ONLY the explanatory
  SQL_CAPTURE_DOCUMENT note and adjacent comments: supplied document declares a
  historical export; current review does not verify historical SQL execution;
  no gate, boolean, comparison, disposition, pricing, capability or SQL changes)
- app/slaif_gateway/cli/catalog_refresh.py (ONLY _minimal_blocked_html presentation
  and directly necessary descriptive help/docstrings; no command/I/O/exit changes)
- app/slaif_gateway/services/catalog_refresh/filesystem.py (docstrings/comments
  only if needed to align trust claims; executable behavior must remain identical)
- tests/unit/test_catalog_refresh_report.py
- tests/unit/test_cli_catalog_refresh.py (presentation/note assertions only)
- tests/unit/test_catalog_refresh_seal.py (presentation/version replay assertions)
- tests/browser/test_catalog_refresh_report.py (NEW standalone file-URL browser
  tests; no Gateway server, PostgreSQL, Redis, or provider dependency)
- tests/fixtures/catalog_refresh/bundle-first-install.json
- tests/fixtures/catalog_refresh/bundle-refresh-ready.json
- tests/fixtures/catalog_refresh/bundle-blocked.json
- tests/fixtures/catalog_refresh/bundle-truncated.json
  (existing four fixtures: renderer-version update only, preserve other facts)
- tests/fixtures/catalog_refresh/report-layout/ (NEW small synthetic report cases,
  browser metrics/screenshots and bounded print evidence only; no keys/secrets)
- tests/fixtures/catalog_refresh/browser-screenshots/ (replace the five existing
  PNGs with actual current-renderer captures, no unrelated binary artifacts)
- docs/catalog-refresh.md
- docs/cli-reference.md (catalog-refresh presentation/truth only)
- admin/catalog-refresh/README.md
- oap/orders/180-h-make-catalog-review-fast-and-readable.md (unchanged)
- oap/active (exact unchanged strategic bytes180-h)
- oap/reports/180-h-make-catalog-review-fast-and-readable.md (new immutable report)

No other paths. No runtime APIs/providers/accounting/quota, SQL/export semantics,
imports/supersession, source parsers, financial thresholds, capability grants,
filesystem/key/cryptographic behavior, migrations, dependencies, deployment,
workflows, architecture allowlists or historical-record changes. Do not change
business decisions or weaken validation merely to improve the view. No live
collector/researcher/apply wrapper in this round. If an actual new product defect
is uncovered, report it to strategy with a reproducer; do not silently expand.

## H1 — A real first screen for a busy administrator

Current committed first-install screenshot1440x900 spends most of the viewport
on prose and repeated identity/SQL/execution descriptions; FX starts at the bottom,
and the gate checklist is below the fold. Unit string-presence tests labelled
"first screen" do not establish viewport placement. Fix actual rendering.

At1440x900, show the following normal-case decision facts without expanding details
or scrolling through evidence prose:

- State READY / READY_WITH_WARNINGS / BLOCKED, concise reason, blocker/review counts.
- Compact provider/profile selection and baseline mode (honest first-install or
  supplied/live baseline), not a long list of every selected model.
- Deterministic checklist covering source evidence by selected provider, FX,
  schema, pricing completeness, pairing, unusual changes, supported capability
  filtering, reconciliation and import-plan validation. Group existing gates
  for display if useful, but preserve the worst applicable state and all detail.
- Per-provider reconciliation and deltas: source models considered, selected/
  proposed, ready, new/changed/unchanged, excluded/incomplete, disappeared/deprecated
  as applicable. Clearly distinguish source inventory from baseline/local rows.
  Counts must reconcile to the existing validated report; do not fabricate zeros
  or an authoritative source list when no source succeeded.
- FX current/proposed pair/rate/delta, official source/date/age/status, or a concise
  truthful explanation that no conversion is needed. Keep native currency -> EUR
  interpretation and reviewed local-runtime versus proposed/derived-rate distinction.
- A short indication of the most important warnings/changes and compact run identity
  (run ID, generated time, SLAIF revision/profile, digest identity accessible).

Use a compact two-column layout/cards/table as appropriate, ordinary legible type,
restrained state colours plus textual labels, and enough whitespace to scan.
Do not meet the viewport criterion by microscopic fonts, hidden blockers, clipped
text, or a giant horizontal table. At1280x800 and a narrow375px viewport, content
must remain readable without page-wide horizontal overflow; natural vertical
scrolling is fine on narrower screens. Long run IDs/model filters/URLs must wrap
or move to a labelled detail section, not force the page wider.

Keep the offline limitation explicit and concise: this version reviews supplied
snapshots; live collection and apply are not implemented. Do not label cached
source parsing as successful live retrieval or suggest READY authorizes an import
that does not exist. Keep create-only/current no-supersession limitations honest.
Normal administrators read ONE primary artifact, never a checklist of files.

## H2 — Changes first, evidence on demand, print without clipping

After the compact decision summary, prioritize "What changed": new models,
price changes with old/new units and currencies and signed movement, route/
capability changes with current/proposed/reason, removed/deprecated observations,
FX changes, and an unchanged count. Unchanged rows remain collapsed by default.
Disappearance is an observation, not a delete operation. Preserve conspicuous
warnings for currency/unit/zero/large movement/missing required values and
unsupported authority; no decision can be downgraded by presentation logic.

Aggregate repeated findings without hiding affected counts. Display concise human
labels; retain exact codes and per-item details on demand. Explain displayed
percentage rounding where a strictly above-threshold movement can display at the
threshold; do not change the exact comparison decision.

Every available detail remains INSIDE this HTML: source/fact provenance and parsed
observations, exact URLs/times/units/currencies/locators/digests, full warnings,
validation outputs, baseline/capture identity, exact proposed import rows, filtered
reasons and unchanged rows. Native details/summary and internal links are suitable.
Clearly label bounded example lists with their total; never imply a truncated
sample is exhaustive. Do not silently drop evidence to make the page small.

Existing provenance/source tables contain up to17columns and expanded observations
up to11; these overflow a normal desktop page. Reflow them into readable tables,
label/value groups or cards. No page-wide overflow in the fully expanded view.
Long identifiers/URLs/digests wrap without truncating their accessible value. A
reader must be able to inspect real observed prices and evidence locators without
opening another file or reading encoded machine blobs as their normal workflow.

Make printing useful: summary and expanded evidence must not clip columns/text,
truncate essential values or lose state meaning when colours are absent. Use
print CSS and actual browser PDF evidence. Clearly define whether print includes
all details or the expanded sections; test that documented behavior. No fragile
frontend stack, JavaScript, scripts, network-on-open, external fonts/assets,
iframes or application server. Preserve escaping, safe links and restrictive CSP.

## H3 — Truthful wording and renderer identity

Correct these precise current-facing discrepancies; preserve G and all earlier
reports/orders unchanged and document corrections in the NEW report:

1. G says same-size in-place mutations are refused. The reader checks opened
   dev/ino/size and EOF; it does not detect all same-size mutations. The accepted
   guarantee is the single captured byte snapshot and authenticated correspondence,
   within the protected namespace/threat scope. State that precisely; no new
   filesystem behavior is authorized to satisfy the old prose.
2. G attributes source-identity race closure to a pre-rename/pre-rmdir check alone.
   The actual boundary combines descriptor anchoring with enforced operator-owned,
   non-peer-writable mutation parents. Check and source-name mutation are separate
   operations; no atomic source-inode comparison exists. Do not claim immunity to
   root/key-controlling/full-authority same-uid code. No need for a new redesign.
3. Receipt verification currently reads with MAX_AUX_BYTES (1MiB);
   RECEIPT_MAX_BYTES8KiB is the signing overhead reservation, not the verifier's
   read cap. Correct docs to actual behavior, not code to prior wording.
4. A missing/unsafe run directory with an otherwise valid key produces verification
   invalid/exit30. Missing/unsafe key is data error/exit65. Correct the exit table;
   do not change CLI behavior.
5. Verify anchors the run and loads an existing key separately; it does not retain
   the entire review key-parent lifecycle or publish anything. Describe the
   command-specific guarantees accurately.
6. Supplied baseline metadata DECLARES historical SQL capture; consuming a file
   does not independently prove that execution occurred. Update the explanatory
   SQL_CAPTURE_DOCUMENT note and docs accordingly, preserving actual current-path
   SQL provenance flags and live-export/no-SQL semantics.
7. The eventual wrapper prints the local report path for browser review; it must
   not require a new management dashboard. Fix the admin README's planned dashboard
   wording to match the accepted one-command/one-static-report architecture.

Bump renderer revision to180.5 and update only that field in the existing four
fixtures. Produce new reports/seals for evidence. Never rewrite/re-sign archived
runs or old evidence; old rendered bundles remain artifacts of their recorded
renderer/check-out. Deterministic rendering must reproduce the same bytes for
identical inputs, and verification of NEW runs must reproduce the new rendering.
No circular receipt/report self-digest. Preserve compact identity and expanded
full identity, not merely a filename or an unsupported AI-confidence score.

## Acceptance and focused verification

AP-H1: actual1440x900 first viewport contains state/reason/counts, compact scope/
baseline, grouped deterministic checklist, provider reconciliation, FX and concise
identity for normal first-install, READY, WARNINGS, BLOCKED and large-unchanged
cases. At least one realistic synthetic two-provider case and long model IDs/URLs
are included. For unusually many findings show ranked counts + links, not pages of
codes above the checklist. No obscured blocker or claimed live retrieval.
AP-H2: changes lead the detailed report, unchanged catalogs are collapsed, all
available raw facts/validation/proposed rows remain accessible inline. Numbers
and worst-state aggregation match the unchanged validation semantics.
AP-H3: expanded report has no page-wide horizontal overflow at1440 and1280 widths;
375px remains usable. Expanded price evidence is visually readable. Print/PDF
retains the documented summary/details and long values without clipping.
AP-H4: no scripts/event handlers/external resources/network calls when opened or
expanding details; malicious source/model/URL strings remain escaped; safe source
links work as links, never auto-fetch. Native internal links have valid targets.
AP-H5: deterministic byte rendering, new-run seal/verify replay, and all prior
source/policy/financial/privacy tests pass. Show semantic-neutrality proof:
proposals, states, gates and monetary/capability comparisons unchanged except
renderer identity and explicitly authorized explanatory SQL note.
AP-H6: current docs corrected, dated history unchanged, report caveats precise,
all changed paths allowed; documentation checker, internal links, changed-Python
lint, git diff --check and all ordinary final-head CI gates green.

Run the focused catalog-refresh unit suite and the NEW standalone browser file.
Use existing venv Playwright/Chromium; render actual file:// documents from the
current pipeline, with JavaScript disabled and request recording. Browser test
assertions must measure bounding rectangles/scrollWidth and visible text, not
just HTML substring presence. Open both outer and nested evidence details where
necessary (the old premature browser-pass claim came from missing the nested
click; do not repeat it). Inspect screenshots and at least one actual print PDF.
Record viewport/metrics/network counts and real command exit codes with source
identities. Update the five existing captures plus bounded focused new evidence.
Do not merely edit expected screenshots without producing and examining reports.

No local database/Redis/Gateway/Compose/HPC/full integrated qualification needed;
G changed no such boundaries and H does not either. Standalone browser tests must
not invoke unrelated server fixtures. Ordinary broad CI remains required. Do not
weaken existing protection tests for layout; adapt only representation/version
assertions when semantically necessary. Skipped checks are not passes.

## Boundaries, setup and publication

Use task-owned temp dirs, current tooling, and synthetic provider/FX data only.
No .env/protected credentials/shared5432/configuration/log access, privileged
postgres identity, live provider calls, Codex research or production import.
No dependencies or system changes. Preserve unrelated worktrees,
.local-provider-catalog, rootAGENTS.md and permanentmessage.txt. No global cleanup.
Remove only owned temporary resources after evidence capture; no real keys in
screenshots/PDFs/logs/reports. Keep the seal key out of the report fixture tree.

Report exact starting/implementation SHAs and changed paths; H1–H3/AP evidence;
actual first-screen/expanded/print/browser results; deterministic counts/identity/
seal replay; semantic-neutrality proof; documentation/link results and CI; exact
G report wording corrections; remaining later workflow work and honest limits.
Do not claim "perfect" or completion of the full administrator workflow.
Report only already-existing CI state at implementation head; report-only SELF
checks occur AFTER publication and are independently verified by strategy. Do not
write a future report-head-green claim into the immutable report as though it
had already happened. Inspect/check them before signalling if feasible, without
rewriting the report.

Commit strategic order/active bytes unchanged on the existing PR branch. Push
implementation before drafting the report. Publish exactly one final immutable
report-only SELF commit whose first parent is the literal stated implementation
head. Verify it is remote PR317 head before exact two-byteOK on the verified
response FIFO. Coding agent never merges or enables auto-merge. No tags/releases.
Await the next strategic order; no next numeric objective before PR317 resolves.
