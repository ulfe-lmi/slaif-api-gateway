# OAP Work Order — 155-f

PR mode: `AMEND_EXISTING_PR`
PR: `#291`
Branch: `oap/155-local-coding-signed-server-module`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Current remote head: `6bb67f4ca19f231b2f214e30c964ea0aac685d3e`

## Objective and reason

Perform the first complete, disposable, real

```text
Codex 0.149.0 -> SLAIF API Gateway PR #291
  -> SLAIF Local Coding PR #7 -> protected Qwen qwen3.8-27b
```

acceptance run after the accepted 155-e identity correction. Prove real signed
identity, same-session reuse, cross-session and cross-key isolation, replay
rejection, streaming, PostgreSQL reservation/finalization/accounting, bounded
failure rollback, privacy, and complete cleanup. Publish the immutable evidence
needed to merge Local Coding PR #7 first and Gateway PR #291 second.

Local Coding 005-i was originally assigned this composed gate, but its canonical
execution host is unavailable from this strategic environment and no Local
Coding agent may be invented or impersonated. The acceptance owner may therefore
move to this same Gateway objective without changing either product contract:
use Local Coding PR #7 as an exact, clean, read-only dependency and leave its
branch untouched. This is not a substitute for the real topology and does not
relax any acceptance criterion.

## Verified starting state

- Gateway PR #291 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 155-e report
  head `6bb67f4ca19f231b2f214e30c964ea0aac685d3e`; its first parent is
  implementation head `4eb768254fcde0a4108bcabb35f175a74bd07a3f`, and the
  report commit changes only
  `oap/reports/155-e-codex-thread-namespace-and-key-bound-session.md`.
- All ten Gateway report-head CI, CodeQL, PostgreSQL, official-client E2E,
  Compose, browser, and documentation checks are successful. Independent
  review also passed 98 focused unit tests, exact fixture hashes, order hashes,
  report topology, and `git diff --check`.
- Accepted 155-e requires equal canonical Codex `session_id`/`thread_id`
  aliases; derives principal from authenticated owner and the opaque session
  from owner principal + authenticated Gateway-key UUID + corroborated Codex
  thread under the v2 domain; and preserves signed identity v1 wire format,
  request-specific nonce/signature, strict-bounded accounting, and hosted-tool
  denial.
- Local Coding PR #7 is OPEN, non-draft, MERGEABLE/CLEAN at immutable 005-h
  report head `6ee2a51aa7b03d4df46e0662d88cc33fd0ef7db8`; its first
  parent is `d2093650ef61200d3ed6ff9516bfd73eb2675182`, its required
  signed-contract head `356be8345dd71d6fddf829278651d18e485731d4`
  is an ancestor, and its `test` check is successful.
- Local 005-h already passed exact capture/candidate/pair/provenance/tool-filter
  preflight and found no Local Coding product defect. It stopped before Docker,
  PostgreSQL, listeners, or inference only because the prior Gateway head did
  not expose stable session context; 155-e directly corrects that gate.
- Exact Codex 0.149.0 is not the host default and must be installed only into a
  private disposable task directory. Do not qualify with host 0.149.1.
- A protected Qwen endpoint is currently healthy and, with the existing
  protected credential reference, reports exactly `qwen3.8-27b`. A stale local
  one-image proxy currently fails upstream and is not the acceptance path.
  Do not alter either endpoint, proxy, service, profile, credential, network,
  model, or listener.
- A clean Local Coding checkout exists at
  `/home/ubuntu/codex-work/slaif-local-coding` on the exact PR head. It is a
  disposable/read-only dependency for this round, not a second product worktree
  to modify.

Abort before live setup if either PR head, report topology, ancestry, required
check, exact order bytes, protected runtime model identity, or clean dependency
state differs. Do not substitute either main branch, an unreported commit, a
synthetic Gateway envelope, host Codex 0.149.1, or a fake Qwen for a required
real-path assertion.

## Required implementation

### 1. Gateway-owned bounded acceptance verifier

- Add the smallest reusable verifier under
  `scripts/verify_local_coding_full_stack.py` plus focused unit tests. It may
  import normal repository code and exact Local Coding PR code from the pinned
  checkout, but must not copy Local Coding product implementation into Gateway.
- The verifier must fail closed on wrong Gateway/Local heads, dirty dependency
  checkout, wrong report parents/topology, missing required checks, wrong Codex
  version, unavailable credential reference, unhealthy/wrong protected model,
  unsafe paths, unexpected pre-existing test listeners/containers, or inability
  to guarantee cleanup.
- Accept protected endpoint/credential facts only through the private
  activation-time runtime reference `/tmp/slaif-155f-runtime.env` (mode 0600,
  owned by the task user, containing only a protected endpoint and credential-
  source pathname; no credential value). Never print, commit, hash into evidence,
  pass via process arguments, or retain the endpoint, credential, raw response,
  or reference contents. Pass credentials to only the Local Coding -> Qwen
  process environment.
- Emit only fixed statuses, booleans, counts, versions, public commit/digest
  facts, bounded durations, and opaque test-request correlations. Never emit
  prompts, source, model text, images, request/response bodies, identity values,
  signatures, nonces, canonical signing bytes, gateway/service/Qwen keys,
  database URLs, private paths, private endpoints, or cache filenames.
- Do not weaken assertions to accommodate runtime behavior. If the exact stack
  exposes a product defect, stop after safe cleanup and publish a truthful
  blocked report; repair requires a later 155 continuation.

### 2. Mandatory no-inference preflight

Before Docker, PostgreSQL, test listeners, or inference:

1. verify both exact immutable report heads, parents, report-only topology,
   ancestry, clean mergeability, and successful required checks;
2. hash and semantically execute every shared signed-identity and tool-filter
   vector against both implementations; reject stale/unknown version, changed
   vector, missing case, malformed wrapper, and divergent outcome;
3. install and verify literal official `codex-cli 0.149.0` in one private
   disposable installation; use a private `CODEX_HOME` and synthetic workspace;
4. run a fresh loopback/no-provider A1/explicit-resume-A2/B capture through the
   registered Gateway v3 normalizer and exact `local-coding-v1` pair, proving
   only safe relationship facts and retaining no raw identifiers;
5. prove malformed/authority-bearing search declarations, explicit hosted or
   dropped search choice, unrelated server pair, missing route capability,
   missing/malformed/unequal session aliases, and spoofed signed headers fail
   before provider/reservation;
6. prove Local Coding drops only exact disabled Codex search candidates,
   preserves ordinary client tools/calls/results, authenticates service Bearer
   separately, verifies signed identity before cache/upstream work, strips all
   internal headers before Qwen, and fails closed on replay/tampering;
7. prove public Gateway key, service Bearer, signing secret, derivation secret,
   database secret, and protected Qwen credential are distinct roles without
   comparing or emitting their values;
8. capture safe protected health/model identity before state and verify the
   exact expected model; make no inference during this preflight.

Any failure stops before later setup stages. Unit/mock evidence is necessary
but never substitutes for the required real composed run.

### 3. Disposable real topology

If and only if preflight passes, create one bounded topology:

```text
ordinary OpenAI client + exact real Codex 0.149.0
  -> exact Gateway PR #291 app on random loopback port
       temporary PostgreSQL 16 container, loopback only, tmpfs
       exact migrations and repository/service seeding
       exact codex-0.149-responses-v1 -> local-coding-v1 route
  -> exact Local Coding PR #7 app on 127.0.0.1:18031
       service_bearer_signed_identity_v1
       responses_tool_policy=drop_disabled_codex_search
       rehydration enabled, fresh private bounded cache
  -> existing protected qwen3.8-27b endpoint
```

- Use only synthetic public/account/session/repository data and generated
  per-run Gateway/service/signing/derivation/database secrets. The existing
  protected Qwen credential is the sole non-synthetic credential and may reach
  only the Qwen request channel.
- No Redis, Celery, email, admin, TLS, public bind, persistent route/profile,
  production database, host network, privileged container, or protected service
  operation is allowed.
- Use an exact unique PostgreSQL container name, official `postgres:16`, tmpfs,
  random loopback host port, finite health timeout, and ownership-tagged task
  roots. Record whether the image pre-existed and remove it only if this round
  pulled it.
- A bounded loopback relay may be used solely to observe safe request facts and
  replay one exact Gateway-signed request in memory. It must not alter bytes,
  log bodies/headers, persist the request, or remain after the run.

### 4. Required real traffic

Run the minimum traffic that proves all of the following without retrying a
failed product/accounting operation:

1. Gateway and Local health/readiness plus one visible synthetic public model;
2. official OpenAI client non-streaming Responses success through real Qwen;
3. official OpenAI client typed SSE through `response.completed` with real
   provider usage;
4. one small synthetic inline image through the selected one-image route;
5. exact real Codex 0.149.0 session A request through the complete chain with
   ordinary local tools plus candidate `tool_search`/`web_search`; Qwen must see
   no disabled search declarations and no Gateway/internal credential headers;
6. explicit real Codex resume of session A proving the same signed opaque Local
   session and intended cache/rehydration reuse, with no unnecessary second
   compiler-model attempt when the applicable cache contract says reuse;
7. a separate real Codex session/process B using the same Gateway credential,
   proving a different opaque Local session and no access to A's protected
   cached/rehydrated state;
8. the same corroborated test session under a second Gateway key for the same
   owner, proving another opaque session and independent accounting/cache
   namespace;
9. one bounded same-session zero-root/history-reduction request, if required by
   the Local rehydration contract, proving signed rehydration rather than prompt
   coincidence;
10. invalid key, over-quota, malformed/unequal identity aliases, explicit
    hosted/dropped search choice, bad signature, timestamp/body/path/query
    tampering, and exact replay rejection at their correct boundaries, with no
    duplicate provider call or leaked reservation/ledger state;
11. one controlled disposable provider-failure path proving terminal Gateway
    reservation rollback/finalization and no corrupt Local cache state. This
    may use a separate fixed synthetic failing upstream; it must not stop or
    perturb protected Qwen.

Session is never authentication, accounting ownership, replay proof, or an
idempotency key. Same-key hostile-client isolation is not claimed; separate
Gateway keys are the security boundary. Do not infer cache reuse from equal
client strings alone: use signed identities plus safe Local metrics/state facts.

### 5. Accounting, security, privacy, and cleanup evidence

- Prove exactly one reservation and one terminal ledger outcome per admitted
  public request, provider-reported usage finalization, zero pending counters,
  no duplicate request IDs, correct per-key counters, and internally consistent
  tokens/cost. Local compiler calls create zero Gateway rows.
- Every Local Coding success remains `strict_bounded`, external capability and
  destination facts remain empty, external provider/route remain null, fence is
  `none`, and no hosted-tool fee/hold metadata exists.
- Rejected pre-provider requests and replay/tampering produce their exact zero
  provider/zero accounting effect. The controlled admitted provider failure
  produces the existing terminal failure/rollback outcome, not a pending hold.
- Prove raw client metadata, authenticated owner/key facts, protected cache
  content, service/signing/derivation secrets, signatures/nonces, prompts,
  source, tools/results, images, Qwen output, private endpoint, and credentials
  are absent from provider bodies where prohibited, Qwen headers, DB metadata,
  audit, metrics labels, logs, errors, fixtures, Git diff, and report.
- On every exit remove only exact task-owned Codex installation/home/workspace,
  Gateway/Local configs and processes, relay, cache, logs, venvs if created,
  PostgreSQL container/tmpfs/database/volume, generated credentials, and newly
  pulled image. Verify no task listeners, processes, containers, volumes, temp
  roots, or pending DB state remain.
- Recheck protected health/model identity after cleanup. Do not mutate the
  protected endpoint, stale local proxy, services, profiles, files, credential,
  model, network, or listeners. Process-local replay/rehydration restart and
  multi-worker limitations remain documented; do not claim persistence that is
  not tested or designed.

## Documentation and acceptance result

- Update only the affected Gateway Local Coding integration, compatibility,
  accounting, security, and test documentation with exact fixture-scoped
  evidence and limitations. Distinguish unit/vector/mock, disposable real
  composition, persistent deployment, production, and release claims.
- If the real run passes, the report must state that the exact open Gateway and
  Local heads form a tested merge pair. It must not call the MVP, release,
  production deployment, hostile multi-tenant isolation, persistent replay, or
  certification complete.
- The unused legacy `_SESSION_KEYS` constant is a known non-behavioral review
  note. Do not mutate accepted identity code merely to remove it in this live
  acceptance round.

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
oap/orders/155-f-real-codex-local-coding-qwen-acceptance.md
oap/reports/155-f-real-codex-local-coding-qwen-acceptance.md
oap/active
```

Use the narrowest subset. No Gateway or Local Coding product module, schema,
migration, dependency, lockfile, endpoint/header, route/pair, pricing,
external-tool, Compose, deployment, service, release, production, or external
repository mutation is authorized. If the verifier cannot be implemented
without changing a product contract, report the exact blocker.

## Required verification

- Focused unit tests for verifier path/head/topology/check/version/privacy/
  cleanup gates and fixed-safe output; no skipped focused test is a pass.
- Existing exact Codex client, Local server identity, tool-policy, PostgreSQL
  accounting, official-client E2E, and documentation tests affected by the
  verifier/docs.
- One fresh no-provider exact 0.149.0 relationship preflight and exactly one
  complete bounded real composed qualification attempt.
- Local Coding exact-head focused identity/tool/cache tests read-only; do not
  run or claim its broad suite unless required to diagnose a failure.
- Ruff on changed Python, Python syntax compilation, `git diff --check`,
  `python scripts/check_documentation.py`, unchanged Alembic head, privacy/
  secret/raw-output scans, cleanup proof, and final GitHub CI/CodeQL.
- Report every named gate as `PASSED`, `FAILED`, `BLOCKED`, `NOT RUN`, or
  `SKIPPED`. Pending/skipped/missing/not-run is never pass.

## Anti-false-positive acceptance

- Synthetic envelopes, mocked Local Coding/Qwen, ordinary OpenAI clients alone,
  structural preflight, unit tests, or green CI cannot satisfy the real Codex
  full-stack gate.
- One Codex request, `--last` without explicit thread resume, two unrelated new
  sessions, client string comparison without signed Local evidence, or cache
  filename inspection cannot prove same-session reuse/isolation.
- A Qwen health/models response without inference, or inference bypassing
  Gateway or Local Coding, cannot prove the topology.
- Hosted search execution, raw client metadata forwarding, unsigned fallback,
  client-authoritative principal/accounting, cross-key cache sharing, duplicate
  accounting, pending holds, replay acceptance, or cleanup residue fails.
- Changing either product branch or testing an unreported/non-green head fails.
- Do not repeat this composition in Objective 156 if this exact round passes.

## Merge choreography and non-goals

- Keep both PRs open during execution. Coding agent never merges or enables
  auto-merge and never writes Local Coding.
- A passing 155-f report is the cross-repository acceptance artifact. Strategic
  review then merges Local Coding PR #7 first, verifies its merge contains exact
  tested head `6ee2a51...` and signed-contract ancestor `356be83...`, rechecks
  unchanged Gateway report head/checks/reviews, and merges Gateway PR #291
  second. Neither PR depends on the other already being merged.
- No persistent deployment/cutover, direct-Qwen rollback retirement, protected
  service/profile/network change, release, tag, publication, production claim,
  Objective 156 activation, or Local Objective 006 work is authorized.

## Setup and publication

- The authoritative OAP selector/order live at the fixed repository root. Use
  the existing clean linked worktree
  `/home/ubuntu/codex-work/slaif-api-gateway-152` for PR #291 product/report
  commits, and first prove its branch/head/clean state plus byte equality with
  the authoritative order and selector. Preserve the unrelated primary
  worktree and every other linked worktree.
- Routine task-local exact Codex install, Python environment, PostgreSQL image,
  loopback processes, and bounded live protected inference are authorized.
  No apt install, sudo outside exact Docker commands, or protected mutation is
  authorized.
- Amend only PR #291. Commit the unchanged order and `oap/active` with any
  verifier/docs implementation. Push all non-report commits and wait for their
  required checks.
- Atomically publish exactly one immutable
  `oap/reports/155-f-real-codex-local-coding-qwen-acceptance.md` containing the
  literal implementation-head SHA and `Report publication commit: SELF`. Its
  first parent must be the implementation head and it must change only the
  report file.
- After publication perform no repository mutation. Verify remote report
  head/topology and final checks, remove the private runtime reference and all
  exact task state, then send exact two-byte response FIFO `OK`. Coding agent
  never merges.
