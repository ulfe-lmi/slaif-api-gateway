# OAP Work Order — 155-ai

PR mode: AMEND_EXISTING_PR
PR: #291
Branch: oap/155-local-coding-signed-server-module
Base: main @ 7ffce834915b74809109e8b579d8541cdcfa9df7
Starting remote head: 3999a524a7306dfd2ac3e6477600b5549d3045ea
Starting implementation parent: d9a30b966ade118df0b8ad61bd6d4a58455d5a51
Frozen pre-155-ah product head: b171ada9ed3320c57186283ed4ce6ffd4389a7c3
Exact Local Coding authority: 4d3ab2fd97d249710f952dd3d2c28936138cc8fa

## Exact authority, objective, and non-goals

The human explicitly authorizes this one exact naming/scope exception,
`155-ai`, on existing PR #291 from immutable 155-ah FAILED report head
`3999a524a7306dfd2ac3e6477600b5549d3045ea`.

155-ai is one narrow signed-identity grammar interoperability correction and
acceptance attempt. It does not authorize `155-aj`, Local Coding changes, Qwen
changes, weakening Local signed-identity validation, arbitrary identifier
relaxation, broad Objective-155 refactoring, merge, auto-merge, cutover, or
release.

Preserve the accepted Codex-0.149 visible-reasoning, null-encrypted,
ID-less-tool-call, and call-ID-HMAC replay implementations. Preserve every
prior activated order/report byte-for-byte, especially immutable 155-ah.

## Verified starting state

- PR #291 is OPEN, non-draft, MERGEABLE/CLEAN, unmerged, with no auto-merge.
- Remote PR head and clean task worktree are exactly
  `3999a524a7306dfd2ac3e6477600b5549d3045ea`.
- That report-only commit changes only
  `oap/reports/155-ah-local-turn2-boundary-diagnostic-and-evidence-closure.md`;
  its first parent is diagnostic head
  `d9a30b966ade118df0b8ad61bd6d4a58455d5a51`; RESULT=FAILED.
- All ten checks pass on the immutable 155-ah report head. Remote `main`
  remains `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- Local Coding is read-only and Git-clean at exact PR #7 report head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`.
- No 155-ai order/report existed before activation.
- The owner-only mode-0600 runtime reference has only the two approved
  endpoint/credential-source keys; unchanged protected model discovery returned
  2xx. Never print or retain either value.
- The coding agent was blocked on the exact control FIFO before activation.
- Governance currently permits through exact `155-ah`. Add only exact
  `155-ai`; keep `155-aj`, arbitrary later multi-letter names, and the next
  numeric objective rejected.

## Fixed source diagnosis

The exact Local source
`src/slaif_local_coding/gateway_identity.py` at
`4d3ab2fd97d249710f952dd3d2c28936138cc8fa` applies
`^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$` independently to signed principal,
session, repository, and route and returns
`signed_identity_field_invalid` otherwise.

Gateway `modules/servers/local_coding/identity.py` at
`b171ada9ed3320c57186283ed4ce6ffd4389a7c3` derives principal, session, and
repository as unprefixed, unpadded URL-safe base64 of the complete HMAC-SHA256
digest. Base64url permits `-` and `_` as its first character, so the producer
does not guarantee its peer’s grammar. Fresh owner/key/session inputs make the
failure probabilistic.

Gateway `LocalCodingRouteContract` currently allows `.` after the first
route character, but Local signed identity does not. The current production
route `qwen38-vision-codex` already satisfies Local’s grammar.

This is a Gateway producer interoperability defect. Never change or weaken
Local.

## 1. Mandatory deterministic pre-fix reproduction

Do not modify Gateway product behavior until fixed synthetic tests prove all of
these against the starting producer:

- current `_opaque_hmac()` can produce an encoded digest beginning with
  `-`;
- it can independently produce one beginning with `_`;
- each fails the pinned Local signed-field regex;
- ordinary alphanumeric-leading outputs pass;
- `qwen38-vision-codex` passes;
- a deterministic, bounded matrix of fixed synthetic secrets plus
  owner/key/session/repository inputs shows the old producer does not guarantee
  the consumer grammar.

Use no randomness and no protected identity. Pin exact synthetic vector inputs
whose old representation begins with each failing character. A test-only
reference implementation of the old encoding may remain to preserve the
regression proof, but production must not retain a legacy fallback.

Run the characterization before changing production and record only vector
classes/counts, not values. If the diagnosis is disproved, publish
RESULT=FAILED and stop.

## 2. Correct opaque HMAC representation

Only after section 1 succeeds, change Gateway’s Local-Coding identity
representation so every HMAC-derived principal, session, and repository:

- begins with one unconditional fixed alphanumeric encoding/version prefix;
- contains afterward only `[A-Za-z0-9_-]`;
- encodes the entire 256-bit HMAC-SHA256 digest without padding or truncation;
- is deterministic and injective over the complete digest representation;
- preserves the existing principal/session/repository HMAC domains and inputs;
- remains well below 256 characters.

An implementation equivalent to
`h + base64url(full_digest_without_padding)` is preferred. Apply it
unconditionally to every digest. Never conditionally prefix only `-`/`_`,
retry derivation, generate random replacements, hash again, truncate, or
manufacture per-request identity.

Tests must decode/remove the fixed prefix back to the exact full 32-byte digest,
prove stable equality for identical inputs, distinctness across the bounded
fixed input/domain matrix, and absence of any conditional collision.

## 3. Producer-side Local-v1 grammar validator

Add one Gateway-owned, version-scoped signed-identity field predicate matching
the pinned Local-v1 grammar exactly:

    ^[A-Za-z0-9][A-Za-z0-9_-]{0,255}$

Before signing/forwarding, require it for principal, session, repository, and
route. Validation must be Local-Coding-v1-specific, not a global OpenAI/client
identifier rule.

Invalid derived identity is an internal/configuration failure and stops before
network/provider work. The signing function must independently refuse any
invalid field so hand-constructed server context cannot bypass derivation.
Never echo the rejected value and never silently rewrite a route.

## 4. Signed-route containment

Preserve the existing general/static route-name behavior. For
`identity_mode=static`, do not gratuitously change the existing route
contract. For `identity_mode=signed_identity_v1`, require the exact Local-v1
signed-field grammar during contract parsing and again before signing.

Prove:

- `qwen38-vision-codex` remains valid;
- signed route starting with `-` or `_` fails;
- signed route containing `.` fails before Local/network work;
- valid internal `_` and `-` after an alphanumeric first character pass;
- the same dotted route under an otherwise valid static contract retains its
  existing parsing behavior;
- invalid values yield only fixed safe configuration errors.

## 5. Exact cross-repository conformance matrix

Using the actual unchanged Local implementation at
`4d3ab2fd97d249710f952dd3d2c28936138cc8fa`, run a deterministic,
privacy-safe matrix over a bounded set of many fixed synthetic owner UUIDs,
Gateway-key UUIDs, canonical session UUIDs, and repository scopes.

For every matrix row:

1. derive the Gateway identity with the corrected producer;
2. construct the exact POST `/v1/responses` body and v1 headers;
3. sign the exact raw body;
4. pass the request through Local’s actual `verify_signed_identity()`;
5. require returned principal/session/repository/route equality;
6. with fresh replay state, prove body and signature tampering fail;
7. with shared replay state, prove the same nonce replay fails;
8. prove raw owner/key/session/repository inputs are absent from derived fields,
   safe output, logs, and exceptions.

The matrix must include the two fixed vectors whose pre-fix encodings began
with `-` and `_`. It must assert exact Local commit/clean state before use.
Do not copy or weaken Local’s verifier in Gateway tests as a substitute. This
may be a workspace-only verifier gate so normal GitHub CI does not depend on a
sibling checkout, but pure producer tests and grammar vectors remain in CI.

No raw identity/header/signature/body/nonce value may be printed or persisted.
Emit only pass/count/boolean classes.

## 6. Safe full-stack verifier evidence

Extend the 155-ah bounded snapshot/projection without retaining values. For
each of at most two Local-bound requests, retain booleans/classes for:

- principal grammar valid;
- session grammar valid;
- repository grammar valid;
- route grammar valid;
- signed-header cardinality exact;
- service Bearer correct;
- signature verifies;
- exact-body participation;
- route matches;
- Local fixed rejection code and stage.

Correct the stage projection bug: the already-safe
`signed_identity_field_invalid` code must map to `signed_identity`, and an
already-projected safe stage must not be remapped as if it were an error code.
Unknown values remain `other`.

Update the snapshot closed schema, CLI sanitizer, privacy canaries, and
per-ordinal/hop evidence tests. Never retain any header or identity value.

## 7. Close every unfinished 155-ah obligation

155-ah remains immutable. Explicitly close or document a genuine stronger
superseding proof for every strategic-review omission:

1. State in the new report that 155-ag already proved real turn 2 passed
   Gateway admission and was forwarded to Local; 155-ah’s one protected
   process separately failed on turn 1 and did not supersede that evidence.
2. Add independent snapshot tests for missing/wrong structure count, each
   absent ordinal, invalid flag, created/completed missing and duplicates,
   response-ID relation, created/completed status, model match, terminal output,
   usage, duplicate/unknown/error events, trace overflow, normal/downstream
   close, handler error, truncation, and lifecycle mismatch.
3. Test all six closed post-forwarding outcomes, plus `other`, with explicit
   supporting ordinal/count/status/terminal predicates.
4. Complete HMAC rotation coverage with:
   - new version-2 function/custom tool references verified by present item ID
     and ID-less call-ID HMAC;
   - old version-1 item and ID-less call references accepted while v1 secret is
     retained;
   - both item and ID-less call paths failing when required old material is
     absent;
   - wrong present item ID never downgrading;
   - deterministic ambiguous cross-version call matches failing;
   - no raw ID/digest/privacy canary in any output.
5. Execute the unchanged legacy Codex-0.148 candidate test with an exact
   task-controlled 0.148 executable in a disposable mount namespace/container,
   never host `/usr/bin/codex`. Do not exclude, skip, xfail, or edit the test.
   If it still fails, retain the exact safe stage/class and RESULT=FAILED unless
   an actually stronger same-contract test proves and documents supersession.

RESULT=PASSED is forbidden while any required 155-ah/155-ai test obligation is
silently omitted.

## 8. Required pre-protected acceptance

Before protected traffic, pass:

- deterministic pre-fix `-`/`_` vectors and matrix;
- corrected fixed-prefix/full-digest/injectivity/stability/isolation tests;
- producer field and signed/static route grammar tests;
- actual Local `verify_signed_identity` cross-contract matrix;
- signing/body/signature/tamper/replay tests;
- complete HMAC item/call rotation/no-downgrade/ambiguity tests;
- complete 155-ah snapshot predicate/outcome tests;
- corrected per-request grammar and Local stage projections;
- existing Codex 0.149 visible reasoning, null-encrypted, prefixed-ID and
  ID-less tool replay regressions;
- fake prefixed-ID and fake non-prefixed/ID-less two-turn actual-Codex paths;
- fake provider-failure and validator-failure accounting;
- executed, non-skipped PostgreSQL replay and context-accounting integration;
- privacy/source/scope checks;
- Ruff/format/compile/diff/documentation hygiene;
- all ten PR checks green on the exact clean implementation head.

Provision only unique task-owned test databases/containers and delete them
after use. Skipped, pending, missing, neutral, cancelled, excluded, or
environment-failed required tests are not passes.

## 9. Exactly one protected qualification

After all gates, run exactly one zero-retry process:

task-local Codex 0.149.0 -> Gateway -> unchanged Local Coding at
`4d3ab2f...` -> unchanged protected Qwen.

The improved 155-ah bounded snapshot and signed-grammar projections must be
active from request one. Require:

- first Local-bound principal/session/repository/route grammar predicates true;
- exact service Bearer/header cardinality/signature/body/route predicates true;
- Local signed identity accepted;
- turn 1 reaches Qwen and closes normally;
- Codex naturally emits the function-result continuation;
- turn 2 passes Gateway and has all signed-identity predicates true;
- turn 2 reaches Local and Qwen;
- visible reasoning, null-encrypted, ID-less tool-call/call-HMAC behavior stays
  exact without fabricated IDs;
- final assistant/message lifecycle closes normally;
- two coherent terminal accounting rows and zero pending;
- privacy, route containment, replay/tamper, and hosted-tool denial remain green.

If any boundary fails, emit and publish the complete sanitized snapshot and
stop. Do not make a second product correction or protected request in 155-ai.
Do not change Local or Qwen.

## Documentation and compatibility

Update only affected Local-Coding identity/compatibility/security/accounting
wording. State the fixed `h`-style representation/version rule without
claiming cryptographic anonymity beyond HMAC pseudonymization. State signed
route grammar, failure-before-network behavior, no raw identity retention,
full-digest entropy, exact Local-v1 scope, and the fact that a green 155-ai
still does not make PR #291 a merge candidate.

## Allowed paths

    app/slaif_gateway/modules/servers/local_coding/identity.py
    app/slaif_gateway/modules/servers/local_coding/contract.py
    app/slaif_gateway/modules/servers/local_coding/adapter.py
    scripts/verify_local_coding_full_stack.py
    tests/unit/test_local_coding_server_module.py
    tests/unit/test_provider_factory.py
    tests/integration/test_local_coding_server_module_postgres.py
    tests/unit/test_local_coding_full_stack_verifier.py
    tests/unit/test_codex_replay_service.py
    tests/integration/test_codex_replay_references_postgres.py
    tests/integration/test_codex_context_accounting_postgres.py
    tests/e2e/test_openai_python_client_responses.py
    tests/unit/test_oap_governance.py
    docs/configuration.md
    docs/responses-compatibility.md
    docs/compatibility-matrix.md
    docs/accounting.md
    oap/active
    oap/orders/155-ai-signed-identity-grammar-interoperability-and-acceptance.md
    oap/reports/155-ai-signed-identity-grammar-interoperability-and-acceptance.md

No other `app/` path, Local/Qwen/Codex source, migration/schema, dependency,
lockfile, registry/pair, prior order/report, AGENTS/OAP protocol, release, or
unrelated file change is authorized.

## Privacy, cleanup, result, and immutable report

Retain no protected prompt/reasoning, raw request/response/SSE/header/body,
principal/session/repository/route/nonce/signature value, owner/key UUID,
HMAC digest, credential, endpoint, tool value/schema, arbitrary exception text,
or temporary path. Synthetic fixed test values remain test-only.

At closure remove the runtime reference and every exact 155-ai task root,
Codex install, namespace/container/database, artifact, process, listener, and
bytecode tree. Preserve protected Qwen and unrelated state. Leave both
worktrees clean.

Before creating the report, prove no `oap/reports/155-ai-*` exists. Publish
exactly one immutable report-only SELF commit whose first parent is the
terminal implementation head and whose only changed path is:

    oap/reports/155-ai-signed-identity-grammar-interoperability-and-acceptance.md

Never amend it. RESULT=PASSED requires every required prior/current test debt
closed, the actual Local matrix green, non-skipped PostgreSQL evidence, all ten
checks, and the single protected two-turn qualification green. Otherwise
publish RESULT=FAILED with the narrowest safe evidence and stop.

The report must distinguish the accepted 155-ag turn-2 forwarding evidence
from 155-ah’s separate first-turn failure, enumerate every carried debt and its
closure/superseding proof, record deterministic old/new grammar evidence,
cross-contract results, snapshot, accounting, checks, topology, cleanup, and
limitations.

Do not merge, auto-merge, activate 155-aj, or infer later work. Even on pass,
PR #291 is not yet a merge candidate; stop for post-acceptance cleanup/splitting
and architectural review. Require all ten checks green on the immutable report
head, send exactly two response FIFO bytes `OK` once, return to one blocking
control-FIFO read, and stop.
