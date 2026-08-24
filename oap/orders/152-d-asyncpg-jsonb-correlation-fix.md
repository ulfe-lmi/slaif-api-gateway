# OAP Work Order — 152-d

PR mode: `AMEND_EXISTING_PR`
PR: `#287`
Branch: `oap/152-real-provider-accounting-qualification`
Base: `main @ 8f2813bf745b90221da33a7cfaf40726c5b1b480`
Current remote head: `cda0a5f81bfc701f2cdca07f7d477ec32ce1c273`
Title remains: `obj152: qualify real-provider accounting evidence`

## Objective and reason

Fix only the verifier's asyncpg JSON/JSONB decoding boundary exposed by the
truthful 152-c live failure. Add deterministic string-codec coverage and keep
live qualification NOT RUN in this round. Do not call either provider or alter
Gateway/accounting behavior.

## Verified starting state and failed-live evidence

- PR #287 remains open, clean, mergeable, and has no auto-merge. Its report-only
  head `cda0a5f81bfc701f2cdca07f7d477ec32ce1c273` has sole parent/frozen live
  candidate `ea8b98fb104f44c1138a025ad5c23c7c30690a52`; all ten checks passed.
- 152-c's production-Compose setup had two enabled providers with retries zero,
  four exact routes/pricing rows, and a fresh key. The actual live attempt made
  exactly one OpenAI Chat non-streaming Gateway request, then stopped with
  `correlation_metadata_invalid`; no retry or second flow occurred.
- Direct bounded PostgreSQL evidence showed the same request finalized HTTP 200
  and successful, 36 total tokens, actual cost `0.000005800 EUR`, estimated cost
  `0.000012900 EUR`, cost source/confidence both `slaif_calculated`, zero pending
  reservations, and zero reserved counters. Privacy and exact cleanup passed.
- The verifier uses asyncpg directly. Its default JSONB representation was text,
  while `_metadata_cost_labels()` required a `Mapping`. The row contained valid
  bounded cost metadata; the verifier rejected its representation before
  correlated completion. Treat this as a verifier defect, not a Gateway rewrite.
- The previous runtime, credentials, relay, containers, networks, volumes,
  ports, and scratch files are gone. Never read provider credential files in
  this implementation-only round.

## Required implementation

### 1. Explicit asyncpg JSON codecs

- Immediately after a new asyncpg connection and before schema/key/correlation
  queries, register explicit codecs for PostgreSQL `json` and `jsonb` in
  `pg_catalog`, using standard JSON encoding and a strict decoder.
- The decoder must require valid UTF-8 JSON, reject duplicate object keys,
  reject excessive input (maximum 64 KiB per safe metadata value), and return
  ordinary Python structures. Codec/setup failure must close the connection and
  return one bounded verifier error before HTTP traffic.
- Do not globally change application database behavior; this applies only to
  the verifier's private asyncpg connection.

### 2. Defensive metadata normalization

- Add a small verifier-only normalizer used by cost-label and privacy checks.
  It may accept an already-decoded mapping or a bounded JSON string and must
  produce a mapping. Reject malformed JSON, arrays/scalars, duplicate keys,
  booleans, oversized strings, or arbitrary objects with bounded error codes.
- Normalize both `response_metadata` and `usage_raw` before validation/privacy
  scanning. Preserve the exact allowlisted cost source/confidence checks.
- Never emit decoded metadata, parse text, exception text, keys, markers, IDs,
  or provider content.

### 3. Focused regression evidence

- Add unit tests reproducing the exact live boundary with asyncpg-like JSONB
  strings for `response_metadata` and `usage_raw`; valid cost metadata must
  correlate successfully with expected token/cost facts.
- Add negative tests for malformed, oversized, duplicate-key, list/scalar, and
  canary-bearing JSON strings.
- Add a fake asyncpg-connection test proving both codecs are registered before
  the first database query and codec failure closes the connection/fails before
  HTTP.
- Preserve all 152-a/152-b tests, exact-run isolation, bounded output, and the
  67 focused Authorization-replacement/adapter tests.
- Update canonical documentation with the exact 152-c failed result and 152-d
  decoder fix boundary. State that no live evidence was run in 152-d and a fresh
  human authorization is needed for a complete replacement eight-flow matrix.

## Exact allowed paths

```text
scripts/verify_real_provider_qualification.py
tests/unit/test_real_provider_qualification_verifier.py
docs/real-provider-qualification.md
oap/orders/152-d-asyncpg-jsonb-correlation-fix.md
oap/reports/152-d-asyncpg-jsonb-correlation-fix.md
oap/active
```

Use the narrowest subset. No application, adapter, migration, Compose, policy,
or accounting code may change.

## Anti-false-positive acceptance

- No provider credential is read and no HTTP/SQL connection is made during
  152-d verification. Synthetic tests are not live qualification.
- A test using an already-decoded dict alone is insufficient; asyncpg-like JSONB
  text must pass/fail the real normalizer path.
- Silently accepting duplicate keys, arbitrary JSON values, unbounded strings,
  or `default=str` as metadata validation fails the objective.
- Cost labels remain allowlisted and privacy markers remain rejected after
  decoding.
- 152-c remains an immutable failed report. Do not rewrite it or claim its one
  successful SQL row completes provider proof.
- Report status: verifier defect fixed, replacement live matrix NOT RUN.
- Every command unsets `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
  `OPENROUTER_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, and
  `RUN_UPSTREAM_TESTS`; historical key files are not touched.
- All final report-head checks must pass.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS .venv/bin/python -m ruff check scripts/verify_real_provider_qualification.py tests/unit/test_real_provider_qualification_verifier.py
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS .venv/bin/python -m pytest -q tests/unit/test_real_provider_qualification_verifier.py <same focused Authorization-replacement tests>
<guarded dry run proving zero HTTP/SQL>
```

Do not run broad local suites. GitHub CI is required on the final report head.

## Boundaries and non-goals

- No live/provider/direct preflight, credential validation, deployment,
  production/shared database, real email, or external state change.
- No endpoint/provider feature, retry behavior, accounting rewrite, generic
  abstraction, module/facial, hosted tool, or SDK work.
- No enterprise, certification, compliance, penetration-test, HA, invoice,
  support, or SLA work.

## Publication and response duties

- Amend only PR #287; never merge or enable auto-merge.
- Publish one immutable `oap/reports/152-d-asyncpg-jsonb-correlation-fix.md` as
  the sole path in the final report-only commit, with live evidence NOT RUN.
- Verify report topology, PR/check state, and no-live-call evidence; then write
  exact `OK` to the response FIFO and resume control.
