# OAP report — 152-d asyncpg JSONB correlation fix

## Identity and result

- Objective: 152-d
- Active selector: 152-d
- Active selector SHA-256: cc8920f03795319932e7e75875c49626385af7ae5525b30ce3579defddb50101
- Work-order SHA-256: 614f398467ee6f88e4fc0342067ef9c0c6838c3ae77a8b6d1cf626e6a63c68d3
- Existing PR: #287, amend-only, no merge, no auto-merge
- Starting order commit: 9f582b8fdc961c520b8f9cd7448578689a023d77
- Implementation commit: 69ca59d6f9c5cad9048e04a82ef5a72e23d78ba7
- Branch: oap/152-real-provider-accounting-qualification
- Report publication commit: SELF
- Result: verifier defect fixed; replacement live matrix NOT RUN
- REAL_PROVIDER_CALLED: false

Objective 152-d amends PR #287 only. It addresses the asyncpg JSON/JSONB
representation boundary exposed by the truthful 152-c failure. It does not
rewrite the 152-c report or promote its one successful SQL row to provider
proof.

## Implementation boundary

The verifier's private asyncpg connection now registers explicit text codecs
for PostgreSQL `json` and `jsonb` in `pg_catalog` immediately after connection
and before schema, key, or correlation queries. The paired decoder and encoder
use bounded standard JSON text. The decoder requires strict UTF-8, rejects
duplicate object keys and non-standard numeric constants, rejects arbitrary
values, enforces a 64 KiB JSON-value bound, and returns ordinary Python
structures. Codec setup failure closes the connection and becomes one bounded
failure before any Gateway traffic.

Correlation and privacy validation normalize already-decoded mappings and
asyncpg-like JSON strings through the same strict rules. Metadata must be an
object; malformed, oversized, duplicate-key, list/scalar, boolean, invalid
UTF-8, arbitrary-object, and canary-bearing values fail closed. Cost source and
confidence remain allowlisted. The privacy scan no longer uses `default=str`
for metadata validation and has explicit bounded handling for database scalar
types.

No application, adapter, migration, Compose, policy, accounting, provider, or
Gateway behavior was changed.

## Verification evidence

All commands unset `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
`OPENROUTER_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, and
`RUN_UPSTREAM_TESTS`.

- `git diff --check`: passed.
- Ruff on the verifier and focused verifier tests: passed.
- Verifier unit module: 60 passed.
- Focused Authorization-replacement/adapter/streaming modules: 67 passed.
- Combined focused run: 127 passed.
- Guarded dry run: `result=not_run`, `real_provider_called=false`,
  `http_requests=0`, `sql_queries=0`.
- Synthetic asyncpg-like JSONB strings correlate successfully with expected
  usage and cost labels.
- Synthetic malformed, oversized, duplicate-key, list/scalar, invalid-UTF-8,
  and canary cases fail with bounded verifier errors.
- Synthetic fake asyncpg connection coverage proves both codecs are registered
  before the first query and that codec setup failure closes the connection
  without issuing a query.

These are deterministic tests and guarded dry-run evidence only. No provider
credential was read, no provider or Gateway HTTP request was made, and no SQL
connection was opened during 152-d verification. The complete replacement
eight-flow live matrix remains NOT RUN and requires fresh human authorization.

## Safety and scope

- 152-c remains an immutable failed live report with one attempted flow and
  `correlation_metadata_invalid`; its result is preserved as historical
  failure evidence.
- No live/provider/direct preflight, credential validation, deployment, real
  email, production/shared database, or external authority was used.
- No key, prompt, completion, raw JSON, request ID, credential, URL secret, or
  provider body was printed or committed.
- No release, production-certification, provider-invoice, security,
  compliance, HA, SLA, or support claim follows from this implementation.
