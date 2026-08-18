# OAP Work Order — 012-a

## Objective

Define the versioned, fail-closed provider-hosted external-tool policy and quota
promise that objectives 013–017 will implement. Add a pure mechanically
testable taxonomy, exact key/route policy schemas, operator ceilings, and
admission-decision contract that distinguish client-operated tools from
provider/external authority without enabling or forwarding any new tool.

## Authoritative start state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote default branch: `main`.
- Starting remote `main`:
  `2a3cc6b2ae1b874a08d07d407a38e12933aebd2c`, merge commit for PR #236.
- Objectives 003 and 011 are merged. Objective 011 established only
  `local_gateway_e2e_qualified=true`,
  `bounded_real_openai_pilot_prepared=true`, and
  `real_provider_e2e=false`.
- Current Alembic head is `0014_codex_context_accounting_compaction`; this
  objective adds no migration or stored policy integration.
- Current standard keys deny provider-hosted tools. Trusted-calibration
  discovery has intentionally broader observation-only allowances but remains
  distinct from standard-key authorization. Do not reuse it as the external-
  tool production policy.
- Existing `hosted_tool_policy.py` classifies/rejects current Chat Completions
  hosted surfaces. Responses request policy also rejects hosted/MCP/provider-
  authority shapes. Preserve those runtime denials unchanged.
- The only unrelated open PR is Dependabot #224. Do not modify or reuse it.
- No objective-012 PR/branch existed at activation.
- PR mode: `CREATE_NEW_PR`.
- Required branch: `oap/012-external-tool-policy-contract-taxonomy`.
- Required PR title:
  `[OAP 012] Define external-tool policy and quota promises`.
- Preserve `.local-provider-catalog/`, linked worktrees, local user config,
  secrets, and every unrelated artifact.

Fetch and reconcile GitHub, repository governance, and these facts before
editing. Start the branch from current remote `main`, never from objective 011's
merged feature branch.

## Official provider taxonomy evidence

Current official OpenAI documentation, checked on 2026-08-18, identifies
Responses tool families including web search, file search, image generation,
code interpreter, hosted shell, apply patch, skills, computer use, MCP, and tool
search. It distinguishes functions and local shell/client workflows from
provider-hosted execution. The MCP/connectors guide states that remote MCP and
connectors connect to and control external services, use built-in `type=mcp`,
may identify a public `server_url` or connector, may require authorization, and
may require or bypass approval.

Primary evidence:

```text
https://developers.openai.com/api/docs/models/gpt-5.6-sol
https://developers.openai.com/api/docs/guides/tools-connectors-mcp
```

Use these sources only to define current wire aliases/authority classes. Do not
claim every model/provider supports every family, and do not infer future
compatibility from a name.

## Product truth and two quota modes

### Strict bounded mode — default

Provider-hosted/external authority is denied. Local/client tools remain governed
by their existing independent key/route/request policies. SLAIF reserves known
model exposure before forwarding and finalizes actual provider usage afterward.
Provider invoice truth and ordinary provider usage variation remain outside an
absolute zero-overrun promise, but there is no deliberately admitted invisible
provider-hosted tool loop.

### Fenced external-tool mode — explicit opt-in

Provider-hosted/external tools require an exact standard-key policy, exact route
support, operator ceilings, finite key limits, and explicit acknowledgement:

> One admitted provider-hosted external-tool request may exceed the key's
> remaining token or cost quota before SLAIF regains control. SLAIF will reject
> concurrent requests for that key while the request is unresolved, finalize
> authoritative provider usage/cost when available, reject following requests
> after exhaustion, and retain a blocking accounting hold when final cost is
> missing, ambiguous, interrupted, or awaiting reconciliation.

Objective 012 defines this promise but does not implement the fence, hold,
forwarding, storage, admin controls, or selected provider contracts. Objectives
013–017 own those steps. Documentation must not describe them as currently
active.

## Authority taxonomy

Add `app/slaif_gateway/services/external_tool_policy_contract.py` as a pure
contract module. Use canonical low-cardinality identifiers; raw provider names,
URLs, credentials, tool arguments/results, prompts, or arbitrary labels never
enter decisions or safe DTO output.

### Client-operated/local authority

Recognize only exact reviewed shapes without provider-side markers:

- `function`;
- `custom`;
- current gated Codex `namespace` declarations;
- `local_shell`;
- client-executed `apply_patch`.

The model asks; the client executes; SLAIF meters each model request. SLAIF does
not execute the tool or meter the external service cost of a client-operated
tool. Client-side MCP/network activity that is not represented as provider-
hosted wire authority remains a client deployment/configuration responsibility;
do not falsely claim the gateway can observe or block undeclared client action.

### Provider-hosted/external authority

Canonical capability IDs must cover at least:

```text
provider_web_search
provider_file_search
provider_code_interpreter
provider_hosted_shell
provider_image_generation
provider_computer_use
provider_tool_search
provider_skill
provider_remote_mcp
provider_connector
provider_url_fetch
```

Map exact current wire aliases, including `web_search`/
`web_search_preview`, `file_search`, `code_interpreter`, provider `shell`,
`image_generation`, `computer`/`computer_use`/preview aliases, `tool_search`,
`skill`/`skills`, and `mcp`. Chat Completions `web_search_options` and known
search-specific models map to `provider_web_search`. Provider-side fetching of
remote image/file URLs is `provider_url_fetch` external authority even though
it is not a tool call; keep it separately identifiable.

For `type=mcp`, distinguish an operator-reviewed connector ID from an operator-
reviewed remote-MCP destination ID, but both remain provider-side external
authority. Any `server_url`, `connector_id`, provider authorization, approval,
deferred loading, or equivalent provider-side marker makes the containing
shape external regardless of its claimed local type.

Client-provided `authorization`, bearer material, cookies, or arbitrary MCP URL
must never become an allowed destination. A future selected provider contract
must resolve an opaque reviewed destination ID to server-side configuration.
Request `require_approval` can never lower the operator/route approval floor.

### Ambiguous and unknown authority

Malformed tool objects, unknown types, mixed local/external markers, aliases
not in the reviewed map, and unknown tool-choice types classify as
`unknown_external_authority` and are denied. Never guess local authority from a
name, description, function schema, namespace, or model.

Background execution, provider-stored state, previous-response state, and
provider authentication are distinct unsupported authority/state surfaces.
External-tool opt-in must not implicitly enable them.

## Exact mechanically representable schemas

### Per-key policy

Parse only an exact object named conceptually `external_tool_policy`:

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

The only external mode is `external_tool_fenced`. It requires:

- a non-empty deduplicated canonical capability allowlist;
- opaque normalized destination IDs only when a selected capability needs
  destinations;
- a positive integer tool-call cap no greater than the absolute operator cap;
- literal `single_request_overrun_acknowledged=true`;
- a standard, non-calibration key with positive finite request, token, and EUR
  cost limits at decision time.

Strict mode must be exactly empty/zero/false. Missing policy is strict denial.
Malformed, partial, extra-key, coerced, duplicated, unknown, overlong, URL-like,
or secret-looking values are invalid and deny, never interpreted as opt-in.

### Per-route policy

Parse only an exact route-capability object conceptually under
`capabilities.external_tools`:

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

External support requires non-empty known capabilities, bounded reviewed
destination IDs, positive route call cap, and all three enforcement/evidence
booleans true. Empty/strict route metadata is exact empty/zero/false. Missing or
invalid metadata grants no support. A model/tool name alone is never a route
capability.

### Operator ceilings

Define a strict immutable operator-ceilings DTO with conservative absolute
defaults and hard validation. At minimum bound:

- distinct external capability count;
- approved destination count;
- provider tool declarations per request;
- provider tool calls/iterations per request.

Recommended initial absolute maxima are 16 capabilities, 8 destinations, 16
tool declarations, and 16 provider calls. Key and route policy may only narrow
them. This module must not add settings/env vars yet; objective 013 owns durable
operator configuration and surfaces.

## Pure admission decision

Provide a pure decision function over:

- classified request facts;
- parsed key policy;
- parsed route policy;
- operator ceilings;
- finite-limit/key-purpose facts.

Return a deterministic safe DTO with `allowed`, quota mode, effective tool-call
cap, fixed reason codes, and these exact positive obligations:

```text
exclusive_key_fence_required=true
single_request_overrun_accepted=true
hold_on_missing_or_ambiguous_final_cost=true
following_requests_block_after_exhaustion=true
```

It may return external-tool allowed only when:

1. every requested canonical capability is known and is in both key and route
   allowlists;
2. every requested destination ID is in both key and route lists;
3. declaration/call counts fit key, route, and operator ceilings;
4. route call-limit/final-usage/final-cost flags are true;
5. key overrun acknowledgement is literal true;
6. key is standard and all request/token/EUR limits are positive finite.

No external facts should preserve strict normal processing without requiring an
external policy. Any unknown/ambiguous fact, invalid policy, missing route
support, unbounded key, destination mismatch, excess count, unsupported state,
or missing acknowledgement denies with fixed low-cardinality codes. Do not
include raw fields/values in exceptions, decisions, logs, or repr.

## Documentation contract

Synchronize terminology and status across behavior/security/accounting/product
docs:

- distinguish client-local, provider-hosted, remote MCP/connector, provider URL
  fetch, and unknown authority;
- use `strict_bounded` and `external_tool_fenced` consistently;
- state the exact single-request overrun/concurrent fence/following block/
  missing-cost hold promise;
- state current runtime remains deny-only until 013–017;
- preserve PostgreSQL quota truth, provider final cost authority, no-content
  storage, credential isolation, and no invoice/compliance claims;
- remove or qualify absolute “hard quota means no request can overrun” language
  where it would contradict existing finalization behavior or the external
  promise;
- keep trusted calibration observation separate from standard-key permission.

Add an explicit versioned schema/example section to
`docs/database-schema.md`, while stating no migration/storage integration occurs
in objective 012.

## Allowed paths

Implementation may change only:

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

The final report-only commit adds only:

```text
oap/reports/012-a-external-tool-policy-contract-taxonomy.md
```

Do not modify current request/runtime hosted-tool enforcement, key service/DB
models, route service, migrations, admin/CLI/templates, provider adapters,
quota/accounting implementation, dependencies, settings/env files, CI, Compose,
README, fixtures, or prior OAP history. If another exact path is required, stop
and report `BLOCKED` for a narrow 012 continuation.

## Focused verification and test economy

Run only:

- the new pure contract/taxonomy unit file;
- focused documentation/OAP drift tests;
- scoped Ruff/format/compile, exact path/topology, official-reference links,
  and `git diff --check`;
- deterministic scans for contradictory quota/tool/current-status language.

Do not run local full unit, integration/PostgreSQL, E2E, Playwright/browser,
Docker/Compose, HPC, manual Codex, or upstream-provider suites. No runtime or DB
behavior changes. GitHub CI owns broad routine coverage. Never call a provider,
gateway, external tool, remote URL/MCP server, production, or staging system.

## Acceptance criteria

1. Every reviewed local/provider/MCP/connector/URL-fetch alias maps to one exact
   authority class; malformed/unknown/mixed shapes fail closed as unknown
   external authority.
2. Exact v1 key/route schemas reject partial, extra, coerced, duplicate,
   unknown, URL-like, secret-looking, and over-ceiling inputs; missing policy is
   strict deny.
3. The pure admission matrix allows only exact standard finite opt-in
   intersections and exposes fence/overrun/hold/following-block obligations;
   it never enables runtime forwarding.
4. Strict mode remains default and current runtime behavior remains deny-only.
   Trusted calibration and client-local tools do not become standard-key hosted
   permission.
5. All affected docs use the same two quota modes and honest promise, with no
   absolute no-overrun/provider-invoice/compliance claim or future feature
   represented as implemented.
6. Focused tests/docs/privacy/path checks and every required report-head GitHub
   check pass; no broad local suite or real external call runs.
7. One new objective-012 PR only; coding agent never merges/enables auto-merge;
   immutable report topology satisfies `SELF`.

## GitHub and report contract

Commit the unchanged 012-a order and `oap/active=012-a` with implementation,
push the required new branch, and create exactly one non-draft PR against
`main` with the exact title. Inspect GitHub checks and repair only in-scope
failures. Never merge or enable auto-merge.

Publish exactly one immutable report at
`oap/reports/012-a-external-tool-policy-contract-taxonomy.md` with literal
implementation SHA, `Report publication commit: SELF`, exact taxonomy/schema/
decision matrices, documentation/contradiction scans, focused tests, GitHub
checks, all broad suites not run, official OpenAI documentation impact,
no-provider/no-runtime/no-migration evidence, and no-merge/no-auto-merge. The
final commit changes only that report and has the implementation head as first
parent. Verify remote report head and required checks, then signal exact `OK`.

