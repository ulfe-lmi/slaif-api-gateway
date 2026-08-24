# OAP Work Order — 152-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/152-real-provider-accounting-qualification`
Base: `main @ 8f2813bf745b90221da33a7cfaf40726c5b1b480`
Title: `obj152: qualify real-provider accounting evidence`

## Objective and reason

Replace the historically synthetic real-provider qualification claims with a
guarded verifier that can correlate every supported live Chat Completions and
Responses request to PostgreSQL truth. This round implements, tests, and
documents the verifier only. It must make no real provider call because fresh
protected credentials and a new bounded human authorization have not yet been
supplied. Keep the PR open for a same-number continuation that performs the
single authorized live qualification.

This is evidence closure for already supported OpenAI and OpenRouter adapters,
not a feature rewrite or endpoint expansion.

## Verified starting state and historical falsification

- Objective 151 merged as PR #286 at
  `8f2813bf745b90221da33a7cfaf40726c5b1b480`. Production appliance wiring and
  a disposable provider-double matrix are independently qualified. No release
  or deployment occurred.
- No Objective 152 PR exists. The only unrelated open PRs are Dependabot #224
  and #250; do not modify or merge them.
- `scripts/verify_real_provider_qualification.py` currently has no database
  input or database client. It cannot query PostgreSQL despite the historical
  report and `docs/real-provider-qualification.md` claiming finalized ledger
  rows and zero pending reservations.
- Its Chat streaming result always emits `request_id=null` and zero usage. It
  only checks `[DONE]`. It has no Responses streaming request at all. The old
  six-call evidence therefore does not independently prove stream accounting,
  request correlation, or all currently supported flow variants.
- Treat Objective 140 artifacts as historical claims, not evidence. Preserve
  them immutably but correct the canonical documentation.
- A previously inherited OpenAI credential was exposed in terminal output.
  It is unusable for this work and must be rotated/revoked. Never enumerate,
  validate, print, source, or call with it. Do not read historical key files.

## Required implementation

### 1. Guarded exact-eight-flow verifier

- Refactor `scripts/verify_real_provider_qualification.py` into a fail-closed
  operator verifier for one invocation covering exactly these eight sequential
  Gateway requests:
  1. OpenAI Chat non-streaming;
  2. OpenAI Chat streaming;
  3. OpenAI Responses non-streaming;
  4. OpenAI Responses streaming;
  5. OpenRouter Chat non-streaming;
  6. OpenRouter Chat streaming;
  7. OpenRouter Responses non-streaming;
  8. OpenRouter Responses streaming.
- Require explicit operator-selected Gateway model identifiers for both
  providers; do not silently use stale historical model names. Keep prompts
  fixed, non-sensitive, minimal, with no hosted/local tools, files, images,
  audio, or external authority. Cap generated output at 32 tokens or less.
- Hard-code a maximum of eight provider-bearing requests, run them strictly
  sequentially, and preserve a configurable minimum gap whose safe default is
  at least 15 seconds. No retry may issue another provider request. Transport,
  HTTP, parse, stream, or database failure stops immediately and reports the
  exact count attempted without retrying.
- Require an explicit live-execution switch and an authorization file outside
  the repository. Validate bounded authorization fields for candidate commit,
  exactly eight maximum requests, both providers, a decimal maximum total cost
  no greater than `0.05 EUR`, and a future expiry. Missing, malformed, broader,
  stale, wrong-commit, symlinked, group/world-readable, or repository-contained
  authorization fails before HTTP traffic.
- Read the Gateway key and PostgreSQL URL only from separate protected files
  outside the repository. Reject symlinks, empty files, unsafe permissions,
  direct secret environment values, argv secret values, and equality between
  the Gateway key and any upstream credential input. Never print secret values,
  prefixes, lengths, hashes, paths, URLs with userinfo, or exception text that
  can contain them.
- It is acceptable for the later live setup to supply provider credentials
  directly to the disposable Gateway through its documented file-backed
  Compose secret inputs. The verifier itself must not load or print provider
  credentials.

### 2. Gateway and disposable-PostgreSQL target refusal

- Require an operator-selected HTTPS Gateway base URL whose path is exactly
  `/v1`, with no userinfo, query, or fragment. Explicitly reject OpenAI,
  OpenRouter, and other known provider-direct hosts. HTTP, a provider URL, or
  an ambiguous base path fails before traffic. Support an explicit CA file for
  disposable local TLS without disabling verification.
- Require every successful HTTP response, including streaming responses, to
  expose one syntactically valid `X-SLAIF-Diagnostic-ID` Gateway ID. Do not use
  caller-controlled `X-Request-ID` as PostgreSQL correlation truth.
- Accept only a PostgreSQL URL from the protected file. Require a loopback host
  and an exact disposable database-name grammar such as
  `slaif_real_provider_qualification_<lowercase-alphanumeric-suffix>`. Reject
  production/staging/shared/default names, non-loopback hosts, URL ambiguity,
  and inherited `DATABASE_URL`/`TEST_DATABASE_URL`.
- On connection, query `current_database()` and require an exact match to the
  validated URL name before any Gateway call. Check the schema is at current
  Alembic head. Never create/drop databases or run migrations in this verifier.

### 3. Real stream and OpenAI-shape validation

- Non-streaming Chat must require HTTP 200, Chat Completion object shape, one
  assistant choice, and valid usage.
- Streaming Chat must capture the Gateway ID from response headers, parse the
  actual SSE stream, require terminal `[DONE]`, reject provider/error events,
  and retain terminal usage from the streamed request when present. A completed
  socket with no `[DONE]` fails.
- Non-streaming Responses must require HTTP 200, a completed Response object,
  output shape, and valid usage.
- Streaming Responses must capture the Gateway ID from initial headers, parse
  actual SSE framing, require exactly one valid terminal
  `response.completed` event with completed response and usage, reject
  `response.failed`, `response.incomplete`, and error events, and reject a
  stream ending without the terminal event.
- Usage parsing must reject booleans, negatives, inconsistent totals, malformed
  objects, and accepted zero-only terminal usage. Do not infer stream success
  from content text or connection close.

### 4. Direct PostgreSQL correlation after every request

- After each response/stream terminal, poll PostgreSQL only for a bounded time
  using that exact `X-SLAIF-Diagnostic-ID`. Require exactly one quota
  reservation and exactly one usage-ledger row with matching relationship.
- Require exact endpoint, selected provider, resolved/requested model,
  streaming flag, HTTP 200/success, terminal reservation `finalized`, terminal
  ledger accounting `finalized`, non-null terminal timestamps, zero released
  state, and non-negative cost/token fields.
- Require authoritative stored token usage to be positive and internally
  consistent. Where provider response usage is available, require exact stored
  input/output/total equality. Record cost-source/confidence honestly: OpenAI
  SLAIF-calculated cost is not provider-invoice truth; provider-reported cost
  may be labeled provider-reported only when the row actually says so.
- After each request require zero pending reservations for that Gateway key and
  zero reserved request/token/cost counters on the key. At the end require
  exactly eight correlated reservations and eight ledger rows for this run and
  no duplicates or uncorrelated rows.
- Scan only the eight correlated rows and their safe JSON/error metadata for
  the fixed prompt marker, expected response marker, and plaintext Gateway key;
  none may be present. Require the key row contains no plaintext Gateway key.
  Do not print raw JSON, errors, IDs, content, or key material.
- Emit one bounded JSON summary with provider, endpoint, streaming, HTTP status,
  terminal shape booleans, token counts, reservation/accounting status,
  cost-source label, and correlation booleans. Emit only
  `gateway_request_id_present=true`, never the ID itself.

### 5. Credential replacement evidence boundary

- Add/retain focused deterministic transport tests proving each OpenAI and
  OpenRouter Chat/Responses streaming/non-streaming adapter replaces the
  Gateway Authorization value with the configured provider credential and does
  not emit both. The live provider cannot echo its received Authorization, so
  documentation and reports must state this evidence composition honestly:
  exact replacement is transport-test evidence; real authenticated provider
  success plus PostgreSQL correlation proves the real adapter path executed.
- Never claim the real provider independently attested to the received header.

### 6. Tests and truthful documentation

- Add a dedicated unit test module covering all pre-traffic refusal gates,
  authorization expiry/commit/count/cost/provider validation, secret-file
  permissions/symlinks/repository paths, base URL and database targeting,
  diagnostic-ID selection, Chat/Responses stream terminal/error/truncation,
  usage validation, direct SQL cardinality/relationship/terminal assertions,
  no-pending/counter checks, metadata canary detection, bounded output, and
  strict no-retry/eight-request accounting.
- Tests may fake HTTP/SQL for deterministic parser/failure coverage. They do not
  qualify a provider and the report must say so.
- Rewrite `docs/real-provider-qualification.md` so Objective 140's six calls are
  explicitly historical and insufficient for current accounting proof. State
  that 152-a made no provider call and that no real-provider qualification is
  current until a later continuation passes all eight flows against disposable
  PostgreSQL.

## Exact allowed paths

```text
scripts/verify_real_provider_qualification.py
tests/unit/test_real_provider_qualification_verifier.py
docs/real-provider-qualification.md
oap/orders/152-a-real-provider-accounting-verifier.md
oap/reports/152-a-real-provider-accounting-verifier.md
oap/active
```

Use the narrowest subset. If a real adapter/accounting defect is discovered,
stop and report it for a continuation; do not change application code under
this verifier-only order.

## Anti-false-positive acceptance

- No real provider call occurs in 152-a. `REAL_PROVIDER_CALLED=true`, live
  credentials, or live evidence in this report fails the round.
- Unit tests and old Objective 140 output cannot satisfy the live gate.
- No result can say OK without eight distinct Gateway IDs internally
  correlated to eight terminal reservation/ledger pairs in the selected
  disposable PostgreSQL database.
- A stream connection closing, `[DONE]` without correlated accounting, a
  `response.completed` event without accounting, or SQL rows selected by time
  window/provider rather than exact Gateway ID fails.
- Printed claims are generated from verified state, not caller-supplied
  evidence fields. Verifier exceptions are reduced to bounded error codes.
- No application behavior, production Compose, provider adapter, migration,
  route policy, or accounting service is changed to make tests pass.
- Explicitly unset inherited `OPENAI_API_KEY`, `OPENAI_UPSTREAM_API_KEY`,
  `OPENROUTER_API_KEY`, `DATABASE_URL`, `TEST_DATABASE_URL`, and
  `RUN_UPSTREAM_TESTS` for all verification. Never read historical key files.
- Every final-report-head GitHub check succeeds. Green CI does not turn this
  implementation-only round into live evidence.

## Required verification

```text
git diff --check
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS .venv/bin/python -m ruff check scripts/verify_real_provider_qualification.py tests/unit/test_real_provider_qualification_verifier.py
env -u OPENAI_API_KEY -u OPENAI_UPSTREAM_API_KEY -u OPENROUTER_API_KEY -u DATABASE_URL -u TEST_DATABASE_URL -u RUN_UPSTREAM_TESTS .venv/bin/python -m pytest -q tests/unit/test_real_provider_qualification_verifier.py <existing focused Authorization-replacement tests>
<guarded no-credential dry run proving failure before HTTP/SQL>
```

Do not run broad local suites. GitHub CI is required on the final report head.

## Boundaries and non-goals

- No real provider call, credential validation, key rotation, production/shared
  database, deployment, release, or external state change in this round.
- No new provider/endpoint/model support, provider adapter rewrite, accounting
  rewrite, retry system, plugin/module SDK, hosted-tool qualification, generic
  adapter abstraction, or facial/module work.
- No enterprise tenancy, SSO/SCIM, MFA, RBAC expansion, formal penetration
  test, certification, compliance, HA, invoice-grade billing, support, or SLA.
- This verifier will support bounded MVP evidence only. It is not a benchmark,
  accuracy evaluation, provider invoice audit, or production certification.

## Publication and response duties

- Create exactly one PR on the named branch. Do not merge or enable auto-merge.
- Publish one immutable
  `oap/reports/152-a-real-provider-accounting-verifier.md` as the sole path in
  a final report-only commit. Mark live provider evidence `NOT RUN` and state
  the exact protected human inputs/authorization still required.
- Verify report SELF topology, PR identity/state, no-live-call evidence, and
  every final check; then write exactly two bytes `OK` to the response FIFO and
  resume the control FIFO.
