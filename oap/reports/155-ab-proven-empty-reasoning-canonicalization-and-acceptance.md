# OAP Report — 155-ab

`RESULT=FAILED`

## Topology

- PR: #291, branch `oap/155-local-coding-signed-server-module`, base `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Starting head: `9b99c0c52e2786598efba23767aa2635ffde080a` (immutable 155-aa report).
- Activation head: `21a96484847cdef769df1dced7c39c037cad811e`.
- Diagnostic implementation head: `1664a53a6dc6ce36a0cb05420901d352c08dabeb`.
- Report publication commit: `SELF`.
- No merge or auto-merge was performed.

The activation commit contained only `oap/active` and the exact 155-ab order.
The exact Local Coding 005-m checkout remained read-only and clean. Local Coding
and Qwen were not modified.

## Pre-protected evidence

The verifier added a bounded, transient reasoning-placeholder discriminator. It
retains only closed state classes for ID, content, summary, and encrypted
content, exact-key/unexpected-field booleans, one-candidate/adjacent-function-pair
booleans, and existing safe boundary/accounting facts. It does not retain IDs,
indices, values, prompts, reasoning text, tool names, arguments/results, headers,
credentials, endpoints, or exception text.

- Focused verifier, governance, policy, replay, streaming, and upstream tests
  passed.
- Full Ruff and compilation passed.
- Fake provider-failure and forced-rejection modes returned their expected
  bounded nonzero results; normal fake qualification passed with two turns and
  two accounting rows.
- All ten required PR checks passed on `1664a53a6dc6ce36a0cb05420901d352c08dabeb`.

## Single protected diagnostic

Exactly one protected diagnostic was executed. It was not retried, and no final
protected request was sent.

| Boundary fact | Safe observation |
| --- | --- |
| Gateway requests/responses | 1; status `2xx`; content class `sse` |
| Local requests/responses | 1; status `4xx`; content class `json` |
| Qwen inference | 0; no inference status was recorded |
| Accounting | one released reservation and one failed ledger class; zero pending |
| Predicate evidence | not produced; no selected reasoning-placeholder observation |
| Failure code | `qualification_turn_counts_g1_l1_q0` |

The diagnostic stopped before the second request and before any reasoning
placeholder could be observed. Consequently, the required semantic-emptiness
predicate was not proven, no canonicalization was implemented, and no ownership
or Local/Qwen failure conclusion is claimed.

## Cleanup and closure

- The ab diagnostic task root and all ab temporary roots were removed by bounded
  cleanup traps.
- No ab verifier process, listener, or task artifact remained.
- The private runtime reference was validated as a mode-0600 regular file owned
  by the current user, unlinked, and verified absent.
- No raw request/response values, identifiers, prompts, reasoning content,
  credentials, endpoints, tool arguments/results, digests, or exception text were
  published.
- No product correction, hook-free final acceptance, retry, release, or merge
  occurred.

This is a truthful failed closure: the required protected diagnostic did not
reach the predicate-bearing second request, so 155-ab ends without correction or
acceptance.
