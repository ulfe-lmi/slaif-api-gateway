# OAP Coding-Agent Report — 012-b

## Work order

- Identifier: `012-b`
- Work-order file:
  `oap/orders/012-b-make-authority-scanning-position-aware.md`
- Work-order SHA-256:
  `b32a07e3ad7cc8daa4ae5e4582dd75a315cfc9f6618b5a2c86d49bfe872bfb0d`
- Active-pointer SHA-256:
  `3e55df0e0968cf55146cf8bb3937bde9c72b55b0bfc08f4258806cb541fb48f3`
- Numeric objective: `012`
- PR mode: `AMEND_EXISTING_PR`

## Status

COMPLETE

## Executive summary

Objective 012-b corrects the pure external-tool authority taxonomy so it
examines provider markers only at semantic declaration/control positions.
Ordinary business-domain property names inside local function parameters/JSON
Schema, descriptions, and custom format/grammar payloads no longer become false
provider authority. Those payloads remain opaque to this taxonomy, are not
retained in its DTOs, and remain independently governed by existing endpoint
validators.

Namespace classification now walks every child with an exact depth bound of
four namespace levels and a total bound of 16 child declarations. Bounded local
function/custom/local children remain client operated; provider tools, raw
MCP/connectors, unknown or malformed children, cycles, excessive depth, and
excessive count fail closed as `unknown_external_authority`.

Provider aliases and MCP/connector authority remain fail closed at their
semantic controls. Raw MCP destinations, authorization, approval, and deferred
loading remain unreviewed external authority and cannot become approved opaque
destinations. Provider filter/query/schema payloads are not recursively treated
as a second authority grant; their complete validation remains objective 016.

All objective-012 key/route schemas, operator ceilings, reviewed destination
rules, standard finite-key requirements, admission decisions, fenced
obligations, and deny-only runtime status are unchanged. No runtime import,
settings/persistence/migration, provider, forwarding, quota, admin, or CLI
wiring was added.

Focused verification passed 149/149 tests and all ten GitHub checks passed on
the literal implementation head. No provider, gateway, URL, MCP server,
external tool, production, staging, database, or real-email action ran.

## Authoritative GitHub state

- Repository: `https://github.com/ulfe-lmi/slaif-api-gateway.git`
- Remote `main` at report drafting:
  `2a3cc6b2ae1b874a08d07d407a38e12933aebd2c`
- Starting remote PR head / immutable 012-a report:
  `9adfc6bab51270df8af519f4b152bf743d5766a6`
- Implementation head SHA:
  `3aaa567ecad6661b997c5ecd68b5d3af86e0467a`
- Implementation-head first parent:
  `9adfc6bab51270df8af519f4b152bf743d5766a6`
- Implementation-head commit message:
  `OAP 012-b: make authority scanning position-aware`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA verified after push)
- Report commit first parent: same as Implementation head SHA
- PR number: `237`
- PR URL: `https://github.com/ulfe-lmi/slaif-api-gateway/pull/237`
- PR title: `[OAP 012] Define external-tool policy and quota promises`
- PR state at report drafting: `OPEN`, non-draft, GitHub `MERGEABLE`
- Base branch: `main`
- Head branch: `oap/012-external-tool-policy-contract-taxonomy`
- Objective-012 PR count: exactly one, PR #237
- Created a new PR this turn: NO
- Amended existing PR #237: YES
- Auto-merge enabled: NO (`autoMergeRequest=null`)
- Merge performed: NO

## Exact authority-position matrix

| Declaration/request position | Taxonomy treatment | Result |
| --- | --- | --- |
| Local `function` or `custom` top-level container | Inspect direct authority-bearing control keys and require a recognizable local name/container | Client operated only with no control marker; otherwise unknown/mixed |
| Nested Chat-style `function` or nested `custom` container | Inspect direct keys in that named container as control positions | Direct `server_url`, `connector_id`, authorization, approval, deferred-loading, server, allowed-tools, credential/header/cookie, or equivalent marker denies |
| Local function `parameters` / JSON Schema | Opaque to authority classification; never recursively scanned or retained | Business properties including `headers`, `authorization`, `server_url`, `connector_id`, `api_key`, `bearer_token`, `cookie`, and `token` do not change client authority |
| Local description | String/content is not scanned or retained | Provider-marker words in prose do not change authority |
| Local custom `format`, grammar, or equivalent client payload | Opaque to authority classification; never recursively scanned or retained | Marker-shaped grammar/business fields do not change client authority |
| `namespace` control level | Inspect direct authority-bearing keys and require a recognizable name plus list | Direct provider control marker denies as mixed/unknown |
| Every namespace child | Traverse bounded child declarations without entering their opaque schema/content | Exact client function/custom/local children pass; provider/MCP/unknown/malformed children fail closed |
| Nested namespace | Traverse namespace containers with cycle detection, maximum depth 4, and total child count 16 | Cycles, fifth namespace level, or seventeenth total child deny |
| Reviewed provider alias control level | Alias remains the canonical provider-external capability; inspect direct control keys | Normal reviewed alias is provider external; an unexpected direct provider-control marker fails closed |
| Provider filter/query/schema payload | Do not recursively reinterpret arbitrary content as a second authority grant | Alias remains provider external; objective 016 retains full contract validation |
| Raw `type=mcp` declaration | Inspect direct semantic destination/control keys only; require exactly one of `server_url` or `connector_id` | Canonical remote-MCP/connector capability, always `unreviewed_external_authority=true`, destination ID absent |
| MCP nested filter/query/schema content | Opaque to destination selection | Cannot create, replace, or ambiguate the semantic destination |
| Unknown type, malformed declaration, or mixed local/external control | Fixed safe unknown classification | Denied fail closed without retaining raw content |

The classifier returns only low-cardinality authority/capability/reason facts.
It never retains or emits local schema, grammar, description, raw MCP value,
authorization, credential, prompt, arguments, result, URL, or arbitrary label.
Classification remains narrower than endpoint validation: `client_operated`
does not mean the request schema/content is valid, accepted, or forwardable.

## Namespace positive and negative evidence

| Case | Expected and observed result |
| --- | --- |
| Namespace containing local function schema business fields, custom grammar marker words, `local_shell`, `apply_patch`, and a bounded nested local namespace | `client_operated`; opaque sentinel absent from DTO repr |
| Namespace with direct `require_approval` | `unknown_external_authority` / mixed local-external control |
| Namespace child `type=mcp` with raw `server_url` | `unknown_external_authority`; child cannot hide MCP authority |
| Namespace child `web_search` | `unknown_external_authority`; child cannot hide provider-hosted authority |
| Namespace child unknown type | `unknown_external_authority` |
| Namespace child malformed function or non-object | `unknown_external_authority` |
| Namespace containing itself | `unknown_external_authority`; traversal terminates through identity-cycle detection |
| Namespace with 17 total child declarations | `unknown_external_authority`; total bound is 16 |
| Five namespace levels | `unknown_external_authority`; maximum depth is four |
| Cyclic object contained only inside local function parameters | `client_operated` at taxonomy level; opaque schema is not traversed and endpoint validation remains independent |

## Preserved MCP/connector evidence

- A direct raw `connector_id` plus authorization and `require_approval`
  classifies as `provider_connector`, retains no destination ID, and remains
  unreviewed external authority.
- A direct raw `server_url` classifies as `provider_remote_mcp`, retains no
  destination ID, and remains unreviewed external authority.
- A nested `connector_id` in an MCP filter does not override or ambiguate a
  direct semantic `server_url`.
- Missing or simultaneous direct `server_url`/`connector_id` destinations fail
  closed.
- Only future server-side `classify_reviewed_external_tool()` resolution can
  create exact `connector:<opaque>` or `remote_mcp:<opaque>` destination facts.
- Request approval cannot lower the operator/route floor.

## Unchanged schema, ceiling, and admission evidence

The continuation did not modify:

- `parse_key_external_tool_policy()` or its exact six-field v1 schema;
- `parse_route_external_tool_policy()` or its exact seven-field v1 schema;
- `ExternalToolOperatorCeilings` or the absolute 16 capability, 8 destination,
  16 declaration, and 16 call maxima;
- canonical capability/alias maps;
- reviewed destination syntax, secret/URL rejection, or capability-kind match;
- `ExternalToolKeyLimitFacts` or the standard positive finite request/token/EUR
  requirements;
- `decide_external_tool_admission()` or any reason/decision ordering; or
- the exact two modes `strict_bounded` and `external_tool_fenced`.

The positive fenced decision continues to return exactly:

```text
allowed=true
quota_mode=external_tool_fenced
exclusive_key_fence_required=true
single_request_overrun_accepted=true
hold_on_missing_or_ambiguous_final_cost=true
following_requests_block_after_exhaustion=true
```

The complete 127-test contract file, including all 012-a schema, ceiling,
finite-key, destination, request classification, admission, and privacy cases,
passed unchanged alongside the new position-aware regressions. Missing policy
remains strict denial, trusted calibration remains distinct from standard-key
permission, and no decision grants runtime forwarding.

## Runtime and privacy boundary

- Application/runtime imports of the contract module outside itself: 0.
- Settings/environment integration: 0.
- Alembic/schema migrations: 0.
- Provider-adapter/request-forwarding integration: 0.
- Key/route persistence, quota fence/hold, admin, CLI, or template integration: 0.
- Generic recursive marker scanner remaining: 0.
- Current hosted-tool/MCP/provider-authority runtime denials changed: NO.
- Existing endpoint-specific validation relaxed or modified: NO.
- Prior immutable 012-a report modified: NO; SHA-256 remained
  `86a49bda57a2e45232315255301ab405d847487d64cac379c5b10f696ba77aec`.

The authority taxonomy answers only who executes or controls a declared tool.
It cannot observe or block undeclared client-side network/MCP activity and does
not confer gateway execution or external-service cost metering for client tools.

## Verification

Final focused pytest command:

```text
.venv/bin/python -m pytest -q tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py tests/unit/test_oap_governance.py
```

Result: PASS, 149/149 tests. Collection comprised 127 external-tool contract
tests, 14 documentation-contract tests, and 8 OAP governance tests.

Additional focused checks:

```text
.venv/bin/python -m ruff check app/slaif_gateway/services/external_tool_policy_contract.py tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py
.venv/bin/python -m ruff format --check app/slaif_gateway/services/external_tool_policy_contract.py tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py
.venv/bin/python -m py_compile app/slaif_gateway/services/external_tool_policy_contract.py tests/unit/test_external_tool_policy_contract.py tests/unit/test_documentation_contract_drift.py
git diff --check
```

Results: Ruff passed; all three scoped files were formatted; compilation passed;
the exact nine-path allowlist, branch/parent topology, runtime non-wiring,
settings/migration non-integration, generic-scanner removal, documentation
status, privacy, prior-report digest, and active/order digest checks passed.
`git diff --check` passed for every implementation path. The unchanged
strategic order has one pre-existing extra blank line at EOF; its exact bytes
and SHA-256 were preserved.

Implementation-head GitHub checks at
`3aaa567ecad6661b997c5ecd68b5d3af86e0467a`:

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

## Bounded failed checks and repairs

1. The first focused run passed all behavior tests but one documentation-drift
   assertion failed because Markdown wrapped the literal phrase
   `function parameters/JSON Schema` between the slash and `JSON`. The wording
   was reflowed without changing meaning.
2. The next focused run passed behavior tests but the new security paragraph
   used `declaration/control level` rather than the shared literal `control
   positions`. It was synchronized to the exact cross-document term.
3. All subsequent focused tests and static checks passed. Neither failed check
   involved runtime execution, a provider, a database, or an external service.

## Acceptance criteria

1. PASS — authority scanning is position aware; benign local schema, grammar,
   description, and business fields cannot become provider authority.
2. PASS — every namespace child is inspected with strict depth/count/cycle
   bounds and cannot hide provider/MCP/unknown/malformed authority.
3. PASS — exact control markers, raw MCP destinations, authorization/approval,
   and unknown shapes remain fail closed and content free.
4. PASS — all 012-a schemas, ceilings, destinations, finite-key requirements,
   admission obligations, quota modes, and deny-only runtime status remain.
5. PASS — focused tests, documentation/privacy/path/non-wiring checks, and all
   implementation-head GitHub checks passed; broad suites/external calls did
   not run.
6. PASS — only PR #237 was amended; no merge/auto-merge occurred; the final
   report commit is SELF and report-only.

## Changes and exact paths

Implementation commit `3aaa567ecad6661b997c5ecd68b5d3af86e0467a`
changed exactly:

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

The strategic order and active pointer were committed unchanged from the
activated inputs. Every earlier order/report remained unchanged. The report
publication commit adds only:

```text
oap/reports/012-b-make-authority-scanning-position-aware.md
```

Documentation updated: AGENTS.md, docs/database-schema.md,
docs/provider-forwarding-contract.md, and docs/security-model.md.

## Scope, omissions, and safety

- Scope deviation: NONE.
- Unexpected unrelated tracked modification: NONE.
- `.local-provider-catalog/` was not modified, staged, or committed.
- Full local unit, integration/PostgreSQL, OpenAI-client E2E,
  Playwright/browser, Docker/Compose, HPC, manual Codex, and
  provider/external-tool suites: NOT RUN, exactly as ordered; broad routine
  coverage was delegated to GitHub CI.
- Provider/gateway/URL/MCP/connector/external-tool call: NONE.
- Production/staging access: NONE.
- Database setup, migration execution, or teardown: NONE.
- Packages/tools/services installed or configured: NONE.
- Sudo-level setup: NONE.
- Credentials searched for or printed: NONE.
- Real email: NONE.
- New PR: NO. Existing PR #237 only.
- Merge: NO.
- Auto-merge: NO.
- Report publication commit changes only this immutable report: YES.

## Coding-agent conclusion

Objective 012-b's execution turn is complete. The external-tool classifier is
semantic-position aware, bounded namespaces cannot hide external authority,
all 012-a policy/admission promises remain unchanged, focused verification and
implementation-head CI passed, runtime remains deny-only, and the coding agent
did not merge or enable auto-merge. Strategic acceptance and any merge decision
remain with the strategic model/human maintainer.
