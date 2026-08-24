# OAP report — 152-b verifier run isolation and bounded output

## Identity and result

- Objective: 152-b
- Active selector: 152-b
- Active selector SHA-256: 9ef1d3fa08daf804556fc45c6036b716a0f2658425fa0135bbbeb76f11b92d1f
- Work-order SHA-256: 6b121a54f085c6fa791e96d0c4b36cebc224032bc097ec728d8fddc6f2fac8b3
- Existing PR: #287, open, base main, no merge, no auto-merge
- Starting remote/report head: 346cdc13bcc1eb42035fb1d6a3e82c137651f4a4
- Implementation commit: 2cbc563ddfc87977324de68aac55a9c1154792fb
- Branch: oap/152-real-provider-accounting-qualification
- Report publication commit: SELF
- Result: implementation-hardened round complete; live qualification NOT RUN
- REAL_PROVIDER_CALLED: false

Objective 152-b amended PR #287 only. No real provider call, Gateway
request, PostgreSQL connection, protected credential read, deployment,
migration, or production/shared database operation occurred.

## Hardened implementation

The verifier now requires an explicit canonical Gateway-key UUID and performs
a pre-traffic PostgreSQL baseline check for exactly one active, unexpired,
unrevoked, unfenced key with zero used/reserved request, token, and cost
counters and zero total quota-reservation and usage-ledger history. The
complete serialized key row is scanned for the plaintext Gateway key.
Protected paths must be absolute, mode-protected, outside the repository, and
must not resolve differently from their normalized absolute spelling, closing
parent-symlink bypasses.

After every ordinal flow, all reservation and ledger request IDs for the
selected key are read and must equal only the verifier's complete seen-ID set
for that ordinal. The final check repeats the all-row set/cardinality
requirement for eight rows, zero pending reservations, and zero reserved
counters; it does not filter by the eight IDs to hide old or concurrent rows.

Successful output is bounded to fixed provider/endpoint/streaming facts, the
validated operator-selected model, exact response and stored input/output/
total token integers, terminal/accounting facts, and the allowlisted
cost-source/confidence vocabulary. Failed output distinguishes
gateway_requests_attempted from correlated_completed_count and emits
real_provider_call_proven only when a valid terminal has exact PostgreSQL
correlation. A failed first Gateway attempt therefore proves neither a
provider call nor a completed flow.

## Verification evidence

All commands unset OPENAI_API_KEY, OPENAI_UPSTREAM_API_KEY, OPENROUTER_API_KEY,
DATABASE_URL, TEST_DATABASE_URL, and RUN_UPSTREAM_TESTS.

- git diff --check: passed.
- Ruff on the verifier and dedicated test module: passed.
- Dedicated verifier tests: 49 passed.
- Existing focused Authorization-replacement/adapter tests:
  test_provider_headers.py, test_openai_provider_adapter.py,
  test_openrouter_provider_adapter.py, test_openai_provider_streaming.py,
  and test_openrouter_provider_streaming.py: 67 passed.
- Guarded dry run: result=not_run, real_provider_called=false,
  http_requests=0, sql_queries=0.
- Guarded live-shaped missing-file run: result=fail,
  attempted_requests=0, gateway_requests_attempted=0,
  correlated_completed_count=0, real_provider_call_proven=false.
- Deterministic failure-output test: attempted=1, correlated=0,
  real_provider_call_proven=false.

The deterministic tests use synthetic HTTP/SQL state only and do not qualify
a provider.

## GitHub evidence

All ten required checks on implementation head
2cbc563ddfc87977324de68aac55a9c1154792fb succeeded:

- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL
- Docker Compose smoke
- Documentation hygiene
- OpenAI-compatible E2E tests
- Playwright browser smoke
- PostgreSQL integration tests
- Unit, lint, and migration head

The report-only publication commit changes only this report file and has
2cbc563ddfc87977324de68aac55a9c1154792fb as its first parent. Report-head checks are independently verified
before the OAP response signal.

## Safety, privacy, cost, and scope

- Live qualification remains NOT RUN; no provider credentials were read,
  validated, printed, or used.
- No Gateway request, PostgreSQL connection, real email, deployment, release,
  or production/shared database access occurred.
- No provider, endpoint, adapter, accounting service, schema, policy, or
  Compose behavior was changed.
- No key, prompt, completion, raw JSON, request ID, URL credential, or
  protected authorization content was printed or committed.
- The authorization cost check is post-response SLAIF accounting evidence. It
  cannot guarantee provider-invoice totals or prevent one individual request
  from crossing the cap. The 32-token bound, selected low-cost models, fresh
  zero-history key, and explicit human authorization remain the pre-call
  controls.
- Objective 140 and 152-a artifacts remain historical/implementation evidence,
  not current live qualification.

Documentation updated: docs/real-provider-qualification.md. Documentation was
checked for API/provider compatibility contracts; no other contract needed an
update because this round changes no Gateway endpoint, forwarding, accounting,
or client behavior.
