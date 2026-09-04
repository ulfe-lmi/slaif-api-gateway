# Objective 155-af — Null-encrypted replay detector and final acceptance

Date: 2026-09-03

RESULT=FAILED

This is the single immutable 155-af report. It records bounded evidence only;
it is not a product or release acceptance claim.

## Topology

- Repository: `ulfe-lmi/slaif-api-gateway`, PR #291,
  `oap/155-local-coding-signed-server-module`.
- Prior immutable report: `1a7c8c51a01d4abcb8b8529e1b9ec272baaa20d6`.
- Activation head: `d5020665b92c320b8a1634998604c3ee133ae176`.
- Diagnostic implementation head: `34ab5afd09af026286779838db21cddad1717877`.
- This report is a report-only `SELF` commit whose first parent is the
  diagnostic implementation head above.
- No merge, release, 155-ag activation, or post-live product correction was
  performed.

## Correction and evidence

The required pre-fix synthetic full-policy regression passed against the old
field-presence detector: a reasoning item with absent ID, visible content,
empty summary, and `encrypted_content: null` was denied before input validation
with `responses_codex_encrypted_reasoning_replay_not_allowed` when the
encrypted-replay grant was absent. The detector source and policy call order
were verified.

The verifier-only/product-scoped correction now treats null as visible state;
only non-null encrypted values request the encrypted-replay path. The selected
0.149 visible-reasoning policy preserves absent/null/present IDs and bounded
UTF-8 visible content without generating IDs. Existing default/0.147 and
non-null encrypted replay behavior remains strict. The accounting verifier now
accepts coherent finalized/finalized, released/failed, and finalized/estimated
admitted-turn pairs, including zero admitted turns with zero rows.

## Tests and checks

- Affected policy, replay, client, stream, payload, quota, verifier, and
  governance unit suites passed.
- Full Ruff, compilation, diff, source, and scope checks passed.
- Normal fake two-turn qualification passed with two turns, one function
  lifecycle, one message lifecycle, and two accounting rows.
- Fake provider-failure and deliberate validator-rejection matrices failed
  closed with bounded evidence and zero pending state.
- All ten PR checks passed on implementation head
  `34ab5afd09af026286779838db21cddad1717877`.
- No protected retry or second protected process was run.

## Single protected diagnostic

Exactly one protected task-local Codex 0.149.0 process ran after the green
diagnostic head and private runtime preflight.

Safe observations:

- Gateway emitted two requests/responses: first 2xx SSE, second 4xx JSON.
- Local received one request and returned one normal 2xx SSE response.
- Qwen received one inference request and returned one normal 2xx SSE response
  with normal close; compiler count was zero.
- The first request had bounded top-level tool classes custom=1, function=5,
  tool_search=1, web_search=1, and tool-choice class `automatic_none`.
- The second request was classified as
  `top_level_function_pair_without_additional_tools`; its bounded input
  projection contained the adjacent function-call/function-call-output pair.
- Gateway safe error classes were code `codex_tool_roundtrip_invalid`,
  parameter root `input`, and parameter field `id`. No raw error text, body,
  IDs, names, arguments, or values were retained.
- The one Local-bound signed projection passed service Bearer equality, exact
  required-header cardinality, canonical/raw-body participation, independent
  HMAC verification, route/method/path/query, timestamp/nonce shape, and no
  extra internal headers.
- The state-bearing reasoning projection remained bounded and ID-absent; no
  ID was manufactured. The null-encrypted detector no longer caused an
  encrypted-replay admission failure.

The fixed failure localization was
`composed_tool_roundtrip_second_turn_gateway_codex_tool_roundtrip_invalid_input_top_level_function_pair_without_additional_tools`.
Accounting showed one finalized reservation and one finalized ledger row, zero
pending state, and one terminal row for the one admitted turn. The second
Gateway rejection occurred before Local admission, so no second row was
required. The ordered two-turn acceptance nevertheless failed at the Gateway
tool-roundtrip contract, and no Local/Qwen ownership conclusion is claimed for
that second-turn rejection. The qualification rejection artifact was absent;
no hook-free final run was authorized or performed.

## Scope, cleanup, and privacy

Changes are confined to the 155-af allowed policy, verifier, test, governance,
topology, and report paths. Local Coding and Qwen were not changed. The
owner-only mode-0600 runtime reference, exact 155-af task roots, installed
Codex files, summaries, processes, listeners, containers, and task database
were absent after cleanup. The Local checkout remained Git-clean with no task
`.venv` or bytecode state.

No credential, endpoint, prompt, request/response body, raw header, canonical
bytes, timestamp, nonce, signature, reasoning text, tool value, arbitrary
exception text, or private artifact was persisted or included here. No retry,
hook-free acceptance, merge, or next objective was inferred.
