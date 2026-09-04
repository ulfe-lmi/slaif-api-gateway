# OAP Work Order — 155-ac

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Current remote head: a0701a3db477e8c34d7c4db981a5216aa7d7ac0b

## Human-authorized continuation and fixed scope

The human explicitly authorized `155-ac` on existing PR #291 after immutable
155-ab report head `a0701a3db477e8c34d7c4db981a5216aa7d7ac0b`.
This is an exact naming/selection exception and a diagnostic/stabilization round
only. It does not authorize `155-ad`, a general multi-letter protocol, reasoning-
placeholder canonicalization, fabricated reasoning identity, weaker validation,
or any Gateway, Local Coding, or Qwen product correction.

Preserve the immutable 155-aa and 155-ab orders/reports. 155-ab did not exercise
the second-turn predicate and is evidence neither for nor against the proposed
empty-reasoning compatibility rule.

## Objective and reason

Restore experimental validity before returning to the second-turn compatibility
question: prove which Codex executable the qualification actually invokes,
classify why the protected first turn changed from 155-aa Gateway 2 / Local 1 / Qwen
1 to 155-ab Gateway 1 / Local 1 / Qwen 0, correct only a proved qualification-
harness/runtime defect if one exists, and run at most one version-pinned protected
two-turn diagnostic to collect the already-defined reasoning-placeholder predicate.

The purpose is reproducible diagnosis, not a green integration result. No product
canonicalization or product fix follows in this round even if the empty predicate is
true.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, has no auto-merge, and is at
  report-only head `a0701a3db477e8c34d7c4db981a5216aa7d7ac0b`; its first parent is
  diagnostic head `1664a53a6dc6ce36a0cb05420901d352c08dabeb`, and the report commit
  changes only
  `oap/reports/155-ab-proven-empty-reasoning-canonicalization-and-acceptance.md`.
- Remote `main` remains `7ffce834915b74809109e8b579d8541cdcfa9df7`; all ten 155-ab
  report-head checks pass; the Gateway worktree is clean.
- Exact Local Coding PR #7 report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa` remains clean and read-only at
  `/home/ubuntu/codex-work/slaif-local-coding-005m`. Do not modify it.
- 155-aa reached Gateway 2 / Local 1 (2xx SSE) / Qwen 1 (2xx SSE, normal close)
  and selected the second-turn malformed `reasoning` item branch. 155-ab stopped
  on turn 1 at Gateway 1 (2xx SSE) / Local 1 (4xx JSON) / Qwen 0, so it produced no
  placeholder evidence.
- The 155-aa report states that an unrelated complete-suite candidate test saw a
  non-pinned host Codex. Current host-default provenance resolves to the system
  installation and reports `codex-cli 0.149.1`. The qualification verifier instead
  intends to install exact npm package `@openai/codex@0.149.0` under its private task
  root, verify raw output `codex-cli 0.149.0`, and pass that exact path into the
  command builder. Previous reports did not retain enough run-specific provenance to
  prove which executable object was invoked; do not infer it from fixture names.
- A recovered bounded 155-ab console summary, not a substitute for immutable
  report evidence, classified the first request as three message input items with
  top-level tool counts custom 1, function 5, tool-search 1, and web-search 1—the
  same coarse first-request facts reported by 155-aa. It mapped the Local error to
  `other`. Re-establish all decisive facts in 155-ac; do not infer a product cause
  from this non-durable summary.
- The private runtime reference will be an owner-only mode-0600 regular file with
  exactly the expected endpoint and credential-source keys. Never render or retain
  its values.
- Every prior activated order and report remains immutable.

## 1. Prove executable provenance before any protected traffic

Audit the complete qualification call chain from package installation through
`_exec_command_0149` and subprocess execution. Add a bounded provenance projection
and pure tests proving all of the following for the executable used by qualification:

- requested package is exactly `@openai/codex@0.149.0`, without a range, tag, host
  fallback, PATH lookup, or reuse of a global installation;
- package metadata and `--version` both identify exact 0.149.0;
- the verified task-local executable object is the same resolved executable object
  passed to model-catalog generation and the protected Codex command;
- the command builder cannot silently replace it with `/usr/bin/codex`, `codex` from
  PATH, another version, or a fixture-only version label;
- the private task-local install is removed during cleanup.

Retain only closed safe provenance facts such as source class
`task_local_exact_npm`, requested/package/raw/invoked version class `0.149.0`,
`verified_binary_is_invoked=true`, `host_default_version_class=0.149.1`, and
`host_default_matches_pinned=false`. Do not retain absolute temporary paths, inode
numbers, package-manager output, environment contents, command stdout/stderr beyond
the exact allowlisted version line, credentials, identifiers, or arbitrary strings.

The host-default fact is diagnostic only. A host mismatch must not fail the protected
runner when the exact task-local binary is proved, and a task-local mismatch must fail
closed before network/provider activity. Update the exact governance test to allow
ordinary one-letter selectors plus only `155-aa`, `155-ab`, and `155-ac`; prove
`155-ad`, other multi-letter IDs, suffixes, and malformed forms fail.

## 2. Reconcile the first-turn boundary without product changes

Compare 155-aa and 155-ab using only immutable report facts, current exact Git
topology, and new bounded projections. Prove that the Gateway product tree and exact
Local product head relevant to turn 1 did or did not change. Do not call either run
"Codex 0.149.0" unless run-specific executable provenance proves it; where historical
provenance was not retained, record `historical_runtime_provenance=unproved`.

Extend only the task verifier/relay with a closed, source-reviewed Local error and
boundary classifier. It may inspect request/response values transiently in memory but
may retain only:

- exact immutable Gateway implementation/report and Local report/parent SHA facts;
- actual safe Codex provenance/version classes from section 1;
- route/profile class, bounded input-item/tool taxonomy counts, request content-type
  class, `stream` boolean, and model/route match booleans;
- service Bearer verification class and signed-identity verification class from a
  closed enum;
- booleans for unique required signed headers, exact raw-body digest participation,
  exact canonical-bytes reconstruction, signature verification, route match,
  timestamp/nonce shape, and no extra internal headers;
- Local status/content-type and an exact Local error code only from a closed allowlist
  derived from immutable Local head `4d3ab2f...`; unknown values become `other`;
- Local rejection stage from a closed enum such as `service_auth`, `signed_identity`,
  `json_route_image`, `tool_policy`, `observation_constitution`, `upstream`, or
  `other`, justified by immutable Local source and bounded counters;
- whether Local tool filtering, observation, constitution/compiler, and upstream
  inference boundaries were not reached, entered, succeeded, or rejected, using only
  fixed counters/classes and no model text;
- Qwen relay compiler-call and inference-call count classes, status/content-type
  classes, normal-close/path/auth-replacement booleans, and accounting terminal
  classes.

The independent signature check must use the exact captured bytes in task memory and
the same ephemeral signing secret, then discard both. It must not log or retain the
body digest, canonical bytes, signature, secret, signed identity values, nonce,
timestamp, or headers. Service/signed-auth facts are evidence only and must not
bypass Local verification or replay protection.

Add pure/fake tests for every closed error/stage/provenance class; wrong version and
host-fallback attempts; service-token mismatch; missing/duplicate/extra signed
headers; body/signature mismatch; route mismatch; tool-policy and constitution
rejection; compiler-only versus inference entry; upstream rejection; unknown codes;
tampered/misaligned/duplicate summaries; cardinality/order/size bounds; and privacy
canaries in every forbidden value position.

Before protected traffic, run exact provenance tests, full Ruff and compilation,
focused capture/verifier/governance/privacy tests, direct pinned capture/fake tests,
and at least two isolated normal fake two-turn runs proving the qualification harness
selects exact 0.149.0 and reproduces the same safe first-turn class. Push the
diagnostic/stabilization head and require all ten PR checks green.

## 3. Harness/runtime stabilization boundary

Use source and pure/fake evidence first to classify the 155-ab divergence as one of:

1. qualification harness/runtime drift;
2. Codex-version drift;
3. signing/service-auth mismatch;
4. changed first-turn request class; or
5. an actual reproducible product/external defect.

If a harness/runtime defect is uniquely proved before protected traffic, correct only
the qualification environment or verifier harness within the allowed files. Preserve
the production Gateway, Local, Qwen, Codex package, route/policy, signing, replay,
accounting, tool, and stream contracts unchanged. Prove the harness correction with
strict regressions and the two isolated fake runs.

If source/fake evidence shows an actual Gateway, Local, or Qwen product defect, or if
more than one cause remains reachable, do not implement a product correction. The
single protected diagnostic may be used only to produce the bounded decisive
classification below; otherwise publish a truthful FAILED report and stop.

Do not alter Local configuration merely to bypass constitution/context behavior; do
not disable signing, service authentication, observation, compiler, cache,
constitution, tool filtering, accounting, or strict Gateway validation; do not use a
fake compiler for the protected run; and do not change prompts/tool contents to steer
around the failure.

## 4. Exactly one protected, version-pinned diagnostic execution

After the clean green pre-protected gates, execute exactly one zero-retry protected
Codex process using the proved task-local `@openai/codex@0.149.0` executable:

real Codex 0.149.0 -> Gateway -> unchanged Local Coding -> unchanged protected Qwen.

Run direct stdout only; do not redirect, pipe, retain, or hash prohibited values.
The first turn is an in-run gate. Require Gateway to admit it, Local to accept it as
2xx SSE, protected Qwen inference to occur with 2xx SSE and normal close, signed body
verification to succeed, and one terminal accounting outcome with zero pending. If
the first turn fails, retain only the section-2 safe classification, publish FAILED,
and stop. Do not retry or attempt a second protected process.

Only after that first-turn gate passes may the same Codex process naturally issue its
function-result continuation. The sole second-turn purpose is to collect the existing
155-ab predicate facts for the unique rejected reasoning item:

- item type exactly `reasoning`;
- ID state absent or null versus other;
- content empty-array versus nonempty/absent/malformed;
- summary empty-array versus nonempty/absent/malformed;
- encrypted content null versus non-null/absent/malformed;
- exact allowed-key-set and unexpected-state-field booleans;
- exactly one candidate and exact adjacent function-call/output chronology.

If the exact empty predicate is true, publish that fact and stop. If any constituent
differs, publish the closed truthful facts and stop. Do not canonicalize, synthesize
an ID, relax validation, retry, run a hook-free acceptance, or implement any product
change in either case.

The one process may produce at most two Gateway requests. Any extra request,
unbounded cardinality, provenance uncertainty, privacy failure, missing accounting
terminal state, or new failure outside the closed classifier ends the run as FAILED.

## Security, privacy, and accounting invariants

Retain no prompts, request/response bodies, body/signature digests, IDs, signatures,
credentials, tool names/arguments/results, reasoning content, raw headers/SSE,
endpoints, arbitrary Local/Qwen errors, exception text, npm logs, or temporary paths.
Do not widen hosted-tool authority, route/pair scope, client/server modules, replay or
idempotency behavior, signed identity, Local cache/session isolation, request bounds,
stream validation, reservation/finalization, or PostgreSQL authority. Unknown or
malformed evidence fails closed. All reservations must be finalized or released and
zero pending; remove task roots, installed Codex, processes, listeners, containers,
temporary summaries, and the private runtime reference before reporting.

## Allowed paths

    scripts/capture_codex_protocol.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_codex_protocol_capture.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_oap_governance.py
    oap/active
    oap/orders/155-ac-pinned-provenance-first-turn-stabilization-and-predicate.md
    oap/reports/155-ac-pinned-provenance-first-turn-stabilization-and-predicate.md

No `app/` product file, schema, migration, dependency, lockfile, fixture, documentation
contract, Local Coding checkout, Qwen/Codex installation, prior order/report, AGENTS,
OAP protocol, merge, auto-merge, release, or next continuation is authorized.

## Report and result contract

Publish exactly one immutable report-only `SELF` commit. `RESULT=PASSED` means the
run-specific task-local 0.149.0 provenance was proved, the single protected process
reproduced a successful first turn, reached exactly one second request, and captured
a complete privacy-safe placeholder predicate—whether that predicate is true or
false. `RESULT=FAILED` applies if provenance is unproved, the first turn does not
reproduce, the second request is not reached/classifiable, evidence/privacy/
accounting is incomplete, or any unauthorized condition appears.

Record activation/implementation/report topology, historical provenance limitations,
safe current provenance, exact first-turn cause/classification, any harness-only
correction, fake/check gates, protected request counts and predicate facts, accounting,
cleanup, and limitations. Do not claim Gateway/Local/Qwen ownership without decisive
boundary evidence. Do not post a green handoff to Local PR #7, merge, or activate
155-ad. Require all ten report-head checks, then write exactly two response FIFO bytes
`OK` once.
