# OAP Report — 164-a

RESULT=PASSED

## Authority and scope

- Order: `oap/orders/164-a-align-local-replay-contract.md` (activated, committed unchanged).
- PR mode: `CREATE_NEW_PR`; single Objective-164 PR.
- PR: #301 `https://github.com/ulfe-lmi/slaif-api-gateway/pull/301` (OPEN, mergeable/CLEAN, no auto-merge, no merge).
- Base: remote `main` at `b818ece39c0f7edcdfca390c1b76b686b4176cc8` (merge tree `925566ff86c395b56d4d1a8688e2a761967e1da6`, app tree `98efa3f4e57f4a98c21a02f9b329151867f3ed8a`), unchanged during execution.
- Branch: `oap/164-local-replay-contract-alignment`.

## Commits and heads

- Implementation commit 1: `01451771810d7f1ed26d484f7842a1eda7090b03`
  (`obj164: align Local Coding replay contract metadata`).
- Implementation commit 2: `64d235caed7f941d45fba70be69893fa70671c9e`
  (`oap: activate 164-a local replay contract alignment`; carries the
  strategic-authored order and `oap/active` unchanged).
- Implementation commit 3 (strategic pre-report correction):
  `47ddf6d89780104fb2a212545363531266c6b36d`
  (`OAP 164-a: name exact Local replay outcomes, version-2 matrix row, and authority pin`).
- Exact implementation head: `47ddf6d89780104fb2a212545363531266c6b36d`.
- Report publication commit: SELF
- Report-only topology (to be verified after push): this report's commit has
  the implementation head as first parent and this report file as the sole
  changed path.

## Source pins (independently re-verified)

Gateway:

- Remote `main` before and after: `b818ece39c0f7edcdfca390c1b76b686b4176cc8`.

Local (`ulfe-lmi/slaif-local-coding`), verified by a fresh read-only clone and
local SHA-256 computation, matching the order exactly:

- Merged main: `efc4dbcd377dd796a670726b16ebc06bd54b6356`
  (merge of Local PR #8, "harden signed-request replay protection").
- Merge tree: `68144646615cf8aec954f737261060f1b1601033`.
- Production implementation: `4e1f07adc5d71c3f17e71b73cb57aec76aa28d9a`.
- Immutable report: `67d895b9666a7b59753c4a373a6d15bc5884e099`, sole path
  `oap/reports/006-a-signed-request-replay-hardening.md`.
- `src/slaif_local_coding/gateway_identity.py` SHA-256
  `8ea6e63920d3a3e4db6d80c1bed7300cacf21e74a7e3d359583dad5694cdd4b5`.
- `src/slaif_local_coding/config.py` SHA-256
  `871c4336068c2e27dad1cae0a5a0f036c4e43e00300b28b2e44d8f4418ee4a6e`.
- Local report SHA-256
  `3df009a5d95fdfda3413e69f2c2293bfca991ce6d7fa2d9bde5824a808ae161b`.
- Handoff:
  `https://github.com/ulfe-lmi/slaif-api-gateway/pull/299#issuecomment-5649192000`
  (read; its Gateway follow-up scope is exactly what this PR implements).

The merged Local `ReplayProtector` source confirms the pinned semantics:
`expires_at = max(now + ttl_seconds, signed_timestamp + clock_skew_seconds)`
(inclusive effective horizon), reclamation only for `expiry < now`
(strictly later), no live-digest eviction at capacity
(`503 signed_identity_replay_capacity_unavailable`), non-finite/backward
clock fail-closed (`503 signed_identity_clock_unavailable`), known replay
distinct (`409 signed_identity_replayed`), digest-only `[0-9a-f]{64}` state.
Local `GatewayIngressConfig` defaults: skew 60, TTL 60, max entries 4096,
nonce 16..128, skew bounds 1..300, TTL bounds 1..86400.

## Fixtures

- New content-free authority fixture
  `tests/fixtures/local_coding/local_replay_authority.json`, file SHA-256
  `da6a9423d4d028e218270329d083550a7c7c552d8877312e5d291b574fc4893d` (literal
  digest asserted in
  `test_local_coding_replay_authority_fixture_pins_exact_source_facts` in
  addition to the exact fact set).
- Unchanged signing fixture
  `tests/fixtures/local_coding/signed_identity_v1_vectors.json` file SHA-256
  `4fdbc6dd46fcd11819a60a7dd4e8892a82ff64cd8da1e108a9fdb2482c13e1f0`
  (literal digest now asserted in
  `test_signed_identity_fixture_matches_exact_canonical_bytes_and_hmac`);
  canonical bytes, HMAC, signed headers, nonce grammar, exact-body signing,
  opaque derivation, and secret-role separation tests remain green.

## Source-derived numeric and versioning decisions

- Replay capability: parser accepts/returns only the source-owned constant
  `LOCAL_CODING_REPLAY_MODE = "process_local_inclusive_horizon_fail_closed"`;
  `process_local_ttl_lru` and every unknown/synonym value are rejected
  (no silent remap).
- Signed identity routes require explicit `clock_skew_seconds` and
  `replay_ttl_seconds` (fail-closed when absent); strict integer/non-bool
  bounds skew 1..300 and TTL 1..86400 retained; `replay_ttl_seconds >=
  clock_skew_seconds` retained; explicit 60/60 accepted (reviewed peer
  default) and another explicit bounded pair (60/120) accepted.
- Dataclass default TTL corrected 120 -> 60 so materialization no longer
  advertises a stale value; static routes permit absent timing values with
  inert 60/60 defaults (signed-only semantics do not leak authority to
  static). Gateway cannot verify the peer's out-of-band configuration;
  documented accordingly.
- `LOCAL_CODING_SERVER_MODULE_VERSION` bumped `"1" -> "2"`; the server
  registry descriptor consumes the exported constant (no duplicate literal).
  Module ID `local-coding-v1`, identity mode `signed_identity_v1`,
  signing/identity key version 1, tool-policy version, client module version
  4, and client/server pairs are unchanged; no `local-coding-v2`
  wire/contract ID was introduced (identity-v1 canonical bytes, headers, and
  transport unchanged).
- No transport header/body field or dynamic probe was added.

## Fail-closed negative nodes (exact, separately executed)

- Retired/unknown replay mode: `retired-ttl-lru`, `truncated-synonym`,
  `unknown-synonym` (parser), `retired-replay-mode`, `unknown-replay-mode`
  (registry, error `local_coding_route_contract_invalid`),
  `retired-replay-mode` (factory, same error, before construction).
- Signed timing: `missing-skew`, `missing-ttl`, `missing-both`, `bool-skew`,
  `bool-ttl`, `coercible-skew`, `coercible-ttl`, `float-ttl`, `skew-zero`,
  `skew-301`, `ttl-zero`, `ttl-86401`, `ttl-below-skew`.
- Provider kind: `wrong-provider-kind`
  (`local_coding_provider_kind_invalid`).
- Deployment: `multi-worker`, `cluster`, `missing`
  (fail-closed before construction; missing rejected by the required-field
  gate, wrong values by the single-worker gate).

## Positive and proof results

- Obligation map: 45 literal obligations, 44 unique mapped nodes (one node
  intentionally shared by two obligations, matching the 163 precedent).
  Collector: `collected=44 missing=[] extra=[]`; all 44 unique nodes executed
  directly: `tests=44 failures=0 errors=0 skipped=0`.
- Focused unit set (local contract/module, provider factory, module
  architecture, 163 SSE framer, both verifier unit files): 287 passed,
  0 failed, 0 skipped.
- Objective-163 framer regressions (adapter bounded-framer close and
  done-marker nodes) pass unchanged; no SSE limit, typed validator, close, or
  accounting law changed.
- Full `tests/unit` suite: 4032 passed, 1 failed, 0 skipped. The single
  failure is `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`,
  a pre-existing local-environment mismatch: the test executes the local
  `codex` binary and requires exactly `codex-cli 0.149.0`, while this
  machine's installed binary reports `codex-cli 0.153.4`. Neither that test
  nor its script is touched by Objective 164; this is not an Objective-164
  product defect and is not counted as a pass for this objective. The
  required focused suites and GitHub CI are the relied-on gates.
- PostgreSQL (one uniquely named task database `slaif_oap164_test_*` via
  `TEST_DATABASE_URL` only): `tests/integration/test_local_coding_server_module_postgres.py`
  2 passed, 0 skipped — the pre-existing no-reservation/no-ledger
  identity-failure proof and the new real route-row
  `ModelRoutesRepository` materialization/reload round-trip that persists and
  reloads the exact new mode plus explicit signed 60/60, parses it, resolves
  the version-2 `local-coding-v1` descriptor, and exercises the provider
  factory into a `LocalCodingAdapter` (construction only; no network).
- Complete official-client Responses E2E file
  (`tests/e2e/test_openai_python_client_responses.py`, 26 tests, task
  database, `ENABLE_EMAIL_DELIVERY=false`): 26 passed, 0 skipped — including
  signed thread namespace, static server module, Codex streaming, zero-argument
  function streaming, and both malformed-stream accounting tests with the
  corrected Local metadata.
- Static: `ruff check` on all changed Python passes; `git diff --check`
  clean; `py_compile` clean; fixture JSON valid. CI has no `ruff format`
  gate (workflow runs `python -m ruff check app tests`); the changed files
  retain their base format state (per-file verified), and the two verifier
  evidence scripts keep their pre-existing long-line style — no
  whole-file reformat was performed to avoid unrelated diff.
- Old-literal scan outside immutable OAP history: `process_local_ttl_lru`
  remains only in explicit negative tests and the fixture's
  `rejected_replay_mode` fact (5 sites, all rejection contexts); no
  current-facing fixture or positive code retains it. "TTL/LRU" prose is
  fully replaced by inclusive-horizon fail-closed statements.

## Production diff review (separate from OAP/report files)

Exactly three production files changed:

- `app/slaif_gateway/modules/servers/local_coding/contract.py`: version
  constant, new replay-mode constant, TTL default 60, parser
  accept/reject of the new mode, signed explicit-timing requirement,
  constant returned in the contract.
- `app/slaif_gateway/modules/servers/registry.py`: descriptor consumes
  `LOCAL_CODING_SERVER_MODULE_VERSION`.
- `app/slaif_gateway/modules/servers/local_coding/__init__.py`: export
  synchronization for `LOCAL_CODING_REPLAY_MODE`.

`adapter.py`, `identity.py`, production `sse_framing.py`, Responses
orchestration/accounting, Codex/tool/call-ID replay, HMAC replay
references, schemas, migrations, provider credentials, and the Local
repository are byte-for-byte unchanged from the Gateway base. Route/
catalog/import/seeding paths were inspected: route capabilities remain
opaque reviewed JSON; no migration or importer rewrite was added; the
PostgreSQL round-trip and factory consume the corrected explicit
capability.

One tightly coupled current fixture site outside the primary list was
changed and is explained here: `tests/unit/test_local_coding_sse_framing.py`
`STATIC_ROUTE_CAPABILITIES` replay-mode value (single line). Mechanically
necessary: the `LocalCodingAdapter` constructor parses the route contract
and fails closed on the retired value, so the two Objective-163 adapter
framer tests would fail at construction without this metadata
synchronization.

## Documentation impact

Updated (current contract statements only): `AGENTIC_CLIENT_INTEGRATION.md`
(section 26: exact reviewed Local outcomes
`503 signed_identity_replay_capacity_unavailable`,
`503 signed_identity_clock_unavailable`, `409 signed_identity_replayed`;
current replay-contract source authority pinned to Local merged main
`efc4dbcd377dd796a670726b16ebc06bd54b6356` with the older
protected-qualification pin `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`
explicitly preserved as historical evidence, not rewritten as a rerun),
`docs/configuration.md`, `docs/module-architecture.md`,
`docs/provider-forwarding-contract.md`, `docs/responses-compatibility.md`,
`docs/security-model.md` (also names the exact Local outcome codes),
`docs/runbooks/provider-key-rotation.md`, `docs/compatibility-matrix.md`
(Local row now explicitly states server module version 2).
Checked and intentionally unchanged: `README.md` (contains no Local replay
statement; top logo/link block untouched), `docs/openai-compatibility.md`
(no affected current Local replay statement), `docs/accounting.md` (no
accounting semantic change; Codex replay statements unaffected).

## Database and environment honesty

- One uniquely named task database was created
  (`slaif_oap164_test_20260913_033456`; an earlier
  `slaif_oap164_task_20260913_032648` was created, then dropped and
  recreated under the `_test_` name because the repository integration
  conftest safety predicate requires `test`/`dev`/`local` in the database
  name). Both were dropped after verification; a final `pg_database` scan
  shows zero `slaif_oap164%` databases.
- To use the existing local PostgreSQL 16 server over TCP (asyncpg), a
  disposable password was set on the local `ubuntu` role via passwordless
  `sudo -u postgres`; this was temporary local test setup only, its value
  was never committed or logged, and at cleanup the role password was reset
  to a fresh unrecorded disposable value. `TEST_DATABASE_URL` pointed only
  at the isolated task database; `DATABASE_URL` was never used for
  destructive setup.
- No HPC harness, no Local service started, no protected inference, no Codex
  live/evidence action, no real provider request, no production data, no
  deployment, no release, no real email.
- Coding-agent model disclosure (human override): the human-authorized
  local `qwen3.8-27b` installation was used as the coding agent for the
  implementation reasoning of this objective. That is the agent's own model
  only, not product traffic. Separately: no Gateway test or verifier
  invoked Qwen product/service inference, no Local service was started,
  and no protected/model qualification traffic occurred.

## GitHub evidence

All ten implementation-head checks on
`47ddf6d89780104fb2a212545363531266c6b36d` (PR #301 head):

| Check | Status |
| --- | --- |
| Unit, lint, and migration head | success |
| PostgreSQL integration tests | success |
| OpenAI-compatible E2E tests | success |
| Playwright browser smoke | success |
| Docker Compose smoke | success |
| Documentation hygiene | success |
| CodeQL (aggregate) | success |
| Analyze (python) | success |
| Analyze (javascript-typescript) | success |
| Analyze Python | success |

Report-head checks are newly pending on the report-only commit; strategic
owns waiting for and independently verifying them, plus merge, remote-main
verification, timing, and post-merge CI. No merge or auto-merge was
performed or enabled.

## Limitations

- The Gateway proves metadata, parser, version, registry, factory,
  catalog, wire, and accounting non-regression only; it does not
  reimplement or test the Local replay algorithm, and no
  multi-worker/restart-persistent/durable/distributed/deployment-qualified/
  production-certified/compliance/release claim is made or implied.
- The broad local unit-suite result is reported as above with its
  pre-existing environmental failure; it is not relied on as an
  Objective-164 gate.
- Local skew/TTL values are operator assertions about a separately
  configured peer; the Gateway cannot verify that out-of-band
  configuration.

## Final labels

```text
REPLAY-MODE-ALIGNED = YES
OLD-REPLAY-MODE-REJECTED = YES
SIGNED-TIMING-EXPLICIT = YES
LOCAL-SERVER-MODULE-VERSION-2 = YES
IDENTITY-V1-WIRE-UNCHANGED = YES
POSTGRES-CATALOG-FACTORY-ACCEPTED = YES
OBJECTIVE-163-FRAMING-REGRESSION-ACCEPTED = YES
ACCOUNTING-UNCHANGED = YES
TASK-DATABASES-CLEANED = YES
PROTECTED-ACCEPTED = NO
MERGED = NO
RELEASE-READY = NO
```
