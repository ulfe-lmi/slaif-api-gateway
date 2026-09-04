# OAP Objective 155-e Report — Codex thread namespace and key-bound session

Report publication commit: SELF

## Immutable execution identity

- Objective: `155-e`
- Active selector: `155-e`
- Active selector SHA-256: `1b54a18096a6df110508fbd872fce9de2171f11e6474e00b74535c4c17aed24a`
- Work-order SHA-256: `157e681a364cbf844908bb3af447d9766858583fdc4d72cccdefb87f53d5ec7a`
- Existing PR: #291, branch `oap/155-local-coding-signed-server-module`
- Prior PR head: `3e8c3505022908a5a107563b3ba0cb9633cf241c`
- Implementation head: `4eb768254fcde0a4108bcabb35f175a74bd07a3f`

The work-order bytes were verified equal to the strategic source before the
implementation commit. The implementation commit contains the unchanged
order and active selector plus only allowed 155-e paths.

## Exact session relationship evidence

The pinned official `codex-cli 0.149.0` capture used one private disposable
installation/workspace and a loopback synthetic Responses server. It made
three requests: session A, explicit `exec resume` for A, and separate session
B under the same installation. The synthetic response completed each request;
no provider call or model inference occurred.

Only safe relationship facts were retained:

- selected source key: `session_id`;
- corroborating alias: `thread_id`;
- both aliases were present, string-typed, canonical UUIDs, equal within each
  request, stable across A1/A2, and different for B;
- installation identity remained constant across A and B and was rejected as
  a session source;
- root-turn, turn, prompt-cache, and input-item identifiers were rejected as
  session sources; per-turn/input-item variance was not used as identity;
- the sanitized fixture records three requests, explicit resume, same-installation
  isolation, fixed synthetic SSE, zero provider calls, and cleanup.

No raw metadata values, prompts, outputs, descriptions, schemas, arguments,
results, IDs, paths, headers, credentials, request/response bodies, hashes of
identity values, or session history are included here. A prior local diagnostic
that printed concrete derived values was terminal-only, was not redirected to
repository files, logs, fixtures, test artifacts, or commits, and is
deliberately excluded from this report.

## Module and Gateway identity contract

`codex-0.149-responses-v1` is module version `3` and is bound to the separate
session-relationship fixture:

- `tests/fixtures/codex/0.149.0/responses-session-relationship-v3.json`
- SHA-256: `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec`
- prior structural fixture provenance: SHA-256
  `baba5403949d44900d8bd3cdef3f7c65bf6abd5109b78bda0b67f3f9787118d1`

The historical structural fixture remains byte-for-byte unchanged at SHA-256
`0a0b62bc7fec7b4da2c504f7db67d260ebe3e2d9fe6be64548c82207a787061d`, and the
v2 structural fixture remains byte-for-byte unchanged at the provenance digest
above.

The module validates equal canonical `session_id`/`thread_id` aliases and
returns exactly one transient internal `identity_hints` entry, `session_id`.
Installation, root-turn, turn, cache, item, and other client metadata are not
identity hints. Missing, malformed, unequal, non-canonical, control-bearing,
URL-like, over-bound, or additional core identity hints fail closed without
echoing values. Request policy drops the complete client metadata object before
provider-body construction.

The Local Coding core now requires authenticated owner and Gateway-key UUID
facts and exactly the canonical session hint. The opaque session derivation is
domain-separated under the new internal v2 derivation and includes owner
principal, authenticated Gateway key, and corroborated client thread. Owner,
Gateway key, session, repository, route, secret, static-mode, and missing/
ambiguous-context boundaries remain isolated and fail closed. The signed v1
wire canonicalization and HMAC header contract are unchanged.

## Signed transport and accounting evidence

The DB-backed official-client E2E passed four requests: two non-stream/SSE
requests for session A and one request for session B through Gateway key one,
then one request using the same owner and same corroborated client session
aliases through Gateway key two.

- A1/A2 opaque sessions matched; B differed; key two differed from key one.
- Nonces and signatures remained request-specific.
- Raw aliases and installation metadata were absent from Local Coding provider
  bodies and headers except for the opaque derived identity fields.
- Gateway key one had three independent finalized reservations/ledger rows;
  Gateway key two had one. Both had zero pending counters.
- Every success used `strict_bounded`, empty external capability/destination
  facts, null external provider/route, fence state `none`, and no external-tool
  fee/hold metadata.
- Provider-returned usage finalized each request.

The PostgreSQL alias-negative tests passed with no reservation or ledger side
effects. Core and module negatives cover missing, malformed, unequal,
installation-only, per-turn-only, and additional/ambiguous identity input.

## Verification ledger

| Check | Result |
| --- | --- |
| Exact 0.149 A1/explicit-resume-A2/B capture and canonical fixture | `PASSED` |
| Historical and v2 fixture byte/digest guards | `PASSED` |
| Exact `verify-live-0149` through registered production normalizer/policy | `PASSED` |
| Focused module, core identity, capture, and privacy unit tests | `PASSED` |
| PostgreSQL integration and no-side-effect negatives | `PASSED` |
| Mocked official-client signed non-stream/SSE E2E, including second key | `PASSED` |
| Ruff, Python syntax compilation, and `git diff --check` | `PASSED` |
| Documentation hygiene | `PASSED`; `DOCUMENTATION_CHECK=OK files=79` |
| Alembic head/schema changes | `PASSED`; unchanged, no migration added |
| Local Coding `005-i`, protected Qwen, composed full-stack acceptance | `NOT RUN`; owned by Local Coding |
| Broad local suite, real provider/model, production cutover, release, merge | `NOT RUN` |

## Cleanup and safety

The exact capture installation `/tmp/slaif-155e.boJfMX`, disposable database
`slaif_gateway_oap_155e_test`, task virtual environment, and task-generated
`uv.lock` were removed or verified absent. No task process or listener remained.
The task-created `uv.lock` was never staged, committed, or reported.

No Local Coding repository or PR was modified. No schema, migration,
dependency, endpoint, route pair, provider adapter, pricing, external-tool,
Compose, deployment, release, or production change was made. No merge or
auto-merge was performed. PR #291 remains open.
