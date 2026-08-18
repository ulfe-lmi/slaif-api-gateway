# OAP Work Order — 006-a

## Objective

Implement the pinned Codex CLI 0.147.0 Responses-lite client-tool declaration
contract: validate and reconstruct the captured `additional_tools` input item,
its `functions`/`collaboration` namespace containers, and exact nested client
tool taxonomy behind explicit key and route gates, while the gateway executes
nothing and all provider-hosted/remote/unknown authority remains denied.

Tool-call/output streaming and actual Codex round trips remain objective 007.

## GitHub state

- Objective/round: `006-a`; PR mode: `CREATE_NEW_PR`.
- Repository/base: `ulfe-lmi/slaif-api-gateway`, `main`.
- Starting main: `c6d9750f82a38b7a7af69ca55eaef6d3d1f28ec5`.
- Objective 005/PR #230 is merged.
- Branch: `oap/006-codex-client-tool-taxonomy-namespaces`.
- PR title: `[OAP 006] Gate Codex client tool namespaces`.
- Unrelated expected open PR: Dependabot #224 only.

Create exactly one PR; continuations amend it.

## Captured authority and exact profile

Use the immutable objective-004 fixture and its approved SHA as structural
evidence. It records a Responses-lite `additional_tools` item with:

- namespace `functions`:
  - `exec` — nested `custom` grammar tool;
  - `wait` — nested `function` tool;
  - `request_user_input` — nested `function` tool;
- namespace `collaboration`:
  - `followup_task`, `interrupt_agent`, `list_agents`, `send_message`,
    `spawn_agent`, `wait_agent` — nested `function` tools.

These are declarations for tools executed by Codex/the client after a model
requests them. Shape plus explicit profile gates establish execution authority;
names alone never do. The gateway forwards approved declarations and meters
model requests, but does not run a tool or claim to meter client-side external
tool cost.

The fixture compatibility diff is the frozen pre-005 baseline and remains
byte-identical. Current behavior is tested separately.

## Governing/start requirements

Read complete AGENTS/OAP governance, Codex/Responses/accounting/forwarding/
security/template contracts, merged 005 implementation/tests, pinned fixture,
request policy, route/key gates, normalized payload builders, and tagged Codex
source. Verify GitHub/main, PR #230 merge, no objective-006 PR, clean worktree,
and fixture SHA.

The strategic model atomically published this order and `oap/active=006-a`;
commit their exact bytes. Branch from current `origin/main`. Preserve all
unrelated local state and user/provider credentials/config.

## Allowed paths

Implementation may change only:

```text
AGENTS.md
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_route_capabilities.py
docs/accounting.md
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/006-a-codex-client-tool-taxonomy-namespaces.md
tests/unit/test_codex_protocol_capture.py
tests/unit/test_key_template_service.py
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_envelope.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_route_capabilities.py
tests/unit/test_upstream_payload_reconstruction.py
```

Final report-only commit adds only
`oap/reports/006-a-codex-client-tool-taxonomy-namespaces.md`.

Do not edit capture script/fixture, upstream dataclass/builders unless a
verified need requires strategic continuation, API schema, database/migrations,
settings, dependencies, providers, CI, deployment, README, or prior history.

## Dual client-tool capability

Add `codex_client_tools` to safe key-template and known route capability
vocabularies, default false and never calibration/default enabled.

An `additional_tools` request requires **both** explicit key capabilities:

```text
codex_request_envelope
codex_client_tools
```

and both explicit route capabilities. Neither implies the other. Ordinary
Responses endpoint/model permission and existing function/custom tool
capabilities do not imply Codex namespace permission.

Key/tool-shape denial occurs before route/DB work; route denial occurs before
Redis, pricing, quota, or provider calls. Detect from input shape, never headers
or names alone.

## Input and taxonomy contract

### `additional_tools` item

- Accept only inside bounded Responses `input` arrays.
- Exact fields: `type`, `role`, `tools`; exact type `additional_tools`; exact
  role `developer`.
- Exactly two unique namespace containers are required for this pinned profile:
  `functions` and `collaboration`; deterministic canonical order.
- No `id`, content, metadata, results, provider state, or extra fields.
- One such item maximum; it is a declaration, not message content.

### Namespace containers

- Exact type `namespace`; fields limited to `type`, `name`, optional bounded
  description, and `tools`.
- Require the exact namespace name set above; names unique.
- Nested namespace/container depth greater than one is denied.
- Descriptions are bounded provider input, never stored/logged.

### Exact nested tool map

Require exact namespace/name/type mapping from the captured profile. Unknown,
missing, duplicate, moved-between-namespace, or changed-type tool declarations
fail closed. Tool names are evidence selectors, not authority by themselves.

- Nested `function` tools reuse current strict bounded function validation:
  fields, identifier, description, JSON schema depth/property/byte/count caps,
  `strict`, and no provider-authority markers.
- `functions.exec` is the one nested `custom` grammar tool. Validate exact
  custom fields and bounded `format.type="grammar"`, allowlisted syntax from
  current local custom-tool policy, and bounded definition bytes.
- Reconstruct fresh dict/list values and deep-copy schema/format structures.
- Recursively reject `server_url`, connector/auth/header/secret/approval
  markers, hosted types, MCP, shell/local_shell/apply_patch/computer/web/file/
  code-interpreter/image/tool-search provider shapes, or unknown fields.

The `exec` declaration may describe client-local operations, including patch
commands, but does not authorize the gateway/provider to execute shell/patch.

### Tool choice and streaming boundary

For an approved additional-tools declaration, accept string `tool_choice`
`none|auto|required`; the pinned profile uses `auto`. Do not accept named/object
choice in this slice. Without approved additional tools/top-level local tools,
existing choice rules remain.

Streaming request admission may carry declarations, but current gateway stream
event allowlist still rejects tool-call/output-item/reasoning events. Do not
claim a completed tool loop or relax event policy here.

## Estimation/privacy/reconstruction

- Count namespace/container fields, descriptions, every nested tool schema/
  grammar definition, and choice bytes conservatively in input admission.
- Enforce total namespace/tool/property/depth/schema/format byte/count caps;
  reject before Redis/pricing/quota/provider.
- Safe estimation evidence contains only approved field/category names and
  aggregate bytes/tokens/counts, never descriptions, property names, grammar,
  tool arguments/results, or schemas.
- Canonical approved `additional_tools` remains inside policy-approved input and
  is forwarded through existing rebuilt Responses payload. No raw body pass.
- Never store/log/audit/export tool descriptions, schemas, grammar, arguments,
  results, client IDs, prompts, or completions.
- PostgreSQL quota/finalization and provider usage remain authoritative. The
  gateway meters model requests, not client-executed tool/service cost.

## Still denied

- Any provider-hosted/external/MCP/connector authority.
- Top-level hosted tools; ambiguous or unknown types/names/namespaces.
- Arbitrary user-defined namespaces/tools outside pinned profile.
- Gateway-side execution of any declaration.
- Tool call/output continuation input and new SSE events until 007.
- Background/state/WebSocket and other future Codex slices.

## Tests

Create `tests/unit/test_responses_codex_client_tools.py` and minimally extend
existing focused tests. Cover:

1. no/key-only/route-only/malformed gates deny; both envelope+tool key/route
   gates required;
2. exact captured namespace/name/type map passes policy and reaches mocked
   provider canonically, with resolved model and no raw extras;
3. every missing/extra/duplicate/moved/wrong-type namespace/tool case denies;
4. depth/count/description/schema/property/grammar/total-byte limits;
5. recursive provider-authority/hosted/MCP/shell/patch/computer/search markers
   deny before route/Redis/pricing/quota/provider;
6. `tool_choice` string rules and no named/object choice;
7. existing top-level local function/custom behavior remains distinct;
8. streaming declarations can be admitted but unsupported tool/output/reasoning
   events remain rejected/documented;
9. estimation increases and exposes only safe aggregate names/counts;
10. provider/log/error/metric/ledger/audit surfaces contain no schema,
    description, grammar, argument/result, prompt, or identifier canaries;
11. templates explicitly propagate both caps, never default them, and retain
    hosted/storage denial;
12. route defaults/unknown flag behavior remain fail closed;
13. immutable fixture/SHA and frozen baseline classifier remain exact;
14. current post-006 request admission is complete for the captured request,
    while response/event/tool-roundtrip compatibility remains incomplete.

No real provider/tool execution.

## Documentation

Update AGENTS and Codex, Responses, forwarding, accounting, security, and
compatibility-matrix contracts with exact dual capability, client execution
ownership, taxonomy, caps, forwarding, estimation/privacy, and remaining 007
event gap. Status: captured request can be admitted for approved profile, but
SLAIF is still **not fully Codex-compatible**. README remains unchanged.

## Non-goals/test economy

No gateway tool execution, hosted/MCP/remote authority, new SSE events/tool
round trips, schema/settings/dependency/CI/admin UI/fixture change, real
provider, production/staging/catalog work, or full compatibility claim.

Do not run full local unit/integration/E2E/browser/Docker/HPC. Run only:

```bash
.venv/bin/python -m pytest tests/unit/test_responses_codex_client_tools.py -q
.venv/bin/python -m pytest tests/unit/test_responses_codex_envelope.py -q
.venv/bin/python -m pytest tests/unit/test_responses_request_policy.py -q
.venv/bin/python -m pytest tests/unit/test_responses_route_capabilities.py -q
.venv/bin/python -m pytest tests/unit/test_upstream_payload_reconstruction.py -q
.venv/bin/python -m pytest tests/unit/test_key_template_service.py -q
.venv/bin/python -m pytest tests/unit/test_codex_protocol_capture.py -q
.venv/bin/python -m pytest tests/unit/test_documentation_contract_drift.py -q
.venv/bin/python -m pytest tests/unit/test_oap_governance.py -q
.venv/bin/ruff check app/slaif_gateway/services/responses_request_policy.py app/slaif_gateway/services/responses_route_capabilities.py app/slaif_gateway/services/responses_gateway.py app/slaif_gateway/services/key_template_service.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_envelope.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_route_capabilities.py tests/unit/test_upstream_payload_reconstruction.py tests/unit/test_key_template_service.py tests/unit/test_codex_protocol_capture.py
git diff --check
sha256sum tests/fixtures/codex/0.147.0/gpt-5.6-sol-api-key-responses.json
git status --short
```

Rerun only affected focused commands. GitHub CI supplies broad evidence.

## Acceptance/PR/report gate

Success requires exact dual-gated declaration admission, recursive authority
denial, bounded conservative estimation, canonical no-execution forwarding,
privacy evidence, unchanged fixture, honest remaining event gap, focused tests,
and all final GitHub checks.

Commit unchanged order/pointer with implementation, create one non-draft PR on
the required branch/title, inspect real checks, and never merge/auto-merge.
Publish one immutable report at
`oap/reports/006-a-codex-client-tool-taxonomy-namespaces.md` with literal
implementation SHA, `Report publication commit: SELF`, exact behavior/tests/
privacy/ordering/fixture evidence, broad suites not run, and docs impact. Final
commit changes only report and has implementation head as first parent; verify
and signal exact `OK`.

If execution ownership, exact taxonomy, privacy, or event separation cannot be
proved, report a blocker rather than broaden. Do not merge.
