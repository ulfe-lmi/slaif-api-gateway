# OAP Work Order — 155-a

PR mode: `CREATE_NEW_PR`
Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
Branch: `oap/155-local-coding-signed-server-module`
Title: `obj155: add the Local Coding signed server module`

## Objective and dependency policy

Implement `local-coding-v1` as a statically registered Gateway server module
with exact-byte Responses transport, service-Bearer replacement, and the
prepared signed-identity-v1 contract. Preserve Gateway core authority for
authentication, client-module selection, route/pair admission, PostgreSQL
quota/accounting, Redis limits, pricing, audit, privacy, and failure handling.

Local Coding PR #7 is currently open rather than merged. Implementation and
deterministic cross-repository conformance are authorized against its immutable
green head `356be8345dd71d6fddf829278651d18e485731d4`; Gateway PR merge is not.
The strategic merge gate remains closed until Local Coding PR #7 is terminal
and its accepted merge commit contains that exact contract head or an explicitly
reviewed successor. Never silently follow a moving branch.

## Verified current state

- Objective 154 merged as PR #290 at
  `7ffce834915b74809109e8b579d8541cdcfa9df7`.
- The Gateway has static client/server registries, qualified module-owned Codex
  0.147 policy, and an exact Codex 0.149 structural client module that is
  pairless/default-denied. Its exact capture observes only inert `web_search`
  as an adapter-managed candidate.
- No Objective 155 branch or PR exists. Unrelated Gateway PRs #224/#250 must
  not be modified.
- Local Coding PR #7 is open, non-draft, mergeable, and green at exact head
  `356be8345dd71d6fddf829278651d18e485731d4`.
- At that pinned head Local Coding implements:
  - `service_bearer_static_identity` and
    `service_bearer_signed_identity_v1` ingress modes;
  - service credential validation before body processing;
  - exact signed method/path/raw-query/body/principal/session/repository/route/
    timestamp/nonce canonical HMAC bytes;
  - bounded timestamp and process-local nonce replay protection;
  - `responses-tool-policy-v1`, which removes exact `web_search` and
    `tool_search` declarations before Qwen and rejects unsafe choices;
  - request-scoped identity propagation to cache/rehydration; and
  - content-free synthetic fixtures under `tests/fixtures/gateway/`.
- Gateway generic providers currently send one configured backend Bearer and
  serialize mappings with `httpx(json=...)`; they emit no trusted identity and
  do not control exact signed bytes.
- Signed-identity v1 contains no signing-key ID. Local Coding replay state is
  process-local TTL/LRU. Therefore this objective must not claim seamless
  overlapping key rotation, multi-worker replay exclusion, or restart-persistent
  replay protection.

## Required implementation

### 1. Static Local Coding server contract

- Add one immutable server module ID/version `local-coding-v1` under
  `app/slaif_gateway/modules/servers/local_coding/` and the static server
  registry. No new arbitrary provider kind, dotted import, dynamic plugin,
  entry point, or module SDK.
- Select the module only when provider kind is `openai_compatible` and the
  resolved route carries an exact versioned Local Coding contract object.
  Provider slug/display name alone cannot select it.
- Define a strict route capability object containing only reviewed fields such
  as contract version, Local Coding route name, Responses tool-policy version,
  identity mode, replay/deployment mode, and optional safe limits. Unknown,
  partial, wrong-version, conflicting, or malformed values fail before provider
  construction and before reservation where current sequencing permits.
- Register `openai-default` → `local-coding-v1` only for ordinary mocked
  transport conformance. Do not add the Codex 0.149 pair; Objective 156 owns
  that authorization after identity/accounting review.
- Existing OpenAI/OpenRouter/generic/facial descriptors and pairings remain
  unchanged.

### 2. Exact body-byte transport

- Build the canonical upstream Responses mapping only after current client,
  policy, model rewrite, route, image/file boundary, and output-limit handling.
- Serialize it once using a documented deterministic UTF-8 JSON encoding.
  Sign the SHA-256 of those exact bytes and send the same bytes via
  `httpx` `content=...` for non-streaming and streaming requests. Never sign one
  serialization and send another through `json=...`.
- Set exact `Content-Type: application/json` and the existing expected Accept
  value. Disable redirects and preserve bounded timeout/no-implicit-retry
  behavior from the resolved route.
- Do not add exact-byte fields to durable request/ledger/audit metadata and do
  not log body bytes or hashes.

### 3. Credential and header separation

- Continue using the provider configuration's `api_key_env_var` value as the
  adapter service Bearer. It is never the public Gateway bearer and never
  reaches Qwen as the Qwen credential.
- Add separate versioned secret inputs for opaque identity derivation and Local
  Coding HMAC signing. Never reuse the Gateway bearer HMAC secret, service
  Bearer, provider/Qwen credential, admin secret, or one-time-secret key.
- Signed internal headers bypass the ordinary provider-extra-header allowlist
  only inside the exact Local Coding server module after core route selection.
  Do not globally add `X-SLAIF-*` to provider header allowlists.
- Strip/ignore all caller-supplied `X-SLAIF-*`, forwarding, cookie, session,
  internal, and Authorization values. The module constructs one exact service
  Authorization value and the reviewed signed headers itself.
- Never expose service/signing/derivation secrets or signed header values in
  responses, logs, errors, diagnostics, metrics, audits, ledger metadata, or
  reports.

### 4. Trusted identity derivation

- Principal: domain-separated opaque HMAC over authenticated Gateway owner
  truth, using the dedicated derivation secret/version. Never send raw owner,
  key UUID, public key ID, email, organization/team/project labels, or bearer.
- Session: derive an opaque HMAC from principal plus one exact bounded client-
  module session/thread hint. The hint is a namespace discriminator, not proof
  of external identity. Missing/ambiguous/malformed session context fails signed
  mode.
- Repository: derive from an explicit server-side key/profile Local Coding
  repository-scope binding plus the principal. Do not parse or trust arbitrary
  workspace paths/URLs from client metadata as repository ownership. Missing
  binding fails signed mode.
- Route: use the exact server-side resolved Local Coding route contract name,
  never caller input or public model alone.
- Hints and raw binding values remain transient and are never persisted/logged/
  audited/exported/forwarded. Only derived opaque values reach Local Coding.
- Static/no-rehydration degradation may be supported explicitly for ordinary
  single-user appliance requests, but it must be a distinct route mode and
  cannot claim shared governed identity or cross-turn rehydration.

### 5. Signed identity v1

- Copy the content-free signed-identity fixture from exact Local Coding commit
  into a Gateway-owned fixture with source repository/commit/digest metadata.
  Verify byte-identical semantic facts and expected HMAC.
- Canonical bytes are exact newline-separated UTF-8, no trailing newline:

  ```text
  slaif-local-coding-identity-v1
  METHOD
  PATH
  sha256(raw_query_bytes)
  sha256(exact_body_bytes)
  principal
  session
  repository
  route
  timestamp
  nonce
  ```

- Use POST, exact `/v1/responses`, empty raw query for current generation calls,
  canonical decimal Unix seconds, bounded cryptographically random unpadded
  base64url/hex-compatible nonce, and `v1=<lowercase HMAC-SHA256>` signature.
- Enforce local bounds matching the pinned Local Coding contract before send.
- Treat signature/auth/replay/timestamp failures as provider failures under
  existing safe accounting release/finalization law; never expose upstream
  identity/error content.

### 6. Rotation and replay limitations

- Gateway configuration must version derivation/signing keys and clearly select
  one active signing version. Because signed-identity v1 carries no key ID and
  pinned Local Coding accepts one signing secret, document and test only a
  coordinated drain/disable/update/restart/re-enable rotation procedure. Do not
  claim overlap or zero-downtime rotation.
- Signed mode is qualified only for one Local Coding worker/process at this
  stage. Multi-worker or restart-persistent replay exclusion requires shared
  replay state in a future coordinated contract; fail configuration/readiness
  or state the exact single-worker requirement rather than claiming broader
  protection.
- Gateway nonce generation must be unique and tested, but it does not replace
  Local Coding replay verification.

### 7. Accounting and failure law

- One public request remains one Gateway reservation and one terminal ledger
  outcome. Local Coding compiler/governance calls are internal capacity and do
  not create Gateway requests/reservations.
- Provider usage returned through Local Coding remains authoritative for final
  Gateway token accounting. Transformation may change actual usage; admission
  estimates remain conservative only.
- Service auth/signature/timestamp/replay/HTTP/parse/stream failure must release
  or finalize according to existing provider failure/streaming laws, leave no
  pending reservation, and store only bounded safe diagnostics.
- No hosted-tool fence/hold path is used in Objective 155. Codex 0.149 remains
  unpaired, and the default client conformance requests contain no hosted or
  adapter-managed declarations.

### 8. Cross-repository deterministic conformance

- Fetch/read only exact Local Coding commit
  `356be8345dd71d6fddf829278651d18e485731d4` into a private disposable checkout
  or via exact content APIs. Do not follow branch HEAD after activation.
- Run the Gateway server module against the pinned Local Coding app with fake
  Qwen/vLLM or its exact conformance harness: non-streaming and streaming
  Responses, service credential separation, exact signed vector, tamper/
  replay/timestamp negatives, body-byte equality, safe response usage and
  errors, no content/secret persistence, and cleanup.
- No real Qwen, provider, external model, production service, or cutover.
- If the pinned Local Coding implementation cannot satisfy a required contract,
  report the exact cross-repository defect; do not weaken Gateway checks.

## Operator and documentation surface

- Add settings/configuration documentation for separate service, derivation and
  signing secret environment/file inputs, identity modes, route contract,
  single-worker replay limitation, and coordinated rotation.
- Provider/route admin and CLI surfaces may display/select only finite reviewed
  Local Coding contract values and safe module/version/readiness facts. They
  never accept secret values, raw identity, dynamic module IDs, or arbitrary
  signed headers.
- Update module architecture, provider forwarding, Responses, security,
  accounting, compatibility and configuration docs. State that Local Coding is
  deterministic/mock-conformant only, Codex 0.149 remains unpaired, and no live
  model/cutover/production claim exists.

## Candidate paths

```text
app/slaif_gateway/modules/contracts.py
app/slaif_gateway/modules/servers/**
app/slaif_gateway/modules/clients/codex_0149.py
app/slaif_gateway/modules/servers/registry.py
app/slaif_gateway/providers/factory.py
app/slaif_gateway/providers/headers.py
app/slaif_gateway/schemas/providers.py
app/slaif_gateway/schemas/policy.py
app/slaif_gateway/config.py
app/slaif_gateway/services/responses_gateway.py
app/slaif_gateway/services/model_route_service.py
app/slaif_gateway/services/key_service.py
app/slaif_gateway/services/key_template_service.py
app/slaif_gateway/api/admin.py
app/slaif_gateway/cli/providers.py
app/slaif_gateway/cli/routes.py
app/slaif_gateway/web/templates/providers/**
app/slaif_gateway/web/templates/routes/**
tests/fixtures/local_coding/**
tests/unit/test_local_coding_server_module.py
tests/unit/test_module_architecture.py
tests/unit/test_provider_factory.py
tests/unit/test_provider_headers.py
tests/unit/test_responses_route_capabilities.py
tests/unit/test_v1_responses_quota.py
tests/integration/test_local_coding_server_module_postgres.py
tests/e2e/test_openai_python_client_responses.py
docs/module-architecture.md
docs/configuration.md
docs/provider-forwarding-contract.md
docs/responses-compatibility.md
docs/security-model.md
docs/accounting.md
docs/compatibility-matrix.md
docs/runbooks/provider-key-rotation.md
oap/orders/155-a-local-coding-signed-server-module.md
oap/reports/155-a-local-coding-signed-server-module.md
oap/active
```

Use the narrowest actual subset and current equivalent tests. No migration is
authorized unless implementation proves durable schema is unavoidable and
stops for strategic review first; prefer existing versioned JSON policy/config.
No Compose or release file change is authorized in 155-a.

## Required verification

- Exact cross-repository fixture provenance/digest and vector equality.
- Unit positive/negative identity derivation, canonical bytes, signing, header
  isolation, exact body send, URL/route capability, pair and config tests.
- Mocked adapter non-stream/stream/error/timeout/auth/signature/replay tests.
- PostgreSQL reservation/finalization/failure/no-pending/privacy tests with a
  disposable DB; skipped DB evidence is not a pass.
- Official-client mocked default Responses E2E through the Local Coding server
  module; no Codex 0.149 pair/E2E yet.
- Pinned Local Coding app/fake-Qwen deterministic cross-repo conformance and
  exact cleanup.
- Ruff changed Python, `git diff --check`, docs checker/tests, unchanged Alembic
  head, final GitHub CI/CodeQL.
- No broad local suite, real model/provider, Qwen, OpenCode, production Compose,
  email, deployment, or live credential.

## Anti-false-positive acceptance

- A generic openai-compatible adapter with extra headers is not a Local Coding
  module.
- Global `X-SLAIF-*` allowlisting, client-supplied signed identity, or signing a
  separately serialized body fails.
- Reusing any existing secret across service/derivation/signing/public/Qwen
  roles fails.
- Fabricating repository/session from request ID, IP, model, route alone, or raw
  public key fails.
- Claiming multi-worker/restart replay protection or overlapping key rotation
  under v1 fails.
- Adding a Codex 0.149 pair or hosted-tool path fails.
- Mock-only Gateway tests without pinned Local Coding conformance fail.
- Green CI cannot satisfy cross-repository/body/signature/accounting evidence.

## Merge gate and publication

- Create exactly one non-stacked Gateway PR; coding agent never merges or
  enables auto-merge.
- Commit this order/selector unchanged and publish one immutable
  `oap/reports/155-a-local-coding-signed-server-module.md` report-only commit.
- Record exact pinned Local Coding commit, fixture digests, implementation head,
  route/identity modes, secrets/rotation/replay limits, focused/DB/E2E/cross-
  repo evidence, cleanup, docs, final checks and limitations.
- The strategic model must not merge the Gateway PR while Local Coding PR #7 is
  open. At merge review, require an accepted Local Coding merge commit that
  contains pinned head `356be834...` or activate a same-PR Gateway continuation
  for a reviewed successor contract.
- After report publication send exact `OK` to response FIFO.
