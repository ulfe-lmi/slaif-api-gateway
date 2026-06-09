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
  --output-dir /tmp/slaif-provider-catalog-openrouter

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
  --no-save-source-snapshots \
  --json
```

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

## Output Files

Every run writes:

- `source-manifest.json`
- `provider-catalog-normalized.json`
- `routes-proposal.tsv`
- `pricing-proposal.tsv`
- `provider-catalog-report.md`
- `warnings.json`

The generated TSV files are input to the existing SLAIF import preview flows.
They are not imports by themselves.

The proposal command self-validates the generated TSV artifacts before it
reports success. If a TSV has malformed rows, invalid JSON cells, invalid
boolean or decimal fields, suspicious secret-like content, or a broken
`source_url` / `source_retrieved_at` split, the run fails with
`proposal_tsv_validation_failed`.

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
2. confirms the import
3. supplies an audit reason

Pricing remains a reviewed local accounting assumption until imported. It is
important for quota/accounting, but it is not invoice-grade truth by itself.

Zero-price pricing rows are report-only by default. They are not pricing-import
ready unless the operator explicitly passes `--allow-zero-prices`. Even with
that flag, the generated row metadata still records
`operator_review_required=true` and `zero_price_requires_review=true`.

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
