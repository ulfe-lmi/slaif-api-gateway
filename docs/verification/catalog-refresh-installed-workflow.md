# Verification: installed administrator catalog-refresh workflow (objective 184)

> **Status:** Implemented and qualified for the administrator mandate
> **Record:** `tests/integration/test_catalog_refresh_installed_workflow.py`
> (plus the focused collection-unit regressions in
> `tests/unit/test_catalog_refresh_collection.py`)
> **Scope:** the installed wheel, executed OUTSIDE the source checkout,
> performs the one-command refresh, the explicit apply, the opt-in
> isolated research fallback, and the report/browser gates. The
> thirty-row closure worksheet (mandate ledger items 1–30) is mapped
> below to concrete evidence.

## What is qualified, and how

The integration module builds, for the exact implementation head:

1. a fresh `git clone --no-hardlinks` checked out detached at that head
   (no branch-name assumption; CI detached checkouts work);
2. a wheel built from that checkout (`pip wheel`, standard build
   isolation) and a separate owned venv that installs ONLY that wheel
   (PyPI dependencies) — no editable install, no source-checkout
   `PYTHONPATH`. The test asserts the installed `slaif_gateway`
   module/resource origins inside that venv;
3. a test-only `sitecustomize` seam in that venv. It is INERT unless
   `SLAIF184_FIXTURE_DIR` is set; when active it serves checked-in
   fixture bytes at the existing `sources.fetch_source` module-global
   seam for the five fixed official URLs, refuses every unmapped URL,
   and denies any physical `httpx` send. An active-but-broken seam
   terminates the interpreter at startup (exit 65) before any CLI code
   runs — it never degrades to physical retrieval. Optional
   `SLAIF184_STALL_SECONDS` (watchdog) and `SLAIF184_FAIL_URLS`
   (forced outage) modes exercise the failure labels. When
   `SLAIF184_MOCK_RESEARCH` is set, the same seam wraps
   `collection.collect_bundle` to replace the CLI-created
   `ResearchConfig` with the already-qualified canned mock transport;
   the REAL Codex worker still executes inside the enforced outer
   boundary.

The controlled source/model fixtures
(`tests/fixtures/catalog_refresh/installed-workflow/`) are recorded with
per-file digests and origins in `provenance.json`: the OpenAI model page
is reconstructed-and-digest-verified against the prior official capture
(181-h collect run `collect-20261012-211145-052117ddc02d`), the v2 set is
a labeled two-occurrence price derivative, the v3 page is the documented
prose-layout variant with unresolved limits, v4 is the truncated model
page (parser-level rejection) and v5 is the positive per-request fee
(billing-level rejection). This is fixture/mock qualification: no
live-source-format or model-accuracy claim.

Migrations run from the source checkout's Alembic configuration (the
wheel does not ship `migrations/`) against one owned PostgreSQL 16
container per module (owned loopback/tmpfs, unique `slaif184.owner`
label, identity-checked cleanup).

## Supported versions and the executable fresh-install path

- Python 3.12+ (wheel built with standard build isolation; no dev
  `PYTHONPATH` or editable install for operation);
- PostgreSQL 16+ for `refresh` (live baseline export) and `apply`
  (migrations run from the source checkout);
- Linux `timeout(1)` on `PATH` for the wrapper watchdog;
- one profile (`standard-v1`), two providers (`openai`, `openrouter`).

The operator recipe (fresh checkout → wheel → clean venv → one
persisted `DATABASE_URL` → source-checkout `alembic upgrade head` →
operator-writable owned run-root and seal-key parent → activated-venv
wrapper invocation → explicit apply) is in
`docs/catalog-refresh.md` ("First install and operation (installed
wheel)") and was exercised by the qualification environment itself.

## Thirty-row closure table

Evidence keys (all within `test_catalog_refresh_installed_workflow.py`
unless noted): `r3r4` bootstrap/verify/apply plus the idempotent apply
retry (`already_committed`, one application row) · `r4b` changed
price+FX refresh and acknowledged apply · `r5` selection/refusals
(a single-model scope, b unknown model, c defaults/unsupported preset,
d unreachable baseline DB refused before collection) · `r6` installed
Codex research fallback · `r7` sealed-run negatives (r1 BLOCKED
run not applicable, r2 unsealed, r3 tampered byte, r4 wrong seal
key, r5 missing confirm/actor/reason, r6 unacknowledged warning, r7
watchdog stall, r8 wrong baseline source for a bootstrap bundle,
r9 forced source outage labels, r10 unversioned research CLI) ·
`r7b` stale-at-apply and post-review drift refusals · `r7c` selected
unsupported billing / selected truncated source · `r8`
browser/print gates on the sealed artifacts · `r9` (inside the `r7`
function) forced-outage failed-collect labeling.
"Inherited" = proof from the accepted 180–183 audits on the same
unchanged code paths; "new" = installed evidence produced by this
module at the recorded head.

| # | Mandate item | Evidence (new / inherited) |
| --- | --- | --- |
| 1 | One refresh command, one report, separate explicit apply | NEW: r3r4 (wrapper bootstrap → one sealed run → explicit `apply` rc 0; the retry resolves `already_committed` with still exactly one application row), r4b (refresh → separate acknowledged apply), r7/r7b (apply refusals). Inherited: 182 apply audit. |
| 2 | Static self-contained offline HTML | NEW: r8 — each installed sealed `REVIEW.html` loads with exactly one network interaction (the document itself), JS disabled, static-offline assertions. Inherited: 180 browser/seal. |
| 3 | First-screen administrator decision overview | NEW: r8 — the nine first-screen selectors (state, scope, checks, per-provider, FX, plan, findings, "What changed" heading + first content) all within the first 1440x900 viewport on the installed bootstrap/refresh/blocked artifacts, unchanged font floors. Inherited: 180/183 geometry gates. |
| 4 | Changes and comparisons readable | NEW: r4b — actual before/after values in the installed report (gpt-3.5-turbo input 0.5→0.75, syn/orc-a 5→7 per-1M, FX 0.925925926→0.892857143) with `price_moved_review`/`fx_moved_review` findings. Inherited: 180 before/after tests. |
| 5 | Deterministic trust/readiness | NEW: r3r4 `verify` rc 0 on the installed sealed run; r7 tamper/negative refusals. Inherited: 180–183 policy/grounding proofs (unchanged validation code path). |
| 6 | Full source/field provenance | NEW: installed bundle carries per-source digests, retrieval records, and field locators (r3r4 artifact assertions); r6 re-grounds sealed research facts against sealed bytes. Inherited: 181 capture, 183 independent grounding. |
| 7 | Deterministic severity and thresholds | NEW: r4b exact warning set (2× `price_moved_review`, `fx_moved_review`, `gate:changes` at the 0.25/0.03 policy thresholds); r7c exact blocker codes for selected unsupported billing and selected truncated source. Inherited: 180/181 boundary/zero/conflict/freshness tests. |
| 8 | Deterministic official sources first | NEW: controlled fixture acquisition through the existing seam with honest fixture labels (no physical DNS/socket; unmapped URLs refuse; forced-outage mode → `fixture_forced_failure` label, r9). Inherited: 181 current-format captured qualification. |
| 9 | Useful Codex fallback for eligible missing facts | NEW: r6 — installed refresh with the packaged template, REAL Codex worker on the qualified machine, canned mock transport at the existing seam; 2 requested/2 returned/2 accepted facts, both mandatory ACK codes (`new_model_exposure`, `research_semantic_method`). Inherited: 183 actual-CLI pipeline/mock/captured-derivative proofs. |
| 10 | Trustworthy execution and artifact identity | NEW: installed sealed `execution_context` (runner-owned code/package/resource identity) and r10 (research CLI that cannot prove its version: exact `cli_unversioned` UNAVAILABLE, no `cli_sha256`, zero facts, no DB mutation). Inherited: 181-i runner-owned context; 183 measured/declaration separation; and the 183 unit identity/asset proof — `test_relocation_keeps_the_identity` / `test_changed_bytes_change_the_identity` / `test_missing_file_is_unavailable` (execution identity follows the bytes; a path relocation changes nothing, changed bytes change it, a missing file is UNAVAILABLE) plus `test_packaged_assets_resolve_with_canonical_bytes` / `test_phase_refuses_missing_template_or_schema` / `test_phase_refuses_missing_asset_package` (canonical packaged template/schema digests; a missing asset or asset package is refused as the safe `research_template_missing`/`research_schema_missing` UNAVAILABLE). |
| 11 | Canonical typed proposal, not competing runtime catalog | NEW: r3r4 bundle/plan identity (sealed `catalog-refresh.json` + authenticated `apply_plan`), r7b stale-at-apply and post-review drift refusals (the re-derived plan identity is re-checked on the locked writer). Inherited: 180 canonical bundle, 182 PG-authoritative apply; `test_apply_uses_the_sealed_plan_identity_exactly` (apply executes the sealed operations/plan/bundle identity exactly — no competing re-derived runtime plan). |
| 12 | Every source model reconciled | NEW: r3r4 all-eligible run reconciles every observed model in the inventory (exclusions with exact machine reasons; no silent cap — the collection note states the exact reconciliation count), r7c exact inventory entries for observed billing/parser failures. Inherited: 181 inventory/filter tests. |
| 13 | Explicit model scope/filtering | NEW: r5a single-model selection (others retained/excluded with reasons), r5b unknown-model BLOCKED (`missing_required_selection`), r7c selected-unsupported-billing and selected-truncated-source BLOCKED with the exact observed reason and `apply_state_not_applicable` on the sealed run. Inherited: 181 selection/unsupported tests. |
| 14 | Consistent existing baseline comparison | NEW: r4b live `--db-url` export identity (baseline digest-verified), r5d unreachable baseline DB refused BEFORE collection (rc 20 `baseline_export_failed`, stage `collection not started`; no collected/sealed bundle, but a minimal BLOCKED report IS published — `blocked-baseline_export_failed` run holding only the minimal `REVIEW.html`/`validation.json`, DB unchanged), r7b stale-at-apply (exact `apply_freshness_blocked`/`source_stale_blocked`, no mutation, no application record) and post-review drift (exact `apply_baseline_stale`, snapshot equality beyond the identified deliberate edit). Inherited: 180 snapshot, 182 locked apply guard. |
| 15 | Honest bootstrap/refresh/history | NEW: r3r4 (SQL-empty bootstrap) → r4b (price+FX refresh supersedes at one effective T; closed history preserved, counts equal before/after except the superseded rows), r9 outage never bootstraps (blocked labels, no rows). Inherited: 181 outage-never-bootstrap, 182 window/history. |
| 16 | Simple supported presets | NEW: r5c defaults (standard-v1, both providers, all eligible) and wrapper/child refusals: unsupported preset exit 2 (child usage), contradictory bootstrap+baseline 65, non-positive `--timeout/--kill-grace` 65, invalid mode 65 (wrapper-own, before spawn). Inherited: standard-v1 contract. |
| 17 | ECB FX in same report, Decimal/accounting direction | NEW: r3r4/r4b BOTH-provider USD workflow — ECB EUR→USD quote rendered as the derived USD→EUR reciprocal (0.925925926 → 0.892857143), Decimal-exact values in the installed report. Inherited: 181 ECB, 182 atomic FX history/coherent capture. |
| 18 | Deterministic acceptance gates | NEW: r7 (BLOCKED/tampered/unsealed/wrong-key runs cannot apply — exact refusals, DB unchanged; r7-r6 unacknowledged warning refused inside the locked transaction with exact `apply_warnings_unacknowledged`), r7c (BLOCKED sealed run → `apply_state_not_applicable` before any plan use or DB contact), r4b (the acknowledged-ACK path executing). Inherited: 180–183 gate tests. |
| 19 | Apply exact reviewed authenticated identity | NEW: r7-r1…r7-r5 (BLOCKED-state not applicable, unsealed receipt, tampered proposal byte, wrong seal key, missing confirm/actor/reason — each refused with its exact code before mutation), r7b (re-derived plan identity re-checked on the locked writer). Inherited (cited separately): 180/182 unit negatives for substituted baseline digest and target mismatch. |
| 20 | Explicit audited one-transaction application | NEW: r3r4/r4b apply (non-blank `--actor`/`--reason`/`--confirm`, one atomic transaction, `catalog_refresh_applications` record with run/bundle/plan identity, audit row), r3r4 idempotent retry (a second `apply` resolves `already_committed` with still exactly one application row and no second mutation). Inherited: 182 real-PG atomicity/idempotency/races. |
| 21 | Reproducible artifacts/provenance chain | NEW: r3r4 asserts the installed venv resolves `slaif_gateway` modules and the packaged `slaif_gateway.resources.catalog_refresh` assets (module/resource origins inside the fresh wheel environment); r8 gates the EXACT sealed HTML artifacts (offline static checks, geometry, print) rather than re-rendering lookalikes; `verify` re-checks receipt/manifest/seal on the sealed bytes; r6 binds the packaged template hash. Inherited: 180 seal/canonical; 183 unit asset proof — `test_packaged_assets_resolve_with_canonical_bytes` (canonical template/schema digests), `test_phase_refuses_missing_template_or_schema` / `test_phase_refuses_missing_asset_package` (missing asset/package refused as safe UNAVAILABLE), `test_relocation_keeps_the_identity` / `test_changed_bytes_change_the_identity` (identity bound to the bytes, not to location). |
| 22 | Full expanded details and usable print | NEW: r8 — initial AND fully-expanded widths pass at 1440/1280/375 on the installed artifacts, and Chromium print-to-PDF produces a non-empty PDF for the READY cases. Inherited: 180 exact browser/PDF. |
| 23 | Whole Codex/config/tools isolation outside checkout | NEW: r6 — packaged template (renamed task `AGENTS.md`) from the wheel resources, actual Codex CLI invocation inside the enforced boundary on the qualified machine; the same r6 case SKIPS on machines without the qualified CLI (CI capability skip — see below), never a local substitute. Inherited: 183 actual boundary/malicious-tool denial/cleanup. |
| 24 | No inferred trust, capability or acceptance bypass | NEW: r7c (selected unsupported billing excluded with the exact `request_charges_unrepresentable` reason and BLOCKED for a required selection — never silently accepted or re-derived), r5c wrapper/preset argument boundaries. Inherited: 181 billing/route denial guards, 183 parent grounding. |
| 25 | Busy-admin primary report, concise command output | NEW: r8 — the first-screen decision surface (banner, counts, plan line, findings) on the installed artifacts; the JSON summary links the single local report (no file checklist). Inherited: 180/183 layout, existing summary contract. |
| 26 | Supported documented install/admin operation | NEW: the documented recipe in `docs/catalog-refresh.md` matches the qualification environment (fresh clone → `pip wheel` → clean venv → source-checkout `alembic upgrade head` → activated-venv wrapper) and was executed by this module. Inherited: concrete wheel-gap identification (184 draft). |
| 27 | Works before Gateway web app startup | NEW: every installed run executes with no Gateway process started (CLI + sealed offline report only; the qualification venv holds no running app). Inherited: existing CLI/offline separation. |
| 28 | Reuse SLAIF primitives | NEW: full 184 diff audit — the only new machinery is the thin one-command wrapper (`cli/catalog_refresh_admin.py`), the packaged research assets, and the test-only seams at existing module globals; no parallel transport/schema/policy machinery. Inherited: 180–183 bounded implementation audits. |
| 29 | Protect accounting/history/concurrency/recovery | NEW: r4b installed price+FX supersession (one effective T, closed windows retained, route authority rows byte-compared across the refresh) on the owned PostgreSQL. Inherited: 182 real-PG old-cost/IDs/recovery/races/rollback (unchanged apply core). |
| 30 | Bounded OAP strategic review/terminal gates | PENDING at this doc's writing (this doc is the closure table the objective report references — it is not the report itself): PR #322 is the unique 184 PR; the report-only SELF commit, the final-head GitHub checks at the recorded implementation head, independent strategic review, and the guarded strategic merge are all not yet complete. The coding agent never merges; auto-merge is not enabled. Inherited: 180–183 immutable transcripts. |

## Capability skips vs local passes

- `r6` (installed actual-CLI research) and the browser/print sub-gates of
  `r8` SKIP on machines without the qualified Codex CLI 0.162.1 /
  Chromium toolchain (ordinary CI runners). The LOCAL execution on the
  qualified machine PASSES and is the recorded evidence; skips are
  reported as skips, never as passes.
- All other installed cases execute on any machine with Docker (owned
  PostgreSQL) and pass at the recorded head.

## Scope deviations and forward scope decisions (disclosed)

1. `app/slaif_gateway/services/catalog_refresh/research.py` was
   asset-only in the original order; the unversioned-CLI pre-task
   refusal guard was added under the forward decision
   `184-a-unversioned-research-refusal-scope-decision.md` (asset-only
   scope deviation disclosed, not an order rewrite).
2. `rendering.py` first-screen wording/spacing under
   `184-a-installed-refresh-layout-scope-decision.md` (minimal layout
   repair only; fonts, viewport gates and decision facts unchanged).
3. `validation.py` baseline-only observed-model refusal under
   `184-a-observed-model-refusal-scope-decision.md`: an explicitly
   required selected model that cannot be safely proposed (unsupported
   billing, incomplete required source facts, or genuine absence)
   BLOCKS with the exact machine reason; observed-but-unproposed IDs
   (out-of-scope exclusion included, alias-resolved) are documented
   retain-local and never "absent from complete source retrieval";
   genuine all-eligible absence keeps `model_disappeared` REVIEW.
   One human label added in `rendering.py` for the new code.
4. Refresh-overview wording: only the create-only TSV exports omit
   existing-row updates; the reviewed typed apply plan executes the
   representable supersessions (concise first-screen wording per the
   layout scope decision).

## Recorded local execution

- Implementation head: recorded in the objective report (see
  `oap/reports/184-a-installed-administrator-workflow.md`); the module
  clones and wheels exactly that head.
- Command: `pytest tests/integration/test_catalog_refresh_installed_workflow.py`
  (8 cases) plus the focused collection-unit regressions
  (`tests/unit/test_catalog_refresh_collection.py`), dev venv
  CPython 3.12.15, owned Docker PostgreSQL 16 per module.
- Result at the recorded head: 8/8 installed cases passed (including
  the r6 actual-CLI case and the r8 browser/print gates on the
  qualified machine); 359/359 focused catalog-refresh unit tests
  passed (353 inherited + 6 new observed-model regressions).

## Limitations (honest scope)

- Fixture/mock qualification: the five official source URLs are served
  by checked-in fixture bytes at the existing seam — physical source
  HTTP/DNS is DENIED for those URLs (and unmapped URLs refuse), and the
  research model transport is the qualified canned mock. No
  live-source-format or model-accuracy claim follows.
- What IS physical in the installed runs, stated explicitly: actual
  SQL against the owned PostgreSQL (owned loopback/tmpfs container),
  actual Docker API calls to create/remove that owned container, and
  the actual Codex worker process on the qualified machine. No
  protected credentials, no provider keys, no production endpoints,
  no real email.
- The qualified Codex CLI and Chromium are machine-specific; CI
  capability skips are distinguished from local passes above.
- No production/import/release/tag/deployment/certification claim
  follows from this record.
