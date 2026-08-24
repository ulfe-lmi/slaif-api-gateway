# OAP Work Order — 154-b

PR mode: `AMEND_EXISTING_PR`
PR: `#290`
Branch: `oap/154-versioned-codex-client-modules`
Base: `main @ 4b04d6519c11c684b2eac70dc1757c515d2ea4ab`
Current remote head: `99e97848bd8a197a499451d6e7d7d68a57a88963`

## Objective and reason

Close three anti-false-positive failures found in independent review of 154-a:

1. `codex-0.147-responses-v1` currently deep-copies the body and emits profile
   facts, while generic `ResponsesRequestPolicy` still owns the actual
   `_validate_codex_*` request/tool/replay/compaction branches and imports a
   large private constant surface from `modules/clients/codex_support.py`.
   That is a wrapper plus relocated literals, not client-module ownership.
2. `codex_support.py` now owns generic Responses message/image/file/tool/
   conversation/text-format constants unrelated to Codex. This creates a
   reverse dependency from generic Responses core into a Codex-named module.
3. The exact retained 0.149 capture records `web_search` but no `tool_search`
   declaration. The fixture findings and module nevertheless accept
   `tool_search` based on the separate Local Coding type-only handoff. An exact
   versioned module may not accept an unobserved field shape.

The existing isolated 0.147 Gateway verifier also returned
`cli_preflight_failed`; this is not passing E2E preservation evidence. Repair
module ownership/capture truth and obtain exact 0.147 no-real-provider E2E or
report a genuine environment blocker without promoting weaker evidence.

## Verified starting state

- PR #290 is open, non-draft, mergeable, and has no auto-merge.
- Report head `99e97848bd8a197a499451d6e7d7d68a57a88963` has implementation head
  `cfd80c826f78aa10740a87e0350f9a09afbbcafe` as first parent and changes only
  the 154-a report. All ten final-head checks passed.
- The immutable 0.147 fixture digest remains correct.
- Exact 0.149.0 capture provenance and cleanup are useful and should be
  preserved, but the fixture/module claim must match observed evidence exactly.
- No Local Coding server module or 0.149 compatible server pair exists.

## Required implementation

### 1. Separate generic Responses from Codex ownership

- Move generic Responses constants (ordinary message/content/image/file,
  generic function/custom tools, conversation metadata, generic hosted-tool
  taxonomy, generic text formats, and other non-version-specific primitives)
  back to generic core or a neutrally named pure Responses support module.
- `modules/clients/codex_*` may depend on neutral generic primitives. Generic
  Responses core must not depend on a Codex-named module for ordinary OpenAI
  behavior.
- Add an architecture test that identifies representative generic constants and
  fails if they are owned/exported from a Codex module.

### 2. Make 0.147 a real policy module

- Introduce a public, immutable module-owned policy specification/hook object
  for the exact 0.147 request envelope, metadata vocabulary, taxonomies,
  limits, item/declaration shapes, stream profile, replay/compaction shape, and
  fixture facts.
- Parameterize reusable core policy mechanics by that specification or move
  the version-specific validators into module-owned pure support. Core may
  retain neutral validation algorithms and all authorization, route, HMAC
  ownership, persistence, quota, and accounting decisions.
- `ResponsesRequestPolicy` must not import dozens of private underscored Codex
  constants/functions. It may import one public neutral protocol/spec type and
  receive the selected module's spec from Gateway orchestration.
- Exact version/tool/taxonomy values must be reached through the selected
  module/spec, not module-global imports in generic core.
- Add an architecture test proving generic Responses request policy contains no
  0.147/0.148 module IDs, profile IDs, exact client taxonomy tuples, or direct
  private imports from Codex modules.
- Preserve all current 0.147 key/route gates, request/stream/replay/compaction,
  profile rendering, HMAC ownership, PostgreSQL accounting, errors, and privacy.

This does not require moving HMAC repositories, route authorization, quota, or
accounting into a client module; those must remain core.

### 3. Make 0.149 fixture and module exact

- Derive accepted adapter-managed candidate types only from exact retained
  capture variants with their allowed-field shapes.
- Since the current exact fixture observes `web_search` but not `tool_search`,
  remove `tool_search` from the fixture's candidate findings and from accepted
  0.149 module shapes unless a new exact 0.149.0 disposable capture variant
  independently observes its complete structural declaration shape.
- The separate Local Coding type-only vector may remain cited as a motivation,
  not as sufficient Gateway acceptance evidence.
- Add a fixture-consistency test computing candidate types/shapes from the
  capture section and requiring exact equality with module constants/findings.
- Keep 0.149 pairless/default denied and out of hosted-tool fence/accounting.

### 4. Exact 0.147 E2E preservation evidence

- Diagnose the isolated verifier's `cli_preflight_failed` using bounded safe
  output only. Do not inspect host Codex user state.
- Obtain exact official Codex 0.147.0 in a private disposable location as was
  done for 0.149.0, verify raw version, and permit the isolated verifier to use
  an explicit validated binary path if its current hard-coded host path is the
  blocker. Any new option must reject symlinks, wrong versions, unsafe paths,
  and secret-bearing argv/output; default behavior remains compatible.
- Rerun the existing no-real-provider local Gateway Codex E2E with disposable
  PostgreSQL/Redis/loopback state. Require its defining profile/tool/accounting
  scenarios to pass and exact cleanup. If an external environment limitation
  remains after the safe binary-path repair, report it precisely; do not call
  the objective preserved by assertion alone.
- Delete all temporary 0.147 artifacts/runtime afterward; commit no binary,
  npm cache, raw request, profile home, workspace, logs, or content.

## Exact allowed paths

```text
app/slaif_gateway/modules/clients/**
app/slaif_gateway/modules/contracts.py
app/slaif_gateway/services/responses_request_policy.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/codex_profile_registry.py
app/slaif_gateway/services/codex_qualification.py
app/slaif_gateway/providers/streaming.py
scripts/verify_codex_gateway_e2e.py
tests/fixtures/codex/0.149.0/responses-structural.json
tests/unit/test_codex_client_modules.py
tests/unit/test_module_architecture.py
tests/unit/test_responses_request_policy.py
tests/unit/test_responses_codex_envelope.py
tests/unit/test_responses_codex_client_tools.py
tests/unit/test_responses_codex_streaming_tools.py
tests/unit/test_responses_codex_multiturn_replay.py
tests/unit/test_responses_codex_compaction.py
tests/unit/test_codex_gateway_e2e_verifier.py
tests/integration/test_codex_client_modules_postgres.py
docs/module-architecture.md
docs/codex-compatibility.md
docs/responses-compatibility.md
docs/provider-forwarding-contract.md
docs/security-model.md
docs/compatibility-matrix.md
oap/orders/154-b-codex-module-ownership-and-capture-truth-closure.md
oap/reports/154-b-codex-module-ownership-and-capture-truth-closure.md
oap/active
```

Use the narrowest subset. Existing 154-a profile/admin/template propagation is
not reopened unless module-spec plumbing requires a precise adjustment.

## Required verification

- Fixture self-consistency/digest/privacy checks for 0.149.
- Focused architecture and complete 0.147/0.149 module/policy/tool/stream/
  replay/compaction suites.
- Focused PostgreSQL no-side-effect 0.149 denial plus current 0.147 accounting/
  replay tests; skipped DB evidence is not a pass.
- Exact 0.147 isolated Gateway Codex E2E with explicit result and no real
  provider, or an honest still-failed result after safe setup exhaustion.
- Ruff changed Python, `git diff --check`, docs checker/tests, one Alembic head,
  and final GitHub CI/CodeQL.
- No broad local suite, Local Coding, Qwen, OpenCode, production Compose, email,
  real provider, or live credential.

## Anti-false-positive acceptance

- Renaming `codex_support.py` while leaving generic core dependent on its
  private Codex constants fails.
- A module spec containing constants but unused by the actual policy path fails.
- Moving core authorization/accounting into the module fails.
- Retaining unobserved `tool_search` acceptance without an exact capture fails.
- Reusing 0.149.1 or handoff-only shapes as 0.149.0 evidence fails.
- Calling the failed 0.147 preflight an E2E pass fails.
- Any 0.149 server pair or hosted-tool execution/fence path fails.

## Boundaries and publication

- No Local Coding, signed identity, service Bearer, exact-body signing, replay
  infrastructure, Qwen, OpenCode, dynamic plugin, migration, provider/accounting
  rewrite, production, deployment, release, certification, compliance, invoice,
  support, or SLA work.
- Amend only PR #290; coding agent never merges or enables auto-merge.
- Publish exactly one immutable
  `oap/reports/154-b-codex-module-ownership-and-capture-truth-closure.md` in a
  report-only commit with literal implementation head as first parent. Record
  ownership movement, fixture truth, exact 0.147 E2E result, focused/DB/CI
  evidence, cleanup and limitations; then send exact `OK`.
