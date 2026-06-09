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

OpenAI assisted cross-checks are optional and require explicit operator
acknowledgement. They use `OPENAI_ADMIN_DISCOVERY_API_KEY`, never
`OPENAI_API_KEY`.

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

## Comparison, Confidence, And Warnings

The workflow compares source sets and reports:

- model present in docs but missing from API
- model present in API but missing from docs
- missing pricing
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

## Safety

- no silent production route updates
- no silent production pricing updates
- no direct DB mutation from fetched docs or provider APIs
- no provider key storage
- no raw source-page or raw provider-response storage in PostgreSQL, audit,
  sessions, or logs
- no hosted tools, MCP/connectors, file search, code interpreter, computer
  use, web search, or image generation enablement through this workflow
