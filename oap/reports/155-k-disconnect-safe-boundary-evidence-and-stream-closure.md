# OAP 155-k report — disconnect-safe boundary evidence

Status: `PARTIAL/BLOCKED`

Reason: the first authorized protected differential invocation reached the
verifier's safe-summary projection but failed with the fixed code
`differential_summary_invalid`. The invocation did not publish a usable
per-boundary result. The order's no-retry instruction therefore stops this
round; no further protected request was run.

## Identity and topology

- PR: #291
- Repository: `ulfe-lmi/slaif-api-gateway`
- Branch: `oap/155-local-coding-signed-server-module`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Starting head: `37c84c9cf32fb63303fe1f1897ca97bb170abb2c`
- Activation commit: `5305d3832a911472d9dbf216cb3fea9e0d6e5942`
- Implementation head: `598915417f510aa592374ec6624905d37546aa18`
- Report publication commit: `SELF`
- No product/runtime application paths were changed.

The activation commit contains only `oap/active` and the exact strategic
155-k order. The implementation commits contain only the two unconditional
allowed verifier paths. The 155-j report is the exact prior report parent and
report-only topology anchor.

## Changed allowed paths

- `scripts/verify_local_coding_full_stack.py`
- `tests/unit/test_local_coding_full_stack_verifier.py`
- `oap/active`
- `oap/orders/155-k-disconnect-safe-boundary-evidence-and-stream-closure.md`
- this report

Documentation impact: no product or contract documentation changed; the
changes are verifier/test-only evidence tooling.

## Implementation and fake evidence

The verifier now:

- emits a fixed, bounded, ordered safe summary for only the boundaries that
  actually ran;
- stops before composition when direct evidence is unambiguously Qwen-owned;
- rejects inconsistent `response.completed` and event-sequence facts;
- records handler exceptions as a fixed safe handler-error fact while
  suppressing stdlib tracebacks;
- drains an already-open upstream stream after downstream disconnect, records
  upstream normal-close independently, and preserves incremental forwarding;
- retains no raw stream IDs, bodies, headers, values, prompts, endpoints, or
  credentials in the emitted summary.

Observed local verification:

- focused verifier unit suite: pass;
- Ruff: pass;
- Python compilation: pass;
- `git diff --check`: pass;
- complete fake rehearsal: pass (`FAKE_REHEARSAL=OK`);
- Local Coding checkout clean and repo-local `.venv` absent after rehearsal;
- all ten implementation-head PR checks on `5989154`: pass.

The fake suite covers exact CLI bytes/order for all three boundaries, direct
only ran/not-run output, the decision table, malformed safe summaries,
incremental forwarding, downstream reset with upstream drain, upstream
truncation, duplicate/unknown/DONE/order/status evidence, and fixed handler
error recording.

## Protected diagnostic ledger

- Authorized protected diagnostic invocations: one.
- Protected request count: unknown within the order's maximum of two. The
  retained safe state does not establish whether the failed invocation ran
  direct only or proceeded to the composed boundary; no new inference is made.
- Direct, Local, Gateway, and composed per-boundary observations: not
  reportable from retained state because the CLI discarded them when the safe
  projector returned `differential_summary_invalid`.
- Safe terminal fact: the verifier returned fixed code
  `differential_summary_invalid` and emitted no usable ownership result.
- Remaining authorized protected diagnostic: not run, by explicit no-retry
  direction.
- Full protected acceptance matrix: not run.
- Ownership decision: none; no Qwen, Local Coding, Gateway, or official-client
  ownership claim is made.
- Acceptance, release, deployment, and merge: none claimed.

The failed invocation was run before the projector correction at the prior
implementation head. The correction is committed and green at `5989154`, but
this report does not retroactively treat it as protected evidence.

## Cleanup and privacy ledger

- Fake and protected task roots were temporary, task-owned, and removed by
  bounded cleanup traps.
- No task process, relay, listener, container, Local `.venv`, or generated
  diagnostic artifact remains.
- The mode-0600 activation runtime reference is removed during final report
  cleanup and verified absent.
- No credential value was printed, persisted, logged, hashed, or committed.
- No protected endpoint, credential source, request body, response value,
  identity, signature, nonce, or session value is included in this report.
- No merge or auto-merge was performed.

## Required continuation

Before any newly authorized protected diagnostic, a continuation must preserve
the fixed per-boundary schema, prove the missing-structure projection and exact
ran/not-run output under fake tests, and retain/report only the allowlisted
boundary summary. It must not infer ownership from this failed aggregate
invocation.
