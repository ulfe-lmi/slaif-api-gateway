# OAP Work Order — 012-b

## Objective

Amend objective-012 PR #237 so provider/external authority is detected only at
semantic tool-control positions, not by recursively treating arbitrary keys
inside local function parameters, custom grammar/format payloads, descriptions,
or other client-owned schema data as provider authority. Preserve fail-closed
unknown/mixed tool declarations, MCP/connector authority, all exact schemas,
ceilings, quota promises, and current deny-only runtime behavior.

## GitHub objective state

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Existing PR: #237,
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/237`.
- PR title: `[OAP 012] Define external-tool policy and quota promises`.
- Required branch: `oap/012-external-tool-policy-contract-taxonomy`.
- Base branch: `main`.
- Remote PR head at activation:
  `9adfc6bab51270df8af519f4b152bf743d5766a6`, the immutable 012-a report
  publication commit.
- Its first parent is implementation head
  `2717003c2981bf40ebaf92cc4ef18c98ba3e6e96`.
- All ten report-head checks were independently observed successful.
- PR #237 is open, non-draft, unique for objective 012, and auto-merge is off.
- Remote `main` remains
  `2a3cc6b2ae1b874a08d07d407a38e12933aebd2c`.
- This is `AMEND_EXISTING_PR`. Reconcile GitHub, amend only PR #237, and never
  create another PR, merge, or enable auto-merge.

## Strategic finding

012-a's `_find_provider_authority_markers()` recursively walks every nested key
inside every declaration. A normal client-operated function can legitimately
define JSON-schema properties named `headers`, `authorization`, `server_url`,
`connector_id`, `token`, or similar business-domain fields. A custom grammar or
description can contain the same words. Those values do not make the provider
execute the tool or grant provider-side authority.

The recursive taxonomy therefore produces a false external-authority result and
contradicts the existing `hosted_tool_policy.py` boundary, which intentionally
does not interpret local function schemas/arguments as hosted execution. If
wired by objective 013, the false positive would deny ordinary client tools for
the wrong reason and make the authority model unusable.

This correction does not relax current request/schema security policy. Existing
Codex additional-tool and endpoint validators may independently reject
authorization/header/secret-like schemas for their own narrower safety
contracts. The external-tool taxonomy answers only **who executes or controls
the declared tool**; it does not make an otherwise invalid request valid.

## Required position-aware classification

### Client function/custom declarations

For reviewed `function` and `custom` shapes:

- inspect the declaration/control level for provider markers;
- accept exact recognizable local name/function/custom containers when no
  control-level provider marker exists;
- treat function `parameters`/JSON Schema, descriptions, custom `format`,
  grammar definitions, and equivalent client-owned payloads as opaque for
  **authority classification**;
- do not retain or emit their content;
- leave full shape/size/depth/secret/security validation to existing endpoint
  policies.

A top-level or exact provider-control-position `server_url`, `connector_id`,
`authorization`, `require_approval`, `defer_loading`, `server_label`,
`allowed_tools`, credential/header container, or equivalent marker on a claimed
local declaration remains mixed/unknown external authority and denies.

### Namespace declarations

Current gated Codex namespaces remain client-operated only when:

- the namespace control level has no provider marker;
- the namespace has a bounded recognizable child-tool list;
- every child is an exact client-operated function/custom/local declaration
  under the same opaque-schema rule.

Nested/recursive namespace cycles, excessive nesting/count, provider-hosted,
MCP/connector, malformed, or unknown child declarations must fail closed as
unknown/mixed external authority. Do not silently discard an external child.

### Provider-hosted and MCP declarations

Provider tool aliases remain provider external. `type=mcp` must continue to
require exactly one semantic destination marker (`server_url` or
`connector_id`) and classify the raw request destination as unreviewed external
authority. Authorization/approval/deferred-loading fields remain external
control facts. Only future server-side `classify_reviewed_external_tool()`
resolution may produce an admissible opaque destination ID.

For provider tool configuration, inspect only reviewed control positions. Do
not recursively reinterpret arbitrary provider filter/query/schema content as a
second authority grant; full provider-contract validation remains objective
016.

Remove the duplicated MCP destination assignment and replace the generic
recursive scanner with small explicit position-aware helpers. Bound namespace
child traversal without recursively entering opaque schemas or raw content.

## Focused regression matrix

Add direct tests proving:

1. local Responses-style and Chat-style function declarations remain
   `client_operated` when their parameter schemas contain properties named
   `headers`, `authorization`, `server_url`, `connector_id`, `api_key`,
   `bearer_token`, `cookie`, or `token`;
2. equivalent custom descriptions/format/grammar payloads do not change the
   authority class and are not retained in DTO/repr;
3. a namespace containing only such local children remains client operated;
4. a namespace containing MCP, provider-hosted, unknown, malformed, cyclic, or
   excessive children fails closed and cannot hide the child authority;
5. the same markers at exact declaration/control positions still produce
   mixed/unreviewed external denial;
6. raw MCP `server_url`/connector/authorization/approval remains external and
   never becomes an approved destination;
7. all 012-a key/route schema, ceiling, finite-key, destination, and admission
   decision matrices remain unchanged.

Tests must not assert that a taxonomy-level client classification guarantees
endpoint acceptance. Add one explicit test/doc statement that current request
validators retain independent authority/schema/content enforcement.

## Documentation correction

Update only affected passages to say:

- provider markers are examined at authority-bearing control positions;
- local function parameters/custom grammar/descriptions are opaque to this
  taxonomy but still governed by existing endpoint validators;
- namespace children cannot hide external authority;
- current runtime remains deny-only and this correction grants nothing.

The immutable 012-a report remains unchanged historical evidence; the 012-b
report records the corrected rule.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/services/external_tool_policy_contract.py
docs/database-schema.md
docs/provider-forwarding-contract.md
docs/security-model.md
oap/active
oap/orders/012-b-make-authority-scanning-position-aware.md
tests/unit/test_documentation_contract_drift.py
tests/unit/test_external_tool_policy_contract.py
```

The final report-only commit adds only:

```text
oap/reports/012-b-make-authority-scanning-position-aware.md
```

Do not edit runtime request policy, current hosted-tool enforcement, settings,
persistence, migrations, admin/CLI, providers, quota/accounting, other docs, or
earlier OAP history. If another path is genuinely required, report `BLOCKED`
for a narrow 012-c decision.

## Focused verification and test economy

Run only:

- `tests/unit/test_external_tool_policy_contract.py`;
- focused OAP/documentation drift tests;
- scoped Ruff/format/compile, exact paths/topology, runtime non-wiring scan, and
  `git diff --check`.

Do not run local full unit, integration/PostgreSQL, E2E, Playwright/browser,
Docker/Compose, HPC, manual Codex, or provider/external-tool suites. GitHub CI
owns broad routine coverage. Never call a provider, gateway, URL, MCP server,
external tool, production, or staging system.

## Acceptance criteria

1. Authority scanning is semantic-position aware; benign local schemas,
   grammars, descriptions, and business fields cannot become provider authority.
2. Namespace children cannot hide provider/MCP/unknown/malformed authority and
   traversal is bounded without entering opaque schema content.
3. Exact top-level/control markers, MCP destinations, authorization, approval,
   and unknown shapes still fail closed.
4. All 012-a policy schemas, ceilings, destination safety, finite-key
   requirements, fenced obligations, and deny-only runtime status remain.
5. Focused tests/docs/privacy/path checks and all report-head GitHub checks pass;
   no broad suite or external call runs.
6. Only PR #237 is amended; coding agent never merges/enables auto-merge; final
   012-b report has valid `SELF` topology.

## GitHub and report contract

Commit the unchanged 012-b order and `oap/active=012-b` with the narrow repair
on the existing branch, push it, and update PR #237's body. Preserve earlier
commits/reports. Inspect GitHub checks and repair only in-scope failures. Never
merge or enable auto-merge.

Publish exactly one immutable report at
`oap/reports/012-b-make-authority-scanning-position-aware.md` with literal
implementation SHA, `Report publication commit: SELF`, exact authority-position
matrix, namespace negative evidence, unchanged admission/schema evidence,
focused tests, GitHub checks, broad suites not run, runtime/provider NOT RUN,
and no-merge/no-auto-merge. The final commit changes only that report and has
the implementation head as first parent. Verify remote report head and required
checks, then signal exact `OK`.

