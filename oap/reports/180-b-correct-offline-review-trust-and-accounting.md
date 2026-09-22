# OAP Report — 180-b: correct offline review trust, accounting, and publication safety

## Identity

- Objective: 180-b (AMEND_EXISTING_PR)
- PR: #317, branch `oap/180-catalog-refresh-bundle-review`, base `main`
- PR state at signal time: OPEN, mergeable, never merged by the coding agent
- Remote `main` base: `b1e6ef0a49d7e5ab6376f6344290f58ff844e671`
- Verified starting SHA (180-b activation commit): `d30306d0130ebdfa6bea93fca99bedeff709ecc2`
- 180-a PR/report head (immutable, corrected below, never edited): `7afa476943b9b254d47fbabe2007a7e2b4c862e4`
- 180-b implementation commits:
  - `1f20b19a2b0146e4ebb218d9440ecddedf34f37b` — obj180-b: correct offline review trust, accounting, and publication safety (27 files)
  - `4c70c29369077782105f5c5c64f3b8935ead2718` — obj180-b: add R3 fabricated-host provenance probe test (1 file)
- **Implementation head: `4c70c29369077782105f5c5c64f3b8935ead2718`**
- Report publication commit: SELF

All 40-hex SHAs above resolve in this repository (`git cat-file -e` verified for each).

## Changed paths (180-b work, `d30306d..4c70c29`)

All within the order's allowed list; no other paths touched:

- `admin/catalog-refresh/README.md`
- `app/slaif_gateway/cli/catalog_refresh.py`
- `app/slaif_gateway/schemas/catalog_refresh.py`
- `app/slaif_gateway/services/catalog_refresh/baseline.py`
- `app/slaif_gateway/services/catalog_refresh/bundle.py`
- `app/slaif_gateway/services/catalog_refresh/policy.py`
- `app/slaif_gateway/services/catalog_refresh/rendering.py`
- `app/slaif_gateway/services/catalog_refresh/sealing.py`
- `app/slaif_gateway/services/catalog_refresh/validation.py`
- `docs/catalog-refresh.md`
- `docs/cli-reference.md`
- `tests/fixtures/catalog_refresh/baseline-synthetic.json`
- `tests/fixtures/catalog_refresh/bundle-blocked.json`
- `tests/fixtures/catalog_refresh/bundle-first-install.json`
- `tests/fixtures/catalog_refresh/bundle-refresh-ready.json`
- `tests/fixtures/catalog_refresh/bundle-truncated.json`
- `tests/fixtures/catalog_refresh/browser-screenshots/{blocked,first-install,large-unchanged,ready,warnings}.png` (5 regenerated)
- `tests/integration/test_catalog_refresh_baseline.py`
- `tests/unit/test_catalog_refresh_bundle.py`
- `tests/unit/test_catalog_refresh_policy.py`
- `tests/unit/test_catalog_refresh_report.py`
- `tests/unit/test_catalog_refresh_seal.py`
- `tests/unit/test_cli_catalog_refresh.py`
- `oap/reports/180-b-correct-offline-review-trust-and-accounting.md` (this report)

`app/slaif_gateway/cli/main.py` was not modified (180-a already wired the offline group). No import executor, pricing/accounting runtime, DB schema/migration, dependency, workflow, Docker/Compose/NGINX, or historical-record change. The PR's cumulative diff vs `main` is 36 files (180-a + 180-b).

## Per-R results

### R1 — Overall readiness reflects executable plans (CLOSED)

- One consistent gate/issue/state model: gate failures are first-class findings (each failing gate adds a `gate:<name>` BLOCKER finding); any blocked proposed mutation makes overall BLOCKED; REVIEW findings make at least READY_WITH_WARNINGS; BLOCKED is never rendered with zero blocking issues.
- Genuinely unchanged rows are no-ops excluded from mutation plans; changed rows (update/supersession) are excluded mutations that BLOCK the run (no apply operation exists in this version). Positive paths preserved: first-install bootstrap is READY with a create-only plan; a true no-change refresh is READY with zero mutations (`routes: nothing to create (NO CHANGES)`).
- Artifacts carry only permitted create rows; excluded/unsupported rows remain in the canonical bundle/report.
- Pairing is by provider + UPSTREAM model + endpoint; public aliases need not equal upstream IDs.
- New behavioral tests (this session):
  - `test_pricing_identity_matching_nothing_fails_closed` — a pricing identity matching neither the route public name nor its upstream is a counted out-of-scope fact (never silently adopted) and the real route blocks with `missing_pricing`; overall BLOCKED.
  - `test_public_alias_pairs_by_upstream_model` — alias route (`requested_model` != `upstream_model`) pairs its pricing through the upstream identity; no missing-pairing findings; the route artifact keeps both names and the already-existing upstream pricing rule is not duplicated into the create-only pricing artifact.
  - `test_same_model_id_is_independent_across_providers` — openai and openrouter rows sharing model ID `synthetic/stable-v1` pair within their own provider only (NEW + UNCHANGED, READY); no cross-provider borrowing, no phantom selected model.
  - Plus existing: `test_true_no_change_refresh_is_ready`, `test_changed_row_alone_blocks_the_run`, `test_new_row_is_create_ready_not_changed`, `test_pricing_tsv_uses_upstream_model_for_aliased_routes`, `test_generated_artifacts_carry_only_the_permitted_create_rows`, CLI exit-code tests (0/10/20).
- Dead branch removed: the old `unpaired_pricing` check compared `p.model` against rows already fetched by `(provider, model)` key, so it was structurally always true; it was misleading dead code. The `pairing` gate now reports its evidence from the real first-class blockers (`missing_route`, `missing_pricing`).

### R2 — Correct FX direction and baseline price semantics (CLOSED)

- Canonical import-ready FX is native currency -> EUR, matching runtime `PricingService.convert_to_eur` (`find_latest_rate(base_currency=native, quote_currency=EUR)`). A supplied EUR->native rate is deterministically reciprocated (Decimal, 9 dp, ROUND_HALF_UP) and recorded with `derived_reciprocal: true` and the original `source_pair`; it is never silently relabeled.
- **FX conversion proof (real runtime path, disposable rows)** — new integration test `test_fx_normalization_matches_runtime_pricing_lookup` against a task-owned PostgreSQL 16 DB:
  - (a) seeded disposable `USD->EUR 0.925925926` row; `PricingService.convert_to_eur(Decimal("1.00"), "USD", at=2026-09-22T12:00Z)` returned exactly `0.925925926` EUR (Numeric(18,9)), `from_currency=USD`, `to_currency=EUR`, and the conversion's `fx_rate_id` equalled the seeded row id.
  - (b) with only `EUR->USD 1.08` seeded, the same USD lookup raised `FxRateNotFoundError` — the runtime never inverts the inverse pair, which is exactly why the validator derives the reciprocal.
  - (c) `_reciprocal(Decimal("1.08")) == Decimal("0.925925926")` and double inversion is stable: `_reciprocal(_reciprocal(Decimal("1.08"))) == Decimal("1.080000000")`.
  - Seeded rows were deleted by unique source string after each phase; the shared fixture rows were left untouched.
- Missing required pair, currency mismatch, contradictory/ambiguous rates, missing provenance/publication date, and expired rates all fail closed (block or review, never READY). All-EUR selected pricing reports FX N/A, not an error.
- Baseline current-price/rate selection mirrors active lookup: disabled rows excluded, strict `valid_from <= now < valid_until`, no fallback to expired/future rows, ambiguous overlapping active rows block instead of inventing a before-value (tests: `test_expired_baseline_rows_are_not_fallback`, `test_future_baseline_rows_are_not_active`, `test_ambiguous_overlapping_active_baseline_rows_block`, FX equivalents).
- Boundaries are strict and documented: price >25% strict (exactly 25% is not a finding); FX >3 calendar days REVIEW, >7 BLOCK; source age >24h REVIEW, >72h BLOCK; zero-price transitions are explicit REVIEW without percentage division. The offline rendering reference time is `generated_at` (run time); future apply will recheck freshness with its own clock — documented in `docs/catalog-refresh.md`.
- Monetary inputs are bounded: hostile huge exponent/precision values are rejected before expensive arithmetic (`test_bundle_rejects_hostile_money_exponents`); money is `Numeric(18,9)`-representable; FX deltas are quantized to 9 dp so `0.030000001` boundaries behave.

### R3 — Source provenance supports the claimed facts (CLOSED)

- Caller-supplied `authoritative`/deterministic labels are rejected at schema level (`test_provenance_authoritative_field_is_rejected`). Provenance is derived from (provider, source kind) exact-official-host rules plus supplied evidence bytes matching the declared digest: OFFICIAL / REVIEW / BLOCKED, never a declared label.
- **Exact order probe covered** — new test `test_fabricated_host_urls_are_review_not_ready`: every source URL in the valid first-install fixture replaced with `https://example.invalid/fabricated-pricing` no longer stays READY with zero warnings; state is READY_WITH_WARNINGS, every source assessment is REVIEW with `source_provenance_review`, while `evidence_state` remains `verified` (the host rule, not the evidence, fails). Lookalike/off-rule hosts, credential URLs, and unsupported (provider, kind) combinations block (`test_bundle_rejects_unsafe_source_urls`, `test_bundle_rejects_unknown_provider_and_source_kind`).
- Per-source, per-field observations are compared independently per billed dimension/unit/currency; disagreement is BLOCKED (`source_contradiction`), never resolved by confidence.
- Evidence is bound to the run: a declared `content_sha256` without accessible matching bytes cannot prove verification — missing evidence is REVIEW ("not verifiable offline"), contradicting evidence is BLOCKED. Supplied/cached evidence is explicitly distinguished from live retrieval in report text; this process never fetches.
- FX provenance may not borrow a model's OpenRouter reference (`test_fx_provenance_may_not_borrow_a_model_source`).
- Dispositions reconcile with evidence: truncated required source blocks without pretending disappearance (`test_review_truncated_source_is_not_disappeared`), scoped selection counts out-of-scope facts explicitly, and every excluded row carries a deterministic reason.

### R4 — Baseline privacy and truthful SQL/integrity claims (CLOSED)

- Free-form notes and unrelated metadata are no longer exported at all (field-specific allowlist only); the ordinary private-content canary `"Synthetic private customer conversation content: sample only."` (deliberately not matching any secret regex) plus `sk-`-style secret canaries are asserted absent from the exported document (`test_export_baseline_complete_redacted_and_deterministic`).
- The digest is described as an **integrity check on document bytes — not authentication, not proof of currency**. Docs and report wording corrected; the report's "Baseline SQL evidence" line displays historical capture versus current review: "baseline consumed from a document; SQL was executed historically at that document's export time, not during this review" (visible in the regenerated screenshots).
- Real PostgreSQL evidence (task-owned disposable DB): complete redacted deterministic export; read-only (table/audit counts identical before/after); REPEATABLE-READ consistency under a concurrent writer (uncommitted row invisible; committed row visible on next export); keyset pagination beyond one page (600-row probe); outage never bootstraps (explicit `baseline_export_failed`, never an empty bootstrap); stale and identity-mismatched baselines rejected by the CLI; live export -> offline CLI replay twice -> byte-identical artifacts -> `verify` valid.
- Export target identity is compared against the parsed configured URL (not a hardcoded suffix/port), with the existing safe-test-URL guards preserved.

### R5 — Filesystem sealing and publication safety (CLOSED)

- **Race-safe final-key creation**: the winner completes a private 0600 temp file (fsync'd) and publishes via atomic `os.link`; `EEXIST` means validate-and-reuse the peer's complete key. The final path only ever holds a complete key; an existing invalid key is never replaced. Proven by `test_concurrent_seal_key_initialization_single_winner` and `test_concurrent_existing_invalid_key_is_never_replaced` (real multi-process initialization).
- **No-symlink semantics actually implemented**: leaf, parent-component, and dangling symlinks are all rejected (`test_symlink_content_file_is_refused`, `test_parent_symlink_component_is_refused`, `test_dangling_symlink_content_file_is_refused`); reads are bounded descriptor-based with per-file/total/count/depth caps, traversal/absolute/duplicate paths and special files refused, and writer/verifier limits kept consistent.
- Tamper proofs: tampering each of the 7 content files, the manifest, or the receipt fails; wrong key fails (`hmac: authentication failed`); a coordinated unkeyed tamper (refreshing file digests, manifest, and semantic digest from local knowledge) still fails; duplicate JSON keys and duplicate manifest paths fail closed; verify never writes or re-signs (size+mtime snapshot identical); no key material appears in any artifact.
- **Atomic publication**: the complete run is built in a private staging directory, sealed last, then published with a single `os.replace`; any failure removes the staging tree and leaves nothing at the final path (`test_review_failure_leaves_no_partial_run`, `test_review_failure_leaves_no_partial_run_at_final_path`); an existing run directory (or symlink) is refused before staging (`test_run_directory_is_never_overwritten`). No global prune.

### R6 — One-glance report and accurate details (CLOSED)

- First screen (1440x900, real Chromium, `file://` URLs): state + why at the top, compact run identity, decision box (why / blockers / review counts / selected scope / baseline / baseline SQL evidence / live-research-unavailable), per-provider summary, create-only execution plan with a status banner, FX current vs proposed (native -> EUR) with derived-reciprocal markers, and aggregated important findings. Measured first-viewport offsets (px): state 126, decision 242, per-provider summary 456, execution plan 588, FX 782-805, findings 881-904 — all core sections on or at the edge of the first screen; expanded identifiers, per-model rows, full warnings, validator JSON, source inventory, and identity details are in the same file's details sections.
- Blocked plans are visually impossible to mistake for READY: red BLOCKED state banner plus a red "At least one execution plan is BLOCKED" box (`test_first_screen_blocks_are_visually_blocked`); READY/READY_WITH_WARNINGS show a green plan banner, with the warnings variant explicitly attributing the state to review findings, not the plan (renderer gap found and fixed this session; also fixed a duplicated FX N/A sentence).
- **Five first-screen screenshots regenerated and visually inspected** (`tests/fixtures/catalog_refresh/browser-screenshots/`): `first-install.png` (bootstrap READY, 1 new, create plan), `ready.png` (scoped no-change refresh, unchanged=1, NO CHANGES plans), `warnings.png` (READY_WITH_WARNINGS exit 10: stale 31h sources, one create + one no-change row, codes `gate:sources`, `source_stale_review`), `blocked.png` (BLOCKED exit 20: `currency_inconsistency`, `gate:completeness`, `gate:pricing.complete`, `missing_required_dimension`), `large-unchanged.png` (80 models, unchanged=80, collapsed).
- Browser assertions per screenshot: exactly 1 document request and **zero sub-resource requests**; **zero `<script>` tags**; **zero `on*` event attributes**; expected state banner text and plan marker present.
- Product language: CLI stage line and report footer say "offline review: review/export/verify only; live source retrieval unavailable in this version; no refresh or apply command exists in this version"; no OAP objective numbers in report/CLI output; all user data escaped; no JS or remote assets; CSP `default-src 'none'; style-src 'unsafe-inline'`.

## Original AP results (Objective 180, carried by 180-b)

- AP-1 PASS — typed bundle + real CLI `review`/`verify`/`export-baseline` on independent inputs; deterministic bytes (`test_render_is_deterministic_and_byte_stable`, replay byte-identity, canonical bundle round-trip).
- AP-2 PASS — all states/severities/count identities and delta cases covered: first-install, unchanged, conflicting (route upstream/pricing currency), zero/missing/unusual, stale/future, truncated, filtered/scoped models.
- AP-3 PASS — generated route/pricing/FX bytes round-trip through the existing import parsers (`test_generated_artifacts_round_trip_through_existing_import_parsers`, `test_generate_fx_json_serializes_rates_as_exact_strings`); unsupported updates blocked honestly; no mutation path exists.
- AP-4 PASS — first screen meets the 30-60 second review design with all details inside one self-contained artifact; verified in a real browser with zero network and zero JS.
- AP-5 PASS — seal/identity correspondence proven; tamper/wrong-key/unkeyed-manifest/symlink/size/depth/changing-byte cases all fail closed; no external authority key exposed.
- AP-6 PASS — PostgreSQL export complete, consistent, read-only; private-content canaries absent; outage never bootstraps; stale/wrong baselines rejected; export and offline replay give the same semantic comparison.
- AP-7 PASS — focused unit/integration/browser verification, docs checker, changed-Python Ruff, `git diff --check`, and all 10 final-head CI checks pass (see below); no skipped or pending test counted as a pass.
- AP-8 PASS — exact path scope (27 allowed paths + this report); no runtime/accounting/import-mutation/dependency/deployment change; old records unchanged; no provider/production call or secret read; task-owned resources cleaned and verified.

## Test commands and results (final, at implementation head)

Environment: task-owned PostgreSQL 16 cluster on 127.0.0.1:5433 with fresh migrated DB `slaif_catalog_refresh_180b_test`; repo `.venv` (Python 3.12); `TEST_DATABASE_URL` pointing at the task DB; `DATABASE_URL` unset.

- `python -m pytest tests/unit/test_catalog_refresh_bundle.py tests/unit/test_catalog_refresh_policy.py tests/unit/test_catalog_refresh_report.py tests/unit/test_catalog_refresh_seal.py tests/unit/test_cli_catalog_refresh.py` → **121 passed** (107 test functions including parametrized cases; per file: bundle 22, policy 29, report 11, seal 22, CLI 23 functions).
- `python -m pytest tests/integration/test_catalog_refresh_baseline.py` → **9 passed** (includes the new R2 FX runtime conversion proof).
- `python -m pytest tests/unit/test_cli.py tests/unit/test_imports.py tests/unit/test_fx_import_service.py tests/unit/test_pricing_import_service.py tests/unit/test_product_scope_docs.py tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_openai_assisted_import_contract_docs.py` → **60 passed**.
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=91`.
- `.venv/bin/ruff check app/slaif_gateway/ tests/` → `All checks passed!` (pinned default rule set E4/E7/E9/F).
- `git diff --check` → clean; allowed-path review → all 27 changed paths inside the order's list.

## New negative probes (180-b)

- Fabricated-host URLs (exact order probe) → READY_WITH_WARNINGS with REVIEW sources, never READY (`test_fabricated_host_urls_are_review_not_ready`).
- Phantom pricing identity → counted out-of-scope + `missing_pricing` BLOCKED (`test_pricing_identity_matching_nothing_fails_closed`).
- Alias pairing and cross-provider same-model-ID independence (`test_public_alias_pairs_by_upstream_model`, `test_same_model_id_is_independent_across_providers`).
- FX: runtime does not invert EUR->USD (`FxRateNotFoundError`), reciprocal/double-inversion determinism, direct+reciprocal agreement within 1e-8, ambiguous FX rows, missing/contradictory pairs, future/expired publication (integration + policy files).
- Sealing: internal/parent/dangling symlinks, concurrent key initialization (single winner; invalid key never replaced), coordinated unkeyed tamper, wrong key, duplicate manifest paths, malformed manifest, bounded size/depth, partial-publication failure leaves nothing, existing-output refusal.
- Hostile money exponents/precision rejected; float money rejected; non-finite values rejected; duplicate JSON keys rejected; over-size bundle rejected; unsafe source URLs (javascript:, file:, credentials, ftp) rejected; caller-supplied readiness/confidence/authoritative fields impossible.
- PostgreSQL: private-content canaries absent from export, read-only counts, concurrent-writer snapshot consistency, pagination beyond one page, outage never bootstraps, stale/tampered baseline files rejected.

## Source observation / corroboration example

`synthetic/stable-v1` (openrouter): source `openrouter|synthetic/stable-v1|openrouter_models_api`, host `openrouter.ai` (exact official host for the kind), `retrieved_at` 1h before run time (fresh), evidence bytes `{"reference":"openrouter|synthetic/stable-v1|openrouter_models_api","snapshot":"synthetic-offline-evidence"}` matching the declared `content_sha256` → classification OFFICIAL, `evidence_state=verified`. The identical evidence pattern on `https://example.invalid/fabricated-pricing` (host rule failure) flips to REVIEW with evidence still verified — proving the classification is derived, and that two references to the same evidence are not independent corroboration (contradiction checks operate on independently represented per-field observations, and the R3 probe shows a shared evidence blob cannot rescue a host-rule failure).

## No-op versus blocked plans

- No-op (true no-change refresh, scoped `synthetic/stable-v1`): overall READY exit 0; counts new=0/changed=0/unchanged=1; plans read "nothing to create (NO CHANGES)"; executable artifacts contain zero rows; report shows the green plan banner and collapsed unchanged details.
- Blocked (price-move update, `bundle-refresh-ready.json` unscoped): updated-v1 proposes input 1 -> 1.2 (excluded update mutation); overall BLOCKED exit 20 with the excluded mutation counted, red plan box, and the `pairing`/`completeness` gates reporting blocked evidence; the changed row never enters any create-only artifact.
- Warnings (stale sources, one create + one no-change): READY_WITH_WARNINGS exit 10; plan green with explicit attribution; findings aggregated first-screen.

## Browser / first-screen evidence

See R6: five 1440x900 Chromium captures from `file://` URLs of runs produced by the actual CLI (four cases) and the same in-process render pipeline (large case); per-capture assertions: 1 document request, 0 sub-resource requests, 0 `<script>` tags, 0 `on*` attributes, correct state banner and plan marker, first-viewport offsets as listed. PNGs committed at `tests/fixtures/catalog_refresh/browser-screenshots/` (regenerated, public/synthetic data only).

## Race / tamper proofs

See R5: concurrent key initialization (two initializers; one winner, loser reuses the verified complete key), invalid existing key never replaced, per-file/manifest/receipt tamper all invalid, coordinated unkeyed digest rewrite still invalid, wrong key fails HMAC, verify is strictly read-only, staging publication is atomic with failure leaving nothing at the final path, existing run dir/symlink refused.

## Corrections to the 180-a report (new report only; 180-a untouched)

1. **`"O_EXCL create, never overwritten"` (180-a, seal evidence line) was false as claimed.** The 180-a `ensure_seal_key` performed an `exists()` check and then wrote the final key in place (temp file + rename): a concurrent initializer winning between the check and the rename was overwritten, and a loser could observe a half-written key. 180-b publishes the final key via atomic `os.link` of a completed, fsync'd 0600 temp file; `EEXIST` means validate-and-reuse; the final path only ever holds a complete key. Proven by the two new concurrency tests.
2. **The 180-a no-symlink claim was not actually implemented as stated**: the old `_safe_file` resolved the path before checking `is_symlink()`, so an internal (non-dangling) symlink was accepted. 180-b checks leaf, parent components, and dangling symlinks separately and uses bounded `O_NOFOLLOW` descriptor reads; all three symlink cases now have dedicated tests.
3. **`"self-authenticating baseline documents"` (180-a, scope and docs lines) overclaimed**: an unkeyed SHA256 is an integrity check on document bytes, not authentication and not proof of a current/live baseline. 180-b docs and reports state exactly that, and the report distinguishes historical SQL capture from the current review (no `sql_checked` boolean manufactures a live-validation claim).
4. **Readiness ignored gate results (R1 probe at 180-a head)**: the 180-a refresh-ready fixture returned overall READY while both route and pricing plans were blocked and the apply gate text said blocked. 180-b makes gate failures first-class findings; any blocked proposed mutation makes overall BLOCKED; the plan banner distinguishes executable (create-only) plans from blocked ones. The 180-a `PASS` claims contradicting these four points are not accepted; the 180-a report itself remains immutable.

## Cleanup and final state

- Task-owned PostgreSQL 16 cluster (port 5433, `/tmp/obj180-pg`) stopped (`pg_ctl stop`), verified no longer listening, and removed; both task DBs (`slaif_catalog_refresh_180b_test`, `slaif_catalog_refresh_test`) dropped with the cluster data directory.
- Screenshot workdirs (including task seal keys) removed via Python `shutil.rmtree`; no shell `rm` used. 180-a marker files under `/tmp/obj180a-*` preserved as that objective's evidence trail; the screenshot generator script remains in `/tmp` (no secrets).
- Shared PostgreSQL on 5432 untouched (verified still listening before and after). `.local-provider-catalog/`, unrelated worktrees, provider/email/GitHub settings, and tags untouched.
- No containers, networks, or volumes were created by this objective.
- Working tree at signal time: exactly the 27 allowed 180-b paths modified, nothing untracked (plus this report at commit time).
- No live source retrieval, no Codex research invocation, no provider inference, no real email, no production action. No secrets printed or committed.

## CI state (implementation head `4c70c29369077782105f5c5c64f3b8935ead2718`)

All ten PR #317 final-head checks passed (polled to green; no pending counted as passed):

- Analyze (javascript-typescript): pass
- Analyze (python): pass
- Analyze Python: pass
- CodeQL: pass
- Docker Compose smoke: pass
- Documentation hygiene: pass
- OpenAI-compatible E2E tests: pass
- Playwright browser smoke: pass
- PostgreSQL integration tests: pass
- Unit, lint, and migration head: pass

## Honest scope statement

Objective 180 (offline bundle + review/export/verify) is corrected and complete on PR #317. This is an RC-beta foundation correction, not production certification. Live research (181), apply (182), and final workflow (183) remain subsequent objectives; nothing in this PR performs live retrieval, mutation, or apply. The coding agent did not merge or enable auto-merge; PR #317 remains OPEN for strategic review.
