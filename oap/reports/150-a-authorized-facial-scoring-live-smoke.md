# OAP Coding-Agent Report — 150-a

## Work order

- Identifier: 150-a
- Work-order file: `oap/orders/150-a-authorized-facial-scoring-live-smoke.md`
- Result: COMPLETE
- PR: #285 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/285
- Base: `main` at `fc6e163b091439e880019877e5fd08fbfa3de7ed`
- Branch: `oap/150-facial-live-qualification`
- Activation commit: `6a0dab0a23454c6aabd9d4ed3614298b6169b49d`
- Implementation head SHA: `51dc18a37bd7f8a1c1db218df23a6b16eacd31e4`
- Report publication commit: SELF

## Objective and evidence classification

Recorded the first explicitly human-authorized live native smoke for the
reviewed `facial_scoring` module in the three permitted documentation
surfaces. The smoke used a transient testing credential outside the
repository, the operator-selected native origin, and a disposable synthetic
image. It returned HTTP 200 with the native `unscorable` result and reason
`no_face_detected`.

The live smoke is classified `PASS` only for credential acceptance, multipart
transport, and safe native response-shape handling. The complete qualification
classification remains mocked HTTP plus PostgreSQL gateway evidence, plus
this one authorized live native smoke. No positive score, model accuracy,
authenticity, calibration, live gateway end-to-end qualification,
certification, production readiness, or SLA claim follows.

## Files changed in the implementation commit

- `docs/configuration.md`
- `docs/compatibility-matrix.md`
- `docs/provider-forwarding-contract.md`

The activated order, `oap/active`, and prior immutable orders/reports were not
edited. The report publication commit changes only this report file.

## Acceptance-criteria evidence

### Criterion 1 — Documentation classification and operator contract

- Result: PASS.
- Evidence: The three named documentation surfaces distinguish the existing
  mocked/PostgreSQL gateway qualification from the authorized live native
  smoke. They preserve `facial_scoring`, native module routing, the
  operator-selected origin, `FACIAL_SCORING_API_KEY`, finite timeout,
  `max_retries=0`, the exact public model, Chat Completions-only admission,
  one data-URL image, fixed `0 EUR` accounting, and normal gateway controls.

### Criterion 2 — Authorized live native smoke

- Result: PASS within the bounded evidence class.
- Evidence: The explicitly human-authorized testing key was accepted by the
  native service for one disposable synthetic-image multipart request. The
  sanitized response was HTTP 200 with native `unscorable/no_face_detected`.
  This proves neither a positive score nor model quality, authenticity,
  calibration, or production behavior.

### Criterion 3 — Privacy and negative boundaries

- Result: PASS.
- Evidence: No credential, service address, client authorization value, image
  bytes, data URL, raw request, raw response body, or provider payload is in
  the changed files or this report. No additional live request was made. No
  production provider row, deployment, rollout, retry, health probe,
  endpoint, migration, runtime adapter, Responses/legacy/streaming path,
  persistence, calibration, moderation, retraining, or token-pricing claim
  was added.

### Criterion 4 — OAP and PR boundaries

- Result: PASS.
- Evidence: Exactly one PR, #285, was created for objective 150-a. The coding
  agent did not merge or enable auto-merge. The implementation commit was
  pushed before report publication. The final publication commit changes only
  this report path and carries `Report publication commit: SELF`.

## Local verification

- `git diff --check`: PASSED.
- `python -m pytest tests/unit/test_facial_scoring_adapter.py
  tests/unit/test_v1_chat_completions_forwarding.py -q`: the system
  interpreter could not start the suite because its environment lacked the
  repository test dependency `structlog`. The same required test selection
  was then run with the isolated repository dev environment, with upstream
  credential variables unset: PASSED — 57 tests.
- `python -m ruff check tests/unit/test_facial_scoring_adapter.py
  tests/unit/test_v1_chat_completions_forwarding.py`: the system interpreter
  lacked Ruff. The same required Ruff selection was then run with the
  isolated repository dev environment: PASSED.
- Final diff scope and sensitive-material scan: PASSED; only the three
  permitted implementation documentation paths were changed before this
  report, and no credential, endpoint, image, data-URL, or raw-payload
  material was found.

## GitHub CI / required checks

Final implementation head verified at
`51dc18a37bd7f8a1c1db218df23a6b16eacd31e4`:

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
- Required final-head checks green before report publication: YES.
- PR #285 state: OPEN; auto-merge: NOT ENABLED.
- No merge commit is recorded by the coding agent.

## Safety and scope confirmations

- Explicitly authorized native smoke: YES; one transient testing credential was
  used out of band and is not reproduced here.
- Production secrets accessed: NO.
- Production systems or databases accessed: NO.
- Real native service call: YES; limited to the authorized disposable smoke.
- Real OpenAI/OpenRouter upstream calls: NO.
- Real email sent: NO.
- Database destructive setup against `DATABASE_URL`: NO.
- Credentials, service addresses, image bytes, data URLs, raw request/response
  content, and provider payloads: NOT added, logged, persisted, or committed.
- Unrelated files changed: NO.
- Scope deviation: NO.
- Extra PR created for objective 150: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled: NO.
- Activated order and `oap/active` edited by coding agent during this cycle:
  NO; they were carried from the activation commit unchanged.
- Report-publication commit changes only this report file: YES.

## Documentation impact

The implementation updates the facial-module compatibility matrix,
configuration guidance, and provider-forwarding contract to record the
authorized native smoke while preserving the bounded operator contract and
all current non-goals. No runtime behavior or public endpoint surface changed.

## Recommended strategic follow-up

PR #285 has green required checks and a clean final implementation head. The
strategic model should independently review the documentation diff, this
immutable report, and the final `SELF` report commit before deciding whether
to merge or request a continuation. The live result remains an unscorable
transport/schema smoke, not a model-quality or production qualification. The
coding agent does not merge.
