# Pricing Catalog And Bounded Overrun

Status: planned RC2-beta direction; current runtime pricing remains the local
pricing/FX implementation described in `docs/database-schema.md`,
`docs/configuration.md`, and `docs/compatibility-matrix.md`.

## Local Catalog Remains Source Of Truth

SLAIF hard quota/accounting must use local pricing rows and FX rates as the
source of truth. Provider metadata can help operators import or compare prices,
but runtime quota cannot silently depend on a live pricing API.

Unknown pricing or unknown required FX conversion must continue to fail closed
for cost-limited keys.

For implemented Chat Completions, the local cost estimate uses the request
policy's total estimated input tokens. That total includes message input plus
conservative serialized estimates for provider-forwarded non-message object/list
fields such as `tools`, legacy `functions`, `response_format` JSON schemas, and
other forwarded objects/lists. Local custom tool definitions, format metadata,
and grammar definitions are included in that ordinary input estimate when
custom tools are route-enabled. This can over-reserve, but prevents large
tool/schema payloads from passing cost checks with a messages-only estimate.
Successful accounting still finalizes from actual provider usage when available.

Chat Completions image input to text output is enabled only behind explicit
route capability and request caps. Image URL/data URL wrapper text is included
in the ordinary message input estimate, but SLAIF does not treat image bytes as
invoice-grade billable tokens and does not infer exact final image cost from
URL or base64 size. Successful accounting still finalizes from provider
usage/cost.

Chat Completions inline file input to text output is enabled only behind
explicit route capability and request caps. The file content-part wrapper,
filename, and inline `file_data` string are included in the ordinary message
input estimate, but SLAIF does not treat file bytes as invoice-grade billable
tokens and does not infer exact final file cost from base64 size. File IDs and
file URLs are rejected in this slice. Successful accounting still finalizes
from provider usage/cost, and OpenRouter provider-reported cost is not
multiplied by file count or `n`.

Chat Completions audio input to text output is enabled only behind explicit
route capability and request caps. The audio content-part wrapper, format, and
base64 `input_audio.data` string are included in the ordinary message input
estimate, but SLAIF does not treat audio bytes or duration as invoice-grade
billable tokens and does not infer exact final audio cost from base64 size.
Audio URLs and audio data URLs are rejected in this PR. Successful accounting
still finalizes from provider usage/cost, and OpenRouter provider-reported cost
is not multiplied by audio count, byte size, duration, or `n`.

The upstream investigation in
[`chat-completions-multimodal-investigation.md`](chat-completions-multimodal-investigation.md)
shows that audio output and broader file modes are documented, but bytes are
not billable tokens. Future audio-output/file-ID/file-URL support needs
modality-specific admission estimates, pricing/catalog fields where upstream
pricing requires them, provider usage parsing, and accounting tests before
those payloads can be enabled for cost-limited gateway keys.

## OpenRouter Price Refresh

OpenRouter publishes model metadata that includes a `pricing` object with
token/request/tool-related price fields where available. A future refresh
workflow may fetch that metadata and turn it into local pricing proposals.

Rules:

- fetch/import is preview-first;
- admins must confirm before rows are created or superseded;
- changes require an audit reason;
- production pricing rows are never silently replaced;
- price values are parsed as decimal strings, not floats;
- unknown fields or provider-secret-looking metadata are rejected.

## OpenAI Pricing

OpenAI publishes pricing on its pricing pages. Unless OpenAI provides a stable
official pricing API for this use case, OpenAI pricing should be curated
manually or imported from an operator-controlled file through the existing
preview/confirm/audit pattern.

Do not scrape or silently refresh OpenAI prices into production rows without a
separate reviewed implementation contract.

## OpenAI Assisted Pricing And Route Proposals

SLAIF includes admin-only CLI and dashboard workflows that can call OpenAI to
help draft pricing and route proposal files:

```bash
slaif-gateway openai-assisted pricing-proposal \
  --output openai-pricing-proposal.tsv \
  --acknowledge-llm-proposal-risk

slaif-gateway openai-assisted route-proposal \
  --output openai-routes-proposal.tsv \
  --acknowledge-llm-proposal-risk
```

The dashboard exposes the same boundary under `/admin/openai-assisted`, with
separate pricing and route proposal pages. It requires an authenticated admin
session, CSRF, and an explicit acknowledgement checkbox before calling OpenAI.
The result page shows cited source URLs, warnings, row counts, and generated TSV
for review, then can submit the generated TSV directly to the existing pricing
or route import preview page. That bridge is still preview-only and non-mutating:
it posts `import_format=tsv`, a safe source label, and the generated TSV to the
deterministic import validator, never to an execution route. If the TSV exceeds
the configured import size limit, the page does not render a hidden preview
payload; the admin must reduce scope or use the copy/download and file-import
workflow. It does not execute import. Proposal generation is synchronous in the
current dashboard implementation and uses the service HTTP timeout; if OpenAI or
web search is slow, the admin should retry later or use the CLI workflow.

The CLI command and dashboard action call OpenAI only when an operator
explicitly runs them. They are disabled unless the server-side admin discovery
environment variable is configured; the default is
`OPENAI_ADMIN_DISCOVERY_API_KEY`. Do not use `OPENAI_API_KEY` for this tool:
`OPENAI_API_KEY` remains reserved for client-side gateway-issued keys. The
default proposal model is controlled by `OPENAI_ASSISTED_CATALOG_MODEL`, and the
CLI or dashboard form can select a model for the proposal request.

Proposal generation uses official OpenAI documentation URLs by default:
`https://platform.openai.com/docs/pricing` and
`https://platform.openai.com/docs/models/compare`. The generator asks OpenAI for
strict JSON, validates the JSON deterministically, and renders local TSV
proposal content. It does not directly mutate `pricing_rules` or `model_routes`,
does not call OpenRouter, does not fetch external FX data, and does not import
rows from a web fetch or LLM response. The dashboard also does not store raw
model responses, raw webpage text, prompts, completions, cookies, sessions, CSRF
tokens, provider keys, encrypted payloads, nonces, or raw request/response
bodies.

LLM-generated proposal files are not authoritative. They are draft operator
inputs. Imported rows become local SLAIF accounting and routing assumptions only
after an authenticated admin previews the parsed rows, explicitly confirms the
import, supplies an audit reason, and every row passes the normal validation and
create-only classification checks.

Pricing proposal files should use reviewed decimal strings. For pricing TSV,
the supported core columns are:

```text
provider	model	endpoint	currency	input_price_per_1m	output_price_per_1m
```

Where the current pricing schema supports them, proposal files may also include:

```text
cached_input_price_per_1m	reasoning_price_per_1m	request_price	valid_from	valid_until	source_url	source_retrieved_at	notes	pricing_metadata
```

`source_retrieved_at` is explicit proposal metadata and is preserved inside
`pricing_metadata` during import validation.

Route proposal TSV files use the current route import fields:

```text
requested_model	match_type	endpoint	provider	upstream_model	priority	enabled	visible_in_models	supports_streaming	capabilities	notes
```

For Chat Completions routes, `capabilities` should include explicit
`chat_completions` boolean flags as documented in
[`database-schema.md`](database-schema.md). Endpoint/model/provider policy does
not imply local function-tool, structured-output, logprobs, hosted-tool,
service-tier, or multimodal permission.

OpenAI-assisted route proposals must not turn search-specific models such as
`gpt-5-search-api`, `gpt-4o-search-preview`, or
`gpt-4o-mini-search-preview` into ordinary Chat Completions routes. Those models
require future hosted web-search policy, pricing, and audit controls; the
proposal workflow should omit them or report them as warnings.

No silent replacement of production pricing rows is allowed. No direct mutation
from a web fetch or LLM call is allowed. Imports are preview-first and
create-only in the current dashboard workflow: invalid, duplicate, conflicting,
overlapping, disabled, or update-classified rows block the whole import with no
mutation. Unknown fields are rejected unless a future proposal contract
explicitly adds them to the schema.

OpenAI prices in proposal files are informative, operator-reviewed local
assumptions. They are not invoice-grade guarantees and do not prove that an
upstream provider invoice will exactly match SLAIF's local accounting. SLAIF
cost limits are hard against local pricing and FX rows; they are budget controls
over the gateway's accounting model, not a provider billing attestation.
Request, token, output, model, and rate limits remain the safer primary controls
for workshops and courses, with money limits acting as an additional guardrail.

The proposal generator deliberately stops at reviewed TSV content. Operators
must inspect the TSV, run the existing pricing or route import preview, and
execute the import only with explicit confirmation and an audit reason. The web
UI can carry the reviewed TSV into preview without copy/paste, but it does not
create a trusted path: unknown fields, secret-looking values, conflicts,
duplicates, unsupported rows, and update-classified rows are handled by the same
validators as uploaded or pasted imports. The generator must reject
secret-looking input and metadata and preserves the rule that provider keys come
only from server-side environment variables or deployment secrets.

## OpenAI Completions Bootstrap CSV

The first-run OpenAI Completions bootstrap command uses local pricing metadata
as SLAIF's accounting source of truth:

```bash
slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

The bootstrap is intentionally local. It does not call OpenAI, does not fetch
prices, and does not inspect provider key values. A configured
`OPENAI_UPSTREAM_API_KEY` alone does not make models visible or priceable:
operators must import local provider, route, and pricing metadata first.
Without matching pricing rows, cost-limited requests fail closed.

The CSV must include one row for every selected catalog model and endpoint:

```text
provider,model,endpoint,currency,input_price_per_1m,output_price_per_1m
```

Supported endpoint values for the current command are `chat.completions` and
`/v1/chat/completions`. `POST /v1/completions` is not implemented, so legacy
Completions pricing rows are not bootstrapped yet.

The command defaults to `--pricing-mode require-file` and fails safely when a
catalog model is missing. `--pricing-mode placeholder` requires
`--confirm-placeholder-pricing`, marks created rows with placeholder metadata
when the schema supports it, and prints a warning. Placeholder pricing is for
smoke tests only, is not real pricing, and must not be used for production
accounting.

The checked-in
[`docs/examples/openai-completions-pricing.example.csv`](examples/openai-completions-pricing.example.csv)
uses placeholder values to demonstrate the format. Operators must replace those
values with reviewed local pricing assumptions before real provider traffic.

## Tool Pricing Fields

Responses tools can add cost beyond ordinary input/output tokens. The RC2
pricing catalog should be able to represent, where applicable:

- input token price;
- cached input token price;
- output token price;
- reasoning token price;
- fixed request price;
- web search price per call or per result;
- file search price per call;
- code interpreter/container session or call price;
- provider-reported cost metadata;
- source currency;
- effective validity window;
- pricing source and operator note.

Tool pricing must be explicit before a tool is enabled for quota-limited keys.
Current Chat Completions web search and other hosted/provider-side tools are
denied by default; model and endpoint allowlists do not enable them.

Chat Completions local custom tools are not hosted/provider-side tools for
SLAIF billing. They have no custom-tool price, billing unit, execution fee, or
ledger cost category. Custom-tool definitions can increase ordinary input
tokens, generated custom-tool input can increase ordinary output tokens, and a
later application request with tool results is accounted as a separate ordinary
gateway request.

## Chat Completions Cost Finalization

Current Chat Completions uses local pricing rows for admission-time reservation.
The pre-call estimate uses estimated input tokens once and the effective output
reservation. For `n > 1`, the output reservation is choice-aware:
`effective_max_output_tokens_per_choice * n`. The gateway does not multiply
input tokens by `n` and does not guess cached input or reasoning-token splits
before the provider returns usage. The provider call is admitted only when that
estimate fits the key's remaining local budget.

After a successful provider response, SLAIF finalizes actual usage even when the
actual token or cost usage exceeds the reservation. This is post-call spend
accounting, not hard real-time spend interruption inside the upstream call. The
ledger records safe reservation-overrun flags and subsequent calls are blocked
when finalized counters exceed the key's configured limits.

Actual Chat Completions cost calculation is component-aware where provider usage
is available:

- uncached input tokens use `input_price_per_1m`;
- cached input tokens use `cached_input_price_per_1m` when configured, otherwise
  ordinary input pricing with reduced cost confidence;
- output tokens use `output_price_per_1m`;
- reasoning tokens are treated as a subset of output tokens for current Chat
  Completions. When `reasoning_price_per_1m` is configured, the reasoning subset
  uses that price and the remaining output tokens use output pricing. Otherwise
  reasoning tokens fall back to output pricing with reduced cost confidence.

For OpenRouter, a valid non-negative provider-reported cost with supported
currency is preferred for actual finalization, while the SLAIF-calculated cost
is retained as comparison metadata. Provider-reported OpenRouter cost is not
multiplied again by `n`; it is treated as the cost for the one upstream request.
For OpenAI, SLAIF-calculated cost remains the actual finalization source unless
a provider-reported cost path is explicitly supported later. Invalid or
unsupported provider-reported costs are ignored in favor of SLAIF calculation
and recorded as safe metadata. No provider pricing fetch, scrape, or extra
upstream call happens during finalization.

All costs are SLAIF local accounting assumptions for quota and reporting. They
are not provider invoice certification.

## Worst-Case Single-Request Cost

Before forwarding a Responses request, the gateway should compute a conservative
maximum cost estimate:

```text
estimated_cost =
  estimated_input_tokens * input_price
  + effective_max_output_tokens * output_or_reasoning_price
  + max_tool_calls * maximum_allowed_tool_call_price
  + fixed_request_price
  + safety_margin_if_configured
```

The exact formula may vary by provider/model/tool, but the inputs and assumptions
must be visible in the admin UI when enabling a policy.

## Bounded Overrun

Tool-enabled Responses requests may finish above the key's remaining cost limit.
That can be acceptable only as a bounded overrun:

- the maximum single-request overrun is computed from configured caps;
- the admin sees that bound before enabling the policy;
- the key/template stores or references the policy revision used for the bound;
- PostgreSQL final accounting records the actual overrun;
- future requests are blocked until the limit is raised or counters are reset.

No unlimited or unbounded tool policy is acceptable for cost-limited keys.

## Cost And Quota Recommendation Inputs

The pricing catalog supports money estimates for Responses policies and
calibration-derived templates, but usage-derived recommendations can be based
primarily on operational limits rather than money. Trusted calibration keys can
produce safe observed Chat Completions usage rows and preview strict
participant-policy proposals from CLI or admin web, but those proposals are
local assumptions until an admin reviews them. Reviewed proposals can now create
durable key-template revisions, but template creation does not create
participant keys, routes, pricing rows, or key policy changes. For workshop
participant keys, token, request, and tool-call limits are often easier to
explain and enforce than exact currency estimates.

Money estimates remain useful as an admin-visible warning and budget preview,
especially for bounded-overrun policy, but they are informational when tool costs
are provider-specific, incomplete, or hard to predict. The recommendation UI
should still show the bounded-overrun estimate and the pricing assumptions used
to calculate it.

Preferred recommendation inputs for participant templates:

- observed request counts;
- observed input, output, reasoning, cached, and total token counts where
  available;
- observed tool calls by type and safe function name where available;
- observed per-request maxima;
- local pricing rows and FX rates where known;
- provider-reported cost metadata where available.

## No Silent Replacement

Pricing refresh workflows must not mutate production pricing invisibly. They
should create proposed rows or preview diffs, then require explicit confirmation
and audit before activation.

## Reference Docs Checked For This Contract

- OpenAI pricing page:
  <https://platform.openai.com/pricing>
- OpenRouter models API metadata:
  <https://openrouter.ai/docs/guides/overview/models>
- OpenRouter web search server tool pricing:
  <https://openrouter.ai/docs/guides/features/server-tools/web-search>
