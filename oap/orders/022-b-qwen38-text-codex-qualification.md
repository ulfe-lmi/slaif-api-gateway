# OAP Work Order — 022-b

PR mode: `CONTINUE_EXISTING_PR`

## Objective and reason

Stop deferring Objective 022. Replace the 022-a placeholder with the actual
hermetic Codex 0.148 → SLAIF → numeric-loopback provider phase and an executable
bounded live verifier on existing PR #248. The absent human LAN variables
prevent only the final real-vLLM call; they do not justify a hand-authored
six-line fixture or a verifier that always prints `LIVE_TARGET_DEFERRED`.

Implement now in small code-and-test slices. Read only the concrete helpers
named below and files required by a failing focused test. Do not repeat broad
reconnaissance or environment discovery.

## Verified continuation state

- `main` is `4ad592e190f6bfa1a8878814519569b6ce7e59a2`.
- Existing ready PR #248 is `[OAP 022] Qualify Qwen3.8 text for Codex`, base
  `main`, branch `oap/022-qwen38-text-codex-qualification`.
- Remote/report head is
  `5d4f1c26255edaffe9e0ac6873287c3f709c971d`; first parent implementation is
  `526d751d3bd7e7711ebda726ece52fffda457ec8`, and the report commit changes only
  `oap/reports/022-a-qwen38-text-codex-qualification.md`.
- 022-a added an unregistered candidate, a manually authored six-line fixture,
  and a 73-line environment preflight. It did **not** run Codex, a loopback
  provider, SLAIF, a tool round-trip, PostgreSQL accounting/privacy, or a live
  backend. Its report is historical evidence of an incomplete first round.
- `SLAIF_QWEN38_TEXT_BASE_URL` and `SLAIF_QWEN38_TEXT_API_KEY` remain absent.
  Do not make a real network call or register the candidate in this round.
- `oap/active` is `022-b`. Amend PR #248 only; never merge or auto-merge.

## Allowed paths

Use the 022-a allowed paths, plus the smallest necessary subset of these exact
existing helpers/tests:

```text
scripts/verify_codex_tool_roundtrip.py
scripts/verify_codex_gateway_e2e.py
tests/unit/test_codex_gateway_e2e_verifier.py
tests/unit/test_qwen38_text_codex_candidate.py
tests/unit/test_qwen38_text_codex_verifier.py
tests/integration/test_openai_compatible_conformance_postgres.py
docs/codex-compatibility.md
docs/compatibility-matrix.md
docs/configuration.md
oap/orders/022-b-qwen38-text-codex-qualification.md
oap/reports/022-b-qwen38-text-codex-qualification.md
```

Do not edit the legacy 0.147 fixture. No migration, admin/RBAC, hosted-tool,
vision/image, or unrelated provider work.

## Required implementation

### 1. Correct the candidate contract

- Preserve the exact ID/CLI/model/provider/Responses/context 150000/client-local
  threshold 125000/text-only facts.
- Replace the copied 32768/128000 output pair with a conservative coherent exact
  pair proven by the hermetic profile; enforce at registry construction that a
  client-local threshold plus maximum output does not exceed context. Do not
  claim a 128000 Qwen output window without evidence.
- Keep search, parallel tools, image, remote compaction, encrypted reasoning,
  hosted/MCP authority, apps/plugins, and freeform apply-patch false/absent.
- After the actual hermetic phase succeeds, set only
  `mocked_qualification=true`; keep `live_qualification=false` and keep the
  candidate outside `CODEX_PROFILE_REGISTRY`/CLI/admin/route declarations.

### 2. Execute, do not simulate, the hermetic phase

Adapt/reuse the bounded mechanics in `capture_codex_protocol.py`,
`verify_codex_tool_roundtrip.py`, and `verify_codex_gateway_e2e.py`; do not copy
their entire legacy verifiers or run their broad matrices.

- Launch installed Codex only after exact `codex-cli 0.148.0` verification,
  with an isolated temporary Codex home/workspace and generated candidate
  base/profile/catalog files at private modes.
- Route Codex to an actual disposable SLAIF gateway backed by isolated
  PostgreSQL/Redis state and one numeric-loopback OpenAI-compatible mock
  provider. Use dummy distinct gateway/upstream credentials and dead external
  proxies. Do not bypass SLAIF by pointing Codex directly at the mock.
- Serve exactly one serial ordinary shell/function call, accept the tool-result
  continuation, then serve a final streaming marker with supported final usage.
  Bound requests, bytes, time, tokens, output, tool calls, and subprocess output;
  no redirects/retries or other network destinations.
- Prove the generated replacement catalog is actually loaded, exact public
  model is sent to SLAIF, exact upstream model is sent only by SLAIF, gateway
  auth is accepted, upstream dummy auth is substituted, and neither credential
  crosses the wrong boundary.
- Prove final ledger/counters, zero pending reservation, and durable application
  table scans contain none of the prompt/output/tool/credential/URL/path
  canaries. Clean up only the disposable resources created by this verifier.

This is a focused phase-gate invocation, not a full test suite. If an external
local dependency needed for the disposable gateway is unavailable, implement
and test the verifier fully, report the exact safe dependency blocker, and do
not fabricate execution.

### 3. Replace the fabricated fixture with captured structural evidence

- Delete/replace the current hand-authored fixture content with the deterministic
  output of the actual hermetic capture. The fixture must carry enough safe
  structure to prove request/event/tool ordering/cardinality, model/catalog
  facts, distinct placeholder relationships, route/key gate facts, and the
  canonical digest—not merely `response.completed`.
- Run the Objective 021 sanitizer with an explicit finite 0.148 structural
  vocabulary. Raw prompt/output, instructions, tool names/descriptions/schemas/
  arguments/results, reasoning, bodies, headers/auth, URLs, environment values,
  and workspace paths must be absent. Add canary scans and a fixture-integrity
  test; update the candidate digest only from this output.

### 4. Replace the live-verifier stub

- `verify_qwen38_text_codex.py` must contain the real bounded orchestration path
  shared with the hermetic verifier. When both live variables are present it
  validates the target/key, provisions disposable SLAIF state, runs the exact
  Codex marker gate, verifies accounting/privacy, and returns pass/fail. It must
  never emit `LIVE_TARGET_DEFERRED`.
- When both are absent it returns `LIVE_TARGET_ABSENT` without network access.
  Both-or-neither remains mandatory.
- Harden URL parsing: canonical `/v1`, valid bounded port, no control/whitespace,
  credentials/query/fragment/percent/backslash/ambiguous path, numeric private/
  loopback/link-local address only, no redirects, and no value reflection.
- Pure tests must inject fake process/network/gateway runners to prove the
  present path actually invokes bounded orchestration and that every failure
  category returns only fixed safe facts. Do not require a real LAN target in
  unit tests.

### 5. Exact runtime evidence

- Record the actual 0.148 request fields and SSE item/event types observed.
  If current gateway policy already accepts them, change no runtime code and
  prove it. If it rejects one required shape, add only the exact gated shape and
  adjacent negative tests. Unknown fields/events and all excluded capabilities
  remain rejected pre-provider.
- Update current docs to label the candidate `mocked-conformant, unregistered,
  live target absent`; do not call it protocol/live qualified.

## Non-goals

No live LAN call while variables are absent, production registration, vision,
Chat translation, search/hosted/MCP tools, parallel calls, freeform patch,
encrypted reasoning, remote compaction, schema migration, production/release
claim, or full local suite.

## Acceptance and focused verification

1. One actual Codex 0.148 → SLAIF → loopback mock serial tool/final-marker run
   passes with generated candidate artifacts and fixed bounded output.
2. Captured fixture is deterministic, structurally meaningful, digest-pinned,
   and content/secret/URL/path free.
3. Gateway route/key/runtime and PostgreSQL accounting/privacy facts are proven
   for the hermetic run; no broad runtime authority is added.
4. Present-variable unit tests prove the live verifier calls real orchestration;
   absent/partial/unsafe values make no network call and never reflect inputs.
5. Candidate is mocked-conformant but unregistered and not live-qualified.
6. Run focused candidate/capture/verifier/changed-runtime tests, the single
   hermetic phase gate, scoped Ruff/compileall, `git diff --check`, and routine
   GitHub CI. Do not run the full local suite.

## Publication

Commit implementation, then publish exactly one immutable
`oap/reports/022-b-qwen38-text-codex-qualification.md` report-only final commit
on PR #248 with literal implementation head and
`Report publication commit: SELF`. Report the actual hermetic command/result,
Codex version, fixture SHA/digest, request/tool/event safe facts, gateway/
PostgreSQL/privacy evidence, live-variable absence, runtime diff or no-change,
focused tests, and checks. Verify remote head, signal exact response-FIFO `OK`,
and return to one control wait. Never merge.
