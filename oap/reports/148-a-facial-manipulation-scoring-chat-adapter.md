# OAP Coding-Agent Report — 148-a

## Work order

- Identifier: 148-a
- Work-order file: `oap/orders/148-a-facial-manipulation-scoring-chat-adapter.md`
- Result: COMPLETE
- PR: #283 — https://github.com/ulfe-lmi/slaif-api-gateway/pull/283
- Base: `main` at `67561d7718af2eac0947b6f1ae31051df59356ca`
- Branch: `oap/148-facial-manipulation-scoring-adapter`
- Implementation head SHA: `45dfa9806ef3f661f0f41e5672b02d3ea429c552`
- Activation commit: `4cec35c5bbe4dd7aab69a41167eaf1d46827068e`
- Report publication commit: SELF

## Objective and scope

Implemented the reviewed, tightly bounded `facial_scoring` native module for
the public `facial-manipulation-scoring` model on non-streaming
`POST /v1/chat/completions`.

The adapter accepts exactly one supported non-empty base64 image data URL,
rejects remote/file/audio/video and unrelated request shapes before native
contact, translates the decoded image to one fixed `image` multipart field at
the configured `/v1/score` path, and authenticates only with
`FACIAL_SCORING_API_KEY` through the existing provider factory. Native
responses are validated into an OpenAI-shaped single-choice text completion;
successful responses report zero prompt, completion, and total tokens.

No live native score request, production provider/route activation, API key
creation, production database mutation, retry/fallback behavior, or release
claim was performed.

## Files changed in the implementation commit

- `app/slaif_gateway/modules/__init__.py`
- `app/slaif_gateway/modules/facial_scoring/__init__.py`
- `app/slaif_gateway/modules/facial_scoring/adapter.py`
- `app/slaif_gateway/providers/factory.py`
- `app/slaif_gateway/services/chat_completion_route_capabilities.py`
- `docs/configuration.md`
- `docs/compatibility-matrix.md`
- `docs/openai-compatibility.md`
- `docs/provider-forwarding-contract.md`
- `tests/integration/test_facial_scoring_adapter_postgres.py`
- `tests/unit/test_chat_completion_route_capabilities.py`
- `tests/unit/test_facial_scoring_adapter.py`
- `tests/unit/test_provider_factory.py`
- `tests/unit/test_v1_chat_completions_forwarding.py`

The activated order and `oap/active` were carried unchanged. The report
publication commit changes only this report file.

## Acceptance-criteria evidence

### Criterion 1 — bounded Chat adapter and static registration

- Result: PASS.
- Evidence: `facial_scoring` is registered in reviewed source code and the
  factory resolves it to `FacialScoringAdapter`; unknown module identifiers
  remain fail-closed. Only the Chat Completions operation is implemented.

### Criterion 2 — strict image admission and native request contract

- Result: PASS.
- Evidence: The adapter requires one image content part, supported media
  types, strict non-empty base64 data URL syntax, and existing bounded image
  URL limits. It rejects remote URLs, `file://`, unsupported media, invalid
  base64, empty data, multiple images, text-only requests, tools, multiple
  choices, streaming, and unsupported controls before the native call. The
  native multipart request contains one fixed `image` field and no client
  text, filename, extra fields, gateway Authorization, cookies, or forwarded
  headers.

### Criterion 3 — response validation, privacy, and failure mapping

- Result: PASS.
- Evidence: Timeout and transport failures use existing safe provider errors;
  HTTP failures use bounded sanitized diagnostics; empty, non-JSON, malformed,
  non-finite, and out-of-range score results fail closed. Scored output uses
  the documented score format and default score type. Unscorable output has
  only a bounded sanitized reason. Raw native bodies, image content, request
  text, credentials, and client headers are not returned, logged, or persisted.

### Criterion 4 — route capability and fixed accounting boundary

- Result: PASS.
- Evidence: The documented capability profile enables text and image input
  while disabling streaming, tools, audio, files, multiple choices, hosted
  tools, structured outputs, and non-default controls. The existing module
  billing path remains authoritative for one request, zero tokens, and exact
  zero EUR request cost; the adapter returns zero-token usage and does not
  perform accounting itself.

### Criterion 5 — scope and OAP boundaries

- Result: PASS.
- Evidence: The implementation changes only the explicit paths in the active
  order, uses the required branch and one PR, does not merge or enable
  auto-merge, and does not modify architecture, migrations, releases, or
  production configuration.

## Local verification

- `env -u OPENROUTER_API_KEY -u OPENAI_API_KEY -u FACIAL_SCORING_API_KEY ./.venv/bin/python -m pytest tests/unit/test_facial_scoring_adapter.py tests/unit/test_module_provider.py tests/unit/test_provider_factory.py tests/unit/test_chat_completion_route_capabilities.py tests/unit/test_v1_chat_completions_forwarding.py -q`: PASSED — 87 tests.
- `env -u OPENROUTER_API_KEY -u OPENAI_API_KEY -u FACIAL_SCORING_API_KEY ./.venv/bin/python -m pytest tests/integration/test_facial_scoring_adapter_postgres.py -q`: SKIPPED — `TEST_DATABASE_URL` was not available locally.
- Focused Ruff command covering the changed module, factory, capability, and
  test paths: PASSED.
- `./.venv/bin/python -m compileall -q app/slaif_gateway/modules`: PASSED.
- `git diff --check`: PASSED.
- A direct mocked multipart check confirmed the native body contains no client
  text, has no Authorization header, and uses the fixed image field.

## GitHub CI / required checks

State observed for implementation head
`45dfa9806ef3f661f0f41e5672b02d3ea429c552`:

- CI run `32651052750`: SUCCESS.
- CodeQL run `32651051659`: SUCCESS.
- Analyze run `32651052748`: SUCCESS.
- Unit, lint, and migration head: SUCCESS.
- PostgreSQL integration tests: SUCCESS.
- Docker Compose smoke: SUCCESS.
- OpenAI-compatible E2E tests: SUCCESS.
- Playwright browser smoke: SUCCESS.
- Documentation hygiene: SUCCESS.
- Analyze (python): SUCCESS.
- Analyze (javascript-typescript): SUCCESS.
- CodeQL: SUCCESS.
- Required GitHub checks green for the implementation head: YES.
- PR review state: no strategic approval or merge is recorded; PR #283 remains
  open and auto-merge is not enabled.
- The report-only commit may trigger fresh checks. The strategic model must
  independently verify the `SELF` commit and final PR state; this report will
  not be rewritten.

## Safety and scope confirmations

- Production secrets accessed: NO.
- Production systems accessed: NO.
- Real native/upstream calls: NO.
- Real email sent: NO.
- Credentials, image bytes, data URLs, raw request/response content, and
  provider payloads: NOT added, logged, persisted, or committed.
- Unrelated files changed: NO.
- Scope deviation: NO.
- Extra PR created for objective 148: NO.
- PR merged by coding agent: NO.
- Auto-merge enabled: NO.
- Activated order and `oap/active` edited by coding agent during this cycle:
  NO; they were carried from the activation commit unchanged.
- Report-publication commit changes only this report file: YES.

## Recommended strategic follow-up

PR #283 has green required checks and is ready for independent strategic
review. The strategic model should review the complete PR, this immutable
report, and the final `SELF`-commit checks before deciding whether to merge or
request a continuation. The coding agent does not merge.
