# OAP Report — 155-aa

`RESULT=FAILED`

## Topology

- PR: #291, branch `oap/155-local-coding-signed-server-module`, base `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Starting/report head: `c8dff50ea60d4e4f515d970751508e9630455eda` (immutable 155-z report).
- Activation head: `d5730b1d981562585a0951e4b490444eb7b0f9f0`.
- Diagnostic implementation head: `d4fbb42447409d7e7bca0843a8a2b70008c957f9`.
- Report publication commit: `SELF`.
- No merge or auto-merge was performed.

The exact Local Coding 005-m checkout remained read-only and clean. Local Coding
and Qwen were not modified.

## Pre-protected evidence

The verifier added a bounded, ordinal-aligned discriminator for the unique
source-reduced raw Gateway code `responses_input_item_invalid`. It retains only
the item/field/other parameter shape, JSON and allowlisted item-type classes,
sorted unique field/type classes, bounded index/object/presence booleans, and
existing safe boundary/accounting facts. Numeric indices, item values, IDs,
prompts, headers, credentials, endpoints, and exception text are not retained.

- Focused verifier, policy, replay, upstream, and governance tests passed.
- Ruff and compilation passed.
- The three fake gates passed with expected classes: provider-failure nonzero,
  forced-rejection nonzero with safe evidence, and normal fake qualification
  success with two turns and two accounting rows.
- All ten required PR checks passed on `d4fbb42447409d7e7bca0843a8a2b70008c957f9`.
- The complete local unit suite had one unrelated environment-sensitive failure
  in the pre-existing Qwen/Codex candidate test because the host Codex binary
  was not the pinned version; no 155-aa source caused that failure.

## Single protected diagnostic

Exactly one protected diagnostic was executed. It was not retried, and no final
protected request was sent.

| Boundary fact | Safe observation |
| --- | --- |
| Gateway requests/responses | 2; statuses `2xx`, `4xx`; content classes `sse`, `json` |
| Local requests/responses | 1; status `2xx`; content class `sse` |
| Qwen inference | 1; status `2xx`; normal SSE close |
| Ordered request profiles | `other`, `top_level_function_pair_without_additional_tools` |
| Second input item types | three `message`, one `reasoning`, one `function_call`, one `function_call_output` |
| Second top-level tool classes | custom 1, function 5, tool-search 1, web-search 1 |
| Raw Gateway error | source-reduced `responses_input_item_invalid`; safe code class `other`; parameter shape `item` |
| Rejected item class | selected item was an object of allowlisted type `reasoning` |
| Rejected item fields | `content:array`, `encrypted_content:null`, `summary:array`, `type:string` |
| Accounting | one finalized reservation/ledger row; zero pending; two-turn acceptance not proven |

The item branch did not prove a supported legitimate shape. The pinned OpenAI
2.41.0 Responses input type requires a reasoning item `id` together with
`summary` and `type`; the observed bounded item-field projection did not contain
`id`. A pure 0.149 policy reproduction therefore rejected the shape before
provider side effects. No product correction was made, because accepting this
shape would not be evidence-backed.

## Cleanup and closure

- The protected diagnostic task root and all aa task roots were removed by
  bounded cleanup traps.
- No aa process, listener, or task artifact remained.
- The validated mode-0600 private runtime reference was unlinked and verified
  absent.
- No raw request/response values, credentials, endpoints, identifiers, prompt
  text, tool arguments/results, digests, or exception text were published.
- No hook-free final acceptance was run; no retry, acceptance, product change,
  release, or merge occurred.

This is a truthful failed closure: the remaining input-item branch was observed,
but its exact rejected shape was not a pinned legitimate contract, so the order
ended without correction or final acceptance.
