# OAP Coding-Agent Report — 149-a

## Work order

- Identifier: 149-a
- Work-order file: `oap/orders/149-a-facial-adapter-qualification-and-operator-evidence.md`
- Result: COMPLETE
- PR: #284 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/284
- Base: `main` at `1505dcbc36fa43e3d890d8c68fd6aa151470560e`
- Branch: `oap/149-facial-adapter-qualification`
- Activation commit: `5e81f3efdd160bae3d72028cda5e4469b6b2b012`
- Implementation head SHA: `31de4a526e9b8755ba3f075a96b75a72f309173c`
- Report publication commit: SELF

## Objective and scope

Added bounded mocked and PostgreSQL qualification evidence for the merged
`facial_scoring` module and documented a reproducible, non-secret operator
setup example. The evidence proves that the adapter remains inside the normal
gateway route capability, authentication, policy, request/rate/concurrency,
quota reservation/finalization/release, revocation/expiry, audit, and privacy
boundaries.

The qualification is deliberately not a live service qualification. No
authorized native credential was supplied, no live score request was made,
and no endpoint reachability, model accuracy, authenticity, calibration,
certification, production, or SLA claim is made.

## Files changed in the implementation commit

- `docs/configuration.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`
- `tests/integration/test_facial_scoring_adapter_qualification_postgres.py`
- `tests/unit/test_facial_scoring_adapter.py`
- `tests/unit/test_v1_chat_completions_forwarding.py`

The activated order, `oap/active`, and prior immutable orders/reports were not
edited. The report publication commit changes only this report file.

## Acceptance-criteria evidence

### Criterion 1 — PostgreSQL route, pricing, quota, and accounting evidence

- Result: PASS.
- Evidence: The focused PostgreSQL test creates only disposable qualification
  metadata for provider slug `facial_scoring`, `kind=module`, the exact public
  model, the narrow Chat capability profile, and a EUR fixed-request pricing
  row at zero request price. `PricingService` returns zero estimated input and
  output tokens and exact zero EUR. A successful finalization records one
  request, zero reserved/actual tokens, exact zero estimated/actual cost, and
  ignores synthetic nonzero provider usage for module accounting. A simulated
  downstream failure releases the pending reservation and restores reserved
  counters. The existing request quota and durable fence checks reject later
  admission without adding another accounting path.

### Criterion 2 — mocked Chat compatibility and failure boundaries

- Result: PASS.
- Evidence: Adapter tests cover scored and unscorable native results, the
  fixed multipart boundary, client-text exclusion, safe 4xx/5xx handling,
  timeout without retry, malformed/empty/non-JSON results, unsupported
  Responses/legacy endpoints, streaming, remote/file/audio/video/multiple
  image forms, tools, controls, and multiple choices. Gateway tests cover
  scored and unscorable OpenAI-shaped responses and prove module streaming is
  rejected before quota reservation or native contact. All native interactions
  use in-process mocks; no live facial service is contacted.

### Criterion 3 — operator setup and qualification classification

- Result: PASS.
- Evidence: Configuration documentation gives a non-secret metadata example
  with operator-selected origin, `FACIAL_SCORING_API_KEY`, finite timeout,
  `max_retries=0`, the exact public route/capability profile, and fixed EUR
  zero pricing. It explicitly states that zero price does not remove
  request/rate/concurrency, quota, revocation, expiry, audit, or failed-attempt
  controls. Compatibility and forwarding documentation classify the evidence
  as mocked/PostgreSQL qualification only and state live qualification
  `NOT RUN`.

### Criterion 4 — privacy and scope boundaries

- Result: PASS.
- Evidence: No credentials, observed service addresses, client text, raw
  image bytes, data URLs, provider payloads, or raw response bodies were added
  to documentation, reports, fixtures, logs, or committed configuration.
  Audit assertions confirm generated gateway key material is absent from audit
  metadata. No runtime adapter source, migration, production row, deployment
  configuration, Responses/legacy surface, remote fetch, persistence,
  calibration, moderation, retraining, or unrelated provider path changed.

### Criterion 5 — OAP and PR boundaries

- Result: PASS.
- Evidence: Objective 149 uses one new PR, #284, on the activated branch. The
  coding agent did not merge or enable auto-merge. The implementation commit
  was pushed before report publication. The report publication commit changes
  only this report path and carries `Report publication commit: SELF`.

## Local verification

- `env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u FACIAL_SCORING_API_KEY
  .venv/bin/python -m pytest
  tests/unit/test_facial_scoring_adapter.py
  tests/unit/test_v1_chat_completions_forwarding.py -q`: PASSED.
- `TEST_DATABASE_URL='postgresql+asyncpg://.../slaif_oap_149_test'
  env -u OPENAI_API_KEY -u OPENROUTER_API_KEY -u FACIAL_SCORING_API_KEY
  .venv/bin/python -m pytest
  tests/integration/test_facial_scoring_adapter_postgres.py
  tests/integration/test_facial_scoring_adapter_qualification_postgres.py
  -q`: PASSED — 3 tests. The database was a disposable local PostgreSQL
  database created for this run and was dropped afterward.
- Focused Ruff command covering the four required test paths: PASSED.
- `git diff --check`: PASSED.
- Initial integration invocation without `TEST_DATABASE_URL`: SKIPPED by the
  repository's safe integration fallback; it was followed by the disposable
  PostgreSQL run above.

## GitHub CI / required checks

Final PR head verified at `31de4a526e9b8755ba3f075a96b75a72f309173c`:

- Unit, lint, and migration head: SUCCESS.
- PostgreSQL integration tests: SUCCESS.
- OpenAI-compatible E2E tests: SUCCESS.
- Playwright browser smoke: SUCCESS.
- Docker Compose smoke: SUCCESS.
- Documentation hygiene: SUCCESS.
- Analyze Python: SUCCESS.
- Analyze (python): SUCCESS.
- Analyze (javascript-typescript): SUCCESS.
- CodeQL: SUCCESS.
- Required final-head checks green: YES.
- PR #284 state: OPEN; merge state: CLEAN; auto-merge: NOT ENABLED.
- The implementation head is equal locally and remotely. No merge commit is
  recorded by the coding agent.

## Safety and scope confirmations

- Production secrets accessed: NO.
- Production systems or databases accessed: NO.
- Real native/upstream calls: NO.
- Real email sent: NO.
- Database destructive setup against `DATABASE_URL`: NO.
- Disposable database isolation: YES; the local qualification database was
  explicit and dropped after verification.
- Redis or external provider state was not used by the qualification tests.
- Credentials, service addresses, image bytes, data URLs, raw request/response
  content, and provider payloads: NOT added, logged, persisted, or committed.
- Unrelated files changed: NO.
- Scope deviation: NO.
- Extra PR created for objective 149: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled: NO.
- Activated order and `oap/active` edited by coding agent during this cycle:
  NO; they were carried from the activation commit unchanged.
- Report-publication commit changes only this report file: YES.

## Recommended strategic follow-up

PR #284 has green required checks and a clean merge state. The strategic model
should independently review the implementation diff, this immutable report,
and the final `SELF` report commit checks before deciding whether to merge or
request a continuation. Live facial-service qualification remains outside
this objective and requires a separately authorized credential and work order.
The coding agent does not merge.
