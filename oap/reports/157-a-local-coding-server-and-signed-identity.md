# Objective 157-a — Local Coding server and signed identity

RESULT=FAILED

Repository: `ulfe-lmi/slaif-api-gateway`
Base: `f45bbd6f0eb9dbccbe39f9c9bd785c12218d2459` (`main`)
Branch: `oap/157-local-coding-server-signed-identity`
PR: #294 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/294
PR state: OPEN, non-draft, no auto-merge
Activation head: `7c6e42e3a75a9348ff247bb3c96fc5679e0f2cc9`
Implementation head: `f3bdd0bcccc7e7c6b643e75d3cb30d4931967600`
Report publication commit: SELF

The implementation and all bounded local/conformance evidence are complete,
but the required final CI Unit/lint job is not green. The failure is recorded
below exactly and no acceptance or merge claim is made. No protected, external
provider, Local Coding product, or Qwen traffic was run.

## Topology and scope

The activation commit contains exactly `oap/active` and the exact 157-a order.
The implementation diff from the authorized base contains exactly these 25
paths:

```text
app/slaif_gateway/config.py
app/slaif_gateway/modules/clients/openai_default.py
app/slaif_gateway/modules/servers/local_coding/__init__.py
app/slaif_gateway/modules/servers/local_coding/adapter.py
app/slaif_gateway/modules/servers/local_coding/contract.py
app/slaif_gateway/modules/servers/local_coding/identity.py
app/slaif_gateway/modules/servers/registry.py
app/slaif_gateway/providers/factory.py
app/slaif_gateway/schemas/providers.py
app/slaif_gateway/services/responses_gateway.py
docs/accounting.md
docs/compatibility-matrix.md
docs/configuration.md
docs/module-architecture.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/runbooks/provider-key-rotation.md
docs/security-model.md
tests/e2e/test_openai_python_client_responses.py
tests/fixtures/local_coding/responses_tool_filter_vectors.json
tests/fixtures/local_coding/signed_identity_v1_vectors.json
tests/integration/test_local_coding_server_module_postgres.py
tests/unit/test_local_coding_server_module.py
tests/unit/test_module_architecture.py
tests/unit/test_provider_factory.py
```

The only production paths changed from base are the ten authorized `app/`
paths above. No unauthorized path was staged or committed. No schema,
migration, replay service/repository, streaming validator, Codex 0.149 client
contract, inherited doctrine, Objective-155 path, or Local repository path was
changed.

The report-only commit must have implementation head `f3bdd0b` as its first
parent and change only this report. PR #291, the Local Coding repository/PR,
Qwen, and Objectives 158–160 remain untouched.

## Exact reconstructed blobs

The required production and fixture blobs are present exactly:

| Path | Required/final blob |
| --- | --- |
| `app/slaif_gateway/config.py` | `24f686830357c270a1205236d69833edd70880d5` |
| `app/slaif_gateway/modules/clients/openai_default.py` | `72644850a93eb740324f436702c22afd1c79e369` |
| `app/slaif_gateway/modules/servers/local_coding/__init__.py` | `191c07089aba4af81a30a00461272a6868ba473f` |
| `app/slaif_gateway/modules/servers/local_coding/adapter.py` | `2ffe984bc593656342b45a246ec716387d1849bf` |
| `app/slaif_gateway/modules/servers/local_coding/contract.py` | `af12e3b26641051c0085f72a1f974a788b6ccf6b` |
| `app/slaif_gateway/modules/servers/local_coding/identity.py` | `c2b87416352ee584eec0a29704e68e6ca29395fb` |
| `app/slaif_gateway/modules/servers/registry.py` | `f29b835f7b7e627b5a2a6a06b27c1b222c6be5cc` |
| `app/slaif_gateway/providers/factory.py` | `cb0f5048547393ee7595f31b3b71da1dfb7bcc6b` |
| `app/slaif_gateway/schemas/providers.py` | `81d48f69213324e8ddce4a6c0ae9f30afd758b08` |
| `app/slaif_gateway/services/responses_gateway.py` | `cd9424edf08450e5fb818193133fe5643c4cd33a` |
| `tests/fixtures/local_coding/responses_tool_filter_vectors.json` | `cdd33cb5c52377f80282803f53005074df091fc8` |
| `tests/fixtures/local_coding/signed_identity_v1_vectors.json` | `e1e4c43e10318ff3170859876dc4d8f6f7d5bdb9` |
```

The mixed source selection was preserved: the accepted final contract and
identity grammar came from the reviewed final source, while
`responses_gateway.py` came from the pre-stream/pre-replay 4eb snapshot. No
advanced Codex reasoning, function/message lifecycle, visible reasoning,
ID-less replay, or later qualification behavior was introduced.

## Pair, transport, identity, and accounting evidence

The static registry contains exactly the authorized
`codex-0.149-responses-v1 -> local-coding-v1` pair for the new server module.
The pair is non-authorizing and does not replace endpoint, key, model, route,
capability, pricing, quota, accounting, or identity gates. Generic, OpenAI,
Codex 0.147, hosted, unknown, and wrong-provider/server combinations remain
separately contained.

The Local adapter is Responses-create and Responses-SSE only. It serializes
the canonical body once as deterministic UTF-8 JSON and sends those exact
bytes with `content=...`. It substitutes the provider-row Local service
Bearer and does not forward the public Gateway Bearer, cookies, caller
headers, or arbitrary internal `X-SLAIF-*` headers.

Signed identity derives principal, session, and repository from authenticated
owner/key truth, the corroborated transient Codex session namespace, and the
server-side repository scope using domain-separated HMACs. Values are
unconditional `h`-prefixed full unpadded base64url SHA-256 digests and are
checked against the exact Local grammar before signing. The signature covers
method, path, raw query, exact body, derived fields, timestamp, and nonce.
Service, signing, and derivation secrets are distinct roles. Replay is
process-local TTL/LRU under the single-worker contract. No secret, raw input,
identity, signature, nonce, body, or digest was retained or printed.

The mocked E2E cases proved separate service authentication, signed identity
and session isolation, same-session reuse, different-session isolation,
different-key isolation, finalized strict-bounded reservations, zero pending
state, and no external-tool fee/hold/capability/destination/provider/route
facts. The PostgreSQL pre-admission case proved no reservation or ledger side
effect on identity failure.

## Verification results

Observed focused results:

- affected unit files: **92 passed**, 0 failed, 0 skipped;
- `tests/integration/test_local_coding_server_module_postgres.py`: **1 passed**,
  0 failed, 0 skipped;
- three affected mocked Local-Coding OpenAI-client E2E cases: **3 passed**,
  20 deselected, 0 failed;
- repository Ruff check on all changed Python paths: passed;
- Python compilation on all changed Python paths: passed;
- staged diff check, exact target blobs, fixture canonical/HMAC checks, secret
  separation tests, and privacy assertions: passed;
- actual unchanged Local consumer at head
  `4d3ab2fd97d249710f952dd3d2c28936138cc8fa`: **16/16** matrix rows passed,
  with 16 valid rows, 16 body-tamper rejections, 16 signature-tamper
  rejections, 16 nonce-replay rejections, 16 duplicate-header rejections,
  16 unique opaque identity tuples, both legacy-prefix vectors, and safe
  privacy exclusion.

The exact consumer matrix retained only bounded counts/booleans; it did not
modify the Local checkout or run a Local/Qwen service.

## CI result and stopping condition

On implementation head `f3bdd0bcccc7e7c6b643e75d3cb30d4931967600`, 9 of 10
required checks succeeded. The failing check was `Unit, lint, and migration
head`. Its final result was **3,655 passed, 1 skipped, 2 failed**. Both
failures are in the forbidden, pre-existing
`tests/unit/test_codex_client_modules.py` path and assert the old state in
which Codex 0.149 had no server pair / was denied before policy. Updating that
path would violate the explicit 157-a allowed-path contract, so no such edit
was made. The other nine checks succeeded: Analyze (javascript-typescript),
Analyze Python, Analyze (python), PostgreSQL integration tests, OpenAI-
compatible E2E tests, Playwright browser smoke, Docker Compose smoke,
Documentation hygiene, and CodeQL.

This out-of-scope CI conflict prevents a truthful PASS. No workaround,
verifier bypass, host Codex substitution, or protected request was used.

## Cleanup and documentation

All task-created disposable PostgreSQL databases, task environments, generated
bytecode/cache/metadata, and temporary roots were removed and verified absent.
The Gateway worktree is tracked-clean and ignored-state-clean. The exact Local
005-m checkout remains clean and at its authorized head. No protected or real
provider call occurred, and no credentials or raw request/response values were
printed, persisted, or committed.

Documentation updated: the eight allowed documentation files describe only
the implemented static Local pair, Responses-only transport, service Bearer,
HMAC identity/grammar, secret roles, process-local replay limit, strict
accounting boundary, and mocked/conformance-only status. The permanent root
agentic-client doctrine link is preserved. No advanced stream/replay or live
qualification claim is made.

Limitations: this is a truthful failed 157-a reconstruction report because the
repository’s final Unit/lint check still contains two stale assertions outside
the order’s allowed paths. It is not a merge, protected qualification,
deployment qualification, release, certification, or production-readiness
claim.
