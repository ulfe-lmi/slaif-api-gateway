# OAP Immutable Report — 181-a: authoritative catalog collection

PR mode: CREATE_NEW_PR — PR #318 (branch
`oap/181-authoritative-catalog-collection`, base `main`).

## Identity

- Remote `main` reference at activation (merge of PR #317,
  2026-09-22T17:12:05Z):
  `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`
- Branch start / activation commit (strategic order file + `oap/active`
  pointer with exact strategic bytes `181-a`; parent is the `main`
  reference above): `cb452079ad5305e6d1208dbd240a738ba113478d`
- Implementation commit / head:
  `d0a6fc90c91a3d4074ec522152decac7eeaa7e17` (18 files, +4641/−109, parent
  `cb452079ad5305e6d1208dbd240a738ba113478d`)
- Report publication commit: SELF (first parent `d0a6fc90c91a3d4074ec522152decac7eeaa7e17`)
- PR #318 remains OPEN. Never merged, auto-merge not enabled, no tag, no
  release. The only published release remains `v0.1.0-rc.1`. No
  production-certification claim follows. Objective 181 is NOT complete:
  182 (Codex), 183 (audited apply), 184 (final wrappers/qualification)
  remain REQUIRED (see final section).

## Changed paths (implementation head vs starting SHA)

All within the order's exact allowed paths; no other path touched
(diff-verified against the order's list; `oap/orders/181-a-*.md` and
`oap/active` unchanged since activation; `docs/README.md` did not need
changes):

New files:

- `app/slaif_gateway/services/catalog_refresh/sources.py` (497 lines) —
  bounded trusted HTTP acquisition: fixed official source registries
  (OpenRouter `/api/v1/models`, OpenAI `pricing.md` / `models.md` /
  per-model page `md`, ECB `eurofxref-daily.xml`), HTTPS + exact
  host/source-family allowlist, no credentials/unsafe ports, private/
  link-local destination guard (injectable resolver), manual redirect
  following (≤3) with per-attempt URL re-validation, 429 + finite
  Retry-After (≤30s, one retry), bounded 5xx/transport attempts (≤3),
  64KiB-chunk decoded-body caps per source kind (OpenRouter 4 MiB, docs
  512 KiB, pages 256 KiB, ECB 1 MiB), encoding allowlist
  (identity/gzip/deflate), request (128) and byte (32 MiB) budgets,
  URL-deduped fetches, safe error type (no bodies, no exception text).
- `app/slaif_gateway/services/catalog_refresh/collection.py` (853 lines) —
  the `collect_bundle` orchestrator: phase-1 whole-catalog snapshots plus
  the OpenAI model-docs index (required provenance source), OpenAI
  candidate → bounded model-page evidence (≤64 pages), standard-v1
  eligibility (exact identities, native-currency standard short-context
  Chat prices, page Model-ID/Chat/text/context/price exact-match),
  complete per-model reconciliation (proposed or one inventory entry with
  a machine reason), refresh preservation (priority/enabled/visible/
  streaming + flat caps only when the stored block is exactly
  `chat_completions`, denials preserved), ECB FX for exactly the needed
  non-EUR currencies.
- `tests/unit/test_catalog_refresh_collection.py` (804 lines, 19 tests) —
  mocked-source E2E through the REAL collector + validator +
  review/seal/verify pipeline (MockTransport + injected resolver):
  bootstrap both providers READY; single-model selection (only the
  selected page fetched); explicit ineligible selection BLOCKED
  (`missing_required_selection`); alias/batch/tier handling; router `-1`
  sentinels, non-text, deprecated, missing-limits, no-standard-prices
  inventory; conflicting pages BLOCK the selected row; true provider
  outage (503) → collection-level BLOCKED run with
  `collection_retrieval_failed`; supplied-bundle replay stays
  `offline_replay`; CLI e2e (bootstrap → sealed run → `verify` valid;
  503 world → exit 20).
- `tests/unit/test_catalog_refresh_sources.py` (488 lines, 23 tests) —
  transport controls against a mock transport: allowlist/host/HTTPS/
  port/credentials refusals; private-destination guard; redirect
  re-validation (3xx to another public host refused, never followed);
  relative-redirect join; 429/Retry-After honored and bounded; 5xx retry
  budget; body-cap truncation recorded; encoding allowlist; URL dedupe;
  budget exhaustion safe failure.

Modified files:

- `app/slaif_gateway/schemas/catalog_refresh.py` — typed
  `CollectionIdentity` (tool/code revision, window, profile, providers,
  model include, dedupe flag), `SourceRetrievalRecord` (requested/final
  URL, retrieved-at, outcome, status, content method/type/bytes/sha256,
  error code — never a body), `CollectionInventoryEntry` (disposition +
  reason code + detail); `RefreshBundle.collection` optional;
  `RENDERER_VERSION` → `181.1`; catalog-refresh models remain frozen.
- `app/slaif_gateway/services/catalog_refresh/source_evidence.py` —
  current official-format adapters: OpenAI standard pricing Markdown
  (Short/Long context input/cached/cache-write/output columns; standard
  section only, no tier flattening), OpenAI model pages (Model ID,
  endpoint table, modalities, context, max output, Text-tokens price
  table with two-table conflict detection), OpenRouter value-level price
  bounds (exponent syntax, non-zero per-1M ≥ 1e-9 quantum), `Cache
  writes` page row → `extra_pricing["cache_write"]`, extended dedupe
  signatures (tier/band/extra) with same-context contradiction blocking
  (`conflicting_model_ids`).
- `app/slaif_gateway/services/catalog_refresh/validation.py` —
  collection gates: `collection_source_unbacked` (every source record
  needs an ok retrieval record with same URL + sha256),
  `collection_retrieval_failed` (per-provider catalog URL must be
  retrieved; an outage is a retrieval failure, never disappearance),
  `collection_inventory_unsupported` (every inventory entry re-verified
  against parsed evidence/baseline); `source_evidence.scope` =
  `live_collection` / `offline_replay` + collection sub-dict; baseline
  models excluded via collection inventory report NOT_FETCHED "retained
  locally per collection inventory", not DISAPPEARED.
- `app/slaif_gateway/services/catalog_refresh/rendering.py` —
  scope-aware wording (banner sub-line, footer, source-evidence line,
  scope card `Collection` row, disappeared note, closing sentence — all
  reference the recorded collection identity so an offline re-review of a
  collected bundle stays truthful) and a new `Collection details`
  section rendered first in the details view (measured retrieval table,
  inventory grouped by reason, NOT_RUN + no-apply note).
- `app/slaif_gateway/cli/catalog_refresh.py` — new `collect` command
  (`--bootstrap` | `--refresh`, `--profile standard-v1`, `--providers`,
  `--models`, `--baseline-file` | `--db-url`, `--run-root`, `--seal-key`,
  `--json`; exit contract 0/10/20/30/65) reusing the shared review/
  seal/verify pipeline tail (`_finalize_review_pipeline`), collection
  baseline resolution (explicit file or read-only `--db-url` SQL
  capture; bootstrap is explicitly baseline-less; no DB outage may
  become bootstrap), collection-level failures → one safe BLOCKED run +
  exit 65/20, compact state/report/counts output; `review`/`verify`/
  `export-baseline` behavior preserved.
- `tests/browser/test_catalog_refresh_report.py` — new `collection`
  case (ready bundle + synthetic measured collection identity): visible
  "Collection details", "recorded collection identity", live-collection
  scope wording, measured retrieval records, NOT_RUN/no-apply note.
- `tests/fixtures/catalog_refresh/bundle-{first-install,refresh-ready,blocked,truncated}.json`,
  `tests/fixtures/catalog_refresh/report-layout/two-provider-long-ids.bundle.json`
  — exactly one line each: `renderer_version` `"180.6"` → `"181.1"`.
- `docs/catalog-refresh.md`, `docs/cli-reference.md`,
  `admin/catalog-refresh/README.md` — `collect` command and flags,
  source registry table, retrieval guarantees and limits, inventory
  reason table, collection-vs-replay semantics, FX derivation wording,
  refresh preservation, 181.1 versioning note;
  `scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=91`.

## C1 — one actual collection command and one report (closed)

`slaif-gateway catalog-refresh collect` is the single new entry point.
`--bootstrap` is explicitly baseline-less; `--refresh` requires
`--baseline-file` or `--db-url` (the existing read-only SQL capture).
Provider selection is a non-empty subset of `openai,openrouter` (default
both); `--models` is an exact-ID include list (empty = all eligible);
one-model selection works (verified live, see smoke). The command gathers
sources, builds the canonical typed bundle, runs the existing route/
pricing/FX validators and warning policy, seals one `REVIEW.html` run,
and prints the established compact state/report/counts line. Nothing is
imported; no import/apply/refresh command exists. A collection-level
failure publishes one safe BLOCKED run with a clear cause and nonzero
exit (unit-verified: 503 world → exit 20, `collection_retrieval_failed`
in the sealed `validation.json`). Run root and seal key stay outside the
repo (private 0700 scratch); seal key never inside the run tree; existing
ownership/no-symlink/no-clobber rules reused. No API server is required.

## C2 — trusted deterministic acquisition (closed)

See `sources.py` above. Key enforcement points, all with dedicated
tests: no arbitrary URL can enter the client (only registry specs);
redirects are followed manually and every hop is re-validated against the
allowlist (a 3xx to any other public host is refused, never followed);
DNS resolution is guarded against private/link-local destinations
(injectable resolver, tested); decoded (not content-length) bytes are
capped per source kind with truncation recorded; 429 is honored within a
finite Retry-After bound; every retrieval is recorded with exact
requested/final URL, retrieved UTC time, outcome, status, content
method/type/bytes, sha256, and parser version — retrieval time is never
reported as publication time; snapshots are deduped by URL/bytes (one
743 KiB OpenRouter payload is fetched once, never per model).

## C3 — contextual normalization, conservative eligibility, complete inventory (closed)

Every observed source model is reconciled exactly once (unit-asserted):
proposed, or exactly one inventory entry with a machine reason. Observed
reason codes in the literal live run A: `service_variant` (71 router
`:batch` rows), `page_no_chat` (8 OpenAI pages without Chat support),
`negative_router_sentinel` (5 router rows with the published `-1`
values — identity preserved, never zeroed or guessed), `page_unavailable`
(5 OpenAI models with no live page), `page_parse_failed` (1: o3, two
conflicting Text-tokens tables — excluded, REVIEW-flagged, not
fabricated), `missing_limits` (1 router row). The remaining approved
codes (`provider_alias_row`, `deprecated_model`, `non_text_modality`,
`no_standard_short_prices`, `page_model_mismatch`, `page_no_text`,
`page_price_conflict`, `baseline_contract_not_flat`,
`baseline_currency_mismatch`, `explicit_selection_excluded`,
`price_below_quantum`) are covered by the unit suite. Explicit
selection of an ineligible model BLOCKs (`missing_required_selection`),
while an outage of the same model class is a retrieval failure, never a
disappearance. Refresh preserves existing exact-route priority/enabled/
visible/streaming and flat capability blocks only when the stored
contract is exactly one `chat_completions` block — including explicit
denials; non-flat contracts and currency mismatches are excluded with an
explicit inventory reason and retained locally.

## C4 — ECB FX, native prices, exact arithmetic (closed)

ECB is fetched only when a proposed price is non-EUR. The quote is
recorded **as published** (EUR is the implicit base of the reference
XML; exact parsed Decimal; publication date from the XML). The native →
EUR rate the runtime looks up is derived by the existing tested FX gate
(exact Decimal reciprocal, 9-dp `HALF_UP`, bounded tolerance contract)
and is marked `derived: true` / `source_pair: "EUR-<CUR>"` in every
`fx_comparisons` entry and in the executable `fx-proposal.json` rows
(`derived_reciprocal: true`), with per-pair provenance
`ecb|EUR-<CUR>|ecb_reference_xml` and the sealed ECB source record
(URL, bytes, sha256, locator) retained. Provider prices stay in their
published native currency (OpenAI USD, OpenRouter EUR); the report's FX
line shows the derived conversion inline. No float arithmetic, no
stale-date substitution, no independent FX rows; the existing
>3/>7-day FX and >24/>72h source thresholds are unchanged. Live run A
records: published EUR→USD `1.1463` (2026-09-22), derived USD→EUR
`0.872371979` (NEW, no baseline).

## C5 — canonical bundle, capture identity, honest replay (closed)

The same typed JSON bundle is the sole semantic proposal artifact; the
collection identity is measured (tool/code revision, window,
per-URL retrieval records) and sealed inside the bundle. `source_evidence.scope`
separates what this invocation ACTUALLY fetched (`live_collection`) from
supplied/replayed declarations (`offline_replay`); the unit test
`test_supplied_bundle_replay_is_offline_scope` and the browser `collection`
case pin both. Sealed `verify` replays the captured bytes and metadata
only — no network, no re-sign, no SQL ("sql_evidence: replayed from
sealed bytes (no SQL executed during verification)"). A caller cannot
override a failed transport/parse to success: `collection_source_unbacked`
and `collection_retrieval_failed` are deterministic gates.
ResearchIdentity is honest `NOT_RUN` for Codex in this objective. All new
identity/evidence/proposal/validation/report bytes are covered by the
existing seal (verified: artifacts/correspondence/digests/hmac/report/
validation all `ok`).

## Acceptance results

- **AP1 (closed):** actual collect CLI → canonical bundle → existing
  validators → sealed REVIEW.html → verify, for bootstrap (live runs A
  and B) and supplied-baseline refresh (unit e2e with exported baseline
  document: READY refresh with preserved route attributes; blocked
  baseline currency mismatch retained locally). One-model selection
  verified live (run B). No API-server dependency; no application
  metadata mutation (no import/apply exists; DB is read-only for
  refresh baselines).
- **AP2 (closed):** current public shapes supported conservatively
  (live run A: 401 proposed route/pricing rows from the 2026-09-22
  snapshots); router `-1`, tiered/unsupported/ambiguous negatives are
  explicitly accounted (inventory reasons above); no ten-row
  preparation; no silent row loss (492/492 observed models reconciled:
  401 proposed + 91 inventory).
- **AP3 (closed):** transport bounds/redirect/host/private-address/
  compression/timeout/429/malformed-source controls are unit-tested
  (23 transport tests); actual captured metadata is distinct from
  replay (scope field + offline replay unit test + sealed verify).
- **AP4 (closed):** price units/currency/FX direction/date/freshness and
  locators are unit-tested; the live run shows the FX derivation chain
  end-to-end (published quote → derived rate, marked derived, locator
  `Cube@time=2026-09-22/Cube@currency=USD`); wrong model/alias/tier/
  field/source conflicts have negative unit tests (page mismatch,
  price conflict, alias without backing, conflicting authoritative
  pages).
- **AP5 (closed):** report states/counts/reasons accurate and readable
  (single REVIEW.html; Collection details section; scope-aware wording);
  live-source status honest (READY_WITH_WARNINGS with the two exact
  REVIEW findings); Codex NOT_RUN; no apply claim; seal/tamper replay
  green (verify `valid: yes` on both live runs; tamper regression suite
  green).
- **AP6 (closed):** mocked-source E2E (19 tests through the real
  collector/validator) and the bounded real unauthenticated live smoke
  below run on the literal final implementation; docs/lint/links/diff
  green (`DOCUMENTATION_CHECK=OK files=91`, `ruff check app tests`
  clean, `git diff --check` clean); exact-path proof above; no runtime
  accounting, dependency, or deployment changes (diff contains none of
  those paths).

## Local verification and actual exit codes

All run in-repo with `.venv/bin/python` / `.venv/bin/slaif-gateway`:

1. Focused regression (9 suites): **269 passed in 28.3s**, exit 0
   (source_evidence 72, bundle 30, policy 41, report 11, seal 28,
   cli_catalog_refresh 28, provider_catalog_proposal 17, sources 23,
   collection 19). Command:
   `pytest tests/unit/test_catalog_refresh_source_evidence.py
   tests/unit/test_catalog_refresh_bundle.py
   tests/unit/test_catalog_refresh_policy.py
   tests/unit/test_catalog_refresh_report.py
   tests/unit/test_catalog_refresh_seal.py
   tests/unit/test_cli_catalog_refresh.py
   tests/unit/test_provider_catalog_proposal.py
   tests/unit/test_catalog_refresh_sources.py
   tests/unit/test_catalog_refresh_collection.py`.
   Stability note (honest record): in the first 9-suite run after the
   FX-semantics change,
   `test_cli_collect_blocked_world_publishes_blocked_run` failed exactly
   once; it then passed in all subsequent runs (five further full
   9-suite runs plus ten isolated runs) and the failure was not
   reproduced or attributed. All reported results are from green runs.
2. Browser suite: **1 passed in 181.45s**, exit 0 (9 cases incl. the
   new `collection` scope case; worktree unchanged).
3. `ruff check app tests` → `All checks passed!`, exit 0.
4. `scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=91`.
5. `git diff --check` (vs branch start) → clean.

### Bounded live smoke (literal final implementation, unauthenticated official GETs only)

Run A — `slaif-gateway catalog-refresh collect --bootstrap
--profile standard-v1 --run-root /tmp/obj181a/live-smoke-runs
--seal-key /tmp/obj181a/live-smoke-seal.key`:

- state **READY_WITH_WARNINGS** ("2 review-level finding(s); no
  blockers"), exit 0, 11.3 s wall, run
  `collect-20260922-203047-042f9e2f7fb8`.
- 43 measured retrievals, 2026-09-22T20:30:47–55Z: OpenRouter
  `/api/v1/models` 200, 743,562 B, sha256 `99d63561c32b7fb8…`; OpenAI
  `pricing.md` 200, 23,950 B, `3046f29bd4b5081f…`; `models.md` 200,
  12,231 B, `4e0419118ce444a6…`; 39 OpenAI model pages (34 × 200, 5 ×
  404 for retired models `gpt-3.5-turbo-0125`, `gpt-3.5-turbo-1106`,
  `gpt-4-0613`, `gpt-4-turbo-2024-04-09`, `gpt-4o-2024-05-13` — pages
  removed upstream; recorded `page_unavailable`, not disappearance);
  ECB `eurofxref-daily.xml` 200, 1,547 B, `5584ddc3fe6a8619…`.
- Reconciliation: 492 observed models = 401 proposed route/pricing rows
  (openai 25, openrouter 376) + 91 inventory (service_variant 71,
  page_no_chat 8, negative_router_sentinel 5, page_unavailable 5,
  page_parse_failed 1 [o3], missing_limits 1).
- The two honest REVIEW findings: `gate:sources` (all required sources
  present; some REVIEW-classified) and `source_evidence_parse_failed`
  (openai/o3 `openai_model_doc:conflicting_price_row` — the live page
  carries two conflicting Text-tokens tables; excluded, never guessed).
- FX: published EUR→USD `1.1463` (2026-09-22) → derived USD→EUR
  `0.872371979` (derived: true, source_pair EUR-USD, state NEW).
- `catalog-refresh verify --run-dir … --seal-key …` → **valid: yes**,
  artifacts/correspondence/digests/hmac/report/validation all `ok`,
  `sql_evidence: replayed from sealed bytes (no SQL executed during
  verification)`, exit 0.

Run B — `slaif-gateway catalog-refresh collect --bootstrap
--profile standard-v1 --providers openai --models gpt-4o …` (same
run-root/seal key):

- state **READY** ("all recomputed gates verified; no review findings"),
  exit 0, 2.8 s wall, run `collect-20260922-203121-37c7c1a52b97`.
- 4 measured retrievals (2026-09-22T20:31:21–22Z): `models.md`,
  `gpt-4o.md` (200, 3,550 B, `c90025dc613e12e7…`), `pricing.md`, ECB
  XML — the single selected model's page only.
- 1 proposed route/pricing row: openai `gpt-4o`, USD, per-1M
  input `2.5` / cached_input `1.25` / output `10` (published standard
  short-context values), provenance `openai|gpt-4o|docs_page`; 38 other
  OpenAI candidates recorded `explicit_selection_excluded` (reconciled).
- `verify` → **valid: yes**, all checks `ok`, exit 0.

Both runs: one supported model per selected provider (run A: 25 OpenAI +
376 OpenRouter; run B: gpt-4o). The OpenRouter catalog grew between the
strategic 17:24Z probe (444 models / 730,233 B) and this 20:30Z run
(453 observed router rows / 743,562 B); live reality wins and no
classification changed. No inference, no authenticated discovery, no
email, no production access occurred. Full retrieval records (URL,
time, status, bytes, sha256 per record) are preserved in
`/tmp/obj181a/live-smoke-evidence.json`.

## CI (PR #318 implementation head)

Reported at implementation head `d0a6fc90c91a3d4074ec522152decac7eeaa7e17`
only (strategy checks the SELF-head CI after publication). All ten
check-runs `completed` / `success`, 0 pending, 0 failed
(poll log `/tmp/obj181a/ci-poll.log`, 2026-09-22T22:37Z): CodeQL, Docker
Compose smoke, Playwright browser smoke, PostgreSQL integration tests,
OpenAI-compatible E2E tests, Documentation hygiene, Unit/lint/migration
head, Analyze Python, Analyze (javascript-typescript), Analyze (python).

## Privacy and no-mutation proof

- No `.env`, credential, or saved-auth read; provider keys are never
  sent anywhere; the live smoke issued unauthenticated GETs to exactly
  the three registered publisher hosts (openrouter.ai,
  developers.openai.com, ecb.europa.eu) and their approved same-
  publisher model pages.
- No shared PostgreSQL 5432 access (bootstrap needs no DB; the refresh
  path reuses the existing read-only baseline capture against an
  explicit operator-supplied source), no Redis, no Docker, no system or
  dependency changes (diff contains no `pyproject`/lock/Docker/workflow
  paths).
- No Codex/subagent/model invocation: ResearchIdentity `NOT_RUN`. No
  import/apply execution. No real email. No secrets in artifacts:
  retrieval records and failure records carry only URLs, times, statuses,
  byte counts, digests, and error codes — never response bodies or
  exception text.
- `.local-provider-catalog/`, root `AGENTS.md`, `message.txt`, and all
  unrelated worktrees are untouched.

## Resource identity and cleanup

- All scratch lived outside the repository under `/tmp/obj181a` (0700):
  `live-smoke-runs/` (two sealed run dirs), `live-smoke-seal.key`
  (outside the run tree), session patch/verify scripts, probe artifacts.
- The pre-FX-fix smoke run was deleted before the final smoke so no
  stale sealed runs remain mixed with final-implementation evidence.
- At round end: the two sealed run directories (REVIEW.html/bundle/
  validation, ~12 MiB each) and session patch scratch are deleted;
  retained evidence: `ci-poll.log`, `live-smoke-evidence.json` (measured
  retrieval records cited above), and the response-OK marker.

## Limitations

- The live smoke is bounded by the order (one full bootstrap run + one
  single-model run); it is a shape/format qualification of the current
  official pages, not a full live catalog audit. Website schemas may
  change; the adapters target the 2026-09-22 shapes and live reality
  wins on re-collection.
- Models whose live pages are ambiguous (e.g., o3's conflicting price
  tables) or absent (five retired OpenAI snapshot models) are excluded
  with explicit REVIEW/inventory reasons — an honest partial package,
  not a silent loss and not a fabricated PASS.
- Existing-row updates remain BLOCKED until 183; no apply/refresh
  command exists in this version.
- No 128-worker HPC/full-matrix run: the order explicitly does not
  require a new DB/Redis/Docker/local-full/HPC matrix for this
  objective; the ordinary CI (10 check-runs) is green at the
  implementation head.

## Still REQUIRED for later objectives (not implemented here)

- **182** — Codex execution/isolation (the research boundary; kept
  `NOT_RUN` here).
- **183** — atomic audited apply/supersession/accounting (existing-row
  updates stay BLOCKED until then).
- **184** — final shell wrappers and clean-install/refresh/apply
  qualification.

This objective does not claim full-goal completion; nothing above erases
those requirements.

## Status

Implementation complete and pushed; PR #318 open at implementation head
`d0a6fc90c91a3d4074ec522152decac7eeaa7e17` with this report-only SELF
commit on top (first parent = implementation head). All local gates
green; CI green at the implementation head. Awaiting strategic review;
no merge, no tag, no release, no next-order pre-activation.
