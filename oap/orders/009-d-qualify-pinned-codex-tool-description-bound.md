# OAP Work Order — 009-d

## Objective

Resolve the exact pinned-client policy blocker reported by 009-c without
weakening ordinary Responses tools: admit Codex 0.147.0's 18,137-byte nested
client-tool description only under the complete exact Codex declaration gate,
with a fixed reviewed 20,000-byte per-description cap, the unchanged 32,768-byte
aggregate cap, conservative metering, and strict negative evidence. Then prove
the real three-request compact verifier succeeds on existing PR #234.

## GitHub state

- Numeric objective `009`, round `009-d`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #234:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`.
- Branch `oap/009-codex-context-output-cache-compaction-accounting`; base
  `main`.
- Starting remote/report head:
  `da375ff9488eeb1cbaaff490c2eef9f539e49fa3`.
- 009-c implementation head:
  `ff1fe09d29764eb0284f9be0d7755965989a994a`.
- 009-c status: `BLOCKED` only because its newly exact policy proof found one
  18,137-byte nested Codex tool description exceeding the ordinary 4,096-byte
  per-tool bound. All focused tests and ten implementation-head checks passed.

Amend PR #234 only. Never create another objective-009 PR.

## Strategic decision and security boundary

The existing ordinary limits remain correct:

```text
RESPONSES_MAX_FUNCTION_TOOL_DESCRIPTION_BYTES=4096
RESPONSES_MAX_CUSTOM_TOOL_DESCRIPTION_BYTES=4096
```

Do not change those settings, their defaults, ordinary top-level function/
custom tool behavior, namespace-description behavior, or their tests.

The fully gated Codex `additional_tools` path already enforces an exact pinned
namespace/tool taxonomy, denies recursive provider/hosted authority, caps each
schema/grammar, caps depth/properties, counts every forwarded byte, and caps all
namespace+tool descriptions together at
`_CODEX_MAX_CLIENT_TOOL_TOTAL_DESCRIPTION_BYTES=32768`. Under only that path,
add a separate fixed per-child-tool description cap:

```text
_CODEX_MAX_CLIENT_TOOL_DESCRIPTION_BYTES = 20_000
```

The cap applies to child `function` and `custom` tools in the exact approved
Codex taxonomy. Namespace descriptions continue to use the ordinary 4,096-byte
cap. No description is trusted authority: all existing hosted/MCP/recursive
authority denials remain, and descriptions remain transient model input only.

This decision is version-pinned qualification, not a generic permission for
large arbitrary tools. The current captured value is 18,137 bytes. A value of
20,000 passes only when every Codex gate/taxonomy check passes; 20,001 fails;
aggregate descriptions above 32,768 still fail.

## Required work

1. Reconcile canonical GitHub, PR #234, all immutable 009 rounds, applicable
   AGENTS/OAP instructions, pinned source/tag/binary, and current exact policy.
2. Commit the strategic `oap/active=009-d` pointer and this order unchanged.
3. Add the fixed Codex-only child-description bound and pass it explicitly into
   the existing function/custom validators only from
   `_validate_codex_additional_tools_item`. Prefer a narrow optional argument or
   dedicated helper; do not duplicate tool validation or bypass any schema,
   grammar, type, name, field, recursion, authority, or canonicalization check.
4. Keep namespace descriptions and ordinary `tools` requests at their existing
   settings-based 4,096 defaults. No configuration, schema, admin, template,
   route, migration, or pricing change is authorized.
5. Add focused tests proving:
   - exact 18,137-byte pinned child description passes under full gates;
   - exact 20,000 passes and 20,001 fails with safe code/parameter;
   - combined descriptions above 32,768 fail even when individuals pass;
   - a 4,097-byte ordinary function/custom description still fails;
   - hosted/provider/MCP authority denial is unchanged for a large description;
   - canonical input/token estimates include the complete large description and
     no description enters errors/evidence.
6. Rerun the exact 009 compact verifier once. It must emit
   `RESULT=OK`, `REQUEST_COUNT=3`, and
   `GATEWAY_COMPACT_POLICY_ACCEPTED=true` along with the existing fixed safe
   keys. Do not print/persist the captured description or any raw request.
7. Update only the contracts that must distinguish the Codex-only 20,000 per-
   child bound from ordinary 4,096 and aggregate 32,768 limits.

## Allowed paths

Implementation may change only:

```text
app/slaif_gateway/services/responses_request_policy.py
docs/accounting.md
docs/codex-compatibility.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/009-d-qualify-pinned-codex-tool-description-bound.md
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_compaction.py
```

Final report-only commit adds only:

```text
oap/reports/009-d-qualify-pinned-codex-tool-description-bound.md
```

The existing verifier must be rerun unchanged. Do not edit it merely to obtain
a pass. Do not change ordinary settings/config, product schemas/migrations,
gateway/accounting/compaction code outside the policy file, dependencies,
fixtures, prior OAP history, CI, deployment, README, or unrelated paths.

## Focused verification and test economy

Run only:

- `tests/unit/test_responses_codex_client_tools.py` and
  `tests/unit/test_responses_codex_compaction.py`;
- focused OAP/documentation contract tests;
- scoped Ruff/compile, `git diff --check`, exact path/topology, fixture digest;
- one final exact pinned Codex context/compaction verifier run.

Do not run full unit, integration, PostgreSQL, E2E, browser, Docker/Compose, or
HPC suites locally. GitHub CI owns broad coverage. Never call a real provider or
side-effecting external tool.

Report literal commands/counts, every broad suite NOT RUN, the exact safe
verifier output, and any failed development attempt honestly.

## Acceptance criteria

1. Exact pinned 18,137-byte description passes only in fully gated exact Codex
   `additional_tools`; 20,000 passes, 20,001 fails, and aggregate >32,768 fails.
2. Ordinary and namespace description caps remain 4,096 by default; no generic
   request, key, model name, or header can reach the Codex-only allowance.
3. All existing field/schema/grammar/taxonomy/authority/privacy validation and
   conservative metering remain intact.
4. Exact unchanged Codex 0.147.0 loopback completes three requests and reports
   gateway compact policy accepted without raw payload persistence/output.
5. Focused tests/docs/quality/path/fixture checks and every report-head GitHub
   check pass; no broad local suite or real provider runs.
6. One existing PR only; coding agent never merges/enables auto-merge; immutable
   report topology satisfies `SELF`.

## PR/report requirements

Commit the unchanged 009-d order/pointer with the focused policy/test/docs
repair, push to PR #234, wait for all implementation-head checks, and never
merge or enable auto-merge. Publish exactly one immutable report at
`oap/reports/009-d-qualify-pinned-codex-tool-description-bound.md` with literal
implementation SHA, `Report publication commit: SELF`, exact boundary/metering/
privacy/verifier evidence, local/GitHub checks, broad suites not run,
documentation impact, and no-merge statement. Final commit changes only that
report and has the implementation head as first parent. Verify remote report
head, then signal exact `OK`.

If the unchanged real verifier still cannot pass or any authority/ordinary cap
must be weakened, report `BLOCKED` rather than widen this decision.
