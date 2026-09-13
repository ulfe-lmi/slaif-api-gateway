# OAP Work Order — 164-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Align the Gateway current Local-Coding route/module metadata with the merged
fail-closed replay implementation in `ulfe-lmi/slaif-local-coding` PR #8.
Replace the false live-LRU capability with the exact cross-repository value
`process_local_inclusive_horizon_fail_closed`, retire the old value, make the
signed skew/TTL metadata truthful rather than silently defaulted, and record
the required server-module semantic version transition without changing the
identity-v1 wire or duplicating Local replay logic.

Complete one coherent Objective-164 PR through implementation, routine
corrections, focused/database/E2E verification, all required CI, skeptical
self-review, and one immutable report. A test failure, stale fixture,
documentation conflict, or implementation difficulty is work to resolve in
this round, not a reason to publish an intermediate failure report or ask the
human for routine decisions. No Qwen, protected inference, Local mutation,
deployment, release, or production action is authorized.

## Reconciled authority and current state

- Canonical Gateway repository: `ulfe-lmi/slaif-api-gateway`.
- Verified Gateway remote `main`:
  `b818ece39c0f7edcdfca390c1b76b686b4176cc8`, merge tree
  `925566ff86c395b56d4d1a8688e2a761967e1da6`, app tree
  `98efa3f4e57f4a98c21a02f9b329151867f3ed8a`.
- Gateway Objective 163 is terminal: PR #300 merged at that main; final report
  `57d94dcd1f3501a881511ebed4c232700eed99f0`; all nine emitted merged-main
  checks are successful. Shared `oap/active` starts at terminal `163-c`.
- Objective 164 is unused: no `164-*` order/report, remote branch, or PR exists.
- Existing open PRs #291, #250, and #224 are unrelated and must remain
  untouched. The only release is historical prerelease `v0.1.0-rc.1`; main is
  currently unprotected and no release/deployment action follows.
- Canonical Local repository: `ulfe-lmi/slaif-local-coding`.
- Verified Local remote/main merge:
  `efc4dbcd377dd796a670726b16ebc06bd54b6356`, tree
  `68144646615cf8aec954f737261060f1b1601033`; merged PR #8 has successful
  main CI and no open Local PR.
- Local production implementation:
  `4e1f07adc5d71c3f17e71b73cb57aec76aa28d9a`; immutable report:
  `67d895b9666a7b59753c4a373a6d15bc5884e099`, whose sole report path has the
  implementation as first parent.
- Exact Local-to-Gateway handoff:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/299#issuecomment-5649192000`.
- Local source pins at merged main:
  - `src/slaif_local_coding/gateway_identity.py` SHA-256
    `8ea6e63920d3a3e4db6d80c1bed7300cacf21e74a7e3d359583dad5694cdd4b5`;
  - `src/slaif_local_coding/config.py` SHA-256
    `871c4336068c2e27dad1cae0a5a0f036c4e43e00300b28b2e44d8f4418ee4a6e`;
  - Local report SHA-256
    `3df009a5d95fdfda3413e69f2c2293bfca991ce6d7fa2d9bde5824a808ae161b`.
- Current Gateway parser accepts/returns only
  `process_local_ttl_lru`, defaults skew 60 / TTL 120 when route values are
  absent, and checks `TTL >= skew`. The adapter uses the parsed body/nonce
  bounds and route name but does not transmit, sign, or enforce skew/TTL.

## PR contract

- Base: current remote `main` at
  `b818ece39c0f7edcdfca390c1b76b686b4176cc8`.
- Branch: `oap/164-local-replay-contract-alignment`.
- PR title: `obj164: align Local Coding replay contract metadata`.
- Create exactly one new Objective-164 PR. Do not reuse, modify, close, or
  merge another PR. Do not merge or enable auto-merge.
- Use a clean isolated worktree if the shared checkout is not suitable. Never
  reset, clean, stash, switch, or discard unrelated user/coding state.
- Commit this exact activated order and `oap/active` unchanged with the
  implementation.

## Source-grounded contract decisions

### Replay capability value

The only current accepted replay value is now:

```text
process_local_inclusive_horizon_fail_closed
```

Reject `process_local_ttl_lru` and every unknown/synonym value. Do not silently
map the old label to the new behavior.

The value describes the merged Local guarantee: retain each admitted SHA-256
nonce digest through the inclusive effective horizon
`max(admission_time + replay_ttl_seconds, signed_timestamp +
clock_skew_seconds)`; reclaim only strictly later; never evict a live digest;
capacity and unsafe wall-clock observations fail closed; known replay remains
distinct. Gateway must not reimplement or pretend to test that algorithm.

### Numeric skew/TTL meaning

Gateway source establishes that `clock_skew_seconds` and
`replay_ttl_seconds` are not propagated to Local and do not control Gateway
signing. They are route assertions about the separately configured peer, not a
negotiated wire value, Gateway-enforced minimum, or runtime discovery result.
Optional fallback values can therefore silently claim behavior the peer need
not have.

For `identity_mode="signed_identity_v1"`:

- require both `clock_skew_seconds` and `replay_ttl_seconds` explicitly in the
  route capability;
- retain strict integer/non-bool bounds of skew 1–300 and TTL 1–86,400;
- retain `replay_ttl_seconds >= clock_skew_seconds`;
- make current reviewed fixtures use explicit 60/60, matching merged Local
  `GatewayIngressConfig` defaults;
- continue accepting a different explicit bounded pair such as 60/120 when
  the operator asserts the Local peer is configured that way; and
- document that Gateway cannot verify this out-of-band peer configuration.

Align the dataclass default TTL with the current peer default at 60 so direct
or static-mode materialization no longer advertises stale 120. Static identity
does not consume replay timing; preserve the current complete route shape and
new replay-mode value for static routes, permit absent timing values there,
and document that their materialized defaults are inert rather than a replay
guarantee. Do not add a transport header/body field or dynamic probe.

### Versioning

The permanent agentic-module doctrine states that changed replay behavior must
not silently reuse a module version. Bump
`LOCAL_CODING_SERVER_MODULE_VERSION` from `"1"` to `"2"` and make the server
registry descriptor consume that constant rather than a duplicate literal.
Test/document version 2.

Do not change the module/contract ID `local-coding-v1`, identity mode
`signed_identity_v1`, signing-key/identity-key version, tool-policy version,
client-module version 4, or client/server pair. The identity-v1 canonical
bytes, headers, and transport are unchanged, while `replay_mode` is already an
explicit required negotiated capability that rejects stale configuration.
Therefore a `local-coding-v2` wire/contract ID would be gratuitous and is not
authorized.

## Allowed paths

Production/module contract:

- `app/slaif_gateway/modules/servers/local_coding/contract.py`
- `app/slaif_gateway/modules/servers/registry.py`
- `app/slaif_gateway/modules/servers/local_coding/__init__.py` only if an
  export needs synchronization; behavior should otherwise remain unchanged

Current verification scripts/fixtures/tests:

- `scripts/verify_codex_0149_local_roundtrip.py`
- `scripts/verify_codex_0149_assistant_output_history.py`
- one new content-free Local replay authority fixture under
  `tests/fixtures/local_coding/`
- `tests/unit/test_local_coding_server_module.py`
- `tests/unit/test_provider_factory.py`
- `tests/unit/test_module_architecture.py`
- `tests/unit/test_local_coding_sse_framing.py`
- `tests/unit/test_codex_0149_local_roundtrip.py` only if verifier static
  assertions require synchronization
- `tests/unit/test_codex_0149_assistant_output_history.py` only if verifier
  static assertions require synchronization
- `tests/integration/test_local_coding_server_module_postgres.py`
- `tests/e2e/test_openai_python_client_responses.py`

Current contract documentation:

- `AGENTIC_CLIENT_INTEGRATION.md`
- `docs/configuration.md`
- `docs/module-architecture.md`
- `docs/provider-forwarding-contract.md`
- `docs/responses-compatibility.md`
- `docs/compatibility-matrix.md`
- `docs/security-model.md`
- `docs/runbooks/provider-key-rotation.md`
- `docs/openai-compatibility.md` only if inspection finds a current Local replay
  statement that must change
- `docs/accounting.md` only if inspection finds an affected statement; no
  accounting semantic change is expected

OAP transcript:

- `oap/active`
- `oap/orders/164-a-align-local-replay-contract.md`
- `oap/reports/164-a-align-local-replay-contract.md`

No other path is authorized unless a tightly coupled current fixture/test site
is mechanically proven necessary; explain that exact addition in the report
before changing it. Historical orders/reports are immutable and excluded from
bulk replacement.

## Required implementation and repository-wide reconciliation

1. Define one source-owned replay-mode constant and use it in parser validation
   and returned `LocalCodingRouteContract`. Do not scatter a new magic string.
2. Implement the signed explicit-timing rule and the truthful 60/60 dataclass
   default decision above. Keep strict bounds and relational validation.
3. Bump the Local server descriptor to module version 2 using the exported
   version constant. Keep the module ID, provider kind, pair registry, factory,
   endpoint restriction, and all authority boundaries unchanged.
4. Add a content-free fixture pinning exact Local main/implementation/report,
   source hashes, new capability identifier, inclusive/fail-closed facts,
   current 60/60 defaults, unchanged identity/signing wire, digest-only/
   bounded/process-local/single-worker/restart limitations, and Gateway
   ownership boundaries. Test its digest and exact fact set. It is evidence of
   reviewed peer metadata, not a Gateway replica of `ReplayProtector`.
5. Replace every current-facing `process_local_ttl_lru` occurrence in code,
   unit/integration/E2E fixtures, and non-historical verification scripts.
   After implementation, repository search outside immutable OAP history must
   find the old literal only in explicit negative tests/documentation that say
   it is rejected; no positive/current fixture may retain it.
6. Update prose that says process-local TTL/LRU. State inclusive horizon,
   strict-later reclamation, no live eviction, fixed fail-closed capacity/clock
   behavior, known-replay distinction, digest-only bounded process-local
   single-worker/non-durable/restart reset limitations, and the fact that
   Gateway declares metadata while Local owns admission/storage.
7. Keep `adapter.py`, `identity.py`, Responses orchestration/accounting,
   Objective-163 SSE framing, Codex/tool/call-ID replay, HMAC replay references,
   schemas/migrations, provider credentials, and Local repository byte-for-byte
   unchanged from Gateway base unless an independently demonstrated direct
   contract error requires strategic continuation.
8. Inspect route/catalog/import/seeding paths. Route capabilities are stored and
   materialized as opaque reviewed JSON; do not add a migration or generic
   importer rewrite merely to change fixtures. Prove PostgreSQL round-trip and
   provider factory consume the corrected explicit capability.

## Mandatory tests and negative controls

Use CPU, fake/httpx loopback, and safe disposable PostgreSQL only.

1. Parser accepts and returns exact new replay mode.
2. Parser rejects old `process_local_ttl_lru` and at least one unknown value.
3. Signed parser requires explicit skew and TTL; rejects either missing,
   booleans/coercible types/out-of-bounds values, and TTL below skew; accepts
   explicit 60/60 and another valid explicit configuration such as 60/120.
4. Static mode remains coherent with the new required replay-mode value and
   inert timing defaults; signed-only semantics do not leak authority to it.
5. Registry resolution and factory select `local-coding-v1` server module
   version 2 only for the exact new contract/provider kind; old/unknown mode and
   wrong provider kind fail before construction/network activity.
6. Existing canonical signed-identity fixture SHA-256 remains
   `4fdbc6dd46fcd11819a60a7dd4e8892a82ff64cd8da1e108a9fdb2482c13e1f0`;
   canonical bytes, HMAC, signed headers, nonce grammar, exact body signing,
   opaque derivation, and secret-role separation tests remain green.
7. PostgreSQL route creation/materialization round-trips the exact new mode and
   explicit signed 60/60 values, resolves the Local module/factory, and
   preserves the existing no-reservation/no-ledger identity-failure proof.
8. Complete official-client Responses E2E passes with corrected Local metadata,
   including signed/static, streaming, zero-argument, malformed-stream
   accounting, and ordinary function paths already in that file.
9. Objective-163 Local framer tests pass unchanged except current fixture
   metadata; no SSE limit, typed validator, close, or accounting law changes.
10. Deployment remains exactly `single_worker`; wrong/missing deployment mode
    fails closed.
11. Unit tests for both non-historical verification scripts pass after metadata
    synchronization. Do not execute their protected/live actions.
12. Add an independent literal Objective-164 obligation set and mapping to
    exact test node IDs covering every item above. Require exact set equality,
    safe paths, no anonymous parameter IDs, collect every mapped node with
    `missing=[]`, and directly execute every unique mapped node with zero skips.
    One parameterized sibling is not evidence for another unless each exact
    sibling node is separately named and executed.

Do not manufacture Gateway capacity/clock/horizon algorithm tests. The new
source fixture and exact Local PR #8 are authority for Local internals; Gateway
tests prove only metadata/parser/version/factory/catalog/wire non-regression.

## Verification and cleanup

- Run focused Local contract/module/provider-factory/unit tests, both verifier
  unit files, Objective-163 framer regressions, and relevant module/governance
  tests.
- Create one uniquely named `slaif_oap164_*` PostgreSQL database using only the
  safe `TEST_DATABASE_URL` path. Run the Local module integration test and the
  complete `tests/e2e/test_openai_python_client_responses.py` file with zero
  skips. Reconcile reservation/ledger/key state, drop every exact task-owned
  database, and prove no `slaif_oap164%` database remains.
- Run Ruff format/check for all changed Python, compile/static JSON checks,
  `git diff --check`, old-literal/current-site scans, and a production-diff
  review separated from OAP/report files.
- Push the implementation to the one Objective-164 branch, create the one PR,
  and wait for all ten normal required checks on the exact implementation head.
  Resolve every routine in-scope failure before report publication.
- Do not run the HPC harness, Qwen, a Local service, protected inference,
  Codex live/evidence actions, a real provider, production data, deployment,
  release, or real email.

## Security, privacy, accounting, and non-goals

- Gateway declares and validates route capability/signing metadata; Local alone
  owns nonce admission, horizon retention, replay/capacity/clock outcomes, and
  process-local storage. Do not add Gateway replay storage or error simulation.
- Preserve provider-secret isolation, public/service/signing/derivation secret
  separation, exact-body HMAC, no raw identity/nonce/signature persistence,
  PostgreSQL accounting truth, ordinary strict-bounded reservations, safe
  pre/post-output failure handling, and no default content storage.
- No schema/migration/dependency/config environment/endpoint/client dialect/
  tool authority/pricing/quota/accounting/SSE change is authorized.
- Do not claim multi-worker, restart-persistent, durable, distributed,
  deployment-qualified, production-certified, compliant, or released replay
  protection.

## Documentation and immutable report

Update every current contract named above that states the old replay behavior.
Explicitly record the module-version-2/no-contract-version-bump decision and
the signed numeric metadata meaning. Check `README.md`,
`docs/openai-compatibility.md`, and `docs/accounting.md`; leave them unchanged
when they contain no affected claim and report that specific check.

Publish exactly one immutable report at
`oap/reports/164-a-align-local-replay-contract.md` only after the complete
implementation is pushed and all ten implementation-head checks are successful.
The report must include:

- `RESULT=PASSED` or a precise genuine external authority/safety blocker;
- PR/base/branch, main/Local source pins, every implementation commit, exact
  implementation head, and `Report publication commit: SELF`;
- report-only topology: first parent equals implementation head and the report
  is the sole changed path;
- replay source fixture digest and unchanged signing fixture digest;
- exact source-derived numeric and versioning decisions;
- old/unknown/missing-timing/provider/deployment fail-closed nodes;
- module/factory/catalog/PostgreSQL/E2E/framer/signing/accounting results;
- literal obligation counts, collection `missing=[]`, direct execution, and
  zero skips;
- exact commands/counts, all ten implementation-head GitHub check states,
  production diff review, docs impact, corrected failures, cleanup, and limits;
- explicit no Local/Qwen/protected/provider/deployment/release action; and
- these literal final labels:

  ```text
  REPLAY-MODE-ALIGNED = YES|NO
  OLD-REPLAY-MODE-REJECTED = YES|NO
  SIGNED-TIMING-EXPLICIT = YES|NO
  LOCAL-SERVER-MODULE-VERSION-2 = YES|NO
  IDENTITY-V1-WIRE-UNCHANGED = YES|NO
  POSTGRES-CATALOG-FACTORY-ACCEPTED = YES|NO
  OBJECTIVE-163-FRAMING-REGRESSION-ACCEPTED = YES|NO
  ACCOUNTING-UNCHANGED = YES|NO
  TASK-DATABASES-CLEANED = YES|NO
  PROTECTED-ACCEPTED = NO
  MERGED = NO
  RELEASE-READY = NO
  ```

The report may state report-head checks are newly pending; strategic will wait
for and independently verify them. Do not merge or enable auto-merge. Signal
exact response `OK` only after the report commit is the verified remote PR head
and its topology is correct.
