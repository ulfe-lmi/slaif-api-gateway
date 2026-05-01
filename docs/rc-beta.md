# RC-Beta Release Notes And Checklist

This document is the operator-facing RC-beta checklist. It complements
[`beta-readiness.md`](beta-readiness.md), which records the detailed readiness
verification pass.

RC-beta means the implemented and documented scope is ready for beta labeling
after CI and local verification pass. It is not a production certification,
compliance attestation, or penetration-test report.

## Implemented Scope

- OpenAI-compatible `GET /v1/models`.
- OpenAI-compatible non-streaming and streaming `POST /v1/chat/completions`.
- OpenAI-shaped errors for unsupported `/v1` endpoints and policy failures.
- PostgreSQL-backed gateway key, quota, reservation, accounting, usage ledger,
  audit, catalog, routing, pricing, FX, admin, and email delivery metadata.
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
- Native Anthropic API is not implemented; Anthropic-family models can be routed
  through OpenRouter's OpenAI-compatible interface.
- Responses API is not implemented.
- Embeddings API is not implemented.
- File, image, and audio endpoints are not implemented.
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
git tag -a v0.1.0-rc-beta.1 -m "SLAIF API Gateway RC beta 1"
git push origin v0.1.0-rc-beta.1
```

The exact version is a maintainer decision. The tag should point to a commit
whose CI run and Docker smoke are green.
