# OAP Coding-Agent Report — 012-a

## Work order

- Identifier: `012-a`
- Work-order file:
  `oap/orders/012-a-external-tool-policy-contract-taxonomy.md`
- Work-order SHA-256:
  `af2baf3bdb37065b59cae54b1b237c5b977d303f419c55e28735ad7946c11b5a`
- Active-pointer SHA-256:
  `a61d596d9d747af3ef3125c30bf40c64332ac5030fd0c9692e4712803647b746`
- Numeric objective: `012`
- PR mode: `CREATE_NEW_PR`

## Status

COMPLETE

## Executive summary

Objective 012-a adds a pure, versioned, fail-closed contract for future
provider-hosted external-tool policy. It defines exact authority classes,
canonical capability IDs, v1 key and route schemas, immutable operator
ceilings, safe content-free DTOs, and a deterministic admission reducer. The
only quota modes are `strict_bounded` and `external_tool_fenced`.

The current runtime remains deny-only for provider-hosted/external authority.
The new module is not imported by application runtime, is not connected to
settings, persistence, routing, forwarding, quota/accounting, admin, or CLI,
and adds no migration. Objectives 013–017 remain required before any fenced
external-tool behavior can become active.

The future fenced-mode promise is exact: one admitted provider-hosted
external-tool request may exceed the key's remaining token or cost quota before
SLAIF regains control; concurrent requests for that key must be rejected while
the request is unresolved; authoritative provider usage/cost must be finalized
when available; following requests must be rejected after exhaustion; and a
blocking accounting hold must remain when final cost is missing, ambiguous,
interrupted, or awaiting reconciliation.

Focused verification passed 131/131 tests, all scoped static/path/privacy/docs
checks passed, and all ten GitHub checks passed on the literal implementation
head. No provider, gateway, MCP server, connector, production, staging,
database, or real-email action ran.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Starting remote `main`:
  `2a3cc6b2ae1b874a08d07d407a38e12933aebd2c`
- Implementation head SHA:
  `2717003c2981bf40ebaf92cc4ef18c98ba3e6e96`
- Implementation-head first parent:
  `2a3cc6b2ae1b874a08d07d407a38e12933aebd2c`
- Implementation-head commit message:
  `OAP 012-a: define external-tool policy contract`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `237`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/237`
- PR title: `[OAP 012] Define external-tool policy and quota promises`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE` / `CLEAN`
- Base branch: `main`
- Head branch: `oap/012-external-tool-policy-contract-taxonomy`
- Objective-012 PR count: exactly one, PR #237
- Created a new PR this turn: YES
- Amended an existing PR this turn: NO
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Exact authority taxonomy

| Reviewed wire/request fact | Authority class | Canonical capability | Destination treatment |
| --- | --- | --- | --- |
| `function`, `custom`, `namespace`, `local_shell`, client `apply_patch` | `client_operated` | none | none; rejected as unknown if provider markers are nested in the shape |
| `web_search`, `web_search_preview`, Chat `web_search_options`, reviewed search-specific Chat model | `provider_external` | `provider_web_search` | none |
| `file_search` | `provider_external` | `provider_file_search` | none |
| `code_interpreter` | `provider_external` | `provider_code_interpreter` | none |
| provider `shell` | `provider_external` | `provider_hosted_shell` | none |
| `image_generation` | `provider_external` | `provider_image_generation` | none |
| `computer`, `computer_use`, `computer_use_preview` | `provider_external` | `provider_computer_use` | none |
| `tool_search` | `provider_external` | `provider_tool_search` | none |
| `skill`, `skills` | `provider_external` | `provider_skill` | none |
| `mcp` plus a connector marker | `provider_external` | `provider_connector` | raw wire destination remains unreviewed; only server-resolved `connector:<opaque>` may be admitted later |
| `mcp` plus a server-URL marker | `provider_external` | `provider_remote_mcp` | raw wire destination remains unreviewed; only server-resolved `remote_mcp:<opaque>` may be admitted later |
| provider-side remote image/file URL fetch fact | `provider_external` | `provider_url_fetch` | separately identifiable, not treated as a tool call |
| malformed, unknown, mixed local/external, ambiguous MCP, or unknown tool choice | `unknown_external_authority` | none | denied fail closed |

The recursive marker set is `server_url`, `connector_id`, `authorization`,
`require_approval`, `defer_loading`, `server_label`, `server_description`,
`allowed_tools`, `api_key`, `bearer_token`, `cookie`, `cookies`, `oauth`, and
`headers`. Cycles and excessive or malformed nested shapes also fail closed.
Raw URLs, provider names, credentials, labels, tool arguments/results, and
prompts never enter admission decisions or safe DTO output. Request
`require_approval` never lowers the future operator/route approval floor.

## Exact v1 schemas

Missing key policy canonicalizes to this strict default; a present strict
policy must match it exactly:

```json
{
  "version": 1,
  "mode": "strict_bounded",
  "allowed_capabilities": [],
  "allowed_destination_ids": [],
  "max_provider_tool_calls_per_request": 0,
  "single_request_overrun_acknowledged": false
}
```

An external key policy uses the same exact six fields, mode
`external_tool_fenced`, a non-empty deduplicated known capability list,
destination IDs only where required, a positive bounded call cap, and literal
acknowledgement `true`.

Missing route metadata canonicalizes to this strict default; a present strict
route policy must match it exactly:

```json
{
  "version": 1,
  "supported_capabilities": [],
  "approved_destination_ids": [],
  "max_provider_tool_calls_per_request": 0,
  "call_limit_enforced": false,
  "final_usage_required": false,
  "final_cost_required": false
}
```

External route support uses the same exact seven fields, a non-empty
deduplicated known capability list, matching reviewed destination IDs, a
positive bounded call cap, and all three enforcement/evidence flags literally
`true`. Key and route parsers reject partial, extra-key, coerced, duplicated,
unknown, URL-like, secret-looking, overlong, over-ceiling, and
destination/capability-mismatched inputs without retaining raw values.

Reviewed destination IDs are exact low-cardinality opaque identifiers of at
most 48 opaque characters after one of these prefixes:

```text
connector:<opaque>
remote_mcp:<opaque>
```

Client-supplied authorization, cookies, bearer material, arbitrary URLs, and
raw connector/server values cannot construct an admitted destination fact.

## Operator ceilings

| Ceiling | Default | Contract absolute maximum |
| --- | ---: | ---: |
| Distinct external capabilities | 16 | 16 |
| Approved destinations | 8 | 8 |
| Provider-tool declarations per request | 16 | 16 |
| Provider-tool calls/iterations per request | 16 | 16 |

The frozen ceilings DTO accepts only literal positive integers no greater than
these maxima. Key and route policies can narrow, never widen, the effective
limit. Objective 012 adds no settings or environment variables.

## Admission decision matrix

| Input state | Allowed | Quota mode / cap | Safe result |
| --- | ---: | --- | --- |
| No external-authority facts | YES | `strict_bounded` / 0 | `no_external_authority`; existing independent local/client processing remains possible |
| Unknown, malformed, mixed, unreviewed, unsupported-state, or approval-floor failure | NO | `strict_bounded` / 0 | fixed low-cardinality denial code |
| Operator capability, destination, declaration, or call ceiling exceeded | NO | `strict_bounded` / 0 | fixed operator-ceiling denial code |
| Provider calls required but requested call cap is not positive | NO | `strict_bounded` / 0 | `provider_tool_call_cap_required` |
| Key policy invalid, missing, or strict | NO | `strict_bounded` / 0 | key-specific fixed denial; strict remains default |
| Route policy invalid or external support missing | NO | `strict_bounded` / 0 | route-specific fixed denial |
| Capability or destination absent from either key or route intersection | NO | `strict_bounded` / 0 | exact key/route mismatch or missing-destination code |
| Effective key/route/operator call cap exceeded | NO | `strict_bounded` / 0 | `effective_call_cap_exceeded` |
| Route evidence flags or literal key acknowledgement missing | NO | `strict_bounded` / 0 | fixed evidence/acknowledgement denial |
| Calibration key or non-positive/unbounded/non-finite request, token, or EUR cost limit | NO | `strict_bounded` / 0 | `standard_key_required` or `positive_finite_key_limits_required` |
| Exact reviewed intersection, standard key, positive finite limits, all gates true | YES | `external_tool_fenced` / minimum of key, route, and operator call caps | `external_tool_fenced_allowed` plus all four obligations true |

The four exact positive obligations are:

```text
exclusive_key_fence_required=true
single_request_overrun_accepted=true
hold_on_missing_or_ambiguous_final_cost=true
following_requests_block_after_exhaustion=true
```

All denied and strict decisions set those obligations false. The reducer
returns policy facts only; it cannot forward, execute, persist, reserve,
finalize, fence, or hold anything.

## Runtime and privacy boundary

- Application/runtime imports of the new module: 0.
- Settings/environment integration: 0.
- Alembic/schema migrations: 0.
- Provider-adapter or request-forwarding integration: 0.
- Key/route persistence, admin, CLI, template, or operator-surface integration: 0.
- Raw values retained in malformed parse results or admission DTOs: 0.
- Current hosted-tool/MCP/provider-authority runtime denials changed: NO.
- Trusted-calibration observation promoted to standard-key permission: NO.
- Client tools promoted to gateway execution authority: NO.

Existing endpoint validators continue to own complete local-tool request-shape
validation. This taxonomy only establishes the authority boundary; it cannot
make an otherwise invalid request valid.

## Official OpenAI documentation impact

The implementation used these primary pages only to identify current wire
aliases and authority boundaries:

```text
https://developers.openai.com/api/docs/models/gpt-5.6-sol
https://developers.openai.com/api/docs/guides/tools-connectors-mcp
```

They support classifying named Responses tool families and treating remote MCP
servers/connectors, their authorization, and approval controls as external
authority. No inference was made that every model/provider supports every
family, that a wire alias grants SLAIF permission, or that provider-hosted
execution is currently enabled.

## Verification

Focused pytest command:

```text
.venv/bin/python -m pytest -q tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py tests/unit/test_oap_governance.py tests/unit/test_product_scope_docs.py tests/unit/test_rc2_feature_scope_docs.py tests/unit/test_openai_assisted_import_contract_docs.py
```

Result: PASS, 131/131 tests. Collection comprised 101 external-tool contract
tests, 13 documentation-contract tests, 8 OAP governance tests, 4 product-scope
tests, 4 RC2 feature-scope tests, and 1 assisted-import documentation test.

Additional focused checks:

```text
.venv/bin/python -m ruff check app/slaif_gateway/services/external_tool_policy_contract.py tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py
.venv/bin/python -m ruff format --check app/slaif_gateway/services/external_tool_policy_contract.py tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py
.venv/bin/python -m py_compile app/slaif_gateway/services/external_tool_policy_contract.py tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py
git diff --check
```

Results: Ruff passed; all three files were already formatted; compilation
passed; the official-reference link scan, exact 18-path allowlist check,
runtime-import scan, settings/migration integration scans, documentation
terminology/current-status scan, and active/order digest checks passed.
`git diff --check` passed for implementation content. The unchanged strategic
order has one pre-existing extra blank line at EOF; its bytes and digest were
preserved exactly.

Implementation-head GitHub checks at
`2717003c2981bf40ebaf92cc4ef18c98ba3e6e96`:

| Required check | Result |
| --- | --- |
| Analyze (javascript-typescript) | PASS |
| Analyze (python) | PASS |
| Analyze Python | PASS |
| CodeQL | PASS |
| Docker Compose smoke | PASS |
| Documentation hygiene | PASS |
| OpenAI-compatible E2E tests | PASS |
| Playwright browser smoke | PASS |
| PostgreSQL integration tests | PASS |
| Unit, lint, and migration head | PASS |

Fresh report-head checks are verified from GitHub after immutable report
publication; their external results cannot be written retroactively into this
SELF report.

## Acceptance criteria

1. PASS — every reviewed local/provider/MCP/connector/URL-fetch alias maps to
   one exact authority class; malformed, unknown, mixed, cyclic, and ambiguous
   shapes fail closed.
2. PASS — exact v1 key/route schemas reject partial, extra, coerced, duplicate,
   unknown, secret/URL-like, overlong, and over-ceiling values; missing policy
   is strict denial.
3. PASS — the pure matrix allows only the exact standard finite opt-in
   intersection and returns all fence/overrun/hold/following-block obligations;
   it grants no runtime behavior.
4. PASS — `strict_bounded` remains the default, runtime remains deny-only, and
   trusted calibration/client-local behavior remains separate.
5. PASS — all affected docs use the same two modes and honest future promise,
   without a zero-overrun, invoice-truth, compliance, or implemented-feature
   overclaim.
6. PASS — focused tests, documentation/privacy/path/contradiction scans, and
   all implementation-head checks passed; broad suites and external calls did
   not run.
7. PASS — exactly one new objective-012 PR exists; no merge/auto-merge occurred;
   the final report commit is SELF and report-only.

## Changes and exact paths

Implementation commit `2717003c2981bf40ebaf92cc4ef18c98ba3e6e96`
changed exactly:

```text
AGENTS.md
app/slaif_gateway/services/external_tool_policy_contract.py
docs/accounting.md
docs/beta-readiness.md
docs/compatibility-matrix.md
docs/configuration.md
docs/database-schema.md
docs/key-templates.md
docs/openai-compatibility.md
docs/product-scope.md
docs/provider-forwarding-contract.md
docs/rc-beta.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/012-a-external-tool-policy-contract-taxonomy.md
tests/unit/test_documentation_contract_drift.py
tests/unit/test_external_tool_policy_contract.py
```

The strategic order and active pointer were committed unchanged from the
activated inputs. Every earlier order/report remained unchanged. The report
publication commit adds only:

```text
oap/reports/012-a-external-tool-policy-contract-taxonomy.md
```

Documentation updated: AGENTS.md, docs/accounting.md,
docs/beta-readiness.md, docs/compatibility-matrix.md, docs/configuration.md,
docs/database-schema.md, docs/key-templates.md, docs/openai-compatibility.md,
docs/product-scope.md, docs/provider-forwarding-contract.md, docs/rc-beta.md,
docs/responses-compatibility.md, and docs/security-model.md.

## Scope, omissions, and safety

- Scope deviation: NONE.
- Unexpected unrelated tracked modification: NONE.
- `.local-provider-catalog/` was not modified, staged, or committed.
- Full local unit, integration/PostgreSQL, OpenAI-client E2E,
  Playwright/browser, Docker/Compose, HPC, manual Codex, and upstream-optional
  suites: NOT RUN, exactly as ordered; broad routine coverage was delegated to
  GitHub CI.
- Provider/gateway/remote URL/MCP/connector call: NONE.
- Production/staging access: NONE.
- Database setup, migration execution, or teardown: NONE.
- Packages/tools/services installed or configured: NONE.
- Sudo-level setup: NONE.
- Credentials searched for or printed: NONE.
- Real email: NONE.
- New PR: YES, exactly PR #237.
- Merge: NO.
- Auto-merge: NO.
- Report publication commit changes only this immutable report: YES.

## Coding-agent conclusion

Objective 012-a's execution turn is complete. The pure contract, taxonomy,
schemas, ceilings, admission matrix, and synchronized documentation passed
focused verification; implementation-head CI passed all ten checks; runtime
remains deny-only; and the coding agent did not merge or enable auto-merge.
Strategic acceptance and any merge decision remain with the strategic
model/human maintainer.
