# OAP Work Order — 155-n

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: 382549cb0e31b22a3464c6622b0f21e48d115944

## Objective and reason

Localize and correct the composed-only verifier's generic composition failure
entirely against an exact fake topology, prove safe artifact emission, and only
then run one new no-retry composed protected request. If Local and Gateway
terminal boundaries validate, complete the real Codex full-stack acceptance.

155-m established a valid pinned direct-Qwen terminal baseline, but its one
composed-only process ended with `unexpected_composed_only` after pre-composition
checks and before safe artifact emission. No product owner or protected request
count can be inferred from that generic failure.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-m report
  head `382549cb0e31b22a3464c6622b0f21e48d115944`; first parent is
  `b2c504ed084664487e1088424bd4503977c90644`, and only the exact 155-m report
  changed.
- All ten report-head checks pass.
- Local Coding PR #7 remains exact, OPEN, non-draft, MERGEABLE/CLEAN at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Gateway and Local worktrees are clean. No 155-m runtime reference, credential
  source, task root, process, listener, safe artifact, or container remains.
- The immutable 155-l direct baseline remains terminal-valid and vocabulary-
  incomplete. It must be reused; no new direct request is authorized.

## 1. Fixed composition stage tracker

Add a finite stage tracker for the composed-only path. At minimum distinguish:

    topology
    runtime_reference
    fixtures
    pinned_direct_baseline
    local_config
    postgres_start
    migrations
    database_seed
    relay_start
    qwen_relay_start
    local_start
    gateway_start
    readiness
    client_stream
    boundary_capture
    accounting
    process_cleanup
    container_cleanup
    repository_cleanup
    safe_artifact

Every unexpected exception maps to exactly
`unexpected_composed_<stage>`. Never print exception text, traceback, paths,
endpoints, values, bodies, or private facts. Known verification failures retain
their fixed codes. Cleanup failure must not erase the primary stage code.

Unit-test each stage mapping and primary-error preservation.

## 2. Exact composed-only fake topology

Implement a `--composed-only-fake` path that executes the same composition
function and stages as protected `--composed-only`, except:

- no runtime reference or protected credential is read;
- Local Coding upstream is the existing exact fake Qwen wire double through the
  same scrubbed relay shape;
- PostgreSQL, migrations, route/key seeding, Gateway, exact Local PR #7,
  signed identity, official OpenAI client, stream capture, accounting, and
  cleanup are real/disposable;
- the immutable 155-l direct baseline is reused exactly;
- no direct diagnostic function can be called;
- exact safe boundary output is atomically retained in a mode-0600 artifact
  under a validated mode-0700 root.

Do not mock `_run_composed_stream_diagnostic` or its return. This must reproduce
the exact path that failed in 155-m.

## 3. Reproduce and correct the exact failure

Run the exact fake composed-only path before changing the failing behavior.
Retain only its fixed stage code. Correct the smallest verifier/test defect.

No Gateway product code may change unless fake evidence proves a Gateway product
defect rather than a verifier/harness defect. Local Coding remains read-only.

After correction, the exact fake path must produce:

- pinned direct evidence with `evidence_source=pinned_155l` and
  `ran_current_invocation=false`;
- current Local/Gateway evidence with `evidence_source=current_155n` and
  `ran_current_invocation=true`;
- terminal and vocabulary verdicts for all boundaries;
- `terminal_boundaries_completed`;
- real disposable Gateway accounting finalized;
- exact safe artifact bytes equal stdout;
- empty stderr and complete cleanup.

## 4. Fake/security/privacy/accounting gate

Before protected traffic, prove:

- every stage code and cleanup path;
- exact fake composed-only end-to-end pass;
- direct-call prohibition;
- bounded recorder memory and strict safe schema;
- no request tools or hosted-search authority;
- signed Local identity accepted in fake composition;
- PostgreSQL reservation/finalization and nonnegative usage;
- no raw/private marker in stdout, stderr, artifact, DB metadata, or logs;
- Local checkout/ignored state clean and no Local `.venv`;
- focused tests, Ruff, Python compilation, `git diff --check`;
- complete legacy fake rehearsal;
- all ten checks green on the exact pushed implementation head.

Any failure blocks protected traffic.

## 5. Newly authorized protected composed request

Only after section 4 passes, read the activation runtime reference without
rendering it, verify protected health/model unchanged, and run exactly one
`--composed-only` protected invocation using:

- the immutable pinned 155-l direct baseline;
- one new minimal text-only official-client request through disposable
  Gateway/PostgreSQL, exact Local PR #7, and protected Qwen;
- no direct request, tools, images, governance, customer data, or retry;
- an exclusive mode-0600 safe artifact retained until report publication.

Maximum new protected requests in 155-n: one composed request. If any stage
fails, stop with the exact finite stage code and do not retry.

## 6. Ownership decision

- Local terminal invalid: `local_owned`; stop with exact Local handoff.
- Local terminal valid and Gateway terminal invalid: `gateway_owned`; only then
  make the smallest conditional Gateway product correction.
- Local and Gateway terminal valid and official client completed:
  `terminal_boundaries_completed`; the missing-terminal gate is closed.
- Any unexpected stage, handler/truncation/error event, invalid accounting,
  malformed baseline/summary, or missing artifact is ambiguous and blocks.

Event-vocabulary review remains reported separately and does not grant
request-side authority or erase terminal facts.

## 7. Conditional Gateway correction

Only on exact Gateway-owned evidence, modify the smallest subset of:

    app/slaif_gateway/modules/servers/local_coding/adapter.py
    app/slaif_gateway/providers/openai_compatible.py
    app/slaif_gateway/providers/streaming.py
    app/slaif_gateway/services/responses_gateway.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_responses_streaming.py
    tests/e2e/test_openai_python_client_responses.py

Preserve provider bytes/order, forwarding, cancellation, disconnect, accounting,
identity, replay/idempotency, route containment, hosted-search denial, and
privacy. Never fabricate completion/usage/cost/tool authority. Add exact
regressions, rerun fake gates/checks, and run one post-fix composed verification.
If it fails, stop.

## 8. Full real acceptance

If terminal boundaries complete, update only verifier acceptance so the real
full stream gate uses terminal validity while retaining vocabulary facts; keep
exact fake-pair assertions for fake rehearsal.

Then:

- rerun focused tests and complete fake rehearsal;
- push the exact final implementation head and require all ten checks green;
- run exactly one no-retry full protected
  real Codex 0.149 -> Gateway -> Local Coding -> Qwen matrix.

The full matrix must prove ordinary/streaming Responses, signed identity,
PostgreSQL accounting, same-session reuse, independent-session/cache isolation,
replay/tamper and idempotency, controlled rollback, request-tool filtering,
credential/privacy boundaries, and complete cleanup.

Do not run the full matrix for Local-owned, Gateway-owned before a verified fix,
or ambiguous evidence.

## Allowed paths

Unconditional evidence paths:

    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_full_stack_verifier.py
    docs/module-architecture.md
    docs/provider-forwarding-contract.md
    docs/responses-compatibility.md
    docs/security-model.md
    docs/accounting.md
    docs/compatibility-matrix.md
    oap/orders/155-n-fake-composed-stage-localization-and-closure.md
    oap/reports/155-n-fake-composed-stage-localization-and-closure.md
    oap/active

Conditional product paths are allowed only after exact Gateway-owned evidence
as listed in section 7.

No Local repository mutation, schema/migration/dependency/lockfile, route/pair/
tool policy, Compose/deployment, protected service, release, or production
mutation is authorized.

## Security, cleanup, publication

- Use unique mode-0700 task roots and atomically created mode-0600 artifacts.
- Runtime reference and task credential source are temporary persistent secret
  material; never render; remove both during post-report cleanup.
- Use task-owned Local `UV_PROJECT_ENVIRONMENT`; never Local `.venv`.
- Clean every environment, artifact, relay, process/listener, DB/container/image
  state, generated lock/bytecode, runtime reference, credential source, and root.
- Keep both PRs open; coding agent never merges or enables auto-merge.

Publish one immutable 155-n report with literal implementation head,
`Report publication commit: SELF`, report-only topology, exact fake/protected
safe artifacts or exact stage codes, ran/not-run counts, terminal/vocabulary
verdicts, checks, accounting/security/privacy/cleanup, and limitations.

After publication make no repository mutation. Wait for report-head checks,
verify topology/mergeability, remove exact task secret/artifact/root state
without rendering, signal exact FIFO `OK`, and stop.

Only complete full-stack PASS creates the merge pair. Strategic then revalidates
and merges Local PR #7 first and Gateway PR #291 second. Do not start Objective
156 or Local Objective 006 before resolution.

