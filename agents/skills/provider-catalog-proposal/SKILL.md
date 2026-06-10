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

OpenAI docs extraction must stay conservative:

- documentation navigation, headings, product names, and category labels are
  not model IDs
- docs-only extraction may legitimately produce zero ready rows
- route/pricing readiness requires a canonical OpenAI model ID plus complete
  supported endpoint/pricing evidence
- unsupported modality/category rows remain report-only

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
slaif-gateway provider-catalog propose openrouter \
  --output-dir /tmp/openrouter-catalog \
  --paired-ready-only \
  --ordinary-chat-only

slaif-gateway provider-catalog propose openai --output-dir /tmp/openai-catalog --include-api-models
slaif-gateway provider-catalog propose all --output-dir /tmp/provider-catalog
```

Before any import preview, run a bounded OpenRouter smoke first. Keep the scope
small enough to inspect manually:

```bash
slaif-gateway provider-catalog propose openrouter \
  --output-dir /tmp/openrouter-catalog-smoke \
  --max-models 50 \
  --fetch-details-limit 10 \
  --paired-ready-only \
  --ordinary-chat-only \
  --no-save-source-snapshots \
  --json
```

2. Review:

- `source-manifest.json`
- `provider-catalog-normalized.json`
- `provider-catalog-report.md`
- `warnings.json`
- `routes-proposal.tsv`
- `pricing-proposal.tsv`

Generated TSV files are self-validated before the command reports success.
Malformed TSV output, invalid JSON cells, invalid booleans, bad decimal fields,
or suspicious cell content must fail the proposal command with
`proposal_tsv_validation_failed`.

3. Compare source sets:

- models present in docs but missing from API
- models present in API but missing from docs
- pricing disagreements
- missing pricing
- zero-price rows
- ambiguous capabilities
- deprecated/expiring models
- hosted/search-only models
- docs tokens that were skipped because they were not canonical model IDs

4. Check confidence:

- `high`: API and docs agree, or official OpenRouter metadata plus unit
  confirmation is complete
- `medium`: docs-only parse is internally consistent
- `low`: assisted-only or otherwise ambiguous

5. Run existing import previews:

```bash
slaif-gateway pricing import --format tsv --file pricing-proposal.tsv --dry-run
slaif-gateway routes import --format tsv --file routes-proposal.tsv --dry-run
```

6. Only after operator review and explicit confirmation should any import be
   executed through the existing audited CLI workflows:

```bash
slaif-gateway pricing import \
  --format tsv \
  --file pricing-proposal.tsv \
  --execute \
  --confirm-import \
  --reason "operator-reviewed pricing import"

slaif-gateway routes import \
  --format tsv \
  --file routes-proposal.tsv \
  --execute \
  --confirm-import \
  --reason "operator-reviewed route import"
```

Dry-run is the default safety checkpoint. The CLI import surfaces reject
implicit writes; execution requires `--execute`, `--confirm-import`, and a
non-empty `--reason`.

Zero-price pricing rows are report-only by default. They must not be treated as
ready for pricing import unless the operator explicitly opts in with
`--allow-zero-prices`, and even then they remain review-required rows with
warning metadata.

`--paired-ready-only` is the safe default for real import preparation because it
excludes route-only and pricing-only mismatches from the generated TSV files.

`--ordinary-chat-only` is the safe default for Chat Completions import
preparation because it excludes ambiguous multimodal, audio, image, VL,
realtime, and similar rows from import-ready TSV output unless the operator
explicitly opts into multimodal proposal candidates.

## Output Contract

The skill should leave the operator with:

- `source-manifest.json`
- `provider-catalog-normalized.json`
- `routes-proposal.tsv`
- `pricing-proposal.tsv`
- `provider-catalog-report.md`
- `warnings.json`

For OpenRouter reviewed imports, package presets are preferred over one flat
catalog when the operator wants staged review surfaces:

- `openrouter-chat-text`: default safe import candidate for ordinary text Chat
- `openrouter-chat-image`: superset of text chat adding image-input to
  text-output rows
- `openrouter-chat-audio`: superset of image chat adding only safe
  audio-capable Chat rows when current SLAIF capability/pricing evidence is
  strong enough
- `openrouter-chat-multimodal`: broader staged review package for safe chat
  multimodal rows
- `openrouter-responses-text`: separate Responses endpoint family; it may
  legitimately emit zero TSV rows when current evidence is insufficient

When packages are requested, the run should also leave:

- `packages/package-index.md`
- `packages/package-index.json`
- `packages/<package>/package-manifest.json`
- `packages/<package>/routes-proposal.tsv`
- `packages/<package>/pricing-proposal.tsv`
- `packages/<package>/model-review.md`
- `packages/<package>/package-report.md`

Review artifacts must stay readable in strict Markdown viewers. Prefer a compact
HTML table in `model-review.md` with short columns and `—` for missing values.
Do not emit wide long-note pipe tables.

## Reporting Requirements

Report:

- which source methods were used
- disagreements or missing fields
- readiness counts for route/pricing TSV rows
- whether OpenAI API listing was used
- whether OpenAI assisted cross-check was used
- that the workflow remained proposal-only
- that route/pricing import preview remains required
