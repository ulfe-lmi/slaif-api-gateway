# Quickstart For First-Time Users

This guide starts SLAIF API Gateway on your computer and walks through the
first admin and gateway-key setup. You do not need real OpenAI or OpenRouter
keys for the basic local admin smoke checks. You need a real upstream provider
key only when you want the gateway to forward a real `/v1` request.

SLAIF API Gateway sits between users and upstream LLM providers. Users keep
using normal OpenAI-compatible clients with `OPENAI_API_KEY` and
`OPENAI_BASE_URL`; the gateway checks local keys, quotas, routing, pricing, and
audit rules before it forwards allowed requests with the server-side provider
key.

## What You Need

- Git, to clone the repository.
- Docker and Docker Compose, to run PostgreSQL, Redis, Mailpit, the API, and
  background workers locally.
- Python 3.12 or newer, only if you want to run tests outside Docker.
- No real provider key for the local dashboard smoke.
- A real upstream provider key only for real provider calls.

Mailpit is included for local fake email. It catches email in a local web inbox
instead of sending real external email.

## 1. Clone The Repository

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
```

You should now be inside the repository directory.

## 2. Create A Local Environment File

```bash
cp .env.example .env
```

`.env.example` contains development placeholders. They are useful for trying the
project locally, but they are not production secrets. Before any real deployment
you must replace HMAC, session, database, SMTP, encryption, and provider
secrets.

For a real OpenAI provider call later, put the server-side upstream key in
`.env` as:

```env
OPENAI_UPSTREAM_API_KEY=sk-your-real-upstream-provider-key
```

This is different from the user's client key. Users set `OPENAI_API_KEY` to a
gateway-issued key.

## 3. Build And Start Local Services

Build the local image:

```bash
docker compose build
```

Start PostgreSQL, Redis, and Mailpit:

```bash
docker compose up -d postgres redis mailpit
```

What this does:

- PostgreSQL stores durable gateway data.
- Redis stores temporary rate-limit and Celery broker state.
- Mailpit catches local test email.

Run database migrations explicitly:

```bash
docker compose run --rm api slaif-gateway db upgrade
```

You should see Alembic apply migrations through the latest head.

Start the API, worker, and scheduler:

```bash
docker compose up -d api worker scheduler
```

Check that the API is alive:

```bash
curl -fsS http://localhost:8000/healthz
```

Expected output:

```json
{"status":"ok"}
```

Check readiness:

```bash
curl -fsS http://localhost:8000/readyz
```

You should see JSON with healthy database and schema status. If readiness fails
with a schema or migration message, run `docker compose run --rm api
slaif-gateway db upgrade` again and retry.

## 4. Create The First Admin

Create an admin account:

```bash
printf '%s\n' 'replace-this-password' \
  | docker compose run --rm api slaif-gateway admin create \
      --email admin@example.org \
      --display-name "Admin User" \
      --password-stdin
```

Use a stronger password for anything beyond local testing.

Open the dashboard:

```text
http://localhost:8000/admin/login
```

Log in with `admin@example.org` and the password you supplied.

## 5. Add Basic Local Metadata

The gateway needs local records before it can issue useful keys and route
requests. You can create these through the dashboard or with CLI commands.

Create an institution:

```bash
docker compose run --rm api slaif-gateway institutions create \
  --name "Example Institute" \
  --country SI
```

Create a cohort:

```bash
docker compose run --rm api slaif-gateway cohorts create \
  --name "Example Workshop 2026"
```

Create an owner. Replace `<institution-id>` with the ID printed by the
institution command:

```bash
docker compose run --rm api slaif-gateway owners create \
  --name Ada \
  --surname Lovelace \
  --email ada@example.org \
  --institution-id <institution-id>
```

Create provider, route, pricing, and FX metadata:

```bash
docker compose run --rm api slaif-gateway providers add \
  --provider openai \
  --api-key-env-var OPENAI_UPSTREAM_API_KEY

docker compose run --rm api slaif-gateway routes add \
  --requested-model gpt-test-mini \
  --match-type exact \
  --provider openai \
  --upstream-model gpt-test-mini

docker compose run --rm api slaif-gateway pricing add \
  --provider openai \
  --model gpt-test-mini \
  --endpoint chat.completions \
  --currency EUR \
  --input-price-per-1m 0.10 \
  --output-price-per-1m 0.20

docker compose run --rm api slaif-gateway fx add \
  --base-currency USD \
  --quote-currency EUR \
  --rate 0.920000000
```

These commands create local metadata only. They do not call OpenAI or
OpenRouter.

## 6. Create A Gateway Key

Create a key for the owner. Replace `<owner-id>` with the owner ID:

```bash
docker compose run --rm api slaif-gateway keys create \
  --owner-id <owner-id> \
  --valid-days 30 \
  --cost-limit-eur 5.00 \
  --request-limit-total 100
```

The plaintext gateway key is shown once. Save it somewhere appropriate for your
local test. The gateway does not store plaintext keys and cannot show old keys
again.

## 7. Try The OpenAI Python Client

Install the OpenAI client on your host if you want to run a client script:

```bash
python3 -m venv .venv-client
. .venv-client/bin/activate
python -m pip install openai
```

Set the standard OpenAI-compatible client variables:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="http://localhost:8000/v1"
```

`OPENAI_API_KEY` is the gateway key you created. `OPENAI_BASE_URL` points the
client at your local gateway.

Create `hello_gateway.py`:

```python
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-test-mini",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)

print(response.choices[0].message.content)
```

Run it:

```bash
python hello_gateway.py
```

If you did not set a real `OPENAI_UPSTREAM_API_KEY` in `.env`, real provider
forwarding will fail safely. The local dashboard, database, migrations, key
creation, and tests can still be tried without a real provider key.

## 8. Check Fake Email In Mailpit

Mailpit is available at:

```text
http://localhost:8025
```

If you create or rotate a key with a pending/enqueued local email delivery, test
messages appear there instead of being sent to the internet.

## 9. Run Local Tests

Unit tests do not need PostgreSQL, Redis, Docker, real provider keys, or email:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/unit
python -m ruff check app tests
alembic heads
git diff --check
```

Database-backed tests use `TEST_DATABASE_URL`, not `DATABASE_URL`:

```bash
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/integration
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/e2e
```

Browser smoke tests need Chromium:

```bash
python -m playwright install chromium
TEST_DATABASE_URL="postgresql+asyncpg://..." python -m pytest tests/browser -m playwright
```

The normal tests mock upstream providers. They do not need real OpenAI or
OpenRouter keys and do not send real external email.

## 10. Stop Or Clean Up

Stop containers but keep local data:

```bash
docker compose down
```

Delete local PostgreSQL and Redis volumes too:

```bash
docker compose down -v
```

Use `down -v` only when you are comfortable deleting local gateway data.

## Troubleshooting

### A Port Is Already In Use

The default API port is `8000`, Mailpit web port is `8025`, PostgreSQL host port
is `15432`, and Redis host port is `16379`. Change the matching value in `.env`,
for example:

```env
API_HOST_PORT=18000
```

Then restart Compose.

### Readiness Fails Before Migration

Run:

```bash
docker compose run --rm api slaif-gateway db upgrade
```

Then check `/readyz` again.

### Real Provider Calls Fail

Check that `.env` contains a real server-side upstream key such as
`OPENAI_UPSTREAM_API_KEY`, then restart API/worker/scheduler:

```bash
docker compose up -d api worker scheduler
```

Do not put the upstream provider key in user client examples.

### Login Fails

Make sure you created the admin account after migrations, and use the email and
password from the `admin create` command. Login errors are intentionally generic.

### No Models Are Visible

`/v1/models` only returns models visible to the gateway key. Check that provider
config, route metadata, key model policy, and key status/validity are correct.

### Unknown Pricing Or FX

Cost-limited requests fail closed when pricing or required FX conversion is
missing. Add pricing and FX rows through the dashboard or CLI before real
provider calls.

### Playwright Browser Dependencies Are Missing

Install Chromium:

```bash
python -m playwright install --with-deps chromium
```

## Deeper Documentation

- [Configuration reference](configuration.md)
- [Deployment notes](deployment.md)
- [Security model](security-model.md)
- [OpenAI compatibility](openai-compatibility.md)
- [Provider forwarding contract](provider-forwarding-contract.md)
- [Compatibility matrix](compatibility-matrix.md)
- [RC-beta readiness report](beta-readiness.md)
- [RC-beta release checklist](rc-beta.md)

RC-beta status means the implemented and documented scope has been verified. It
is not a production certification, compliance attestation, or penetration-test
report. Real deployments still need operator-managed secrets, HTTPS/Nginx
hardening, backups, monitoring, and incident response plans.
