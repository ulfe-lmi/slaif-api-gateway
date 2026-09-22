# OAP Report - 180-c: bind proposed facts to source evidence

## Identity

- Objective: 180-c (AMEND_EXISTING_PR)
- PR: #317, branch `oap/180-catalog-refresh-bundle-review`, base `main`
- PR state at signal time: OPEN, mergeable, never merged by the coding agent
- Remote `main` base: `b1e6ef0a49d7e5ab6376f6344290f58ff844e671`
- Verified starting SHA (180-c activation commit): `0636f62f3475ae06b0e350964928cec5b20ad731`
- 180-b PR/report head (immutable, never edited): `80b8242dc5a4092a0d52aa34da6167e9a860ec3c`
- 180-b implementation SHAs referenced by the correction below (immutable):
  - `1f20b19a2b0146e4ebb218d9440ecddedf34f37b` (original 180-b implementation, 27 files)
  - `4c70c29369077782105f5c5c64f3b8935ead2718` (180-b implementation head)
- 180-c implementation commit:
  - `7e470132447ea9475eee37fd9da447171eade42c` - obj180-c: bind proposed facts to source evidence (21 files, +3054/-136)
- **Implementation head: `7e470132447ea9475eee37fd9da447171eade42c`**
- Report publication commit: SELF

All 40-hex SHAs in this report resolve in this repository (`git cat-file -e` verified for each at publication time).

## Changed paths (180-c work, `0636f62..7e47013`)

All within the order's allowed list; no other paths touched:

- `app/slaif_gateway/schemas/catalog_refresh.py` (renderer constant 180.1, evidence fields)
- `app/slaif_gateway/services/catalog_refresh/source_evidence.py` (new, 1043 lines, pure bounded parsing/observations/reconciliation)
- `app/slaif_gateway/services/catalog_refresh/validation.py` (evidence phase, per-model fact binding, FX quote binding, inventory reconciliation)
- `app/slaif_gateway/services/catalog_refresh/rendering.py` (source evidence summary line, expanded evidence details, truthful source-status wording)
- `docs/catalog-refresh.md` (new "Source evidence binding (offline replay)" subsection, blocking conditions, report section)
- `docs/cli-reference.md` (offline source input contract)
- `admin/catalog-refresh/README.md` (preparing source evidence, offline replay)
- `tests/fixtures/catalog_refresh/bundle-first-install.json`, `bundle-refresh-ready.json`, `bundle-blocked.json`, `bundle-truncated.json` (synthetic snapshot adaptation; no credentials, no real customer data)
- `tests/fixtures/catalog_refresh/browser-screenshots/{first-install,ready,warnings,blocked,large-unchanged}.png` (5 regenerated)
- `tests/unit/test_catalog_refresh_source_evidence.py` (new, 41 functions / 46 collected)
- `tests/unit/test_catalog_refresh_policy.py`
- `tests/unit/test_catalog_refresh_report.py`
- `tests/unit/test_cli_catalog_refresh.py`
- `tests/integration/test_catalog_refresh_baseline.py` (source fixture adaptation only)

Not touched although allowed (not needed this round): `services/catalog_refresh/bundle.py`, `services/catalog_refresh/sealing.py`, `cli/catalog_refresh.py`. `app/slaif_gateway/cli/main.py` not modified. `provider_catalog_proposal.py` reuse-only, not modified. No import executor, pricing/accounting runtime, DB schema/migration, dependency, workflow, deployment, or historical-record change. `oap/orders/180-c-bind-proposed-facts-to-source-evidence.md` and `oap/active` committed unchanged at the activation commit.

## Per-C results

### C1 - Typed observations and supporting snapshots (met for this focused round)

- New module `source_evidence.py`: frozen `Observation` dataclass carrying `source_key`, `provider`, `model`, `field` (`pricing:<dim>` / `model:context_length` / `model:max_output_tokens` / `model:capability:text` / `model:deprecated` / `fx:rate`), row/field `locator`, canonical exact-string `value`, `unit` (`per_1m_tokens` / `none` / `currency_pair`), `currency`, and `parser` identity. Observations are properties of parsed bytes only; the docstring states explicitly that an observation is "never manufactured by copying a proposed value to its provenance sources."
- Canonical comparison semantics: values compared as exact `Decimal` (so `1` and `1.0` agree as numbers but raw unit/currency mismatches do not); canonical comparison currency EUR; import-contract 9-dp quantization (`Numeric(18,9)`); currency conversion only through a verified FX rate (`to_eur` refuses unbound currencies, which surfaces as `fx_evidence_unbound` blockers per affected model - no invented FX).
- Independence: `independent_digests` counts distinct snapshot digests among matching observations; repeated references, duplicate URLs, and aliases to identical bytes never add corroboration. Cross-provider independence is tested (same model ID under OpenAI mirror with operator input stays REVIEW-only and never corroborates the OpenRouter row).
- Operator policy separation: `PROVIDER_OBSERVED_CAPABILITIES = {"text"}`. Alias, priority, visibility, enabled, match_type, supports_streaming and other route-local choices are never claimed from provider pages and never backed by evidence; they cannot broaden the gateway capability contract.
- Versioning decision (documented in module docstring and `docs/catalog-refresh.md`): the subsystem is unmerged, so the typed bundle contract deliberately evolves while unmerged; schema stays at version 1, renderer `180.1`; the evolution is additive on the validation side (no new top-level bundle fields); incompatible inputs (unknown provider/source-kind pairs, malformed snapshots, digests contradicting bytes) are rejected at load or classified BLOCKED/REVIEW, never silently accepted.

### C2 - Real deterministic parsing, semantic extraction honestly classified (met for this focused round)

- Registered parser registry `PARSER_IDS` (the registry, not caller strings, decides what is deterministic):
  - `(openrouter, openrouter_models_api)` -> `openrouter_models_api/v1`
  - `(openai, openai_models_api)` -> `openai_models_api/v1` (identity-only: cannot prove price/limits)
  - `(openai, openai_pricing_docs)` -> `openai_pricing_docs/v1`
  - `(openai, openai_models_docs)` -> `openai_models_docs/v1`
  - `(ecb, ecb_reference_xml)` -> `ecb_reference_xml/v1`
- Pure helper reuse through a bounded adapter from `provider_catalog_proposal` (no live generator or fetcher invoked): `_openrouter_models_from_payload`, `_parse_openai_models_api`, `_parse_openai_pricing_docs`, `_parse_openai_models_docs`, `_extract_tabular_blocks`, `_doc_price_cell`, `_convert_openrouter_price`, `_safe_openai_model_id`. No confidence-score heuristics copied into the new report.
- Bounds enforced before decoding/parsing: 4 MiB snapshot, 1 MiB XML, 500 JSON items, 5000 docs table rows, 500 models per snapshot, 64 FX currencies. Failures are safe code-only (`SnapshotFormatError` codes such as `missing_data_array`, `malformed_xml`); JSON rejects duplicate keys and non-finite constants at bundle load. XML parsed with stdlib `ElementTree` only - no external entity fetching, no network URL resolution.
- OpenRouter path parses the actual official models API shape and derives per-token USD values and recognized dimensions deterministically, then normalizes per-1M with exact Decimal arithmetic to the SLAIF import contract.
- FX: ECB has its own publisher/source identity (`provider=ecb`, `source_kind=ecb_reference_xml`, ecb.europa.eu reference URL). The offline parser preserves the original EUR-based quote and publication date; a normalized USD->EUR fact binds only to a quote whose rate equals the fact's rate or its exact reciprocal within `FX_BINDING_TOLERANCE` (1e-8, identical to the FX gate's direct-vs-reciprocal consistency tolerance, so binding and gate can never disagree) and whose publication date equals the fact's quote date. Live ECB retrieval remains later work and must reuse this parser.
- Trust classes: `official_source_keys` require host-rule + digest + registered parser + successful parse. `semantic_source_keys` (operator_input kind or extraction `semantic`) are REVIEW-only, never verified; a caller label or explanation cannot promote them. Required facts backed only by unapproved/off-host sources block (`source_evidence_unapproved`); required facts with no supporting parsed observation block (`source_evidence_unsupported`).

### C3 - Inventory and executable proposals must reconcile (met for this focused round)

- Source inventory is derived independently from the parsed snapshots (`parse_snapshot` -> `ParsedModel`/`ParsedFxQuote`), then reconciled against selection, supported scope, ready rows, incomplete rows, and excluded rows. "Considered" is not defined as the sum of output counters.
- Detected and blocked: duplicate source model ID in a snapshot; selected model absent from its complete snapshot (`source_evidence_model_missing`); proposal for a model absent from its evidence (`source_evidence_unsupported`); truncated sources; parse failures on required sources (`source_evidence_parse_failed`). No silent row disappearance; dropped/incomplete candidates stay visible in the report.
- Retain-local behavior for disappeared models preserved; no automatic deletion.
- Executable artifacts contain only reconciled, valid rows: the adversarial `{}` reproducer (below) produces header-only route/pricing TSVs and an empty FX JSON - invalid rows cannot enter executable output even if another row is valid.
- Pairing is by provider + upstream model + endpoint; public aliases bind through upstream identity (tested); same model IDs across providers are independent (tested); ordinary text Chat Completions only under the current standard profile.

### C4 - One report, evidence available inline, meaningful tests (met for this focused round)

- `rendering.py`: first screen shows a compact truthful line (e.g. "5 fact(s) bound to parsed snapshot observations"); the same artifact's expanded "Source evidence" section lists per-source state, registered parser, parsed model/quote counts, and per-model bound facts with exact locators, parsed values, units, currencies, plus FX quote bindings (rate, date, pair, tolerance). No separate file homework. HTML-escaped, deterministic, no JS, no network (verified in the browser evidence below).
- The first-screen layout was not reworked; the gate-checklist-below-fold issue is carried (see carried blockers).
- Required independent-input cases implemented as behavioral tests across the new file and the adapted policy/report/seal/CLI files, including full CLI/report/seal recomputation (CLI `review` exit codes 0/10/20/65 with sealed `validation.json` and `REVIEW.html` recomputation; report rendering from real `validate_bundle` results; seal recompute). The six case groups of the order are covered: hostile bytes with correct self-supplied digests, conflicting/duplicate/repeated observations with canonical numeric equality, real per-token USD -> per-million and EUR-USD normalization, raw inventory vs output counts with missing/dropped/duplicate rows, valid bootstrap/create-only and true no-change plus alias/cross-provider independence, and no-network/no-DB/no-import purity plus unsafe-markup safety (hostile model name cannot become code, shell, or report markup).

## Real snapshot/observation example (captured at implementation head)

Fixture `tests/fixtures/catalog_refresh/bundle-first-install.json`, openrouter source (url `https://openrouter.ai/api/v1/models`, `openrouter_models_api/v1`), model `synthetic/chat-v1`:

- `pricing:input` loc `data[0].pricing.prompt` value `0.27` unit `per_1m_tokens` currency `USD`
- `pricing:cached_input` loc `data[0].pricing.input_cache_read` value `0.027` unit `per_1m_tokens` currency `USD`
- `pricing:output` loc `data[0].pricing.completion` value `1.08` unit `per_1m_tokens` currency `USD`
- `model:context_length` loc `data[0].context_length` value `128000`
- `model:max_output_tokens` loc `data[0].top_provider.max_completion_tokens` value `8192`
- `model:capability:text` loc `data[0].architecture.input_modalities + output_modalities` value `true`
- `model:deprecated` loc `data[0].deprecation.is_deprecated` value `false`

FX example: EUR-based quote EUR->USD `1.08` (publication date equal to the fact quote date) binds the USD->EUR direction as reciprocal `0.925925926` (within 1e-8). Normalization at the 9-dp import contract: `0.54 USD/1M -> 0.500000000 EUR/1M`, `2.16 USD/1M -> 2.000000000 EUR/1M`. Canonical equality: proposed `1` and observed `1.0` agree as numbers; unit/currency mismatches do not.

## Adversarial outcomes

- The order's exact reproducer: load `bundle-first-install.json` in memory, set every source `evidence_b64` to base64(`{}`) and `content_sha256` to SHA-256 of those same two bytes, `load_bundle` + `validate_bundle` with no baseline and the bundle policy.
  - At 180-b (`1f20b19`, application tree identical at `4c70c29`): READY, zero warnings, one executable route row and one executable pricing row (per the order's independent reproduction).
  - At 180-c implementation head: **BLOCKED** with `source_evidence_parse_failed` (openrouter `openrouter_models_api:missing_data_array`; ecb `ecb_reference_xml:malformed_xml`), five `source_evidence_unsupported` findings (`model:capability:text=true`, `model:context_length=128000`, `model:max_output_tokens=8192`, `pricing:input`, `pricing:output`), `fx_evidence_unbound`, `gate:sources`, `gate:completeness`. Executable artifacts: `routes-proposal.tsv` header-only, `pricing-proposal.tsv` header-only, `fx-proposal.json` `[]`.
- Unrelated valid JSON with a correct self-supplied digest: parse failure (`missing_data_array`), BLOCKED, never verified.
- Parseable `{"data": []}`: `source_evidence_model_missing` + `source_evidence_unsupported`, BLOCKED.
- Duplicate source model ID: BLOCKED. Wrong source locator/model/provider/endpoint references (including alias renames that must not bind): BLOCKED. Unknown (provider, source_kind) pair: no registered parser, BLOCKED. Missing evidence: BLOCKED.
- Fabricated off-host URLs with matching digests: `source_evidence_unapproved`, overall BLOCKED (off-host sources cannot back required facts; the sources are still classified for reporting).
- Hostile snapshot text (model name `synthetic/chat-v1<img/onerror=alert(1)>` in the bundle model name and snapshot): report renders escaped `&lt;img`, no real tag, no script, no on-attribute; the plan is unaffected by markup injection.
- Repeated references to one snapshot count as one independent digest; conflicting observations across two genuinely distinct official-format snapshots produce `contradicting` findings rather than silent selection.

## Positive outcomes (not degenerate all-blocked)

- First-install bootstrap: READY with a create-only plan (5 facts bound to parsed snapshot observations in the fixture).
- True no-change refresh against a baseline: READY, zero mutations (`routes: nothing to create (NO CHANGES)`).
- Ready-with-warnings path: aged sources and other review findings yield READY_WITH_WARNINGS (4 review findings in the warnings screenshot case), not BLOCKED.
- Public alias pairs by upstream model; same model ID across providers stays independent; operator/semantic input is REVIEW-only and never masquerades as verified.

## Test commands and results (all at implementation head `7e470132447ea9475eee37fd9da447171eade42c`)

```text
unset DATABASE_URL
python3 -m pytest tests/unit/test_catalog_refresh_bundle.py \
  tests/unit/test_catalog_refresh_policy.py tests/unit/test_catalog_refresh_report.py \
  tests/unit/test_catalog_refresh_seal.py tests/unit/test_cli_catalog_refresh.py \
  tests/unit/test_catalog_refresh_source_evidence.py -q
# 167 collected (bundle 30, policy 29, report 11, seal 28, cli 23, source_evidence 46), 0 failed, exit 0

TEST_DATABASE_URL="postgresql+asyncpg://ubuntu@127.0.0.1:5433/obj180c_test" \
  python3 -m pytest tests/integration/test_catalog_refresh_baseline.py -q
# 9 collected, 0 failed, exit 0 (one pre-existing unrelated alembic DeprecationWarning)

python3 -m pytest tests/unit/test_cli.py tests/unit/test_imports.py \
  tests/unit/test_fx_import_service.py tests/unit/test_pricing_import_service.py \
  tests/unit/test_product_scope_docs.py tests/unit/test_rc2_feature_scope_docs.py \
  tests/unit/test_openai_assisted_import_contract_docs.py -q
# 60 collected, 0 failed, exit 0

python3 scripts/check_documentation.py   # DOCUMENTATION_CHECK=OK files=91
python3 -m ruff check <all changed Python files>   # All checks passed (E4/E7/E9/F)
git diff --check   # clean
```

Ruff initially reported two unused imports in touched paths (`re` in `validation.py`, `socket` in the new test file); both were removed and the focused batteries re-ran green. No full local suite/HPC run was performed (not required by this focused order).

## Browser / first-screen evidence

Five screenshots regenerated with the maintained Playwright script (`/tmp/obj180c_screenshots.py`, kept; derived from the preserved 180-b script), Chromium, network disabled (all non-document requests aborted), 1440x900:

- `first-install.png`: READY, "5 fact(s) bound to parsed snapshot observations", renderer 180.1
- `ready.png`: no-change refresh vs baseline, READY, no-change plan
- `warnings.png`: READY_WITH_WARNINGS, 4 review findings (aged sources incl. ECB)
- `blocked.png`: BLOCKED, 9 facts bound, `currency_inconsistency` / `missing_required_dimension` findings
- `large-unchanged.png`: 80-model no-change case, READY, 80 unchanged

For all five: `document_requests=1`, `sub_resource_requests=0`, `script_tags=0`, `on_attrs=0`; the script also asserted the source-evidence summary line and the "bound to parsed snapshot observations" decision-box line in the DOM. The committed PNGs are the output of that asserting run; first-install and blocked were visually inspected in this session.

## Corrections to the 180-b report (new report only; 180-b untouched)

1. The 180-b report's claim that independent per-field observations are compared is not established by `_fact_observations`: that helper copied one selected fact's values to each provenance-named source and then compared those copies. 180-c removes that shortcut from the validation path: `se.derive_observations` is the sole observation source and derives observations only from digest-verified parsed snapshot bytes (locator, value, unit, currency, parser identity). Provenance labels still name sources for reporting but never manufacture observations.
2. The 180-b source example contained only reference and snapshot labels, no billed values; this report lists real parsed observations (see example section).
3. The 180-b CLOSED/PASS claims on the carried blockers below are not accepted by strategy and are re-listed here as unresolved.

## Carried blockers (UNRESOLVED - not waived, not passed, not deferred out of the human mandate)

- Baseline capability keys can carry arbitrary private text, including in errors. Dropping all pricing_metadata can lose financial comparison meaning.
- Extreme exponent raises decimal.Overflow; financial normalization and exact policy boundary semantics need completion. Missing indispensable FX dates and baseline inverse-vs-runtime-current interpretation need reconciliation.
- Filesystem parent replacement bypasses lexical symlink checks. CLI verify accepts a symlinked key; CLI input reads are unbounded. os.replace publication can clobber a concurrently created empty output directory. Special-file and aggregate-size handling, descriptor identity/permissions need full review.
- The concurrent snapshot test does not commit between reader pages/queries; its current result also holds under READ COMMITTED and is insufficient proof.
- Report first-screen gate checklist remains below the fold. First-install historical-SQL wording was false; any correction must be verified along with per-provider/FX summaries and truthful current-vs-captured evidence.

Objective 180 is NOT complete by this round. This round does not authorize imports and does not advance to 181. Strategy owns the next continuation and the eventual merge decision.

## Cleanup and final state

- Disposable user-owned PostgreSQL 16 (port 5433, data dir `/tmp/obj180c-pg`, database `obj180c_test`) created solely for the adapted integration fixture: stopped with `pg_ctl stop` and the data dir removed. Shared PostgreSQL on 5432 untouched. No other databases, keys, or containers created.
- `/tmp/obj180b-shots-*` screenshot workdirs removed (task-owned). Preserved: `/tmp/obj180a-fifo-ok-marker`, `/tmp/obj180a-fifo-ok.log`, `/tmp/obj180b_screenshots.py`, `/tmp/obj180c_screenshots.py`.
- Working tree clean after the implementation commit. Unrelated worktrees, `.local-provider-catalog/`, root `AGENTS.md`, and `message.txt` untouched. No global prune.

## CI state (implementation head `7e470132447ea9475eee37fd9da447171eade42c`)

Queried with `gh pr checks 317 --repo ulfe-lmi/slaif-api-gateway`, polled until all checks terminal (pending never counted as passed). All ten checks passed:

- Unit, lint, and migration head - pass (2m20s)
- PostgreSQL integration tests - pass (2m22s)
- OpenAI-compatible E2E tests - pass (1m14s)
- Playwright browser smoke - pass (1m17s)
- Docker Compose smoke - pass (55s)
- Documentation hygiene - pass (7s)
- CodeQL - pass (3s)
- Analyze Python - pass (1m15s)
- Analyze (python) - pass (2m14s)
- Analyze (javascript-typescript) - pass (46s)

## Honest scope statement

- Offline replay of supplied snapshots proves extraction consistency of the supplied bytes against proposed facts. It does not authenticate a live retrieval that never occurred; snapshot origin/retrieval claims are caller-supplied labels, not attestation. The future trusted collector will establish actual retrieval; nothing in this round fabricates its attestation or treats a supplied boolean as one.
- No live source retrieval, Codex research, provider inference, real email, production action, or protected credentials were used. Only synthetic/public cached data.
- PR #317 remains OPEN; no merge, no auto-merge, no tag, no release. The only published release remains `v0.1.0-rc.1`.
