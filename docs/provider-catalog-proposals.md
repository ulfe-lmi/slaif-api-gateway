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

- `--source api`
- `--source assisted`
- `--include-model`
- `--exclude-model`
- `--endpoint-scope chat_completions`
- `--endpoint-scope responses`
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
