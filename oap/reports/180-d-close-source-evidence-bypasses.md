# OAP Report - 180-d: close source evidence bypasses

## Identity

- Objective: 180-d (AMEND_EXISTING_PR)
- PR: #317, branch `oap/180-catalog-refresh-bundle-review`, base `main`
- PR state at signal time: OPEN, never merged by the coding agent
- Remote `main` base: `b1e6ef0a49d7e5ab6376f6344290f58ff844e671`
- Verified starting SHA (180-d activation commit): `8a08c615f10e1bd23922270d594970d043a2e363`
- 180-c PR/report head (immutable, never edited): `f728c7468ed352d3ca3ad1945bcd95a968552782`
- 180-c implementation commit (immutable): `7e470132447ea9475eee37fd9da447171eade42c`
- 180-d implementation commit:
  - `e3d2c7d3e37aa083781723bae194a1dd80f30b94` - obj180-d: close source evidence bypasses (19 files, +1674/-677)
- **Implementation head: `e3d2c7d3e37aa083781723bae194a1dd80f30b94`**
- Report publication commit: SELF

All 40-hex SHAs in this report resolve in this repository (`git cat-file -e` verified for each at publication time). The implementation commit was pushed before this report was drafted; the PR head at drafting time was the implementation head.

## Changed paths (180-d work, `8a08c61..e3d2c7d`)

All within the order's allowed list; no other paths touched (19 files, +1674/-677):

- `app/slaif_gateway/schemas/catalog_refresh.py` - `RENDERER_VERSION` 180.1 -> 180.2; `openai_models_docs` added to `SOURCE_KINDS`, resolving the parser-registry vs SOURCE_KINDS mismatch the order required to be resolved coherently (parser `openai_models_docs/v1` was already registered).
- `app/slaif_gateway/services/catalog_refresh/source_evidence.py` - strict bounded snapshot parsing (duplicate JSON object keys and non-finite constants rejected in each decoded snapshot, at all nesting levels); bounded price-cell bound before any formatting/math helper; raw-row structure validation with original row indices preserved; URL-based source independence; conflicting-value detection with EUR normalization and an unresolvable-currency marker; explicit duplicate-row policy (identical dedupe with reconciled counts / conflicting block); per-observation serialization (`observed_value`, `unit`, `currency`, `locator`, `normalized_eur`, `conversion`, source URL/digest/parser/retrieval time); `reconcile_model_facts` with `binding_model` (the route's effective upstream model) and per-field declared-source validation; `semantic_only` removed from the contract.
- `app/slaif_gateway/services/catalog_refresh/validation.py` - per-field fact binding to declared sources and the route upstream (D1); authoritative FX quote binding pass executed before the model loop, building `fx_to_eur` exclusively from fully bound quotes (D2); FX publication date / future-publication / provenance checks; selection reconciliation with per-ID dispositions and the `selection_unexplained_omission` blocker (D4); wiring for all D1-D3 blocker/finding codes.
- `app/slaif_gateway/services/catalog_refresh/rendering.py` - evidence presentation only (no layout rewrite): expandable per-fact observation table (Source, Locator, Observed value, Unit, Currency, Normalized (EUR), Conversion, URL, Content digest, Parser, Retrieved), FX quote table (observed quote, quote locator, derivation, quote date, backing source, digest), and a selection-reconciliation paragraph. All output escaped; the first-screen decision box is unchanged in structure.
- `docs/catalog-refresh.md` - source-evidence section rewritten: strict snapshot parsing, per-field declared-source + upstream-model binding, unresolvable-currency marker, URL-based independence, authoritative FX binding and its blocking codes, per-ID selection reconciliation, in-report observations, 180.2 renderer versioning.
- `docs/cli-reference.md` - offline source input contract (changed source/selection input semantics only).
- `admin/catalog-refresh/README.md` - "Preparing source evidence" (changed source/selection input semantics only).
- `tests/unit/test_catalog_refresh_source_evidence.py` - 46 -> 62 collected; D1-D5 end-to-end regressers run through `validate_bundle` plus nearby positive cases; the tests that previously codified the bypasses (semantic-FX READY_WITH_WARNINGS, unproposed-candidate READY) were corrected to assert the contract, not kept.
- `tests/unit/test_catalog_refresh_policy.py` - FX tests recast for authoritative quote binding (agreement incl. direct + exact reciprocal, ambiguity, missing date, future publication, provenance borrowing, operator mirror).
- `tests/integration/test_catalog_refresh_baseline.py` - renderer version 180.1 -> 180.2 (only change).
- `tests/fixtures/catalog_refresh/bundle-first-install.json`, `bundle-refresh-ready.json`, `bundle-blocked.json`, `bundle-truncated.json` - renderer version bump (only change in each; verified by diff).
- `tests/fixtures/catalog_refresh/browser-screenshots/{first-install,ready,warnings,blocked,large-unchanged}.png` - 5 regenerated at 1440x900 by the asserting screenshot run.

Not touched although allowed (not needed this round): `services/catalog_refresh/bundle.py`, `services/catalog_refresh/sealing.py` (seal verification already recomputes the canonical validation JSON - including the new serialized observations - via `validate_bundle` + `validation_json_bytes` and byte-compares it, so no second semantic truth is introduced), `cli/catalog_refresh.py`, `provider_catalog_proposal.py` (reuse-only), `app/slaif_gateway/cli/main.py`. No import executor, pricing/accounting runtime, DB schema/migration, dependency, workflow, deployment, or historical-record change. No live retrieval, provider calls, Codex research, imports, or apply. `oap/orders/180-d-close-source-evidence-bypasses.md` and `oap/active` committed unchanged at the activation commit.

## Per-D results

### D1 - Bind every field to its actual upstream and claimed sources (closed)

- `reconcile_model_facts` is now called per (provider, model) with `binding_model` = the route's **effective upstream model**. Provider facts bind to provider + actual upstream model + applicable endpoint/pricing context; the module docstring states that a public alias is local routing policy, not a model whose price can be borrowed.
- EACH financial/capability/limit field is validated against the references its own fact declares. Referenced-but-wrong field/model/provider evidence blocks instead of being silently repaired from unrelated sources: D1.2 reproducer (`pricing[0].provenance` -> existing ECB source key) -> BLOCKED `source_evidence_reference_mismatch`, 0 rows; alias collision where both names exist in the catalog and the other name carries a different price -> `source_evidence_value_mismatch`; D1.1 reproducer (`routes[0].upstream_model` -> `synthetic/unobserved-upstream`, everything else untouched) -> BLOCKED `source_evidence_model_missing` + `source_evidence_unsupported`, 0 rows (before: READY with a pricing row at the original model's EUR 0.25 input / EUR 1.00 output prices).
- The valid alias case is preserved and tested: public B -> observed upstream A may use A's prices when the evidence explicitly supports A; public A -> unobserved/different B may not.
- Selective citation is closed: conflicting-value detection scans ALL official-source observations for the binding model, not only the sources the fact's references name; normalized (EUR) comparison means a conflicting supplied observation blocks even when the proposal omitted that source from its field references (test: two snapshots, same URL, differing digests -> `source_observations_contradict`).
- Positive OpenRouter and OpenAI paths proven through the complete validator and the CLI: the OpenRouter first-install fixture stays READY with its route + pricing rows; the OpenAI path uses real official-source kinds - `openai_models_api` (identity, api.openai.com), `openai_pricing_docs` (markdown table 0.54/2.16 USD, openai.com), `openai_models_docs` (context length / max output tokens) - backing a `gpt-5.2` NEW row with `observed_value == "0.54"` and `normalized_eur == "0.500000000"` asserted, and the CLI review (baseline-file mode) asserts the model block's `context_length` renders in the generated HTML.
- An operator-input mirror cannot verify provider facts: `test_operator_input_mirror_cannot_verify_provider_facts` (openai stays BLOCKED `source_evidence_unsupported`; openrouter stays UNCHANGED). Endpoint support is never inferred from a related model (covered by tests).

### D2 - A semantic label is not evidence; FX must be authoritative (closed)

- Strict parsing closes the label bypass: `_json_loads_bounded` rejects duplicate JSON object keys and non-finite constants (NaN/Infinity) in EACH decoded snapshot, at all nesting levels, with code-only errors (no traceback, no raw-secret echo). D2.1 reproducer (OpenRouter snapshot bytes -> `{}`, digest updated, `extraction` set to `semantic`) -> `source_evidence_parse_failed` + `source_evidence_unsupported` -> BLOCKED, 0 rows (before: READY_WITH_WARNINGS with executable rows while the identical bytes labelled `deterministic` blocked). Empty/unrelated/missing required-value evidence BLOCKs regardless of extraction label, optional/required caller flag, or presence of another semantic source.
- The `semantic_only` / `source_evidence_semantic_only` review-only backing mechanism - a model-wide semantic boolean that waived per-field proof - is REMOVED from the contract; no `semantic_only` occurrence remains anywhere in the evidence path. A genuine semantic extraction that the offline contract cannot represent (actual official supporting text/locator with value/unit/currency and identity) BLOCKs the candidate honestly until a bounded researcher provides it; nothing copies proposal values or treats a string label as proof. Valid structured-source positive paths are kept and tested.
- FX: the authoritative binding pass runs BEFORE any currency normalization or model loop. Each FX fact must bind to a parsed authoritative quote: a quote whose currency pair matches, whose source is an approved official source, whose rate agrees with the fact within `FX_BINDING_TOLERANCE` (1e-8) in the direct direction or with its exact reciprocal in the reciprocal direction, whose quote source is declared in the fact's own provenance, and whose publication date equals the quote date (a fact with no publication date blocks). Binding failure codes: `fx_evidence_unbound` (no quote; "semantic/manual rates are not evidence"), `source_evidence_unapproved` (quotes exist but only from unapproved sources), `fx_rate_not_finite_positive`, `source_observations_contradict` (distinct FX snapshots disagree), `source_evidence_value_mismatch` (rate matches no verified quote/reciprocal), `source_evidence_reference_mismatch` (verified quote source not declared), `fx_evidence_date_mismatch` (missing or non-equal publication date). Gate-level checks add `fx_provenance_invalid_reference`, `fx_ambiguous_{currency}`, `fx_missing_required_pair`, `fx_contradictory_rates`, `fx_invalid_reciprocal`, `fx_future_publication`, plus age codes `fx_no_publication_date`/`fx_stale_review` (REVIEW) and `fx_stale_blocked` (BLOCKER); once quote binding is active the gate-level ambiguity/contradiction codes are defense-in-depth only (subsumed; documented by tests). `fx_to_eur` is built EXCLUSIVELY from fully bound quotes, so a candidate rate merely labelled verified before its later check can never be used for comparison. Both directions, date, currency, finite-positive rate, and complete supporting source are checked.
- D2.2 reproducer (ECB source removed; numeric FX fact retained; provenance -> `openrouter|EUR-USD|docs_page` with `extraction=semantic` and bytes "fx notes with no numeric rate" plus correct digest) -> BLOCKED `fx_evidence_unbound`, `fx_backed=[]`, 0 executable rows (before: READY_WITH_WARNINGS with a guessed FX rate used to justify USD-observed prices as EUR proposals).

### D3 - Strict snapshot parsing, canonical conflict checks and real locators (closed)

- Duplicate keys and non-finite constants are rejected in each decoded snapshot, not merely the outer bundle (see D2). The D3.1 reproducer (second inner `prompt` key with conflicting value `0.00000999`, digest regenerated) -> BLOCKED with a `duplicate_key` parse finding (before: READY, zero issues, executable rows).
- Raw structure is validated and original row indices preserved BEFORE any reused pure helper; invalid rows are rejected or represented with explicit disposition/reason/count - never silently filtered. D3.2 reproducer (`null` row inserted before the valid model) -> BLOCKED `malformed_row`; clean payloads keep true raw indices (locator `data[1].pricing.prompt`), and the emitted locator can no longer point at a null row (before: READY with `data[0].pricing.prompt` pointing at null).
- Hostile decimal input is bounded before formatting/math: `_BOUNDED_PRICE_CELL = ^[+-]?(?:\d{1,18}(?:\.\d{1,15})?|\.\d{1,15})(?:[eE][+-]?\d{1,3})?$` - `1e9999`, a 17-digit fraction, bare `1e`, and empty strings all yield `invalid_price` with code-only errors (no huge allocation, no uncaught `Decimal` error); ordinary per-token precision is preserved (`0.00000054` accepted).
- Conflicting rows/observations within ONE snapshot block (`source_observations_contradict`) even though only one digest is involved; identical duplicate rows are deduplicated only under an explicit policy with reconciled counts and a truthful REVIEW finding `source_duplicate_rows_deduplicated` (the report does not claim BLOCKED where policy merely warns).
- Value comparison uses exact `Decimal` plus unit/currency/context: equal decimal spellings agree (1 == 1.0); a missing/unknown/contradictory source unit is never assigned USD/per-million by assertion - the observation keeps its unit and the comparison is marked unresolvable (`UNRESOLVED (no verified FX binding for this currency)` marker) rather than guessed.
- Independence is now URL-based: `independent_source_urls` counts DISTINCT official URLs; repeated retrievals or aliases of the same URL (even with differing digests) count as one source, without suppressing conflicting observations (which still block). XML remains offline and entity/network safe.

### D4 - Explicit selection and complete per-ID reconciliation (closed)

- Every parsed raw identifier reconciles into exactly one disposition: selected/proposed, explicitly excluded with an actual reason, incomplete/blocked, duplicate/malformed, or retained historical local state. The report carries the names/reasons and aggregate counts (`explicitly_excluded_models` per provider) without low-value per-row warnings.
- D4.1 reproducer (one additional fully populated eligible text model in the raw snapshot, digest regenerated, `model_include` empty, proposals unchanged) -> BLOCKED `selection_unexplained_omission` with a per-ID inventory (before: READY/zero issues with only a "1 unproposed" counter while the UI said all models of selected providers).
- Explicit subsets are preserved: both models proposed -> READY with 2 rows; a subset that excludes the extra model with a reason -> READY with `explicitly_excluded_models: 1` named in the report. No eligible model is force-imported; conservative profiles and the no-op/executable-plan guarantees are retained (80-model large-unchanged case stays READY, 80/80 unchanged, 0 omissions).
- No auto-created routes; no automatic deletion of disappeared local rows to make counters pass.

### D5 - The actual observations inside the one report (closed)

- The canonical validation result now serializes, per backed fact, the actual derived observations with their binding/normalization: source, URL, content digest, parser identity, retrieval time, exact locator, observed value, unit, currency, normalized EUR value, and the exact transformation (e.g. "USD to EUR at 0.925925926 (EUR-USD, reciprocal of verified quote, quote date 2026-09-21)"), plus unresolvable-currency markers where applicable.
- `REVIEW.html` renders them in expandable `<details>` evidence: a per-fact table (Source, Locator, Observed value, Unit, Currency, Normalized (EUR), Conversion, URL, Content digest, Parser, Retrieved) under "Source evidence - parsed snapshot observations (offline replay)", an FX quote table, and the selection-reconciliation paragraph. Output is escaped, bounded, offline, deterministic, and printable; no extra-file/base64 homework for the administrator. The normal first-screen view stays compact (decision box unchanged; expanded material lives in on-demand details).
- Seal verification recomputes these same fields: `sealing.py` (unchanged) re-runs `validate_bundle` and byte-compares `validation_json_bytes(report)`, so the serialized observations are part of the sealed truth - no second semantic truth.
- Renderer version bumped 180.1 -> 180.2 (`RENDERER_VERSION`, fixture bundles, integration baseline replay) because the report content contract changed.

## Before/after reproduction outcomes

| Reproducer | BEFORE (180-c, independently reproduced) | AFTER (implementation head `e3d2c7d`, regression-tested) |
|---|---|---|
| Positive baseline (first-install fixture, untouched) | READY, 1 route + 1 pricing row | READY (all positive paths preserved) |
| D1.1: `routes[0].upstream_model` -> `synthetic/unobserved-upstream` only | READY + pricing row at original model's prices | BLOCKED (`source_evidence_model_missing` + `source_evidence_unsupported`), 0 rows |
| D1.2: `pricing[0].provenance` -> existing ECB source key only | READY | BLOCKED (`source_evidence_reference_mismatch`), 0 rows |
| D2.1: OpenRouter snapshot -> `{}` + updated digest, `extraction=semantic` | READY_WITH_WARNINGS + executable rows | BLOCKED (`source_evidence_parse_failed` + `source_evidence_unsupported`), 0 rows |
| D2.2: ECB source removed, FX provenance -> semantic `docs_page`, "fx notes with no numeric rate" + correct digest | READY_WITH_WARNINGS, `fx_backed=[]`, executable rows (guessed rate) | BLOCKED (`fx_evidence_unbound`), `fx_backed=[]`, 0 rows |
| D3.1: second inner `prompt` key with conflicting value `0.00000999`, digest regenerated | READY, 0 issues | BLOCKED (parse `duplicate_key`) |
| D3.2: `null` row inserted before the valid model | READY; locator `data[0].pricing.prompt` pointed at null | BLOCKED (`malformed_row`); clean payloads keep raw indices (`data[1].pricing.prompt`) |
| D4.1: extra fully eligible text model in snapshot, `model_include` empty | READY/zero issues; "1 unproposed" counter only | BLOCKED (`selection_unexplained_omission`, per-ID inventory); subset with both proposed -> READY 2 rows; subset excluding the extra -> READY, `explicitly_excluded_models: 1` named |

## Real observation example (first-install, rendered in REVIEW.html)

`pricing:input` backed fact for the selected OpenRouter model: locator `data[0].pricing.prompt`, observed value `0.27` USD `per_1m_tokens` -> normalized `0.250000000` EUR, conversion "USD to EUR at 0.925925926 (EUR-USD, reciprocal of verified quote, quote date 2026-09-21)". This row is serialized in the canonical validation result and rendered inside the expanded evidence details of the generated HTML; the CLI review test asserts the generated HTML contains `data[0].pricing.prompt`, `0.27`, `per_1m_tokens`, `0.250000000`, and `0.925925926`, and the browser run asserts the same locator and observed value in the DOM after expanding the details (first-install `0.27`, ready `0.54`).

## Test commands and results

All commands run from the repository root in the project venv (Python 3.12.3, pytest 9.0.3), at the implementation head, after the implementation commit and before this report:

```text
python -m pytest tests/unit/test_catalog_refresh_bundle.py tests/unit/test_catalog_refresh_policy.py \
  tests/unit/test_catalog_refresh_report.py tests/unit/test_catalog_refresh_seal.py \
  tests/unit/test_cli_catalog_refresh.py tests/unit/test_catalog_refresh_source_evidence.py -q
  # 183 collected (bundle 30, policy 29, report 11, seal 28, cli 23, source_evidence 62) - all passed, RC=0

TEST_DATABASE_URL="postgresql+asyncpg://ubuntu@127.0.0.1:5433/obj180d_test" \
  python -m pytest tests/integration/test_catalog_refresh_baseline.py -q
  # 9 collected - all passed, RC=0 (disposable user-owned PostgreSQL 16 on port 5433; isolated database)

python -m pytest tests/unit/test_cli.py tests/unit/test_imports.py tests/unit/test_fx_import_service.py \
  tests/unit/test_pricing_import_service.py tests/unit/test_product_scope_docs.py \
  tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_openai_assisted_import_contract_docs.py -q
  # 60 collected - all passed, RC=0

python -m ruff check <all changed Python files>   # All checks passed!
python3 scripts/check_documentation.py            # DOCUMENTATION_CHECK=OK files=91
git diff --check 8a08c61..e3d2c7d3e3              # clean
```

No full local suite/HPC run was performed (not required by this focused order). Unit tests remained independent of the integration database.

## Browser / first-screen evidence

Five screenshots regenerated with the maintained asserting Playwright script (`/tmp/obj180d_screenshots.py`, kept; derived from the preserved 180-c script), Chromium, network disabled (all non-document requests aborted), 1440x900:

- `first-install.png`: READY, `d5_observations_rendered: true` (expanded details contain the locator + observed value)
- `ready.png`: no-change refresh vs baseline, READY, `d5_observations_rendered: true`
- `warnings.png`: READY_WITH_WARNINGS, 4 review-level findings; no blockers
- `blocked.png`: BLOCKED - `currency_inconsistency`, `gate:completeness`, `gate:pricing.complete`, `missing_required_dimension`
- `large-unchanged.png`: 80-model no-change case, READY, 80/80 unchanged, 0 unexplained omissions

For all five: `document_requests=1`, `sub_resource_requests=0`, `script_tags=0`, `on_attrs=0`; the script asserted the source-evidence summary line, the decision-box evidence line, the per-case plan box, and (for first-install/ready) the D5 locator + observed value inside the expanded details DOM. The committed PNGs are the output of that asserting run (`SCREENSHOTS_OK`); first-install and blocked were visually inspected in this session.

## Corrections to the 180-c report (new report only; old reports and orders remain immutable)

1. 180-c claim C4 - that the actual generated HTML contained the observed model prices/units/locators - was FALSE. The 180-c `source_evidence` payload carried only scope/note/backed-fact proposed values + source IDs + an independence count; it carried no observed values, units, currencies, or locators, and the HTML did not contain `data[0].pricing.prompt` or the observed USD/token value behind the EUR 0.25 proposal. 180-d serializes the actual derived observations in the canonical validation result and renders them in expandable evidence details (D5), with the claim now proven by CLI HTML assertions and DOM assertions.
2. 180-c claim C1 - independence via `independent_digests` - counted DISTINCT DIGESTS, so repeated retrievals of one official URL with differing hashes counted as independent corroboration. 180-d replaces it with `independent_source_urls`: distinct official URLs; same-URL retrievals/aliases count as one source, while conflicting observations from them still block.
3. 180-c claim C2 - `semantic_only` / `source_evidence_semantic_only` "review-only" backing - was a codified bypass: a model-wide semantic boolean waived per-field proof, and semantic/undated FX could stay at REVIEW while executable rows were still emitted. The mechanism is removed; empty/unrelated/missing required-value evidence BLOCKs regardless of extraction label, and FX without a parsed authoritative quote and matching publication date BLOCKs (D2).
4. 180-c claim C3 - "duplicate model ID inside one snapshot is REVIEW" - overstated the policy: conflicting duplicates now BLOCK (`source_observations_contradict`); only identical duplicates dedupe, with reconciled counts and a truthful REVIEW finding. Separately, the 180-c assertion that an extra unproposed eligible candidate could remain READY codified the D4 bypass (no per-ID disposition, no all-eligible omission block); unexplained omissions under an all-eligible selection now block (`selection_unexplained_omission`).
5. The 180-c tests that asserted these bypasses (semantic-FX READY_WITH_WARNINGS with executable rows, unproposed-candidate READY) were corrected to assert the intended contract; they were not kept as behavior.

## Carried blockers (UNRESOLVED - not waived, not passed, not deferred out of the human mandate)

- Baseline capability keys can carry arbitrary private text, including in errors. Dropping all pricing_metadata can lose financial comparison meaning.
- Extreme exponent raises decimal.Overflow; financial normalization and exact policy boundary semantics need completion. Missing indispensable FX dates and baseline inverse-vs-runtime-current interpretation need reconciliation.
- Filesystem parent replacement bypasses lexical symlink checks. CLI verify accepts a symlinked key; CLI input reads are unbounded. os.replace publication can clobber a concurrently created empty output directory. Special-file and aggregate-size handling, descriptor identity/permissions need full review.
- The concurrent snapshot test does not commit between reader pages/queries; its current result also holds under READ COMMITTED and is insufficient proof.
- Report first-screen gate checklist remains below the fold. First-install historical-SQL wording was false; any correction must be verified along with per-provider/FX summaries and truthful current-vs-captured evidence.

Scope note (180-d D3): the offline snapshot parse path now bounds raw decimal digits/exponents before any formatting/math helper, as this order's D3 requires; the carried blocker above concerns financial normalization and exact policy-boundary semantics in the import path, which this round does not touch.

Objective 180 is NOT complete by this round. This round does not authorize imports and does not advance to 181. No next numeric objective may be activated until PR #317 is fully accepted and resolved. Strategy owns the next continuation and the eventual merge decision.

## Cleanup and final state

- Disposable user-owned PostgreSQL 16 (port 5433, data dir `/tmp/obj180d-pg`, database `obj180d_test`) created solely for the integration replay: stopped with `pg_ctl stop` and the data dir removed. Shared PostgreSQL on 5432 untouched. No other databases, keys, or containers created.
- Task-owned screenshot workdirs `/tmp/obj180d-shots-*` removed.
- Preserved: `/tmp/obj180a-fifo-ok-marker`, `/tmp/obj180a-fifo-ok.log`, `/tmp/obj180b_screenshots.py`, `/tmp/obj180c_screenshots.py`, `/tmp/obj180d_screenshots.py`, `/tmp/obj180d-*.log`, `/tmp/obj180d-patches`, unrelated worktrees, `.local-provider-catalog/`, root `AGENTS.md`, and `message.txt`. No global prune.
- Working tree clean after the implementation commit.

## CI state (implementation head `e3d2c7d3e37aa083781723bae194a1dd80f30b94`)

Queried with `gh pr checks 317 --repo ulfe-lmi/slaif-api-gateway` after the push; all ten checks terminal and passed:

- Unit, lint, and migration head - pass (2m25s)
- PostgreSQL integration tests - pass (2m45s)
- OpenAI-compatible E2E tests - pass (1m47s)
- Playwright browser smoke - pass (1m14s)
- Docker Compose smoke - pass (1m8s)
- Documentation hygiene - pass (5s)
- CodeQL - pass (3s)
- Analyze Python - pass (1m21s)
- Analyze (python) - pass (1m43s)
- Analyze (javascript-typescript) - pass (42s)

## Honest scope statement

- Offline replay of supplied snapshots proves extraction consistency of the supplied bytes against proposed facts. It does not authenticate a live retrieval that never occurred; snapshot origin/retrieval claims are caller-supplied labels, not attestation. The future trusted collector will establish actual retrieval; nothing in this round fabricates its attestation or treats a supplied boolean as one.
- No live source retrieval, Codex research, provider inference, real email, production action, or protected credentials were used. Only synthetic/public cached data.
- PR #317 remains OPEN; no merge, no auto-merge, no tag, no release. The only published release remains `v0.1.0-rc.1`.
