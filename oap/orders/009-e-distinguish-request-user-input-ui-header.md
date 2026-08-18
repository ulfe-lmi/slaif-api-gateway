# OAP Work Order — 009-e

## Objective

Resolve the exact pinned-client authority-detector false positive reported by
009-d: distinguish the one benign `request_user_input` JSON-schema property
named `header` (a short UI label) from provider HTTP headers, without weakening
any other nested authority, hosted-tool, MCP, secret, connector, approval, or
ordinary-tool denial. Then make the unchanged exact Codex 0.147.0 compact
verifier complete on existing PR #234.

## GitHub state

- Numeric objective `009`, round `009-e`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #234:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`.
- Branch `oap/009-codex-context-output-cache-compaction-accounting`; base
  `main`.
- Starting remote/report head:
  `6a0d062f6c1832ae781bcd1bdc9db86dfba9b165`.
- 009-d implementation head:
  `dfcdbbba29cf0f0a04332888ce676cf40ed9ab68`.
- 009-d status: `BLOCKED` only because the unchanged exact verifier next hit
  safe code `responses_codex_client_tools_provider_authority_not_supported` at
  pinned declaration `input[0].tools[0].tools[2]`, `request_user_input`. Its
  focused tests and ten implementation-head checks passed.

Amend PR #234 only. Never create another objective-009 PR.

## Pinned-source finding and strategic decision

Pinned source `rust-v0.147.0` at
`be6e8eac029b183056b7e4402879f15d2c85f61b`, file
`codex-rs/core/src/tools/handlers/request_user_input_spec.rs`, defines a local
client function `request_user_input`. Its question schema contains:

```text
parameters.properties.questions.items.properties.header
```

That `header` is a short user-interface label, not an HTTP header or provider
authorization surface. The recursive Codex authority detector currently rejects
any nested key containing `header`, producing the false positive.

Under only the already exact, fully gated taxonomy tuple:

```text
namespace=functions
tool=request_user_input
type=function
```

allow the normalized key `header` only at this complete path:

```text
parameters.properties.questions.items.properties.header
```

This is not a general string/substring exemption. Continue to reject:

- `headers`, `http_headers`, `request_headers`, or any other header-bearing key;
- `header` at every other path or tool;
- authorization/authentication/auth/API keys/secrets;
- connector/server/MCP/approval fields;
- hosted/shell/computer/search/interpreter/image/tool-search types;
- any unknown outer declaration field or taxonomy mismatch.

Ordinary Responses tools and all other Codex tools keep the current detector
unchanged. The exact schema still passes all existing size/depth/property/type/
additional-properties checks and is conservatively metered.

## Required work

1. Reconcile canonical GitHub, PR #234, every immutable 009 round, applicable
   AGENTS/OAP instructions, pinned source/tag/binary, and current detector/tests.
2. Commit the strategic `oap/active=009-e` pointer and this order unchanged.
3. Make the recursive detector path-aware with an optional immutable set of
   complete allowed key paths (or equivalent narrow mechanism). Supply exactly
   the one UI-header path only after namespace/name/type match the approved
   `functions.request_user_input` taxonomy. Default/no allowlist behavior must
   remain byte-for-byte semantically strict.
4. Do not skip the recursive scan for the tool or its parameters. Continue
   scanning the allowed `header` property's nested schema and every sibling.
5. Add focused tests proving:
   - exact pinned request-user-input schema with the path-exact UI `header`
     passes under all gates and remains metered;
   - `headers` at that location fails;
   - singular `header` one level higher/lower and elsewhere fails;
   - the same exact path under another namespace/tool fails;
   - nested `authorization`, `secret`, connector, server URL, approval, MCP,
     and hosted type siblings still fail;
   - no private canary/path content enters safe messages/evidence;
   - ordinary tools remain unchanged.
6. Rerun the unchanged exact 009 verifier once. It must emit `RESULT=OK`,
   `REQUEST_COUNT=3`, `GATEWAY_COMPACT_POLICY_ACCEPTED=true`, and all prior fixed
   safety booleans. Do not edit the verifier or print/persist any raw payload.
7. Update only contracts that must explain the path-exact UI-header distinction
   and unchanged provider-header/authority denial.

## Allowed paths

Implementation may change only:

```text
app/slaif_gateway/services/responses_request_policy.py
docs/codex-compatibility.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/009-e-distinguish-request-user-input-ui-header.md
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_compaction.py
```

Final report-only commit adds only:

```text
oap/reports/009-e-distinguish-request-user-input-ui-header.md
```

The verifier must remain unchanged. Do not edit settings/config, ordinary tool
contracts, gateway/accounting/compaction code outside the policy file,
schema/migrations, dependencies, fixtures, prior OAP history, CI, deployment,
README, or unrelated paths.

## Focused verification and test economy

Run only:

- `tests/unit/test_responses_codex_client_tools.py` and
  `tests/unit/test_responses_codex_compaction.py`;
- focused OAP/documentation contract tests;
- scoped Ruff/compile, `git diff --check`, exact path/topology, fixture digest;
- one final unchanged exact pinned Codex context/compaction verifier run.

Do not run full unit, integration, PostgreSQL, E2E, browser, Docker/Compose, or
HPC suites locally. GitHub CI owns broad coverage. Never call a real provider or
side-effecting external tool.

Report literal commands/counts, exact safe verifier keys, every broad suite NOT
RUN, and failed development attempts honestly.

## Acceptance criteria

1. Only the exact pinned UI-header key/path/tool/namespace exception passes;
   plural/alternate paths and every other tool remain denied.
2. All auth/secret/connector/server/approval/MCP/hosted recursive denials,
   ordinary behavior, schema bounds, exact taxonomy, and metering remain intact.
3. The unchanged exact Codex 0.147.0 verifier completes its three-request V1
   compact loop and reports gateway policy accepted with no raw persistence/
   output or real provider call.
4. Focused tests/docs/quality/path/fixture checks and every report-head GitHub
   check pass; no broad local suite runs.
5. One existing PR only; coding agent never merges/enables auto-merge; immutable
   report topology satisfies `SELF`.

## PR/report requirements

Commit the unchanged 009-e order/pointer with the focused policy/test/docs
repair, push to PR #234, wait for all implementation-head checks, and never
merge or enable auto-merge. Publish exactly one immutable report at
`oap/reports/009-e-distinguish-request-user-input-ui-header.md` with literal
implementation SHA, `Report publication commit: SELF`, exact path/authority/
metering/privacy/verifier evidence, local/GitHub checks, broad suites not run,
documentation impact, and no-merge statement. Final commit changes only that
report and has the implementation head as first parent. Verify remote report
head, then signal exact `OK`.

If the unchanged verifier exposes another mismatch or any broader authority
exception is required, report `BLOCKED`; do not generalize this decision.
