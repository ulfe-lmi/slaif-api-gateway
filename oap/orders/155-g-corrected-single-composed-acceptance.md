# OAP Work Order — 155-g

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `63b8a459d8a1b50e22e47feaa0dff8efc8b6957b`

## Objective and reason

Run one fresh corrected real

```text
Codex 0.149.0 -> Gateway PR #291 -> Local Coding PR #7
  -> protected qwen3.8-27b
```

composition using the final 155-f verifier, then publish truthful immutable
acceptance or the first fixed runtime gate. This is the minimum continuation of
the failed 155-f attempt, not a new design round.

155-f reached Local startup but incorrectly let `uv` create an ignored `.venv`
inside the exact read-only Local dependency checkout. It produced no composed
request or product evidence. Final 155-f implementation head
`feb55ced305839f0793597eebca2304d917517dc` corrects that defect by setting
`UV_PROJECT_ENVIRONMENT` directly to task-owned state, refusing a repository-
local environment before and after composition, and converting unexpected
exceptions to fixed stage codes. Those corrections pass focused and final-head
CI but were intentionally not exercised by a second 155-f composition.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable blocked
  report head `63b8a459d8a1b50e22e47feaa0dff8efc8b6957b`; first parent is
  `feb55ced305839f0793597eebca2304d917517dc`, and the report commit changes only
  `oap/reports/155-f-real-codex-local-coding-qwen-acceptance.md`.
- All ten report-head checks are successful.
- Local Coding PR #7 remains OPEN, non-draft, MERGEABLE/CLEAN at exact report
  head `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` is an ancestor and `test` is
  successful.
- `/home/ubuntu/codex-work/slaif-local-coding` is at that exact head, Git-clean,
  and has no `.venv` or task residue.
- No 155-f/155-g process, listener, container, temp root, runtime reference, or
  database remains.
- The protected model is healthy and unchanged. The only allowed private
  endpoint/credential reference for this round is the strategic mode-0600 file
  `/tmp/slaif-155f-runtime.env`; never print, commit, hash, log, or retain its
  values.

Abort before setup if any exact head, topology, ancestry, required check,
selector/order byte, dependency cleanliness, runtime-reference permission, or
protected model identity differs.

## Mandatory pre-composition gate

Before Docker, PostgreSQL, test listeners, or inference:

1. commit and push the unchanged 155-g order and selector on the existing PR,
   verify local HEAD equals remote PR head, then require all ten checks green;
2. verify 155-f report topology and Local PR pin/ancestry/clean checkout;
3. run the focused verifier tests, Ruff, syntax compilation, `git diff --check`,
   and exact affected Codex/client/identity/tool-policy tests;
4. prove the final verifier contains no placeholder/fake acceptance facts, no
   `response.content` buffering, and no private endpoint/credential TOML sink;
5. use the real pinned Local `load_settings` against a task-temporary generated
   config and prove it selects signed identity, loopback Qwen relay, synthetic
   relay credential, exact route/tool policy, and task-owned Local environment;
6. install literal official Codex 0.149.0 only under task state and run the
   exact no-provider A/explicit-resume-A/B relationship capture; do not use host
   Codex 0.149.1;
7. verify protected health/model identity through the scrubbed reference and
   retain only the fixed success fact;
8. prove Local checkout `.venv` remains absent and no task infrastructure exists.

A deterministic pre-infrastructure verifier defect may be corrected once in
the same PR using only the allowed verifier/test paths, followed by fresh green
checks. It does not consume the composed attempt. Do not broaden behavior or
refactor architecture.

## Single real composition

After the complete pre-composition gate passes, invoke the final verifier once.
The verifier must construct and clean exactly the bounded topology and traffic
defined by 155-f, including:

- exact real Codex A1, explicit-resume A2, and independent B processes;
- ordinary non-streaming, incremental SSE through completion, one synthetic
  image, signed identity, same-session reuse, cross-session isolation, and
  second-Gateway-key isolation;
- exact Gateway-to-Local replay/body/path/query/signature negatives;
- Local cache/rehydration reuse and isolation metrics;
- scrubbed streaming Local-to-Qwen relay with real provider/compiler call
  counts, synthetic-to-protected credential replacement, no disabled search
  tools, and no Gateway/Local internal headers or credentials at Qwen;
- invalid key, over-quota, malformed aliases, explicit hosted/dropped search
  choice, controlled separate provider failure, terminal PostgreSQL accounting,
  rollback, zero pending counters, empty external facts, and privacy scans;
- post-cleanup protected health/model proof and complete task-resource absence.

Once Docker, a listener, Local startup, or protected inference begins, do not
retry the composition in this round. On failure, preserve the fixed safe stage/
error code, clean all task state, and report exactly what ran and did not run.
Never turn a verifier/harness failure into a Gateway or Local product claim.

## Acceptance

PASS requires fixed verifier output
`RESULT=OK status=real_composed_acceptance`, every required internal evidence
boolean/count assertion, exact clean heads, and full cleanup. Independently
verify safe counts/statuses from DB/metrics/relay state; the fixed terminal line
alone is not sufficient.

A PASS makes exact Gateway implementation head and Local report head a tested
merge pair. It does not claim persistent deployment, production, release,
certification, hostile same-key isolation, multi-worker/restart-persistent
replay, or MVP completion by itself.

## Exact allowed paths

```text
scripts/verify_local_coding_full_stack.py
tests/unit/test_local_coding_full_stack_verifier.py
docs/module-architecture.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/accounting.md
docs/compatibility-matrix.md
oap/orders/155-g-corrected-single-composed-acceptance.md
oap/reports/155-g-corrected-single-composed-acceptance.md
oap/active
```

Use only order/active/report unless a pre-infrastructure defect or truthful
documentation correction requires the narrow verifier/test/docs subset. No
Gateway or Local product module, schema, migration, dependency, lockfile,
route/pair/header, Compose, deployment, protected service, external repository,
release, or production change is authorized.

## Cleanup and publication

- Remove only exact task-owned Codex install/home/workspace/output, Gateway and
  Local environments/config/cache/logs, relays/processes/listeners, PostgreSQL
  container/tmpfs/database/volume, generated credentials, newly pulled image,
  and `/tmp/slaif-155f-runtime.env`. Never operate protected Qwen or unrelated
  worktrees/services.
- Verify Local `.venv` absent, both repositories clean, no task listener/process/
  container/temp root, no `uv.lock`, and protected health/model unchanged.
- Amend only PR #291. Coding agent never merges or enables auto-merge.
- Push all non-report work, wait for all required checks, and record the literal
  implementation head.
- Atomically publish exactly one immutable
  `oap/reports/155-g-corrected-single-composed-acceptance.md` with literal
  implementation SHA and `Report publication commit: SELF`; its first parent is
  the implementation head and it changes only that report.
- After report publication make no repository mutation. Verify remote report
  head/topology/checks, send exact response FIFO `OK`, and end the round.

## Merge gate

Neither PR merges during coding execution. After a passing 155-g report,
strategic review merges Local Coding PR #7 first, verifies the tested head and
signed-contract ancestor in the merge, then rechecks the unchanged Gateway
report head/checks/reviews and merges PR #291. A failed/blocked report keeps both
PRs open and requires a concrete same-objective decision; do not activate
Objective 156 or Local Objective 006.
