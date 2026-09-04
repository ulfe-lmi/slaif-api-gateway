# OAP Report — 155-y

`RESULT=FAILED`

## Topology

- PR: #291, branch `oap/155-local-coding-signed-server-module`, base `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Starting head: `db7d67a83fa72b6e642147195d759556d33527b0`.
- Activation commit: `b860216cc6218920ffc5cf086359f582de8176d0` (parent is the starting head).
- Pre-cleanup implementation head: `a0ad53be830466d3acd34717d1f2e124619781dd`.
- Cleanup implementation head: `70a5224ff9e7dd07bf2d957baf4cb6717a39e896`.
- Report publication commit: `SELF`.
- No merge or auto-merge was performed.

The cleanup implementation reverted the unproven standalone function-output
admission, call-digest lookup, session-scope replay changes, and their product
regressions to activation behavior. It retains only the 155-y topology and the
privacy-safe ordered `request_profile_classes` verifier diagnostic. The
production files reverted in this cleanup compare byte-for-byte with activation
for the affected replay, policy, gateway, and product-test paths. No
`standalone_function_output` symbol remains in the worktree.

## Evidence

Pure and fake evidence observed before the cleanup correction:

- The ordinary fake composed tool round trip passed with two turns, one
  function lifecycle, one message lifecycle, and two accounting rows.
- The fake provider-failure path and forced-validation-rejection path both
  returned bounded nonzero results with zero pending accounting.
- The ordered request projection classified the two observed ordinals as
  `other` followed by
  `top_level_function_pair_without_additional_tools`.

Exactly one completed protected qualification request was consumed before the
cleanup correction. It was not retried and no final protected request was sent.
Its retained safe result was:

| Fact | Bounded observation |
| --- | --- |
| Gateway requests/responses | 2; statuses `2xx`, `4xx`; content classes `sse`, `json` |
| Local requests/responses | 1; status `2xx`; content class `sse` |
| Qwen inference | 1; status `2xx`; normal SSE close |
| Request profiles | `other`, `top_level_function_pair_without_additional_tools` |
| Codex failure category | `turn_failed` |
| Accounting | one finalized reservation/ledger row; zero pending |
| Rejection artifact | absent |

The result was not a two-turn acceptance: the second Gateway request did not
reach Local or Qwen. Because the bounded retained result did not include the
Gateway error-code/parameter class, the exact rejected contract is unknown.
No ownership or accounting conclusion beyond the facts above is claimed. The
speculative standalone correction was therefore reverted rather than accepted.

An earlier interrupted launcher reached infrastructure startup; its exact
verifier/uvicorn children were stopped and no Codex process was observed before
that stop. No evidence or request count is claimed for that launcher.

## Verification and cleanup

- Focused affected unit files passed: local full-stack verifier, replay service,
  Responses replay, and Responses streaming-tools tests.
- `python -m ruff check app tests` passed in an isolated task environment.
- All ten required checks passed on cleanup head
  `70a5224ff9e7dd07bf2d957baf4cb6717a39e896`.
- The cleanup head was pushed to PR #291 and matched the remote head.
- The repository and detached Local checkout were clean; no Local `.venv`
  remained.
- No 155-y temporary root, listener, or task process remained after cleanup.
- No endpoint, credential, raw body, header value, identifier, prompt, tool
  argument/result, or exception text was retained in this report.

This report records a failed continuation admission qualification. There was no
acceptance, no retry, no final protected run, and no merge.
