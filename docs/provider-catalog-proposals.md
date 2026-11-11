# Provider Catalog Proposals

SLAIF includes proposal-only tooling for OpenAI and OpenRouter provider catalog
metadata.

The workflow is operator-assisted and deterministic first:

1. collect official provider metadata
2. compare multiple source methods
3. generate local proposal artifacts
4. preview the generated TSV through the existing route/pricing import preview
5. execute an import only after explicit operator confirmation and audit

The proposal workflow never directly mutates provider configs, model routes,
pricing rows, FX rows, keys, quotas, or usage rows.

## Commands

```bash
slaif-gateway provider-catalog propose openrouter \
  --output-dir /tmp/slaif-provider-catalog-openrouter \
  --paired-ready-only \
  --ordinary-chat-only

slaif-gateway provider-catalog propose openai \
  --output-dir /tmp/slaif-provider-catalog-openai \
  --include-api-models

slaif-gateway provider-catalog propose all \
  --output-dir /tmp/slaif-provider-catalog-all
```

Optional comparison flags:

- `--max-models N` (finite per-provider cap, honored for BOTH supported
  providers AFTER include/exclude filtering; models beyond the cap are
  reported as omitted scope, never silently mixed in)
- `--source api`
- `--source assisted`
- `--include-model`
- `--exclude-model`
- `--endpoint-scope chat_completions`
- `--endpoint-scope responses`
- `--currency EUR` (output currency; see [Output currency and FX
  conversion](#output-currency-and-fx-conversion-217-a); default `USD`
  keeps the native source prices and needs no database)
- `--save-source-snapshots`
- `--json`
- `--allow-zero-prices`
- `--paired-ready-only`
- `--ordinary-chat-only`
- `--include-multimodal-chat-candidates`
- `--package`
- `--all-packages`
- `--include-deprecated`
- `--include-ambiguous-capabilities`

OpenAI assisted cross-checks are optional and require explicit operator
acknowledgement. They use `OPENAI_ADMIN_DISCOVERY_API_KEY`, never
`OPENAI_API_KEY`.

Before any import preview, run a bounded OpenRouter smoke. The recommended
first-pass command is:

```bash
slaif-gateway provider-catalog propose openrouter \
  --output-dir /tmp/slaif-provider-catalog-openrouter-smoke \
  --max-models 50 \
  --fetch-details-limit 10 \
  --paired-ready-only \
  --ordinary-chat-only \
  --no-save-source-snapshots \
  --json
```

For an actual import-preview preparation run, the recommended safe sequence is:

```bash
slaif-gateway provider-catalog propose openrouter \
  --output-dir "$OUT" \
  --max-models 500 \
  --fetch-details-limit 50 \
  --paired-ready-only \
  --ordinary-chat-only \
  --no-save-source-snapshots \
  --json

slaif-gateway pricing import \
  --format tsv \
  --file "$OUT/pricing-proposal.tsv" \
  --dry-run \
  --json

slaif-gateway routes import \
  --format tsv \
  --file "$OUT/routes-proposal.tsv" \
  --dry-run \
  --json

slaif-gateway pricing import \
  --format tsv \
  --file "$OUT/pricing-proposal.tsv" \
  --execute \
  --confirm-import \
  --reason "operator-reviewed pricing import" \
  --json

slaif-gateway routes import \
  --format tsv \
  --file "$OUT/routes-proposal.tsv" \
  --execute \
  --confirm-import \
  --reason "operator-reviewed route import" \
  --json
```

For OpenRouter reviewed import preparation, package presets are preferred over a
single flat catalog. The default safe import candidate is
`openrouter-chat-text`:

```bash
slaif-gateway provider-catalog propose openrouter \
  --output-dir "$OUT" \
  --max-models 500 \
  --fetch-details-limit 50 \
  --package openrouter-chat-text \
  --package openrouter-chat-image \
  --package openrouter-chat-audio \
  --package openrouter-chat-multimodal \
  --package openrouter-responses-text \
  --no-save-source-snapshots \
  --json
```

Package aliases are also accepted:

- `chat-text`
- `chat-image`
- `chat-audio`
- `chat-multimodal`
- `responses-text`

`--all-packages` emits every current OpenRouter package preset.

## Admin GUI proposal workspace (217-a)

The same generator is available as a bounded queued job in the admin
dashboard "Catalog workspace" (`/admin/operations/catalog/proposals`),
default-off behind the same `CATALOG_REFRESH_*` operator setup as the
[catalog refresh GUI](catalog-refresh.md#admin-gui-workspace-g15-delivered-by-217-a).

- The form exposes the SAME closed choices as the CLI: provider scope
  (`openai` / `openrouter` / `all`), the closed endpoint-scope vocabulary
  (`chat_completions`, `responses`), the closed package presets, currency,
  and the finite model/detail/web-call caps (the public `max_models` cap is
  PER PROVIDER and is honored for both providers after include/exclude
  filtering).
- Source methods are captured honestly: OpenRouter ALWAYS uses docs + the
  models API (the selection does not remove either); `api`/`assisted` are
  OpenAI-only and require the EXISTING `OPENAI_ADMIN_DISCOVERY_API_KEY`
  deployment secret (never the model-facing key) plus, for `assisted`, the
  explicit risk acknowledgement. `max_web_calls` is a REQUESTED prompt
  budget, not proven hard provider call/cost enforcement. Unsupported
  combinations (e.g. OpenRouter + assisted) are refused before any
  dispatch or network activity, with a useful fixed refusal rather than a
  post-fetch failure.
- The include/exclude model filters are the closed `catalog_upstream`
  record choice (official upstream IDs, latest ~100 + older search +
  manual entry; oversized explicit selections are refused, never
  truncated).
- The generated route/pricing TSVs (plus normalized JSON, warnings,
  report, source manifest) are bounded downloads from operator custody,
  with a CLOSED preset + closed-file package selector; they bridge to the
  EXISTING import preview and are UNSEALED proposal artifacts (no
  cryptographic "verified" claim). The GUI displays prices with their
  actual units (token dimensions per 1,000,000 tokens; the request
  dimension per request), with the row's ACTUAL currency (the output
  currency after one captured FX conversion, or native USD by default).
  Non-USD output uses a real FX conversion as documented in
  [Output currency and FX conversion](#output-currency-and-fx-conversion-217-a).
- The job acknowledgement and "Refresh status" navigation bind to the
  EXACT server-created job id (an explicit unknown or foreign-family id is
  refused, never substituted by the newest job), and the result page
  displays the provider scope that was actually generated.

## Output currency and FX conversion (217-a)

The proposal's `--currency` option (CLI) and the Currency select (GUI:
the closed `USD` / `EUR` / `GBP` / `CHF` choices) set the OUTPUT currency
of the generated pricing rows. Official source amounts stay NATIVE USD
through parsing and cross-checking (assisted outputs included) — the
conversion is a bounded post-extraction step, never an instruction to a
source or model.

- **USD (default)**: the identity conversion. Native source prices are
  emitted unchanged, with NO database access — USD output remains
  offline-capable.
- **Non-USD**: ONE explicit, currently-active, configured
  **direct USD→target** rate row (managed through the existing FX
  administration, e.g. `slaif-gateway fx add`) is captured exactly once,
  at job start, with a single database transaction that is closed before
  any network or generation. That one captured rate converts EVERY
  monetary dimension (per-1M-token prices and the per-request price) of
  EVERY row with one Decimal conversion following the established
  price contract (quantum 0.000000001, ROUND_HALF_UP, Numeric(18,9)
  bound). Missing/zero prices stay missing/zero; a positive price that
  would underflow to zero or overflow the import bound refuses the whole
  proposal.
- Each candidate batch (the root output and every selected package) is
  converted before ITS artifacts are written, and ALL of them use the
  ONE captured FX fact — so a completed proposal's root JSON/TSV/report
  and package outputs agree. A failed or partial generation is NOT a
  complete proposal and must not be imported. Each converted row keeps
  the original USD amounts plus the applied FX pair, rate UUID, rate,
  validity window, and capture time in its metadata; the normalized
  JSON and source manifest carry the same FX fact, and the report
  states the applied conversion. The official source unit
  (e.g. `usd_per_token`) is never relabeled.
- Refusal semantics (CLI and GUI): a missing or not-currently-active
  configured direct pair (including an unconfigured database) refuses
  the proposal safely BEFORE generation (`proposal_fx_unavailable` /
  `proposal_fx_rate_missing` in the GUI job; a fixed safe CLI error).
  Prices are NEVER relabeled, and there is no inferred inverse,
  cross-currency graph, or automatic FX fetch. Other validation or
  conversion failures (e.g. underflow/overflow) fail the job normally
  without publishing a complete proposal.
- The captured rate is FROZEN until the proposal is re-run; re-running
  captures the latest active configured pair at that time. Runtime
  quota/accounting behavior is unchanged by a proposal's output currency.
  This proposal-side USD→target conversion is DISTINCT from the UNCHANGED
  runtime accounting requirement that published pricing resolves to
  EUR. The existing pricing service captures FX during REQUEST
  pricing/accounting, not during this proposal import — so: a GBP
  output needs the configured USD→GBP pair for the proposal
  conversion, and USING those GBP prices for EUR accounting still needs
  the configured GBP→EUR pair under the unchanged runtime rules (EUR
  pricing is identity). Importing prices does not create or infer that
  second pair. The two surfaces use independently configured direct
  pairs; there is no rate graph, no inferred inverse, and no accounting
  change.

This is an intentional correctness fix: before 217-a, a non-USD
`--currency` relabeled the native USD amounts (the pre-existing
dual-currency per-million label behavior). The shared CLI and GUI
generator now performs the same verified conversion; the default USD
output is unchanged.

## Source Methods
## Source Methods

OpenRouter:

- official public `https://openrouter.ai/api/v1/models`
- official docs/reference for pricing-unit confirmation
- optional `links.details` enrichment

OpenAI:

- official pricing docs for pricing
- official models docs for endpoint and feature context
- optional `GET /v1/models` availability check using
  `OPENAI_ADMIN_DISCOVERY_API_KEY`
- optional existing OpenAI-assisted proposal workflow as a cross-check only

OpenAI docs extraction is intentionally conservative. Documentation navigation
labels, product/category headings, bare context-window labels, and unsupported
modality buckets are never treated as model IDs. A docs-only OpenAI run may
produce zero ready rows; that is acceptable and safer than emitting bad import
rows.

## Output Files

Every run writes:

- `source-manifest.json`
- `provider-catalog-normalized.json`
- `routes-proposal.tsv`
- `pricing-proposal.tsv`
- `provider-catalog-report.md`
- `warnings.json`

When package presets are requested, the run also writes:

- `packages/package-index.md`
- `packages/package-index.json`
- `packages/<package>/package-manifest.json`
- `packages/<package>/routes-proposal.tsv`
- `packages/<package>/pricing-proposal.tsv`
- `packages/<package>/model-review.md`
- `packages/<package>/package-report.md`

Package presets are capability supersets within an endpoint family:

- `openrouter-chat-text`: baseline ordinary text Chat Completions package
- `openrouter-chat-image`: superset of `openrouter-chat-text`, adding
  image-input to text-output rows only
- `openrouter-chat-audio`: superset of `openrouter-chat-image`, adding only
  safe audio-capable Chat rows that current SLAIF chat capability and pricing
  metadata can represent
- `openrouter-chat-multimodal`: broader staged review package for safe chat
  multimodal rows
- `openrouter-responses-text`: separate `/v1/responses` endpoint family, not a
  Chat superset

Responses package names beyond `openrouter-responses-text` remain future/report
only until current `main` has explicit route/pricing capability evidence for
them.

`openrouter-chat-text` is the default safe import candidate. Image, audio, and
Responses packages are separate review surfaces, not mixed into the ordinary
text package.

The generated TSV files are input to the existing SLAIF import preview flows.
They are not imports by themselves.

`routes-proposal.tsv` and `pricing-proposal.tsv` are written in the same column
shapes accepted by the actual route/pricing dry-run import validators on
current `main`.

The proposal command self-validates the generated TSV artifacts before it
reports success. If a TSV has malformed rows, invalid JSON cells, invalid
boolean or decimal fields, suspicious secret-like content, or a broken
`source_url` / `source_retrieved_at` split, the run fails with
`proposal_tsv_validation_failed`.

For OpenAI docs-only proposals, readiness additionally requires:

- a canonical OpenAI model ID
- explicit support for a currently implemented SLAIF endpoint
- complete parseable pricing for the target endpoint, including output price
- supported modality/feature alignment for that endpoint

Unsupported modality rows such as image-only, audio-only, embeddings-only,
files, moderation, search-specific, or other non-chat categories remain
report-only and must not appear in Chat Completions import TSV rows.

For OpenRouter and OpenAI Chat Completions import preparation, ordinary text
chat rows are the default. Ambiguous multimodal, image, audio, VL, realtime,
music, and similar rows remain report-only unless the operator explicitly opts
into multimodal chat candidates.

## Comparison, Confidence, And Warnings

The workflow compares source sets and reports:

- model present in docs but missing from API
- model present in API but missing from docs
- missing pricing
- zero-price rows that remain review-required
- pricing disagreement
- unit confirmation gaps
- deprecated or expiring models
- unsupported modalities
- hosted-tool or search-specific models
- future-endpoint/report-only rows

Confidence is conservative:

- `high`: direct official sources agree
- `medium`: deterministic docs-only parse is internally consistent
- `low`: assisted-only or otherwise ambiguous

## Import Boundary

Generated proposals do not change runtime behavior until an operator:

1. previews the TSV with the existing pricing/route import validators
2. executes the import with `--execute`
3. confirms the import with `--confirm-import`
4. supplies a non-empty audit reason with `--reason`

Pricing remains a reviewed local accounting assumption until imported. It is
important for quota/accounting, but it is not invoice-grade truth by itself.

Dry-run remains the default safety checkpoint. The CLI import commands reject
implicit writes; without `--dry-run` or the full
`--execute --confirm-import --reason ...` sequence, they exit non-zero.

Import execution mutates local route/pricing metadata only after explicit
confirmation. It does not call providers, does not fetch new proposal data, and
should be rehearsed against a disposable local database before any real local
deployment import.

Package review files are generated for human review. `model-review.md` uses a
compact HTML table with short columns, `—` for missing values, and separate
reasoning-capable vs separately priced reasoning presentation. These review
files are for operators; they are not import sources by themselves.

Zero-price pricing rows are report-only by default. They are not pricing-import
ready unless the operator explicitly passes `--allow-zero-prices`. Even with
that flag, the generated row metadata still records
`operator_review_required=true` and `zero_price_requires_review=true`.

`--paired-ready-only` removes route-only and pricing-only mismatches from the
generated import TSVs. This is the safest default before any real preview or
eventual audited import execution.

## Safety

- no silent production route updates
- no silent production pricing updates
- no direct DB mutation from fetched docs or provider APIs
- no direct import execution from proposal output
- no provider key storage
- no raw source-page or raw provider-response storage in PostgreSQL, audit,
  sessions, or logs
- no hosted tools, MCP/connectors, file search, code interpreter, computer
  use, web search, or image generation enablement through this workflow


### Current OpenAI linked documentation

When the HTML index has no legacy endpoint blocks, proposals retrieve the
canonical Markdown pricing/index documents and at most 64 individual official
model pages (four requests at a time, within the existing GUI byte/time budgets).
The requested model cap and model filters further narrow that scope. API model
listing remains identity/availability evidence and cannot grant endpoint support.
A page must declare the exact requested model ID, text modalities, and supported
endpoint rows. Page retrieval, format, and identity failures remain report-only.
The per-model page URL is retained in proposal provenance. Canonical IDs in
published flat Standard pricing are fetched even when absent from the featured
models index; the page must still confirm the exact identity.

Only explicit flat **Standard** prices enter this TSV family. Batch prices,
context-dependent prices, and cache-write price tables are not flattened into
ordinary input/output prices. Such pricing requires a separately representable
pricing contract; the generated report flags the limitation. Deprecated pages
remain report-only. With ordinary-chat-only enabled, current vision-capable
models may be projected to text-only routes; image and hosted-tool permissions
are not granted. Existing legacy block behavior is preserved.

Selected endpoint scopes control both route and pricing exports. A
Responses-only selection cannot emit Chat Completions rows. For OpenAI the
explicit model-page endpoint table is the authority; for OpenRouter the
per-model `endpoints` API array is the authority. Absence of that array preserves
legacy Chat behavior but does not grant Responses support. A model may support
Responses without supporting Chat Completions. Each endpoint is evaluated
independently and paired only with pricing for that exact endpoint.

Responses proposals contain the bounded stateless text subset: text and
stateless create, documented streaming and local function/structured-output
features when supported. Storage, previous-response references, images, custom
tools, Codex privileges and provider-hosted tools are not granted. The
ordinary-chat filter applies to Chat Completions candidates; it cannot suppress
a valid text Responses projection of a model that also supports vision.
`openrouter-responses-text` now exports evidenced Responses pairs as its own
endpoint family. Missing endpoint evidence remains report-only.

Verify actual row counts and warnings instead of interpreting a completed
artifact job as an import-ready catalog. Provider records must exist before
route import. Provider creation and enabling remain explicit administrator
actions, separate from proposals.
