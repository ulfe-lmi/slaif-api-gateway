# OAP Execution Report — 181-b: Correct catalog pricing eligibility and refresh preservation

## Identity

- Objective: 181 — authoritative catalog collection (SAME PR 318, branch `oap/181-authoritative-catalog-collection`)
- Round: **181-b** (AMEND), selected by `oap/active` = `181-b`
- Order: `oap/orders/181-b-correct-catalog-pricing-and-refresh-semantics.md` (committed unchanged this round)
- Starting HEAD (round-start activation commit): `4dcae0fa216f7c77f588f7289104aef10d7c6781`
- Implementation head: `109461ab428ec7efaf32b7a2625f13d559f2b856`
- Report commit: SELF (first parent = implementation head `109461ab428ec7efaf32b7a2625f13d559f2b856`; verified with `git rev-parse HEAD^` before the OK signal)
- Canonical `main`: `6d07e9d304fccd40af7c2f2fdd0bf3e22f7893bf`
- PR 318 head before this round: `32d3e91113046425cb71ce1a048e4bc1a0b54cca` (181-a immutable report head)
- PR 318 head after this round: the SELF report commit (verified via `git ls-remote origin oap/181-authoritative-catalog-collection` and `gh pr view 318 --json headRefOid`, both equal to the report head, before the two-byte OK)

## Summary

181-b closes the four independently reproduced strategic findings at the exact
181-a head: (B1) flat proposals that silently dropped published billable
charges and flattened published long-context prices; (B2) the
`baseline_target_mismatch` representation bug on real
`collect --refresh --baseline-file` runs and the alias-clobbering refresh
behavior; (B3) the models-index parser yielding zero models from the current
linked-index format, leaving observed IDs unexplained; (B4) unpinned CLI exit
semantics. All fixes live in the allowed catalog-refresh paths; no runtime
pricing/accounting/forwarding/import behavior changed; no apply or
refresh command was added; transport/capture-identity fixes remain deferred
to the next same-PR round as the order requires.

## Changed paths (implementation commit `109461a` only)

- `app/slaif_gateway/services/catalog_refresh/source_evidence.py`
- `app/slaif_gateway/services/catalog_refresh/collection.py`
- `app/slaif_gateway/services/catalog_refresh/validation.py`
- `app/slaif_gateway/services/catalog_refresh/rendering.py`
- `app/slaif_gateway/schemas/catalog_refresh.py`
- `app/slaif_gateway/cli/catalog_refresh.py`
- `tests/unit/test_catalog_refresh_collection.py`
- `tests/unit/test_catalog_refresh_source_evidence.py`
- `tests/fixtures/catalog_refresh/collection/models-index-current.md` (new bounded synthetic current-format fixture)
- `docs/catalog-refresh.md`
- `docs/cli-reference.md` (catalog-refresh section only)
- `admin/catalog-refresh/README.md`

(`bundle.py` required no changes this round. Commit stat: 12 files,
+2444/−129. `oap/orders/181-b-...md` and `oap/active` byte-identical;
`oap/reports/181-a-...md` untouched.)

## B1 — Decision: shared, independently enforced flat billing eligibility

One deterministic policy (`standard_v1_billing_decision`) decides flat
standard-v1 billing eligibility for each model from **all** authoritative
observations — every billing tier, every context band, every published
pricing key. The collector runs it **before proposal** (an ineligible
model's page is never even fetched) and the validator **recomputes it from
the parsed official evidence for every bundle**, live collection and
offline supplied-bundle replay alike. Capturing an observation is not
enforcing it.

| Observation | Decision |
|---|---|
| core text dims `input` / `cached_input` / `output` per 1M (short band) | proposed |
| positive `internal_reasoning` (router) published per 1M | **carried** as `reasoning` dimension (`per_1m_tokens`) |
| positive `request` (router) published per request | **carried** as `request` dimension (`per_request`) |
| a legitimate `0` on any billable key | no-charge, never a missing fact |
| published long-context standard prices (OpenAI standard tier), **including $0** | excluded `long_context_prices_unrepresentable` (a published contextual price; no cheaper-band choice) |
| contextual override tiers (`overrides`, JSON array or stringified list) | excluded `contextual_overrides_unrepresentable` |
| positive `input_cache_write` / `input_cache_write_1h` (router) or `cache_write` / `cache_write_long` (OpenAI) charges | excluded `cache_write_charges_unrepresentable` |
| published pricing key outside the recognized set (e.g. `per_image`) | recorded `unknown_pricing_keys`, excluded `unknown_billing_dimension` |
| source `-1` sentinel on **any billable dimension** (core, reasoning, request, cache-write, web_search) | excluded `negative_router_sentinel` (unverifiable charge; never converted to zero) |
| conflicting positive billable observations for one dimension | excluded `conflicting_billing_observation` (equal observations are not a conflict) |
| positive charge that quantizes to zero at the 9-dp import contract | excluded `price_below_quantum` (never stored as a free price) |
| positive hosted `web_search` charge | **accepted unreachable** under the explicit tested policy (hosted web search is a denied hosted operation in the standard-v1 profile), with the evidence shown on the route warnings — never silently dropped |
| OpenAI `batch` / `flex` / `fast` tiers | **service variants** of the same model, mirroring OpenRouter `:batch`: never block and never flatten the standard tier; a model with only non-standard rows is `no_standard_short_prices` |

Additional B1 semantics, all pinned by tests:

- explicitly selecting an excluded model **BLOCKs** (`missing_required_selection`);
- a live collection that fetched sources but proposed nothing is
  `collection_empty_bootstrap` (BLOCKED) — an empty usable bootstrap is never
  READY (a refresh against an existing baseline may legitimately propose
  nothing while retaining every baseline model);
- supplied-bundle bypass negatives: dropping a carried positive charge
  blocks (`proposed_row_billing_dim_missing`), altering it blocks
  (`proposed_row_billing_dim_mismatch`), and injecting a proposal for a
  billing-ineligible model blocks (`proposed_row_billing_ineligible` with the
  exact policy reason in the finding);
- flat, complete siblings stay usable in default discovery; exclusions are
  aggregated with exact machine reasons in the one report; unsupported-row
  exclusions do not claim a provider-wide failure;
- no FX, price, unit, or permission is inferred; the exact Decimal ECB
  reciprocal/date/freshness contracts are unchanged.

## B2 — Decision: real refresh identity and route-policy preservation

- **Target representation**: the collector declares `target_database` as the
  **database name** plus explicit `target_host` / `target_port` fields
  (schema-gated, credential-checked). The full `host:port/database` identity
  remains bound inside the hashed baseline content: a substituted document
  still fails the digest check (`baseline_identity_mismatch`), and any
  database/host/port mismatch BLOCKs (`baseline_target_mismatch`). No check
  was weakened.
- **Local route authority is keyed by upstream and never overridden**:
  - one flat-representable exact baseline row is a local route identity: the
    proposal preserves its public alias (`requested_model`), match type,
    `priority`, `enabled`, `visible_in_models`, `supports_streaming`, and its
    capability block projected onto flat keys **only when the contract is
    exactly one `chat_completions` block** — including explicit denials
    (denied stays denied; nothing is granted);
  - a genuinely unconfigured model keeps the exact upstream name;
  - **multiple aliases/priorities are never reduced** (`baseline_multiple_routes`,
    both retained with `NOT_FETCHED` dispositions);
  - **prefix/glob baseline routes covering an upstream** retain the model
    (`baseline_contract_not_flat`); the routing pattern itself is local
    state — an explicit `NOT_FETCHED` retention, never a source disappearance;
  - non-flat exact contracts and non-USD baseline pricing currencies are
    retained locally with their exact inventory reasons;
  - a baseline **public alias remaining mapped to a present upstream is not a
    disappeared model** (inventory dispositions resolve alias → upstream);
  - a supplied bundle that replaces the alias with an upstream-named route or
    adds a parallel upstream-named route BLOCKs (`alias_route_replaced`, both
    conditions pinned).
- Pairing semantics: model/pricing facts under an upstream identity pair
  through the route's `upstream_model` (the established 180-f pairing
  authority) in both directions, so preserved-alias proposals validate
  without missing-pairing blockers; unpaired phantom identities still block.
- No new upstream-named route is ever invented because an alias exists;
  provider destinations are unchanged; existing-row changes remain BLOCKED
  under the create-only semantics until 183.

## B3 — Decision: complete inventory and honest semantics

- The current OpenAI linked-index format is parsed with a bounded
  deterministic extraction: model-page bullets
  (`/api/docs/models/<id>.md`) — the ID is the **page path, never the display
  name**; the documented specialized-models exception that declares
  `Model ID: \`<id>\`` inline (exactly one accepted; zero or more than one
  deterministically skip the bullet); uppercase/path-invalid IDs are a format
  error; duplicates across sections dedupe to the first occurrence;
  non-bullet prose links are never extracted. Index rows are identity-only
  (parser `openai_models_docs/v2`); the legacy block format still parses
  (`openai_models_docs/v1`) unchanged.
- **Every observed model ID — including index-only IDs — receives exactly one
  explained disposition** (`index_only_no_standard_prices` for the
  index-only case); the strategic-reproducer selection of an index-only model
  BLOCKs.
- `source_model_counts` records distinct observed **source** identities per
  provider, deliberately separate from local route/alias rows: a source
  catalog is not a route table, and pricing rows are not the entire official
  model catalog. The report renders the row only when non-empty (old bundles
  re-render byte-identical).
- Supplied inventory claims are recomputed: billing-exclusion entries are
  re-derived with the shared policy (the exact reason must match),
  `price_below_quantum` requires an eligible decision plus a below-quantum
  carried charge, `baseline_contract_not_flat` is upstream-aware (one
  non-flat exact row or a covering wildcard route), `baseline_multiple_routes`
  requires ≥2 exact rows, `index_only_no_standard_prices` requires an
  identity-only observation and no standard short prices.

## B4 — Decision: actual CLI exit statuses and stage wording

Pinned by fully mocked CLI tests (injected world, mocked DNS resolver — no
live DNS, coherent clocks):

| Scenario (real `collect`/`review` CLI path) | Exit | State |
|---|---|---|
| bootstrap, eligible world | 0 | READY |
| `--refresh --baseline-file`, valid canonical-digest baseline (the 181-a BLOCKED reproducer) | 0 | READY |
| FX publication age 4 calendar days (review threshold 3) | 10 | READY_WITH_WARNINGS (`fx_stale_review`) |
| FX publication age exactly 3 calendar days (fresh boundary) | 0 | READY |
| provider catalog 503 | 20 | BLOCKED — run published, `stage` starts with `live collection` |
| substituted baseline document (digest mismatch) | 20 | BLOCKED `baseline_identity_mismatch` |
| tampered declared `target_database` or `target_host` | 20 | BLOCKED `baseline_target_mismatch` |
| semantically blocked collect (e.g. retrieval failure) | 20 | BLOCKED — the 65 path now reserves for unpublished data errors (e.g. unreadable/invalid `--baseline-file`) |
| `verify` of a valid sealed run | 0 | valid |

The `stage` parameter is forwarded through every `_blocked_identity`
publication so a collect-stage block shows the live-collection wording, not
the offline-review line.

## Measured commands and results (this machine, this round)

Focused regression (9 suites, `tests/unit/test_catalog_refresh_{source_evidence,bundle,policy,report,seal,collection,sources}.py`, `test_cli_catalog_refresh.py`, `test_provider_catalog_proposal.py`):

```
308 passed in 30.71s
```

Browser report test (renderer import safety / layout assertions):

```
tests/browser/test_catalog_refresh_report.py: 1 passed in 178.16s
```

Static gates: `python -m ruff check app tests` → `All checks passed!`;
`scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK files=91`;
`git diff --check 4dcae0f` → clean. No `baseline_route_attrs` remnants
(anywhere in `app`/`tests`); proposal-builder call sites match the new
signatures.

New/updated tests: 34 test functions in
`tests/unit/test_catalog_refresh_collection.py` (B1 reproducers, supplied
bypass negatives, OpenAI tier/band/extra cases, B2 alias/prefix/retention
reproducers, B3 index cases, CLI exit/stage pins) and 5 in
`tests/unit/test_catalog_refresh_source_evidence.py` (direct shared-policy
cases both providers, request/unknown-key parsing, current linked-index
fixture parse, fail-closed index shapes) plus one bounded synthetic
current-format fixture.

### Bounded live smoke (authorized unauthenticated official GETs, literal final code)

Run A — `slaif-gateway catalog-refresh collect --bootstrap --providers openai,openrouter --run-root /tmp/obj181b/live-runs/a --seal-key /tmp/obj181b/seal.key --json`:

- **exit 10** (READY_WITH_WARNINGS), `verify` exit 0;
- 293 proposed models (openai 17 / openrouter 276) — down from 181-a's 401
  (openai 25 / openrouter 376) exactly as the corrected policy requires:
  inventory now reconciles `contextual_overrides_unrepresentable` 52,
  `unknown_billing_dimension` 28, `cache_write_charges_unrepresentable` 20,
  `long_context_prices_unrepresentable` 10, `negative_router_sentinel` 5,
  `service_variant` 71, `index_only_no_standard_prices` 70,
  `page_no_chat` 6, `page_unavailable` 5, `page_parse_failed` 1,
  `missing_limits` 1 (269 inventory entries; every observed model reconciled
  once);
- 40 routes carry visible `web_search` accepted-unreachable evidence;
- 33 retrievals (28 ok, 5 failed): all 5 failures are HTTP 404s of
  deprecated dated OpenAI model pages listed in the pricing document
  (`gpt-3.5-turbo-0125`, `gpt-3.5-turbo-1106`, `gpt-4-0613`,
  `gpt-4-turbo-2024-04-09`, `gpt-4o-2024-05-13`) — recorded as observed
  incompleteness, never disappearance;
- 2 review-level findings: `gate:sources` (optional sources
  REVIEW-classified/aged) and `source_evidence_parse_failed` (one live model
  page with a genuinely conflicting price row — fail-closed, not proposed);
- source_model_counts: openai 109, openrouter 453 (source catalog
  identities, distinct from the proposed route rows);
- FX: ECB EUR→USD **1.1463** published 2026-09-22 (fresh), recorded as
  published; derived USD→EUR **0.872371979** (9-dp HALF_UP reciprocal).

Run B — `slaif-gateway catalog-refresh collect --bootstrap --providers openai --models gpt-4o --run-root /tmp/obj181b/live-runs/b --seal-key /tmp/obj181b/seal.key --json`:

- **exit 0** (READY), `verify` exit 0; exactly one proposed model
  (`openai/gpt-4o`); 4 retrievals (pricing, models index, model page, ECB),
  all ok.

Full URL/status/bytes/digest/retrieval evidence:
`/tmp/obj181b/live-smoke-evidence.json` (outside the repository; seal keys
and run directories stay outside Git). **Explicit disclaimer: transport and
capture-identity assurance remains UNCLOSED** — the deferred findings below
are open; this smoke proves bounded live collection behavior, not transport
closure.

## Negative / privacy / no-mutation / no-runtime-diff evidence

- No shared PostgreSQL 5432 access, no shared-cluster config/log reads, no
  privileged postgres identity, no live database anywhere in this round
  (all refresh tests use synthetic in-memory/`--baseline-file` documents;
  the CLI db-snapshot path is untouched).
- No `.env` reads, no credential/secret access, no saved-auth reads; seal
  keys live in `/tmp/obj181b/` with 0600 and never enter Git or logs.
- No live inference, no provider credentials, no email, no Codex
  invocation (`research` remains `NOT_RUN` in both live bundles), no
  production URL use, no new dependencies, no package/system changes.
- No runtime diff: only the six allowed catalog-refresh modules (plus
  schemas/CLI/docs/tests/fixture) changed; no runtime
  pricing/accounting/forwarding/import execution; no DB model or migration
  change; `RENDERER_VERSION` unchanged (`181.1`); the rendered muted note
  now states the exact flat-eligibility policy.
- No merge, no auto-merge, no tag/release, no new PR; PR 318 amended only.
- Live smokes were the only network egress, bounded to the registered
  official sources (unauthenticated GETs).

## Documentation impact statement

`docs/catalog-refresh.md` now states: the exact flat-eligibility policy
(including the web_search accepted-unreachable policy and the
batch/flex/fast service-variant rationale), the new inventory reason
codes, the models-index-as-model-evidence section, the refresh
preservation semantics (alias preservation, multiple-alias and
wildcard retention, alias-replacement blocking, target identity
representation), the collection-vs-replay re-verification bullets
(`collection_empty_bootstrap`, billing recomputation, `alias_route_replaced`),
and a `collect` row in the exit-code table with the live-collection stage
wording. `docs/cli-reference.md` (catalog section) and
`admin/catalog-refresh/README.md` carry the matching concise statements.
Internal links verified by `scripts/check_documentation.py`.

## Corrections to 181-a claims (181-a remains immutable)

1. **"OpenRouter EUR" was a report typo**: the code and the source have
   always been USD. Corrected in this report and the docs; the correct USD
   code was never relabeled to match the typo.
2. **The RWW/exit-0 statement was mis-measured** (measured through a pipe
   that masked the CLI exit). The exact CLI behavior is now pinned by
   mocked end-to-end tests: READY 0, READY_WITH_WARNINGS 10, BLOCKED 20
   (blocked runs always published with the `live collection` stage line),
   65 reserved for unpublished data errors.
3. **`baseline_target_mismatch` on real `collect --refresh --baseline-file`
   was a real representation bug** (collector declared `host:port/db` while
   the finalizer compared the database name): fixed as database-name +
   explicit host/port fields with the digest binding preserved, and pinned
   by a real-CLI test that now exits 0.
4. **The models index was silently ignored** (parser yielded 0 models from
   the current linked format; index-only IDs had no disposition): fixed and
   pinned; source vs route counts are now reported separately.

## Remaining findings (deferred — UNCLOSED, no closure claimed)

Per the order, these stay for the next semantic-independent same-PR round:

- offline review of an intact collected bundle, with network forbidden,
  still claims `live_collection` — presence of a caller-supplied
  `CollectionIdentity` is not measured execution evidence;
- mixed public + loopback DNS is accepted; arbitrary non-registry
  path/query on an approved host is accepted;
- static transport budget / connection-binding / decompression concerns;
- package-version-only code identity.

Transport/capture-identity closure is explicitly **not** claimed in this
round, and no live-collection claim is made for offline replay.

## Objective 181 status

181-b closes the B1–B4 findings of this order. It does **not** close
Objective 181: **182 (Codex isolation), 183 (atomic pricing/FX
supersession/accounting), and 184 (final wrappers and qualification)
remain REQUIRED**, and the full human mandate (one refresh command → one
self-contained report → one explicit audited apply) is not complete. Not all
181 APs are closed; no final 181 public qualification is claimed.

## CI (implementation head only)

All ten check-runs at the implementation head `109461ab428ec7efaf32b7a2625f13d559f2b856`
succeeded (CI does not resolve the deferred transport/capture findings; it
confirms the implementation is regression-clean at this head):

  - Analyze (javascript-typescript): success
  - Analyze (python): success
  - Analyze Python: success
  - CodeQL: success
  - Docker Compose smoke: success
  - Documentation hygiene: success
  - OpenAI-compatible E2E tests: success
  - Playwright browser smoke: success
  - PostgreSQL integration tests: success
  - Unit, lint, and migration head: success

CI was observed on the implementation head only, as the order requires; the
report-only SELF commit is a documentation change and is not claimed to
re-qualify the matrix.

