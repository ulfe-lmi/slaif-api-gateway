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
