# OAP Work Order — 155-o

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: e26ac23ce352d7318615a4b01f4662f2bc3a165b

## Objective and reason

Add bounded hop counters and a finite error class to the composed-only evidence,
then run one new no-retry protected composed request to determine whether the
current failure belongs to Gateway, Local Coding, or the Local-to-Qwen path.

155-n proved the exact fake composition and ran one protected composed request.
The protected Gateway stream emitted created/in-progress/error, while the
Gateway-to-Local relay retained no response structure/status. Existing evidence
does not say whether Gateway called Local or whether Local called Qwen.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-n report
  head `e26ac23ce352d7318615a4b01f4662f2bc3a165b`; first parent is
  `bd0cfd976bfd570561d7943be2d62686d4d48972`, and only the exact 155-n report
  changed.
- All ten report-head checks pass.
- Local Coding PR #7 remains exact, OPEN, non-draft, MERGEABLE/CLEAN at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` remains an ancestor.
- Gateway/Local worktrees and task state are clean. No prior runtime reference,
  credential source, root, process, listener, artifact, or container remains.
- The pinned direct baseline is terminal-valid. No new direct request is allowed.

## 1. Fixed hop evidence

Extend the strict safe artifact with one `COMPOSED_PATH` line containing only:

- Gateway-to-Local request count class: `zero`, `one`, or `many`;
- Gateway-to-Local response count class;
- Local response status/content-type class;
- Local relay rejected/handler/truncation/downstream-close booleans;
- Local-to-Qwen inference call count class;
- Qwen upstream response count/status/content-type class;
- Qwen terminal-completion, handler/truncation/path-rejection booleans;
- Gateway error-event presence and finite error code/type class;
- Gateway accounting terminal/finalized boolean;
- final decision enum.

Counts must be projected to classes before output. Do not emit correlation IDs,
paths, endpoints, model text, bodies, messages, headers, credentials, signatures,
sessions, DB identifiers, or arbitrary values.

## 2. Finite error classification

For an SSE `error` event retain only:

- allowlisted error-object field names;
- an enum mapped from exact error code/type values already defined by Gateway's
  public error contract;
- `unknown` for every unreviewed value.

Never retain or print error message/detail, arbitrary code/type strings, provider
body, exception text, or raw JSON. Unit-test known and hostile/unbounded values.

## 3. Ownership decision

Apply the hop evidence in order:

- Gateway-to-Local request count zero: `gateway_owned`.
- Exactly one Local request, no Local-to-Qwen inference, and Local connection/
  response fails: `local_owned`.
- Local-to-Qwen inference occurs and Qwen response is non-2xx, truncated, missing,
  or terminal-invalid before Local produces a response: `local_qwen_owned`;
  Gateway product must not change.
- Qwen terminal-valid but Local response is missing/error/terminal-invalid:
  `local_owned`.
- Local response terminal-valid but Gateway emits error or lacks terminal:
  `gateway_owned`.
- Local and Gateway terminal-valid and official client completes:
  `terminal_boundaries_completed`.
- Counter contradictions, many calls, missing safe facts, or cleanup/accounting
  failure: `ambiguous_stream_evidence`.

Unknown response-event vocabulary remains a separate compatibility fact and does
not grant request-side tool authority.

## 4. Exact fake gate

Before protected traffic:

- extend `--composed-only-fake` to emit exact `COMPOSED_PATH` evidence;
- prove every ownership branch using configurable fake failures at each hop;
- prove one-and-only-one call classes, terminal/error mapping, safe unknown error,
  accounting, artifact/stdout equality, empty stderr, and cleanup;
- prohibit direct diagnostic calls and protected runtime access;
- run focused tests, Ruff, compilation, `git diff --check`, exact fake composed,
  legacy fake rehearsal, and all ten checks on the exact pushed head.

Any failure blocks protected traffic.

## 5. Newly authorized protected diagnostic

Only after section 4 passes and is green, read the activation runtime reference
without rendering it, verify protected health/model unchanged, and run exactly
one composed-only request. No direct request, tools, images, governance/customer
data, or retry. Retain the mode-0600 safe artifact through report publication.

Maximum new protected requests in 155-o: one composed request.

## 6. Conditional action

- On `local_owned` or `local_qwen_owned`, make no Gateway product change.
  Publish an exact Local Coding continuation handoff from safe facts and stop.
- On `gateway_owned`, make the smallest correction only within:

      app/slaif_gateway/modules/servers/local_coding/adapter.py
      app/slaif_gateway/providers/openai_compatible.py
      app/slaif_gateway/providers/streaming.py
      app/slaif_gateway/services/responses_gateway.py
      tests/unit/test_local_coding_server_module.py
      tests/unit/test_responses_streaming.py
      tests/e2e/test_openai_python_client_responses.py

  Preserve bytes/order, forwarding, cancellation, accounting, identity, replay,
  route/tool containment, and privacy. Never fabricate terminal/usage/cost/tool
  authority. Rehearse, check, and run one post-fix composed verification.
- On `terminal_boundaries_completed`, update only full-verifier terminal
  acceptance, rerun fake gates/checks, and run exactly one no-retry full real
  Codex 0.149 -> Gateway -> Local Coding -> Qwen matrix.
- On ambiguity, stop.

The full matrix requirements remain ordinary/streaming Responses, signed
identity, PostgreSQL accounting, session/cache isolation, replay/tamper and
idempotency, rollback, request-tool filtering, credential/privacy, and cleanup.

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
    oap/orders/155-o-hop-evidence-and-error-owner-closure.md
    oap/reports/155-o-hop-evidence-and-error-owner-closure.md
    oap/active

Conditional Gateway product paths are allowed only on exact Gateway-owned
evidence. No Local repository mutation, schema/migration/dependency/lockfile,
route/pair/tool policy, Compose/deployment, protected service, release, or
production mutation is authorized.

## Security, cleanup, publication

Use unique mode-0700 roots and atomically created mode-0600 artifacts. Runtime
reference and task credential source are temporary persistent secret material;
never render and remove both after report publication. Use task-owned Local
`UV_PROJECT_ENVIRONMENT`, never Local `.venv`. Clean all artifacts, relays,
processes/listeners, DB/container/image state, generated files, secrets, and roots.

Publish one immutable 155-o report with literal implementation head,
`Report publication commit: SELF`, report-only topology, exact fake/protected
safe artifacts, hop/error/ownership facts, request counts, accounting/security/
privacy/cleanup/check ledgers, handoff if applicable, and limitations.

After publication make no repository mutation. Wait for report checks, verify
topology/mergeability, remove exact task state without rendering, signal exact
FIFO `OK`, and stop.

Only complete full-stack PASS creates the merge pair. Strategic then revalidates
and merges Local PR #7 first and Gateway PR #291 second. Do not start Objective
156 or Local Objective 006 before resolution.

