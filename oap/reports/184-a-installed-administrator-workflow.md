# OAP Execution Report — Objective 184-a: Installed Administrator Workflow

Report status: IMMUTABLE (finalized at the exact final implementation head
`6b376054ee410c3378adbdf6faee08ee6b4e0ffc`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first parent =
this implementation head; only this report path differs).

- Implementation head SHA: 6b376054ee410c3378adbdf6faee08ee6b4e0ffc
- Report publication commit: SELF

## 1. PR identity and merge state

- PR: #322 `feat: qualify the installed administrator catalog refresh
  workflow` (the unique 184 PR; CREATE_NEW_PR).
- Branch: `oap/184-installed-admin-workflow`.
- Base: `main` at `c9c7630da1d7abf87029e130f486b4075e73d9b5` (verified
  unchanged at publication time; PR #321 merged before 184 activation).
- Commit chain on the branch (22 commits: 1 activation + 21
  implementation):
  - `8dbe970` — activation: strategic order + `oap/active` (order bytes
    unchanged since).
  - `1ea864d` — implementation head v1: installed `slaif-catalog-refresh`
    wrapper entry point, packaged research assets, installed-workflow
    fixtures, bootstrap/verify/apply case.
  - `97a41ed`, `4bdbd12`, `31a2990`, `df1ac68` — harness/seam correctness
    (fail-loud active-seam startup, exact-HEAD clone, fresh temp
    ownership, named SQL params, executed startup-failure control).
  - `864e8c4`, `42d10d9`, `087c429`, `459fa0d`, `89f85ca` — v2 refresh
    case (changed prices + FX, acknowledged supersession), finding/warning
    read, route-authority row-identity proof.
  - `5b50997`, `b933e12`, `3f56a55` — owned loopback/tmpfs/labeled
    PostgreSQL fixture (SDK reload before reading published port mapping,
    explicit qualified daemon socket).
  - `bb89c35`, `3f9d653` — first-screen layout repair (renderer only,
    layout scope decision).
  - `f4c210b` — R5–R8 installed cases + safe unversioned-research
    refusal.
  - `e38c23e` — observed-model truthful refusal (validator) + installed
    r7b/r7c qualification rewrite.
  - `be8914f` — plan-line concise TSV/apply wording + r7c apply exit
    code. **This is the independently e2e-tested head** (section 5).
  - `55e1e1d` — thirty-row verification doc.
  - `094dd4b` — verification doc factual attribution fixes (rows
    10/11/14/20/21/30).
  - `6b37605` — verification doc count/provenance corrections (actual
    601-test scope; 184 asset-test provenance). Final implementation head;
    first parent of SELF.
- Report-only SELF commit: the publication commit of this report; first
  parent = implementation head `6b37605…`; only this report path differs.
- Merge performed: NO. Auto-merge: not requested/enabled. Coding agent
  never merges.
- Order: `oap/orders/184-a-installed-administrator-workflow.md` (activated
  bytes immutable; unchanged by any implementation commit); `oap/active` =
  `184-a` (5 bytes, no LF). All prior 180–183 orders/reports remain
  IMMUTABLE and untouched.

## 2. Environment

- Coding checkout `/home/janezp/codex-work/slaif-api-gateway`; strategic
  root `/home/janezp/codex-supervision/slaif-api-gateway`.
- Development venv `/tmp/slaif-181c-strategic-venv` (CPython 3.12.15;
  pytest, Ruff, Playwright, Docker SDK, asyncpg) — development only.
- Installed proof environment (R3, exercised by the integration module
  itself for the exact implementation head): a fresh `git clone
  --no-hardlinks` checked out detached at that head (no branch-name
  assumption), a wheel built from that checkout with standard build
  isolation, and a separate owned venv that installs ONLY that wheel
  (PyPI dependencies) — no editable install, no source-checkout
  `PYTHONPATH`. The test asserts the installed `slaif_gateway`
  module/resource origins inside that venv. Package identity = that
  exact-head wheel; the wheel does not ship `migrations/`, so migrations
  run from the source checkout's Alembic configuration (documented).
- PostgreSQL: one owned Docker container per module (`postgres:16`,
  16.15), loopback-only random port binding, tmpfs data directory, unique
  `slaif184.owner` label; identity inspected before migration; cleanup
  removes only the exact created ID with matching label (Docker NotFound
  treated as already removed; no label-scan fallback). Only the owned
  synthetic URL is ever supplied to the installed CLI — never
  `DATABASE_URL`/`.env`/shared 5432.
- Real Codex CLI under test (qualified machine): `codex-cli 0.162.1`,
  binary `/home/janezp/.codex/packages/standalone/releases/0.162.1-x86_64-unknown-linux-musl/bin/codex`,
  sha256 `628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`
  (pinned release; identity bound to the exact copied template/schema and
  executed binary).
- Research worker: Docker 29.1.3 with the pinned image
  `python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f`
  (`--pull=never`), standard isolated gateway mode, unchanged from the
  accepted 183 boundary.
- Browser: Playwright Chromium, JS disabled, scoped
  `LD_LIBRARY_PATH=/tmp/slaif-browser-runtime-8h8e0e6z/extract/usr/lib/x86_64-linux-gnu`
  on targeted commands only (owned temporary runtime; no system install).
- No system package installs, no production `DATABASE_URL`/`.env` contact,
  no real source GET, no provider key, no real email, no production
  import.

## 3. What 184-a implements

- **R1 one-command installed entry point**
  (`app/slaif_gateway/cli/catalog_refresh_admin.py`, new console script
  `slaif-catalog-refresh`): a thin composition of the EXISTING
  collect/review pipeline via argument-list subprocess plus the standard
  Linux `timeout` watchdog. Watchdog covers ONLY the read-only collect
  path — never apply/review/export/verify/status. Defaults: `standard-v1`,
  both providers, all eligible; explicit bootstrap/refresh; optional
  provider and single/list model selection; opt-in existing research
  options. Positive finite timeout required (300 s default), positive
  KILL grace (5 s default); mode validated by the wrapper BEFORE spawn
  (invalid mode refused exit 65 without spawning); unsupported preset
  refused by the child (exit 2); exact child exits preserved. No automatic
  apply, retry, browser server, or Gateway startup; compact readiness/run/
  report identity output, not a file checklist.
- **R2 packaged research assets**: `app/slaif_gateway/resources/
  catalog_refresh/` (research-instructions.md + research-output.schema.json,
  relocated R100 from `admin/catalog-refresh/`, single canonical copy),
  `pyproject.toml` package-data + console script; `research.py` resolves
  them through `importlib.resources` (identical in checkout and wheel).
  Canonical digests are digest-pinned in tests
  (`test_packaged_assets_resolve_with_canonical_bytes`); a missing
  template/schema or a missing asset PACKAGE refuses as the safe
  `research_template_missing`/`research_schema_missing` UNAVAILABLE —
  identity is never invented, and no host fallback exists.
- **Observed-model truthful refusal** (validator, under the observed-model
  refusal scope decision): an explicitly selected model that cannot be
  safely proposed now BLOCKS with the exact machine reason
  (`explicitly_selected_not_proposable`, detail carries the inventory
  reason code such as `request_charges_unrepresentable` or
  `page_parse_failed`); a selected model genuinely absent from the
  complete sources BLOCKS with `missing_required_selection` and truthful
  absence wording. Observed-but-unproposed IDs (out-of-scope exclusions
  included, alias-resolved upstream entries) are documented retain-local
  and are NEVER reported as `model_disappeared`. Genuine all-eligible
  absence keeps `model_disappeared` REVIEW. Baseline-contract,
  wildcard-only, deprecation, and truncated-selection behavior preserved.
- **R8 first-screen wording** (renderer only, under the layout scope
  decision): the installed BOTH-provider refresh kept the first change
  past the 900 px first screen (914.9 px local; the CI metric variant
  reached 917.9) because the plan line duplicated TSV/apply purpose in
  wrapped prose. Concise truthful wording ("TSV exports contain creates
  only; N reviewed updates execute here") and a compact Collection row
  (mode + retrieval counts + details link; historical collector identity
  and timestamps stay fully visible in the expanded details) restored the
  margin. No font, viewport, decision-fact, or assertion changes.
- **Docs** (R9, allowed files only): install recipe
  (`docs/catalog-refresh.md` "First install and operation (installed
  wheel)"): fresh checkout → wheel → clean venv → one persisted
  `DATABASE_URL` → source-checkout `alembic upgrade head` →
  operator-writable owned run-root and seal-key parent → activated-venv
  wrapper invocation → explicit apply; the wrapper resolves the
  `slaif-gateway` child through the activated venv (or `--cli-bin` on the
  same installed binary). `docs/cli-reference.md` and
  `admin/catalog-refresh/README.md` watchdog default corrected to 300 s
  (the 120 s cooperative collection target is a separate parameter and
  remains 120). `docs/security-model.md` drift statements corrected to
  inspected current behavior. New `docs/verification/
  catalog-refresh-installed-workflow.md`: the thirty-row closure table
  with new-vs-inherited evidence mapping (reviewed twice for exact
  attribution; the record at the final head is that doc).

## 4. CI at the final implementation head (authoritative)

Runs on `6b376054ee410c3378adbdf6faee08ee6b4e0ffc` (PR #322): CI run
`38516011580` + CodeQL run `38516011624`:

| Check | Result |
|---|---|
| Unit, lint, and migration head | PASS (4671 passed, 1 skipped, 75.38s) |
| PostgreSQL integration tests | PASS |
| OpenAI-compatible E2E tests | PASS |
| Playwright browser smoke | PASS |
| Docker Compose smoke | PASS |
| Documentation hygiene | PASS |
| CodeQL: Analyze (python) | PASS |

All final-head checks are SUCCESS at the exact head; no unresolved check.
Intermediate heads during development were superseded by later pushes
(their CI runs show the normal cancelled-on-supersede pattern); the last
fully completed heads before the final one, `3f9d653` and `55e1e1d`, were
all-SUCCESS.

## 5. Installed workflow qualification (local, qualified machine)

Byte-identity binding: the independent e2e-tested head is
`be8914fce38737d4640c419db73d0459348bb437`; every commit from it to the
final head `6b37605` touches ONLY
`docs/verification/catalog-refresh-installed-workflow.md`
(`final-runtime-evidence-binding.json` under the strategic
`review-artifacts/184-a-review/` records the binding). The root's
independent execution of the exact 8 installed cases (zero skips) and the
exact 6 new regressions at `be8914f` therefore binds to IDENTICAL final
runtime/test bytes. A local module execution at `55e1e1d` (same
runtime/test bytes) recorded **8 passed in 170.60 s**
(`/tmp/slaif184-module-run3.log`).

The eight cases in
`tests/integration/test_catalog_refresh_installed_workflow.py` (each
builds the exact-head wheel/venv and runs the INSTALLED command from
outside the checkout, clean cwd/environment):

1. `test_r3r4_installed_bootstrap_verify_apply` (41.9 s) — wrapper
   bootstrap on SQL-empty DB → one sealed run → `verify` rc 0 → explicit
   `apply` (actor/reason/confirm + `--ack-warnings
   new_model_exposure`) rc 0; the retry resolves `already_committed`
   with STILL exactly one `catalog_refresh_applications` row (no second
   mutation).
2. `test_r4b_installed_refresh_changed_prices_fx_and_apply` (9.7 s) —
   v1→v2 refresh against the live coherent baseline: gpt-3.5-turbo input
   0.5→0.75, syn/orc-a 5→7 per-1M, FX 0.925925926→0.892857143; one report
   with before/after; acknowledged apply supersedes price/FX at ONE
   effective T (closed windows retained, counts equal before/after except
   the superseded rows); route authority rows compared by the captured
   row identity across the refresh.
3. `test_r5_installed_selection_and_refusals` (14.0 s) — (a) single-model
   selection (others retained/excluded with exact reasons); (b) unknown
   model BLOCKED (`missing_required_selection`); (c) defaults and
   refusals: unsupported preset exit 2 (child usage), contradictory
   bootstrap+baseline 65, non-positive `--timeout`/`--kill-grace` 65,
   invalid mode 65 (wrapper-own, before spawn); (d) unreachable baseline
   DB refused BEFORE collection: rc 20 `baseline_export_failed`, stage
   `collection not started`, no collected/sealed bundle, but a minimal
   BLOCKED report IS published (`blocked-baseline_export_failed` run
   holding only minimal `REVIEW.html`/`validation.json`), DB unchanged.
4. `test_r6_installed_research_fallback` (16.6 s) — installed refresh
   with the packaged template (renamed task `AGENTS.md`) and the REAL
   qualified CLI 0.162.1 inside the enforced 183 outer boundary, canned
   mock transport at the existing `collect_bundle` seam (transport-only
   substitution; recorded honestly); 2 requested / 2 returned / 2
   accepted facts; both mandatory ACK codes
   (`new_model_exposure`, `research_semantic_method`); exact plan/HTML/
   seal/verify on the grounded facts.
5. `test_r7_installed_apply_negatives` (40.3 s) — sealed-run apply
   negatives r1–r10: r1 BLOCKED state not applicable, r2 unsealed, r3
   tampered proposal byte, r4 wrong seal key, r5 missing
   confirm/actor/reason, r6 unacknowledged warning (exact
   `apply_warnings_unacknowledged`, refused inside the locked
   transaction), r7 watchdog stall (owned stalled fixture collection:
   GNU timeout 124/137, no run published, no overwriting an earlier
   run, no automatic retry), r8 wrong baseline source for a bootstrap
   bundle, r9 forced source outage labels (`fixture_forced_failure`,
   blocked run, never bootstraps), r10 unversioned research CLI (exact
   `cli_unversioned` UNAVAILABLE, no `cli_sha256`, zero facts, no DB
   mutation). Each refusal verified with its exact code and DB snapshot
   equality.
6. `test_r7b_installed_apply_boundary_negatives` (16.7 s) — stale-at-
   apply (exact `apply_freshness_blocked`/`source_stale_blocked`, rc 20,
   no mutation, no application record) and post-review drift (deliberate
   owned ordinary catalog edit committed via an explicit
   `engine.begin()` setup helper with affected-row assertion, then exact
   `apply_baseline_stale`, rc 65, snapshot equality beyond the identified
   deliberate edit).
7. `test_r7c_installed_refresh_source_failures` (9.7 s) — selected
   unsupported billing and selected truncated/malformed source: both
   BLOCKED rc 20 with the exact observed inventory reason
   (`request_charges_unrepresentable` / `page_parse_failed` +
   `openai_model_doc:malformed_price_row`), no `model_disappeared`, no
   actionable plan, no DB mutation; sealed run apply refused rc 20
   `apply_state_not_applicable` before any plan use or DB contact.
8. `test_r8_installed_report_browser_gates` (19.0 s) — the EXACT sealed
   installed artifacts (bootstrap READY, refresh READY_WITH_WARNINGS,
   blocked case) under JS-disabled offline Chromium: the nine first-screen
   selectors all within the first 1440x900 viewport (worst bottom ≤ 900);
   initial AND fully-expanded widths pass at 1440/1280/375 with zero
   offenders; Chromium print-to-PDF produces a non-empty PDF for the READY
   cases; exactly ONE network interaction per document (the document
   itself); unchanged font floors and hash assertions.

## 6. Focused unit scope and the six new regressions

- Focused scope: `pytest tests/unit/test_catalog_refresh_*.py
  tests/unit/test_cli_catalog_refresh.py` — **601 tests across 16 files**
  at the final head (root-summed collect; the collect count alone is not
  a pass). Executed at `094dd4b` (byte-identical runtime/test bytes to
  the final head): pytest exit 0, all collected tests passed.
- The six NEW 184 observed-model regressions in
  `tests/unit/test_catalog_refresh_collection.py` (root-verified PASS,
  0 skip; JUnit `independent-six-selection-regressions.xml`):
  `test_refresh_selected_unrepresentable_billing_blocks_truthfully`,
  `test_refresh_unselected_observed_excluded_retained_not_disappeared`,
  `test_refresh_selected_unparseable_page_blocks_truthfully`,
  `test_refresh_true_absence_still_disappears`,
  `test_refresh_alias_of_observed_excluded_upstream_retained`,
  `test_refresh_selected_genuinely_absent_baseline_blocks`.
- Broad final-head unit status is the CI "Unit, lint, and migration head"
  job (section 4): 4671 passed, 1 skipped.

## 7. The thirty-row closure

All thirty numbered mandate rows map to concrete evidence in
`docs/verification/catalog-refresh-installed-workflow.md` (the record at
the final head, reviewed twice for exact attribution). Summary of the
mapping discipline: "NEW" = installed evidence produced by this module
at the recorded head; "INHERITED" = proof from the accepted 180–183
audits on the same unchanged code paths, cited by exact test where
material (execution-identity semantics, sealed plan identity, asset
provenance, apply identity negatives, billing/capability guards). Row 30
actual state at THIS report's writing: the final-head GitHub checks are
complete and SUCCESS (section 4); this report publishes as the
report-only SELF commit (the publication commit is SELF); independent
strategic review of all thirty requirements, report topology,
diff/docs/security/accounting, and all final-SELF checks, and the
guarded strategic merge, remain PENDING. The coding agent never merges;
auto-merge is not enabled.

## 8. Mock versus live; credentials

- The five official source URLs are served by checked-in fixture bytes at
  the existing `sources.fetch_source` seam via a test-only
  `sitecustomize` in the installed venv: it is INERT unless
  `SLAIF184_FIXTURE_DIR` is set; when active it refuses every unmapped
  URL and denies any physical `httpx` send; an active-but-broken seam
  terminates the interpreter at startup (exit 65) BEFORE any CLI code —
  it never degrades to physical retrieval (executed startup-failure
  control recorded). `SLAIF184_STALL_SECONDS` (watchdog) and
  `SLAIF184_FAIL_URLS` (forced outage) exercise the failure labels.
- Research model transport: the qualified canned mock at the existing
  `collect_bundle` seam; the REAL Codex worker still executes inside the
  enforced outer boundary. **Zero live model calls.**
- What IS physical in the installed runs, stated explicitly: actual SQL
  against the owned PostgreSQL container, actual Docker API calls to
  create/remove that owned container, and the actual Codex worker
  process on the qualified machine.
- No protected credential value was printed or committed; no protected
  auth file was read; no provider keys, no production endpoints, no real
  email.

## 9. Product defects found and fixed during 184-a

1. `research.py` installed asset gap: repo-relative `parents[4]` paths
   absent from the wheel → packaged `importlib.resources` assets +
   package-data (R2).
2. `research.py`: `ModuleNotFoundError` from
   `importlib.resources.files` escaped `run_research_phase` (only
   `OSError` caught) → normalized to the safe UNAVAILABLE
   `research_template_missing`/`research_schema_missing` path
   (`test_phase_refuses_missing_asset_package`).
3. `validation.py` observed-model classifier defect (root probe
   reproduced from real collector/validator): an explicitly selected
   observed model with a non-contract reason returned READY/no warnings
   (and a genuinely absent selected model was reported
   `model_disappeared`) → BLOCK with the exact machine reason;
   observed-but-unproposed IDs retained-local, never "disappeared"
   (section 3; six regressions).
4. Wrapper: an unsupported mode was not checked before spawn (the child
   saw `--help` and exited 0 without refresh) → wrapper-own mode
   validation before spawn; non-positive `--kill-grace` passed
   `timeout -k 0`, which DISABLES the KILL escalation → positive finite
   grace required.
5. Renderer: installed refresh first screen exceeded the 900 px gate
   (914.9 px local / 917.9 under the CI font metric) → concise truthful
   plan/Collection wording (layout scope decision); fonts, viewport
   gates, decision facts and assertions unchanged.
6. Docs: watchdog default 120 → 300 (`admin/catalog-refresh/README.md`,
   `docs/cli-reference.md`); install recipe child resolution via the
   activated venv, one persisted `DATABASE_URL`, operator-writable owned
   run-root instead of root-owned `/var/lib`.
7. Thirty-row verification doc: evidence attribution corrected in two
   strategic review rounds (retry→r3r4; r5d minimal BLOCKED report;
   exact inherited test names; stale/drift vs injected plan mismatch;
   actual-state pending row 30; actual 601-test scope; 184 vs 183 asset-
   test provenance).
8. Unversioned-research CLI pre-task guard: `research.py` was asset-only
   in the original order; the guard was added under the forward decision
   `184-a-unversioned-research-refusal-scope-decision.md` (a scope
   deviation disclosed as such, not an order rewrite).

## 10. Scope deviations and forward scope decisions (disclosed)

Every changed path is either in the order's exact permitted-path list or
under one of the three strategic forward scope decisions (read before
their edits; original order bytes immutable, no re-signal):

1. `184-a-installed-refresh-layout-scope-decision.md` → `rendering.py`
   minimal first-screen wording/spacing repair only (no schema/policy/
   accounting/transport change).
2. `184-a-unversioned-research-refusal-scope-decision.md` → the
   pre-task N/A version refusal in `research.py` (disclosing the
   asset-only deviation) plus its focused test.
3. `184-a-observed-model-refusal-scope-decision.md` → the `validation.py`
   baseline-only selection/observed-retention correction plus the six
   focused collection-unit regressions.

No financial/runtime/accounting/schema/migration/transport/grounding/
isolation redesign, no new framework or platform, no production test
hooks, no runtime fallbacks, no broad test-matrix runs (focused economy:
saved executions and final-head CI are the recorded truth; the broad
unit scope ran once at the recorded head and CI at the final head).

## 11. Capability skips vs local passes

- `r6` (installed actual-CLI research) and the `r8` browser/print
  sub-gates SKIP on machines without the qualified Codex CLI 0.162.1 /
  Chromium toolchain (ordinary CI runners). The LOCAL execution on the
  qualified machine PASSES and is the recorded evidence (section 5);
  skips are reported as skips, never as passes.
- All other installed cases execute on any machine with Docker (owned
  PostgreSQL) and pass at the recorded head (byte-identity binding,
  section 5).

## 12. Limitations (honest scope)

- Fixture/mock qualification: the five official source URLs are fixture
  bytes; physical source HTTP/DNS is DENIED for those URLs (unmapped
  URLs refuse); the research model transport is the qualified canned
  mock. No live-source-format or model-accuracy claim follows.
- The installed module is a local qualification (Docker + qualified CLI
  required); CI at the final head covers unit/integration/E2E/browser/
  Compose/docs hygiene + CodeQL (section 4).
- Completion is workflow implementation qualification per the order —
  never a production, release, tag, deployment, or certification claim,
  and no invoice-equivalence claim for locally calculated costs.

## 13. Files changed (32, vs base `c9c7630`)

Implementation (allowed paths or forward-decided scope):
- `pyproject.toml` (console script + package-data)
- `app/slaif_gateway/cli/catalog_refresh_admin.py` (new thin wrapper)
- `app/slaif_gateway/resources/catalog_refresh/__init__.py` (new)
- `app/slaif_gateway/resources/catalog_refresh/research-instructions.md`
  (R100 relocation of the canonical packaged asset)
- `app/slaif_gateway/resources/catalog_refresh/research-output.schema.json`
  (R100 relocation of the canonical packaged asset)
- `app/slaif_gateway/services/catalog_refresh/rendering.py` (layout
  scope decision)
- `app/slaif_gateway/services/catalog_refresh/research.py` (asset
  loading; unversioned-refusal scope decision)
- `app/slaif_gateway/services/catalog_refresh/validation.py` (observed-
  model refusal scope decision)
- `admin/catalog-refresh/README.md`
- `docs/catalog-refresh.md`, `docs/cli-reference.md`,
  `docs/security-model.md`
- `docs/verification/catalog-refresh-installed-workflow.md` (new
  thirty-row closure table)
- `tests/integration/test_catalog_refresh_installed_workflow.py` (new)
- `tests/unit/test_catalog_refresh_admin.py` (new)
- `tests/unit/test_catalog_refresh_collection.py` (six new regressions)
- `tests/unit/test_catalog_refresh_research.py` (asset assertions)
- `tests/fixtures/catalog_refresh/installed-workflow/` (11 controlled
  fixture inputs + `provenance.json` + canned research result)

Activation (strategic bytes committed unchanged):
- `oap/orders/184-a-installed-administrator-workflow.md`
- `oap/active` (exact `184-a`, 5 bytes, no LF)

No other paths, dependencies, or runtime fallbacks were added. No
skipped test is reported as pass anywhere above.

## 14. Final statement

- Implementation head SHA: 6b376054ee410c3378adbdf6faee08ee6b4e0ffc
- Report publication commit: SELF
- Base: `c9c7630da1d7abf87029e130f486b4075e73d9b5`; PR #322; branch
  `oap/184-installed-admin-workflow`.
- All final-head checks SUCCESS at the exact head (section 4): 4671
  passed / 1 skipped unit, plus integration, E2E, browser, Compose,
  docs hygiene, and CodeQL.
- Independent strategic review of all thirty requirements, report
  topology, diff/docs/security/accounting, and the final-SELF checks,
  and the guarded strategic merge, are PENDING.
- The coding agent never merges and does not enable auto-merge; merge
  authority for OAP-managed PRs belongs to the strategic model as the
  human maintainer's delegate, after independent review and satisfactory
  final-head checks.
