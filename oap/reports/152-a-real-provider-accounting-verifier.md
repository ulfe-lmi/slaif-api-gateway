# OAP report — 152-a guarded real-provider accounting verifier

## Identity and result

- Objective: 152-a
- Active selector: 152-a
- Active selector SHA-256: ab51038bc3b8b473e82ddf4af057c69bf9938a784ba9d345236625a360762822
- Work-order SHA-256: 5a4871a4ce287f1e699885d0675530ff9607aa6072b7f4625d8448ceca655916
- Base: main at 8f2813bf745b90221da33a7cfaf40726c5b1b480
- Implementation commit: 38951e044b51b2a5a576524c747349a3cad19b15
- Branch: oap/152-real-provider-accounting-qualification
- Pull request: #287, open, base main, no merge, no auto-merge
- Report publication commit: SELF
- Result: implementation-only round complete; real-provider qualification NOT RUN
- REAL_PROVIDER_CALLED: false

Objective 152-a added the guarded verifier, deterministic refusal/parser/
correlation tests, and truthful documentation. No provider credential was
read, validated, printed, or used. No Gateway request, PostgreSQL target
connection, deployment, migration, or production/shared database operation
was performed.

## Implementation

The verifier now enforces exactly eight sequential flows:

1. OpenAI Chat Completions non-streaming;
2. OpenAI Chat Completions streaming;
3. OpenAI Responses non-streaming;
4. OpenAI Responses streaming;
5. OpenRouter Chat Completions non-streaming;
6. OpenRouter Chat Completions streaming;
7. OpenRouter Responses non-streaming; and
8. OpenRouter Responses streaming.

It requires operator-selected models, a maximum output of 32 tokens, a
minimum inter-request gap of 15 seconds, an explicit live switch, separate
mode-0600 protected files outside the repository, an exact current-commit
authorization, both providers, exactly eight requests, a future expiry, and a
maximum total authorization cost no greater than EUR 0.05. It rejects
provider-direct or non-HTTPS Gateway targets, non-loopback/shared PostgreSQL
targets, inherited secret environment values, secret argv values, symlinked
or unsafe protected files, stale schemas, malformed usage, incomplete/error
streams, duplicate/truncated terminals, and any retry.

Every successful response is required to expose a valid
X-SLAIF-Diagnostic-ID. After each terminal, the verifier selects exactly that
ID in PostgreSQL and requires one finalized quota reservation, one matching
finalized usage-ledger row, exact endpoint/provider/model/streaming/status
facts, positive consistent usage, non-negative accounting, zero pending
reservations, and zero reserved key counters. It scans only the correlated
safe metadata/key row for prompt, response, and plaintext-key canaries and
emits no request ID or content. The final check requires eight distinct
reservation/ledger pairs and an authorized total actual cost.

## Verification evidence

Commands were run with OPENAI_API_KEY, OPENAI_UPSTREAM_API_KEY,
OPENROUTER_API_KEY, DATABASE_URL, TEST_DATABASE_URL, and RUN_UPSTREAM_TESTS
unset.

- git diff --check: passed.
- Ruff on the verifier and dedicated test module: passed.
- Dedicated verifier tests: 37 passed.
- Existing focused Authorization-replacement/adapter tests:
  test_provider_headers.py, test_openai_provider_adapter.py,
  test_openrouter_provider_adapter.py, test_openai_provider_streaming.py,
  and test_openrouter_provider_streaming.py: 67 passed.
- Guarded dry run:
  result=not_run, real_provider_called=false, http_requests=0,
  sql_queries=0.
- Guarded live-shaped invocation with missing protected files:
  result=fail, error_code=gateway_key_file_invalid,
  attempted_requests=0, real_provider_called=false.

The dry-run and missing-file checks performed no HTTP or SQL operation. The
focused tests use fake HTTP/SQL state and do not qualify a provider.

## GitHub evidence

Before report publication, all ten required checks on implementation head
38951e044b51b2a5a576524c747349a3cad19b15 succeeded:

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

The report-only publication commit is required to change only this report
file, have the implementation commit as its first parent, and remain the
remote PR head. Report-head checks are independently verified before the OAP
response signal.

## Safety, privacy, and scope

- No real provider call or provider credential validation occurred.
- No real email was sent.
- No production/shared database was contacted or modified.
- No migration, application route, provider adapter, accounting service, or
  production Compose behavior was changed.
- No gateway key, provider key, protected authorization content, prompt,
  completion, raw response, request ID, or URL credential was printed or
  committed.
- The dedicated tests do not establish real-provider qualification.
- Objective 140's six-call artifacts remain historical and insufficient for
  current eight-flow accounting proof.
- A later same-number continuation requires fresh protected human inputs:
  an explicit HTTPS Gateway URL and CA choice if needed, a disposable
  loopback PostgreSQL URL, a separate Gateway key file, separate
  mode-0600 authorization JSON, and explicit operator-selected OpenAI and
  OpenRouter model identifiers. The verifier itself must not load provider
  credentials.

Documentation updated: docs/real-provider-qualification.md. Documentation was
checked for the API/provider compatibility contracts; no other contract
needed an update because this round changes no Gateway endpoint, forwarding,
accounting, or client behavior.
