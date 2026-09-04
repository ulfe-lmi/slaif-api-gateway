# OAP Report — 155-z

`RESULT=FAILED`

## Topology

- PR: #291, branch `oap/155-local-coding-signed-server-module`, base `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Starting/report head: `b499323eacbd450f566df0a6ad768a9437dff025` (immutable 155-y report).
- Activation commit: `dfa7454f067a545e6fd6d0a2157250168e05497f`.
- Diagnostic implementation head: `65d20cf5d9ed58db95847f8f60f6a122dc3ec77f`.
- Report publication commit: `SELF`.
- No merge or auto-merge was performed.

The activation commit is the exact order-only 155-z activation with the prior
155-y report as parent. The exact Local Coding 005-m checkout and its signed
contract ancestry were preserved. Local Coding and Qwen were not modified.

## Pre-protected evidence

The diagnostic verifier was corrected to retain status-aligned, privacy-safe
Gateway error evidence, including ordered request profiles, second-input item
types, top-level tool-type counts, and bounded function item field/type sets.
The error-class matrix covers `codex_tool_roundtrip_invalid`,
`replay_reference_not_found`, `replay_route_mismatch`,
`route_capability_not_supported`, and `other`, with root/leaf and duplicate/
ordinal-alignment negatives.

On the exact diagnostic head:

- Normal fake qualification passed with two turns, one function lifecycle, one
  message lifecycle, and two accounting rows.
- Fake provider failure returned bounded nonzero evidence with one Qwen-side
  rejection and released/failed accounting with zero pending state.
- Forced fake rejection returned bounded nonzero evidence with the retained
  safe rejection artifact and zero pending state.
- Full Ruff, compilation, and focused verifier/replay/policy tests passed.
- All ten required PR checks passed on `65d20cf5d9ed58db95847f8f60f6a122dc3ec77f`.

## Single protected diagnostic

Exactly one pre-correction protected diagnostic was executed. It was not
retried and no decisive final request was sent.

| Boundary fact | Safe observation |
| --- | --- |
| Gateway requests/responses | 2; statuses `2xx`, `4xx`; content classes `sse`, `json` |
| Local requests/responses | 1; status `2xx`; content class `sse` |
| Qwen inference | 1; status `2xx`; normal SSE close |
| Ordered request profiles | `other`, `top_level_function_pair_without_additional_tools` |
| Second input item types | `message`, `message`, `message`, `reasoning`, `function_call`, `function_call_output` |
| Second top-level tool counts | custom 1, function 5, tool_search 1, web_search 1 |
| Function field classes | bounded field/type classes only; no values retained |
| Gateway error code class | `other` |
| Gateway error parameter | root `input`, leaf `other` |
| Accounting snapshot | query succeeded; one finalized reservation/ledger row; zero pending |

The verifier returned the bounded failure code
`qualification_accounting_incomplete` after the one-turn accounting state did
not satisfy the two-turn qualification gate. Because the exact Gateway error
code class remained `other`, no Gateway branch was proven and no product
correction was made. No ownership, replay, route-capability, or broader
accounting conclusion is claimed.

## Cleanup and privacy

- The protected diagnostic task root was removed by its bounded cleanup trap.
- No 155-z temporary root, listener, process, or task artifact remained.
- The detached Local checkout was clean and had no task-created `.venv`.
- The Gateway checkout was clean before report creation.
- No endpoint, credential, raw body, header value, identifier, prompt, tool
  argument/result, digest, or exception text was retained or published.

This is a truthful failed diagnostic closure. No protected retry, no hook-free
final, no acceptance, no product correction, and no merge occurred.
