# Provider Catalog Proposal

Use this skill when an operator asks to refresh or prepare provider model,
route, pricing, or capability proposal files for SLAIF.

This skill is proposal-only. It does not mutate provider configs, routes,
pricing rows, FX rows, keys, quotas, or usage records.

## When To Use

- The operator wants current OpenAI or OpenRouter model metadata proposals.
- The operator wants `routes-proposal.tsv` and `pricing-proposal.tsv`.
- The operator wants source comparison, confidence, disagreement reporting, or
  missing-pricing reporting before using the existing SLAIF import previews.

## When Not To Use

- Normal `/v1` runtime request handling.
- Silent or automatic production refresh.
- Any task that should directly update the database.
- Tasks requiring real upstream smoke tests.
- Unrelated quota, routing, or provider-forwarding work.

## Source Priority

OpenRouter:

1. Official public `https://openrouter.ai/api/v1/models`
2. Official model docs / schema reference for pricing unit confirmation
3. Optional per-model `links.details` enrichment

OpenAI:

1. Official pricing docs for pricing
2. Official models docs / comparison docs for endpoint and feature context
3. Optional `GET /v1/models` using `OPENAI_ADMIN_DISCOVERY_API_KEY` for
   availability/basic model IDs only
4. Existing OpenAI-assisted proposal workflow only as an optional cross-check,
   never as the sole trusted source

## Required Safety Rules

- Proposals only.
- Preview first through existing pricing/route import preview commands.
- No direct import execution unless the maintainer explicitly asks for it.
- Never use `OPENAI_API_KEY` for admin discovery. Use
  `OPENAI_ADMIN_DISCOVERY_API_KEY`.
- Never store raw provider responses, raw docs pages, prompts, completions,
  provider keys, gateway keys, cookies, CSRF/session tokens, or raw request or
  response bodies in the database, audit rows, or logs.
- Raw source snapshots may be saved only in the operator output directory and
  only when explicitly requested.
- Hosted tools, MCP/connectors, search-specific models, code interpreter, web
  search, file search, computer use, and image generation remain unsupported
  unless a future PR explicitly implements policy, pricing, accounting, and
  tests.

## Workflow

1. Generate proposal artifacts with:

```bash
slaif-gateway provider-catalog propose openrouter --output-dir /tmp/openrouter-catalog
slaif-gateway provider-catalog propose openai --output-dir /tmp/openai-catalog --include-api-models
slaif-gateway provider-catalog propose all --output-dir /tmp/provider-catalog
```

2. Review:

- `source-manifest.json`
- `provider-catalog-normalized.json`
- `provider-catalog-report.md`
- `warnings.json`
- `routes-proposal.tsv`
- `pricing-proposal.tsv`

3. Compare source sets:

- models present in docs but missing from API
- models present in API but missing from docs
- pricing disagreements
- missing pricing
- ambiguous capabilities
- deprecated/expiring models
- hosted/search-only models

4. Check confidence:

- `high`: API and docs agree, or official OpenRouter metadata plus unit
  confirmation is complete
- `medium`: docs-only parse is internally consistent
- `low`: assisted-only or otherwise ambiguous

5. Run existing import previews:

```bash
slaif-gateway routes import --input routes-proposal.tsv --dry-run
slaif-gateway pricing import --input pricing-proposal.tsv --dry-run
```

6. Only after operator review and explicit confirmation should any import be
   executed through the existing audited workflows.

## Output Contract

The skill should leave the operator with:

- `source-manifest.json`
- `provider-catalog-normalized.json`
- `routes-proposal.tsv`
- `pricing-proposal.tsv`
- `provider-catalog-report.md`
- `warnings.json`

## Reporting Requirements

Report:

- which source methods were used
- disagreements or missing fields
- readiness counts for route/pricing TSV rows
- whether OpenAI API listing was used
- whether OpenAI assisted cross-check was used
- that the workflow remained proposal-only
- that route/pricing import preview remains required
