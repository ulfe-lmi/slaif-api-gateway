# OAP Work Order — 155-i

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `8b433ba740071733585bcf4ac1fddaaf83368ac3`

## Objective and reason

Restore complete Objective-155 audit evidence, close the remaining fake-Qwen
ordinary-response 404 using privacy-safe diagnostics, require a complete fake
full-stack PASS, and only then perform at most one protected-Qwen acceptance.

155-h correctly stopped before protected execution after a diagnostic printed
the private endpoint and credential-source pathname via a `RuntimeReference`
representation. No credential value or retained artifact was exposed. Its
immutable report is truthful but omits the required implementation-head,
publication, verification, and cleanup ledgers; it must not be edited.

155-h implementation head `a7c63222d0995aa866d6733bd03d5b27a3c5bd1d`
contains the staged verifier and fake Qwen. Fake-only work proved the full
topology reaches ordinary response, corrected stage preservation, route
capabilities, and service-token plumbing, then localized the remaining failure
to a fixed Local-bound HTTP 404 before fake Qwen inference. No fake PASS or real
acceptance exists.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-h report
  head `8b433ba740071733585bcf4ac1fddaaf83368ac3`; first parent is
  `a7c63222d0995aa866d6733bd03d5b27a3c5bd1d`, and only
  `oap/reports/155-h-staged-fake-rehearsal-and-final-real-acceptance.md` changed.
- All ten report-head checks are successful.
- Local Coding PR #7 remains exact, OPEN, clean, and green at
  `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; signed-contract head
  `356be8345dd71d6fddf829278651d18e485731d4` is an ancestor.
- Both checkouts and Local ignored state are clean. No task `.venv`, generated
  lock/bytecode, temp root, process, listener, container, database, runtime
  reference, or retained diagnostic log exists.
- Protected Qwen was not called in 155-h.

## 1. Privacy-safe diagnostic boundary

- Make every runtime-reference representation fixed/redacted. `repr`, `str`,
  exception formatting, assertion output, dataclass helpers, logging, and test
  failure output must never contain endpoint or credential-source values.
- Add tests with canary endpoint/path values proving neither value appears in
  representation, exceptions, fixed terminal output, pytest assertion output,
  or any verifier result/evidence object.
- Diagnostic helpers may emit only finite allowlisted stage names, numeric HTTP
  status, fixed public error code, counts, and booleans. Never print arbitrary
  request path: classify it as exactly `v1_responses`, `double_v1_responses`,
  `bare_responses`, or `other`.
- No diagnostic may print/return raw body keys if they could expand later,
  headers, body/content, identity/session/nonce/signature, endpoint, source path,
  process environment, exception text/repr, or private filesystem paths.
- Task logs, if unavoidable, are mode 0600, scanned without displaying matches,
  deleted before continuing, and never committed/reported.
- Any further private value exposure stops the round before protected execution.

## 2. Restore the missing audit trail

The 155-i immutable report must explicitly include:

- literal 155-h report and implementation heads and the fact that 155-h report
  was truthful but procedurally incomplete;
- literal 155-i implementation head and `Report publication commit: SELF`;
- PR/base/branch/starting head, changed paths, commit sequence, checks;
- the fake rehearsal attempt ledger, including safe stage/code progression and
  ran/not-run facts;
- protected attempt ledger if reached;
- focused/static/CI commands and exact pass/fail/blocked distinctions;
- privacy incident scope, cleanup, repository/ignored-state, no merge, and all
  documented limitations.

Do not copy private terminal values into the report and do not rewrite any prior
order/report.

## 3. Close the fake ordinary-response 404

- Use only fake mode and the finite diagnostic boundary above to classify where
  the 404 originates: Gateway-to-Local relay path/status, Local-to-Qwen relay
  path/status, or fake terminal route.
- Reconcile exact URL composition among seeded Gateway provider base URL,
  Gateway provider adapter, signed relay, Local proxy base/path handling, Qwen
  relay, and fake Qwen routes.
- Correct only verifier fixture/relay mapping. Do not change Gateway or Local
  product routing and do not accept multiple guessed aliases; the fake must
  implement exactly the same effective path as protected mode.
- Add focused path-mapping/404 tests and fail closed on every other path.

Continue the permitted fake-only correction loop until one clean full fake
rehearsal returns `FAKE_REHEARSAL=OK` and proves every existing identity,
streaming, image, compiler/cache/rehydration, replay/tamper, second-key,
preprovider-negative, controlled-failure, Qwen-wire, accounting, privacy, and
cleanup assertion. A Gateway/Local product-contract failure stops the round;
do not hide it as a fake defect.

## 4. Pre-real gate and one protected attempt

Protected execution is forbidden until:

- redaction tests, focused verifier tests, Ruff, compilation, diff/docs, and
  affected Codex/client/identity/tool/accounting tests pass;
- one complete fake full-stack PASS exists on a clean implementation head;
- all non-report work is committed/pushed and all ten required checks pass;
- exact 155-h/155-i topology, current remote/local head, Local pin/ancestry, real
  Local `load_settings`, exact no-provider Codex 0.149 capture, both repository
  tracked/ignored cleanup, and absence of all fake task resources are verified;
- the strategic mode-0600 `/tmp/slaif-155f-runtime.env` is present, shape-valid,
  and used without rendering its values; scrubbed protected health/model
  identity passes.

Then run real mode exactly once. PASS requires
`RESULT=OK status=real_composed_acceptance` plus the complete safe evidence
matrix and cleanup. No retry after real-mode Docker/listener startup or protected
inference. On failure report the fixed exact stage/code and ran/not-run ledger.

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
oap/orders/155-i-redacted-fake-closure-and-protected-acceptance.md
oap/reports/155-i-redacted-fake-closure-and-protected-acceptance.md
oap/active
```

No Gateway/Local product module, schema, migration, dependency, lockfile,
route/pair/header, Compose, deployment, external repository, protected service,
release, or production mutation is authorized.

## Cleanup, publication, and merge gate

- Remove only exact task-owned fake/real environments, configs, caches, logs,
  Codex state, relays, processes/listeners, PostgreSQL state/newly pulled image,
  runtime reference, generated locks/bytecode. Preserve tracked Local `uv.lock`
  and unrelated state.
- Verify both repositories and Local ignored state clean, no task `.venv`, no
  task process/listener/container/temp root, and protected model unchanged.
- Keep both integration PRs open during coding. Coding agent never merges or
  enables auto-merge.
- Push all non-report work and require all ten checks green. Publish exactly one
  immutable `oap/reports/155-i-redacted-fake-closure-and-protected-acceptance.md`
  containing the complete ledger, literal implementation head, and
  `Report publication commit: SELF`; its first parent is the implementation head
  and it changes only that report.
- After publication make no repository mutation; verify remote topology/checks,
  send exact response FIFO `OK`, and end.
- A passing report creates the exact tested merge pair. Strategic merges Local
  PR #7 first, verifies tested/signed-contract ancestry, rechecks unchanged
  Gateway head/checks/reviews, and merges PR #291 second. Do not start Objective
  156 or Local Objective 006 before this gate resolves.
