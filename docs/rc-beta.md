# RC-Beta Release Notes And Checklist

This document is the operator-facing RC-beta checklist. It complements
[`beta-readiness.md`](beta-readiness.md), which records the detailed readiness
verification pass.

RC-beta means the implemented and documented scope is ready for beta labeling
after CI and local verification pass. It is not a production certification,
compliance attestation, or penetration-test report.

Tag-specific release notes for the first release candidate are in
[`releases/v0.1.0-rc.1.md`](releases/v0.1.0-rc.1.md).

The latest external RC1 review baseline is archived at
[`security/reviews/2026-05-review-6.0-rc1.md`](security/reviews/2026-05-review-6.0-rc1.md).
It supports RC-beta readiness for the implemented scope while keeping remaining
production-readiness work explicit. Follow-up PRs address non-message Chat
Completions input estimation and quota/accounting/reconciliation invariant-test
coverage. Production/operator runbooks are now documented under
[`runbooks/README.md`](runbooks/README.md); they improve operational readiness
but are not a production certification.

## Implemented Scope

- OpenAI-compatible `GET /v1/models`.
- OpenAI-compatible non-streaming and streaming `POST /v1/chat/completions`.
- Non-streaming Chat Completions local custom tools behind explicit route
  capability; streaming custom tools remain unsupported.
- Bounded Chat Completions multiple choices behind explicit
  `chat_multiple_choices` route capability, including streaming choice-index
  pass-through.
- Chat Completions image input to text output behind explicit
  `chat_image_inputs` route capability, with bounded remote URL/data URL
  validation and ordinary provider-usage finalization.
- Chat Completions inline file input to text output behind explicit
  `chat_file_inputs` route capability, with bounded inline base64 `file_data`,
  safe filename/type validation, file IDs and file URLs rejected, and ordinary
  provider-usage finalization.
- Chat Completions audio input to text output behind explicit
  `chat_audio_inputs` route capability, with bounded raw base64 `wav`/`mp3`
  input, audio URLs/data URLs rejected by default, no local transcription, and
  ordinary provider-usage finalization.
- Chat Completions non-streaming audio output behind explicit
  `chat_audio_outputs` route capability and audio-output pricing metadata,
  with generated audio/transcripts forwarded to the client but not stored or
  logged.
- OpenAI-shaped errors for unsupported `/v1` endpoints and policy failures.
- Explicit Chat Completions route/model capability metadata, enforced
  separately from gateway-key endpoint/model/provider allowlists.
- PostgreSQL-backed gateway key, quota, reservation, accounting, usage ledger,
  audit, catalog, routing, pricing, FX, admin, and email delivery metadata.
- Chat Completions accounting uses admission-time budget checks plus post-call
  finalization. A successful call can finalize above its reservation; the
  ledger records safe overrun/cost-source metadata and subsequent calls are
  blocked when finalized counters exceed key limits.
- Streaming live-burn margin is planned future work only. It is documented in
  [`streaming-live-burn-margin.md`](streaming-live-burn-margin.md) as a
  gateway-side provisional interruption milestone, Chat Completions first and
  Responses second; it is not active RC-beta behavior.
- Optional Redis operational rate limiting for request, estimated-token, and
  concurrency throttles.
- Admin dashboard for keys, records, providers, routes, pricing, FX, usage,
  audit, email delivery, import preview/execution workflows, and usage/audit
  CSV exports.
- Bulk key import execution for `none`, `pending`, and `enqueue` email modes.
- CLI administration commands for the implemented metadata, key, usage, email,
  reconciliation, and migration workflows.
- Docker Compose packaging for API, worker, scheduler, PostgreSQL, Redis, and
  Mailpit.
- Nginx reverse-proxy example with streaming-safe proxy settings.
- Operator runbooks for secret rotation, key leak response, backup/restore,
  reconciliation, Redis/DB incidents, metrics thresholds, Docker/Nginx
  troubleshooting, admin access, and RC-beta upgrades.

## CI Coverage

The GitHub Actions CI workflow is expected to run on pull requests, pushes to
`main`, and manual dispatch:

- Unit tests, Ruff, Alembic head check, and whitespace check.
- PostgreSQL-backed integration tests with Redis service available.
- OpenAI-compatible E2E tests using mocked upstream providers and the official
  OpenAI Python client.
- Playwright Chromium admin dashboard browser smoke.
- Docker Compose config, build, explicit migrations, API/worker/scheduler smoke,
  `/healthz`, `/readyz`, and Nginx syntax validation.
- Documentation hygiene checks for whitespace, README brand-header preservation,
  and public client environment variable naming.

CI uses `TEST_DATABASE_URL` for test databases. It does not use `DATABASE_URL`
for destructive setup, does not require real OpenAI/OpenRouter provider keys,
and does not send real external email.

The CodeQL workflow runs Python analysis on pull requests, pushes to `main`,
weekly schedule, and manual dispatch. Dependabot checks Python and GitHub
Actions dependencies weekly without automatic merging.

## Docker Smoke Coverage

The Docker smoke sequence should pass before tagging:

```bash
cp .env.example .env
docker compose config
docker compose build
docker compose up -d postgres redis mailpit
docker compose run --rm api slaif-gateway db upgrade
docker compose up -d api worker scheduler
curl -fsS http://localhost:8000/healthz
curl -fsS http://localhost:8000/readyz
docker run --rm --network "$(basename "$PWD")_default" \
  -v "$PWD/deploy/nginx:/etc/nginx/conf.d:ro" \
  nginx:stable nginx -t
docker compose down -v
```

Migrations remain explicit. API, worker, and scheduler containers must not run
migrations automatically.

## Known Limitations

- Bulk synchronous `send-now` key import execution is not implemented.
- Streaming live-burn margin is not implemented. Its future implementation must
  preserve final provider usage/cost authority, PostgreSQL hard quota truth,
  Redis temporary-state-only boundaries, and no streamed-content storage.
- Native Anthropic API is not implemented; Anthropic-family models can be routed
  through OpenRouter's OpenAI-compatible interface.
- Responses API support is limited to stateless text-output
  `POST /v1/responses` with string input, bounded input item arrays,
  route-enabled user-message URL/data URL image input, route-enabled
  user-message URL/data URL file input, non-streaming JSON, typed SSE
  streaming, non-streaming structured `text.format` JSON object/schema output,
  plus non-streaming local function and custom tools, explicit key endpoint
  permission, route capability, provider route, and pricing metadata.
  Hosted/provider-side Responses tools,
  storage/state, background mode, retrieval/delete/cancel/list routes,
  `input_image.file_id`, `input_file.file_id`, `/v1/files`, file
  search/retrieval tools, audio input, image generation, multimodal output, and
  MCP/connectors remain future work. Current Chat
  Completions usage profiling and trusted calibration keys, available from CLI
  and admin web creation, provide safe calibration-foundation metadata. Admins
  can now preview calibration usage summaries and strict participant-policy
  proposals from CLI and admin web, then create durable key-template revisions
  from reviewed proposals. Single-key creation from a selected template revision
  is implemented for normal standard keys, including sanitized policy metadata
  for the implemented stateless local Responses subset. Bulk participant-key
  generation, policy mutation, and hosted/stateful/multimodal Responses
  template policy remain future work.
  See `responses-compatibility.md`.
- Embeddings API is not implemented.
- File, image, and audio endpoints are not implemented.
- Chat Completions file IDs, file URLs, audio URLs, streaming audio output,
  custom audio-output voices, previous-audio references, and `n > 1` with audio
  output are not implemented. Non-streaming Chat Completions audio output is
  implemented only behind explicit route capability and pricing metadata. The
  upstream evidence and future implementation roadmap are documented in
  [`chat-completions-multimodal-investigation.md`](chat-completions-multimodal-investigation.md).
- MFA is not implemented.
- Full RBAC is not implemented; every active admin is a full operator and
  `superadmin` is metadata/future-proofing.
- Owner/institution/cohort delete and anonymization workflows are not
  implemented.
- External FX refresh workflows are not implemented.
- Arbitrary old plaintext key resend is intentionally not implemented.
- Real upstream smoke tests are disabled by default and require explicit
  operator opt-in plus real provider credentials.
- There is no formal security certification, formal penetration test, SOC/ISO
  attestation, or compliance certification.

## Release Checklist

Before tagging an RC-beta release:

- CI is green on the release candidate branch or commit.
- CodeQL has completed without release-blocking findings.
- Docker Compose smoke has passed.
- Nginx syntax validation has passed.
- `docs/beta-readiness.md`, `docs/compatibility-matrix.md`, and README match the
  implemented scope.
- `docs/runbooks/README.md` links the current operator runbooks.
- README still starts with the SLAIF logo/link block.
- No real provider keys, gateway keys, SMTP passwords, HMAC secrets, session
  secrets, one-time-secret encryption keys, or `.env` files are committed.
- Known limitations are visible in README or linked release docs.
- The tag target is recorded in release notes.

## Local Verification Suite

Run these checks locally when cutting a release candidate:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/unit
python -m ruff check app tests
alembic heads
git diff --check
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/integration
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/e2e
python -m playwright install chromium
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/browser -m playwright
docker compose config
```

Use a disposable test database for `TEST_DATABASE_URL`. Do not point destructive
test setup at `DATABASE_URL`.

## Tagging Guidance

Tag only after the release checklist is complete:

```bash
git tag -a v0.1.0-rc.1 -m "SLAIF API Gateway v0.1.0-rc.1"
git push origin v0.1.0-rc.1
```

The exact version is a maintainer decision. For this RC-beta preparation pass,
the recommended tag is `v0.1.0-rc.1`. The tag should point to a commit whose CI
run and Docker smoke are green.
