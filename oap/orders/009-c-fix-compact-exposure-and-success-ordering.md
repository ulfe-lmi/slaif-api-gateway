# OAP Work Order — 009-c

## Objective

Resolve three strategic acceptance defects in the substantive 009-a V1 compact
path on existing PR #234: reserve the full configured compact output exposure
when the pinned endpoint cannot carry `max_output_tokens`, emit success metrics
only after HMAC replay persistence succeeds, and make the exact pinned-CLI
compact request prove it passes the gateway's own strict policy. Also reject
unknown compact response fields without narrowing documented safe metadata.

## GitHub state

- Numeric objective `009`, round `009-c`.
- PR mode: `AMEND_EXISTING_PR`.
- Existing PR #234:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/234`.
- Branch `oap/009-codex-context-output-cache-compaction-accounting`; base
  `main`.
- Starting remote/report head:
  `0b4b24d3ff7465210be2db9ba43e8dfb99a1c5b7`.
- 009-a product implementation:
  `1fcb90b2e947c1cd4a43c68b34e5f6ad04353600`.
- 009-b migration-expectation implementation:
  `38548620aa5edfe58104b5f3e2ba39094c33d923`.
- All ten current report-head checks are green. This continuation is required
  by independent strategic review, not by CI.

Amend PR #234 only. Never create another objective-009 PR.

## Strategic findings

### 1. Compact admission under-reserves output exposure

Pinned Codex V1 `POST /v1/responses/compact` intentionally omits
`max_output_tokens`. The gateway correctly preserves that exact upstream shape,
but `apply_codex_route_limits(..., include_output_field=False)` currently uses
the route default (qualification value 32,768) for reservation. Because no
field constrains the provider to that default, the maximum bounded provider
exposure is the route/model maximum (qualification value 128,000). Reserving
only 32,768 violates the objective's conservative admission contract.

For a gated V1 compact request, keep `max_output_tokens` absent upstream but set
the effective/requested output exposure used by context checks, quota, pricing,
live accounting, and evidence to the validated route maximum. The route maximum
must already be within the operator absolute ceiling. Ordinary Responses and
non-Codex compact behavior remain unchanged.

### 2. Success metrics precede the final success boundary

`handle_response_compact` currently calls `_record_success_metrics` immediately
after accounting finalization and before `_persist_codex_replay_references`.
If HMAC persistence then fails, accounting is correctly charged and the client
receives an error, but success metrics have already been emitted. Move success
metrics after successful compact-reference persistence. A persistence failure
must produce the safe existing server error, release operational concurrency,
return no normal compact success, and emit no success metric.

### 3. Exact compact policy and response strictness lack end-to-end proof

The 009-a verifier proves exact Codex 0.147.0 sends a V1 compact request, but its
compact branch only parses JSON; it does not prove the captured body passes
`ResponsesRequestPolicy.apply_compact`. Feed that exact in-memory captured body
through the gateway policy with the compaction gate and route-limit logic before
declaring success. Print only one additional fixed boolean result; never print
or persist the body.

The compact response validator checks the exact output item but currently
ignores unknown top-level fields. Accept only `output`, `usage`, and optional
bounded standard safe metadata `id`, `object`, and `created_at`; validate any
present safe metadata and reject every other top-level field. Preserve the
pinned mock's minimal `output`+`usage` shape and the documented
`object="response.compaction"` shape. No raw content may enter errors/evidence.

## Required work

1. Reconcile canonical GitHub, PR #234, all immutable 009 rounds, applicable
   AGENTS/OAP rules, and the exact current implementation before editing.
2. Commit the strategic `oap/active=009-c` pointer and this order unchanged.
3. Add a deliberate route-limit mode for Codex V1 compact that:
   - uses validated `codex_limits.max_output_tokens` as effective reservation;
   - keeps upstream `max_output_tokens` absent;
   - performs context-window and both operator-ceiling checks with that maximum;
   - leaves ordinary create and non-Codex compact behavior byte-for-byte
     semantically unchanged.
4. Reorder compact success handling to `accounting finalized -> HMAC reference
   persisted/committed -> success metric -> normal JSON success`. On HMAC
   failure, prove charged failure/no success metric/no normal response and safe
   500-class OpenAI-shaped error without ID, digest, or ciphertext echo.
5. Make the manual verifier's actual captured compact body pass the real gateway
   compact policy and route-limit function in memory. Add fixed output
   `GATEWAY_COMPACT_POLICY_ACCEPTED=true`. Continue to delete transient request
   objects and persist/print no raw payload.
6. Enforce the strict top-level compact response allowlist and safe metadata
   validation described above. Reject unknown, malformed ID/object/timestamp,
   extra output, missing usage, malformed usage, and plaintext/extra item fields.
7. Add focused positive/negative tests for all findings, including a full
   mocked `handle_response_compact` timeline. Update only documentation whose
   current 32,768 compact-reservation wording or success-boundary statement
   becomes inaccurate.

## Allowed paths

Implementation may change only:

```text
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/responses_request_policy.py
docs/accounting.md
docs/codex-compatibility.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
oap/active
oap/orders/009-c-fix-compact-exposure-and-success-ordering.md
scripts/verify_codex_context_compaction.py
tests/unit/test_codex_context_accounting.py
tests/unit/test_responses_codex_compaction.py
```

Final report-only commit adds only:

```text
oap/reports/009-c-fix-compact-exposure-and-success-ordering.md
```

Do not modify migration/schema/model/repository/pricing arithmetic, 009-a/009-b
history, dependencies, fixtures, CI, deployment, README, or unrelated paths.
If another exact path is genuinely required, report `BLOCKED`; do not widen
scope yourself.

## Focused verification and test economy

Run only:

- `tests/unit/test_codex_context_accounting.py` and
  `tests/unit/test_responses_codex_compaction.py`;
- directly affected OAP/documentation contract tests;
- scoped Ruff/compile, `git diff --check`, exact path/topology checks, fixture
  digest, and one final exact pinned CLI verifier run.

Do not run full unit, integration, E2E, browser, Docker/Compose, PostgreSQL, or
HPC suites locally. No schema/DB behavior changes in this round. GitHub CI owns
the broad rerun. Never call a real provider or use a side-effecting tool.

The report must distinguish any development failures from the final passing
commands and list every broad suite NOT RUN.

## Acceptance criteria

1. Gated V1 compact reserves/prices/checks route maximum output exposure while
   forwarding no unsupported max-output field; ordinary paths are unchanged.
2. Compact normal success and success metrics occur only after accounting and
   HMAC persistence. Persistence failure is charged, returns a safe server
   error, emits no success metric, and returns no normal compact payload.
3. Exact compact top-level/item/usage shapes pass; unknown/malformed/plaintext
   fields fail without content echo.
4. Exact Codex 0.147.0 loopback still produces three requests and now proves
   its captured compact body passes gateway policy/limits; output remains fixed
   safe booleans/counts only.
5. Focused tests, scoped quality/privacy checks, fixture digest, docs, and exact
   allowed-path checks pass; no broad local suite or real provider runs.
6. Every report-head GitHub check is green before strategic merge.
7. One existing PR only; coding agent performs no merge/auto-merge; immutable
   report topology satisfies `SELF`.

## PR/report requirements

Commit the unchanged 009-c order/pointer with the focused repair, push to PR
#234, wait for all implementation-head checks, and never merge or enable
auto-merge. Publish exactly one immutable report at
`oap/reports/009-c-fix-compact-exposure-and-success-ordering.md` with literal
implementation SHA, `Report publication commit: SELF`, exact exposure/timeline/
response/verifier evidence, local and GitHub checks, broad suites not run,
documentation impact, and no-merge statement. The final commit changes only
that report and has the implementation head as first parent. Verify remote
report head, then signal exact `OK`.

If the exact captured compact body cannot pass the gateway policy or maximum
exposure cannot be reserved without violating the pinned upstream shape,
report `BLOCKED` rather than weaken the contract.
