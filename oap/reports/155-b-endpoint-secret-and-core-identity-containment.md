# OAP Objective 155-b Report — Local Coding endpoint and identity containment

Report publication commit: SELF

## Immutable execution identity

- Objective: `155-b`
- Active selector SHA-256: `8fa9b6d8a9e876e8bfc88c65f347b3064b2306a68b2a798528e2c4a88834e5ff`
- Work-order SHA-256: `c0e0e6d23f6f0b17aea87ab508e9c45a1147323c7f5a9eef963acbca4f2e0b3b`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- 155-b activation commit: `992bd2b`
- Implementation commit: `eac9c63`
- Branch: `oap/155-local-coding-signed-server-module`
- PR: #291, `obj155: add the Local Coding signed server module`

The activation commit contains the exact selector and work-order bytes. This
report is the sole later report-only commit for 155-b; the earlier 155-a report
is unchanged.

## Endpoint containment

`LocalCodingAdapter` now inherits directly from `ProviderAdapter` and owns its
own exact-byte Responses transport and response/SSE parsing helpers. It no
longer inherits any OpenAI adapter endpoint implementation or ordinary
`_post_json`/`_stream_sse` helper.

The supported transport matrix is exactly:

| Operation | Result |
| --- | --- |
| `forward_response` with `/v1/responses` or `responses` | Supported; exact deterministic UTF-8 bytes, service Bearer, and signed identity when the route requires it |
| `stream_response` with `/v1/responses` or `responses` | Supported; exact deterministic UTF-8 bytes and typed SSE parsing |
| Chat Completions | Rejected with `unsupported_provider_endpoint` before HTTP |
| Responses input-token count and compact | Rejected before HTTP |
| Stored-response retrieve/delete/input-items | Rejected before HTTP |
| Conversations and Conversation items | Rejected before HTTP |
| Audio speech/transcription/translation | Rejected before HTTP |
| Embeddings and Realtime client secrets | Rejected before HTTP |
| Every other current `ProviderAdapter` operation | Rejected before HTTP |

The exhaustive operation test matrix proves rejected operations make zero
transport calls. The architecture guard forbids OpenAI adapter inheritance and
direct ordinary OpenAI transport helpers in the Local Coding package.

## Secret-role containment

Local Coding service credentials, signing secrets, and derivation secrets are
validated as visible ASCII values with the reviewed 32–4096-byte bound. During
adapter construction, the dynamic provider-row service Bearer is compared in
constant time against active signing and derivation secrets and against known
Gateway/admin/one-time/provider secrets. Equality fails with only the bounded
`local_coding_secret_roles_not_separate` error code; secret values are never
included in the error or diagnostics.

The secret matrix covers service=signing, service=derivation,
signing=derivation, known core-secret equality, malformed service values, and
all-distinct static/signed construction. Static mode does not require unused
identity secrets, but configured optional secrets are still checked.

## Core identity boundary

The core `_build_local_coding_server_context` boundary now fails closed for
malformed Local Coding route contracts and provider selection errors before
reservation. Signed derivation requires:

- authenticated `uuid.UUID` owner truth;
- exactly one bounded transient client session/thread hint;
- a server-side `responses_policy.local_coding_repository_scope` binding;
- the exact resolved Local Coding route contract; and
- the dedicated versioned derivation secret.

The returned context contains only `identity_mode`, opaque HMAC-derived
`principal`, `session`, `repository`, and the resolved `route`. Tests prove
same-input stability, isolation across owner/session/repository/route changes,
absence of raw values, missing/ambiguous session rejection, missing repository
rejection, missing-secret rejection, malformed-route rejection, non-Local
Coding `None` behavior, and static-mode behavior without identity inputs.

This is a core boundary proof plus adapter/pinned-application conformance. It
is not a Codex-composed E2E qualification, and Codex 0.149 remains
pairless/default-denied.

## Pinned dependency and conformance

Local Coding PR #7 remains an external read-only dependency at immutable head
`356be8345dd71d6fddf829278651d18e485731d4`. It remained OPEN, non-draft,
MERGEABLE/CLEAN, and green at its `test` check. The coding agent did not
modify or merge it.

The final pinned run used a disposable checkout at that exact commit, real
loopback HTTP servers for the pinned Local Coding app and fake Qwen endpoint,
and synthetic credentials only. Final output:

```text
RESULT=OK
PINNED_LOCAL_CODING_HEAD=356be8345dd71d6fddf829278651d18e485731d4
QWEN_REQUESTS=2
NONSTREAM_STATUS=200
STREAM_CHUNKS=3
SERVICE_BEARER_SEPARATED=true
SIGNED_HEADERS_VERIFIED=true
EXACT_BODY_LOOPBACK=true
QWEN_REAL_PROVIDER_CALLED=false
PINNED_CHECKOUT_CLEANUP=OK
```

The pinned checkout and its temporary files were removed after the successful
run. An earlier ASGI-only streaming attempt exposed a test-transport
`StreamConsumed` artifact and was not counted as evidence; the final real
loopback run above is the accepted conformance result.

## Verification

| Area | Result |
| --- | --- |
| Final focused unit/config/factory/architecture/route/quota/docs suite | `312 passed in 31.11s` |
| PostgreSQL containment proof | `1 passed in 3.61s`; isolated `slaif_oap_155b_test` database; reservation and ledger counts unchanged on identity failure |
| Mocked official OpenAI-client Local Coding E2E | `1 passed in 7.33s`; finalized reservation and usage ledger, service credential replacement, static route |
| Pinned Local Coding fake-Qwen conformance | `RESULT=OK`; exact signed non-stream/stream transport and cleanup as above |
| Documentation checker | `DOCUMENTATION_CHECK=OK files=79` |
| Ruff changed Python and `git diff --check` | pass |
| Alembic head | unchanged at `0024_quota_reservation_accounting_facts (head)` |
| Final PR #291 GitHub checks on `eac9c63` | all ten successful: Unit/lint/migration, PostgreSQL integration, OpenAI-compatible E2E, Playwright, Docker Compose, Documentation hygiene, CodeQL, Analyze Python, Analyze python, Analyze javascript-typescript |

No broad local suite, real provider/Qwen, Codex pair, OpenCode, production
Compose, email, deployment, release, live credential, or certification run
was performed. No production, cutover, multi-worker replay, restart-persistent
replay, overlapping rotation, or live-model claim follows.

## GitHub and publication audit

Before report publication, PR #291 was OPEN, non-draft, MERGEABLE, CLEAN, with
no auto-merge request and all ten required checks successful. The report-only
commit must use implementation commit `eac9c63` as its first parent and change
only this report path. The coding agent does not merge or enable auto-merge.

Safety confirmations: no code changes remain outside the implementation and
this report, no `DATABASE_URL` destructive setup was used, the PostgreSQL proof
used an isolated disposable test database, no real upstream calls or email were
made, and no secrets were printed, persisted, or committed.
