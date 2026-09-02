# OAP Report — 155-ac

`RESULT=FAILED`

## Topology

- PR: #291, branch `oap/155-local-coding-signed-server-module`, base `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Starting head: `a0701a3db477e8c34d7c4db981a5216aa7d7ac0b` (immutable 155-ab report).
- Activation head: `17993c2cba0bc225b89abffa8a78b6900f57862c`.
- Diagnostic implementation head: `b32c50b92cccba229b37a9abb642611f3f8dc588`.
- Report publication commit: `SELF`.
- No merge or auto-merge was performed.

The activation commit contained only `oap/active` and the exact 155-ac order.
The exact Local Coding 005-m checkout remained read-only and clean. Local Coding,
Qwen, Gateway product code, and Codex were not modified.

## Provenance and pre-protected gates

The qualification chain installed and verified the exact task-local npm package
`@openai/codex@0.149.0`. Safe retained provenance facts were:

- source class `task_local_exact_npm`;
- requested, package, raw version, and invoked version class `0.149.0`;
- task-local-under-root, verified-binary-invoked, and catalog/command-binary-same
  predicates true;
- host-default version class `0.149.1`, with host-default match false.

The host installation was diagnostic only and was never used as the qualification
executable. No absolute temporary path, package-manager log, command output, or
environment contents were retained.

- Focused verifier, governance, and Codex capture tests passed.
- Full Ruff and compilation passed.
- Two isolated normal fake two-turn runs passed with two turns, one function
  lifecycle, one message lifecycle, and two accounting rows.
- All ten required PR checks passed on `b32c50b92cccba229b37a9abb642611f3f8dc588`.

## Single protected diagnostic

Exactly one zero-retry protected Codex process was executed. Its first-turn gate
failed, so the same process did not issue a second request. No retry and no final
protected acceptance were performed.

| Boundary fact | Safe observation |
| --- | --- |
| Codex provenance | exact task-local `0.149.0`; host default `0.149.1` mismatch |
| Gateway requests/responses | 1; status `2xx`; content class `sse` |
| Local requests/responses | 1; status `4xx`; content class `json` |
| Qwen inference | 0; no inference status |
| First request profile | `other` |
| First input item classes | three `message` items |
| First top-level tool classes | custom 1, function 5, tool-search 1, web-search 1 |
| Local error class | `other`; no narrower safe allowlisted code was retained |
| Accounting | one released reservation and one failed ledger class; zero pending |
| Empty-reasoning predicate | not reached and therefore unproved |

The bounded failure code was `qualification_turn_counts_g1_l1_q0`. The available
facts do not distinguish a Local product rejection from a harness/runtime cause,
and no ownership conclusion is claimed. No reasoning placeholder was observed;
therefore no canonicalization, ID handling, or strict-validation decision was
made.

## Cleanup and closure

- The ac diagnostic task root and all ac temporary roots were removed by bounded
  cleanup traps.
- No ac verifier process, listener, or task artifact remained.
- The private runtime reference was validated as an owner-only mode-0600 regular
  file, unlinked, and verified absent.
- No raw request/response values, identifiers, prompts, reasoning content,
  credentials, endpoints, tool arguments/results, digests, or exception text were
  published.
- No product correction, second request, retry, hook-free final, acceptance,
  release, or merge occurred.

This is a truthful failed diagnostic closure. The exact executable provenance was
proved, but the protected first turn did not reach Qwen, so the 155-ab
empty-reasoning question remains unresolved without a new authorized continuation.
