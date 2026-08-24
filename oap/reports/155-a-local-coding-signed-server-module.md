# OAP Objective 155-a Report — Local Coding signed server module

Report publication commit: SELF

## Immutable execution identity

- Objective: `155-a`
- Active selector SHA-256: `bfdec91f030aff1a9c0bac35fc6c66c4f4ec66148c07645db28a339730ca39f2`
- Work-order SHA-256: `08e8e1671b3bf839437c0276f76df40573da480f040ee24b89d73aad8c9d0f35`
- Base: `main @ 7ffce834915b74809109e8b579d8541cdcfa9df7`
- Activation commit: `45eb9f51c2bb3963deb78021f9c0ee50176366a6`
- Implementation commit: `c48c61a673b250d193e25a36b495e6d7acae10f7`
- Branch: `oap/155-local-coding-signed-server-module`
- PR: #291, `obj155: add the Local Coding signed server module`

The activation commit contains the exact selector and work-order bytes. This
report is the sole later report-only commit for the objective.

## Implementation

The Gateway now has a static `local-coding-v1` server module selected only by
the exact versioned route contract, provider kind `openai_compatible`, and the
reviewed route capabilities. Generic OpenAI/OpenRouter descriptors and pairs
remain unchanged; `openai-default -> local-coding-v1` exists only for ordinary
mocked transport conformance, and Codex 0.149 remains pairless/default-denied.

The module serializes the final Responses request once as deterministic UTF-8
JSON, signs the SHA-256 of those exact bytes, and sends those same bytes with
`httpx` `content=...`. It sets the exact service Bearer from the provider row,
ignores caller-supplied internal/auth/forwarding headers, and constructs the
approved signed headers only inside the module. Streaming and non-streaming
Responses use the same exact-byte transport boundary with no implicit retry or
redirect behavior.

Signed identity v1 derives opaque principal, session, and repository values
from server-side facts using a dedicated derivation secret. Raw owner, key,
email, repository binding, session hints, bearer, and body data are not
forwarded or persisted. Missing or ambiguous signed identity context fails
before reservation. Static mode is explicitly distinct and does not claim
shared governed identity or rehydration.

The route contract enforces the pinned identity, replay, and deployment modes,
safe bounds, and rejects unknown or malformed values. Configuration has
separate versioned derivation and signing secrets. Because the pinned signed
contract has no key ID and replay state is process-local TTL/LRU, the qualified
deployment is one worker/process only; rotation is coordinated drain,
disable, update, restart, and re-enable. No overlapping rotation,
multi-worker replay exclusion, restart-persistent replay protection, live
model cutover, production, or certification claim is made.

Responses accounting remains Gateway-owned: one public request has one
reservation and one terminal ledger outcome; provider usage remains the final
accounting authority; service-auth, signature, timestamp, replay, HTTP, parse,
and stream failures use existing safe release/finalization laws. No exact body
hashes, identity values, signed headers, secrets, or payloads enter durable
metadata, logs, audit, metrics, or reports.

## Cross-repository provenance and conformance

Local Coding PR #7 was read only at immutable green head
`356be8345dd71d6fddf829278651d18e485731d4`. It remains OPEN, non-draft,
MERGEABLE/CLEAN, with its `test` check successful. The coding agent did not
modify or merge that PR, and did not follow a moving branch.

Gateway-owned fixtures retain source provenance for the pinned Local Coding
content:

- signed identity vector source raw fixture SHA-256:
  `92c09c03a40dbdf5e6e08b9e5d7f5c6e2c777e14467845d351f219cbb9a66588`;
- Responses tool-filter vector source raw fixture SHA-256:
  `58ff37d43778895b198f687aa4c54cbe41953809db8af97e7357c5d791c111e6`.

The pinned application was cloned into a private disposable checkout and
exercised against fake loopback Qwen/vLLM transport. Final conformance output:

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
```

The disposable checkout, temporary PostgreSQL/Redis state, server processes,
and logs were cleaned after the run. No real Qwen, provider, external model,
production service, or live credential was used.

## Verification

| Area | Result |
| --- | --- |
| Focused unit/provider/config/route/quota suite | `286 passed in 31.69s` |
| PostgreSQL focused integration | `4 passed`; disposable isolated database; no-side-effect denial and accounting/replay coverage |
| Mocked official OpenAI-client Local Coding E2E | `1 passed`; static route, exact service Bearer/body/model, finalized reservation and ledger |
| Pinned Local Coding fake-Qwen conformance | `RESULT=OK`; non-streaming and streaming, signed headers, service credential separation, exact body bytes |
| Documentation checker | `DOCUMENTATION_CHECK=OK files=79` |
| Documentation contract tests | passed |
| Alembic head | `0024_quota_reservation_accounting_facts (head)` |
| Ruff changed Python and `git diff --check` | pass |
| Final PR #291 GitHub checks | all ten successful: Unit/lint/migration, PostgreSQL integration, OpenAI-compatible E2E, Playwright, Docker Compose, Documentation hygiene, CodeQL, Analyze Python, Analyze python, Analyze javascript-typescript |

The supercomputer sharded harness was not run; this objective used the
required bounded focused suites and deterministic pinned cross-repository
conformance instead. There were no failing shards, slowest-shard results, or
skipped test phases to report. Browser and Docker Compose checks ran in GitHub
CI. No broad local suite, real email, release, deployment, or production
verification was run.

## GitHub and publication audit

At report preparation, PR #291 was OPEN, non-draft, MERGEABLE, CLEAN, and had
no auto-merge request. Its final implementation head was
`c48c61a673b250d193e25a36b495e6d7acae10f7`; the report-only commit must use
that commit as its first parent and change only this report path. The coding
agent does not merge or enable auto-merge.

Safety confirmations: no code was modified after the implementation commit;
no `DATABASE_URL` destructive setup was used; database integration used an
isolated disposable database; no real upstream calls or email were made; and
no secrets were printed, persisted, or committed.
