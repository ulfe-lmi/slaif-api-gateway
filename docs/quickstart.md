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
secrets. `.env` is a clear-text local runtime configuration file; never commit
it. On shared systems, restrict it with:

```bash
chmod 600 .env
```

For a real OpenAI provider call later, put the server-side upstream key in
`.env` as:

```env
OPENAI_UPSTREAM_API_KEY=replace-with-real-upstream-provider-key
```

This is different from the user's client key. Users set `OPENAI_API_KEY` to a
gateway-issued key.

## 3. Generate Local Runtime Secrets

`.env.example` has placeholders for server runtime secrets. Generate them with
SLAIF's CLI instead of writing ad hoc Python snippets. These values protect
server-side HMAC signing, admin sessions, and encrypted one-time key deliveries.
They are not user gateway keys.

Host-local CLI workflow:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
slaif-gateway secrets generate hmac --version 1 --env-file .env --write
slaif-gateway secrets generate admin-session --env-file .env --write
slaif-gateway secrets generate one-time --env-file .env --write
slaif-gateway secrets validate-env --env-file .env
```

Docker-only workflow:

```bash
docker compose build api

docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  api slaif-gateway secrets generate hmac --version 1 --env-file .env --write

docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  api slaif-gateway secrets generate admin-session --env-file .env --write

docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  api slaif-gateway secrets generate one-time --env-file .env --write

docker compose run --rm --no-deps \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/workspace" \
  -w /workspace \
  api slaif-gateway secrets validate-env --env-file .env
```

The explicit bind mount makes the container update your host `.env` file.

The `--write` option intentionally writes generated runtime secrets into the
local clear-text `.env` file for bootstrap convenience. It does not print the
generated value, refuses `.env.example`, and will not replace existing
non-placeholder values unless you pass `--force`. The generator is not a
complete production secret-management system; production deployments should use
platform secret managers, Docker secrets, or equivalent operational secret
management where available.

Keep these rotation cautions in mind:

- Changing `TOKEN_HMAC_SECRET_V1` invalidates existing gateway keys signed with
  that secret unless the old secret remains configured.
- Changing `ADMIN_SESSION_SECRET` logs active admins out.
- Changing `ONE_TIME_SECRET_ENCRYPTION_KEY` can make existing encrypted
  one-time key deliveries undecryptable.

## 4. Build And Start Local Services

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

## 5. Create The First Admin

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

## 6. Add Basic Local Metadata

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

### Import provider, route, and pricing metadata before testing real OpenAI calls

Setting `OPENAI_UPSTREAM_API_KEY` is necessary for real OpenAI forwarding, but
it is not sufficient. SLAIF does not call OpenAI to discover models for
`/v1/models`. The models endpoint returns local route metadata that is:

- enabled;
- visible in the model list;
- allowed by the gateway key's endpoint and model policy.

If no local routes have been imported, `/v1/models` correctly returns an empty
OpenAI-shaped list:

```json
{"object":"list","data":[]}
```

If local pricing is missing, cost-limited requests fail closed before provider
forwarding. The recommended first-time path is:

1. Bootstrap the OpenAI Completions catalog.
2. Verify provider, route, and pricing metadata exists.
3. Create or edit a gateway key with the right allowed endpoints and models.
4. Test `/v1/models`.
5. Then test `chat.completions`.

The catalog bootstrap command seeds local metadata for the curated
Completions-compatible Chat Completions catalog. It creates or verifies the
`openai` provider config, exact `/v1/chat/completions` routes, and pricing rows.
It is about `/v1/chat/completions` now. Legacy `/v1/completions` is not
implemented in this repository state, and `--include-legacy-completions` is
rejected.

Fast local smoke path with explicit placeholder pricing:

```bash
docker compose run --rm api slaif-gateway bootstrap openai-completions-catalog \
  --pricing-mode placeholder \
  --confirm-placeholder-pricing \
  --apply
```

Verify the metadata before creating or testing a key:

```bash
docker compose run --rm api slaif-gateway providers list
docker compose run --rm api slaif-gateway routes list
docker compose run --rm api slaif-gateway pricing list
```

For the first gateway key, use these policy values:

```text
Allowed endpoints:
/v1/models
/v1/chat/completions

Allowed models:
gpt-4o-mini
```

Then test model visibility with the standard OpenAI-compatible client
variables. `OPENAI_API_KEY` is the gateway-issued key, not the upstream OpenAI
provider key:

```bash
export OPENAI_API_KEY="sk-slaif-..."
export OPENAI_BASE_URL="http://localhost:8000/v1"

curl -fsS "$OPENAI_BASE_URL/models" \
  -H "Authorization: Bearer $OPENAI_API_KEY" | python -m json.tool
```

Expected outcome: the returned `data` array should include `gpt-4o-mini`, or
whichever catalog model the key allows. If `data` is empty, use the "No Models
Are Visible" troubleshooting checklist below.

Placeholder pricing is only for local wiring smoke tests. It must not be used
for real budgeting decisions.

Real pricing path:

1. Copy the example file.
2. Replace placeholder prices with operator-reviewed pricing assumptions.
3. Run the bootstrap command in the default `require-file` mode.

```bash
cp docs/examples/openai-completions-pricing.example.csv local-openai-pricing.csv
# edit local-openai-pricing.csv with reviewed local pricing assumptions

docker compose run --rm api slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

The required pricing CSV columns are:

```text
provider,model,endpoint,currency,input_price_per_1m,output_price_per_1m
```

Both bootstrap modes create local metadata only. They do not call OpenAI, fetch
pricing, read provider key values, create gateway keys, or alter `.env`. The
provider config stores only the env var name `OPENAI_UPSTREAM_API_KEY`.
`OPENAI_API_KEY` remains the client-side gateway key variable.

Add FX metadata if any imported pricing uses a non-EUR currency. The example
below is a manual local assumption, not a fetched FX rate:

```bash
docker compose run --rm api slaif-gateway fx add \
  --base-currency USD \
  --quote-currency EUR \
  --rate 0.920000000
```

These commands create local metadata only. They do not call OpenAI or
OpenRouter.

## 7. Create A Gateway Key

Create a key for the owner. Replace `<owner-id>` with the owner ID:

```bash
docker compose run --rm api slaif-gateway keys create \
  --owner-id <owner-id> \
  --valid-days 30 \
  --cost-limit-eur 5.00 \
  --request-limit-total 100 \
  --allowed-endpoint /v1/models \
  --allowed-endpoint /v1/chat/completions \
  --allowed-model gpt-4o-mini
```

The plaintext gateway key is shown once. Save it somewhere appropriate for your
local test. The gateway does not store plaintext keys and cannot show old keys
again.

You may allow every catalog model by editing the key policy through the
dashboard or service workflows, or list only the selected catalog model IDs with
repeated `--allowed-model` options.

Before sending a chat request, verify local model visibility:

```bash
curl -fsS http://localhost:8000/v1/models \
  -H "Authorization: Bearer $GATEWAY_KEY"
```

## 8. Try The OpenAI Python Client

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
    model="gpt-4o-mini",
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

## 9. Check Fake Email In Mailpit

Mailpit is available at:

```text
http://localhost:8025
```

If you create or rotate a key with a pending/enqueued local email delivery, test
messages appear there instead of being sent to the internet.

## 10. Run Local Tests

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

## 11. Stop Or Clean Up

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

`/v1/models` only returns local enabled, visible routes allowed by the gateway
key policy. Check each item directly:

1. Did you run `slaif-gateway bootstrap openai-completions-catalog ... --apply`?
2. Does `slaif-gateway providers list` show `openai`?
3. Does `slaif-gateway routes list` show `gpt-4o-mini`, or the model you are
   requesting?
4. Does `slaif-gateway pricing list` show rows for `openai`, the model, and
   `chat.completions`?
5. Does the gateway key allow `/v1/models`?
6. Does the gateway key allow `/v1/chat/completions`?
7. Does the gateway key allow the requested model, or allow all catalog models?
8. Is the key active, not expired, not suspended, and not revoked?
9. Is `OPENAI_UPSTREAM_API_KEY` set in the API container?
10. Did you restart API, worker, and scheduler after changing `.env`?

Check that the upstream key is visible to the container without printing the
secret:

```bash
docker compose run --rm api python - <<'PY'
import os
key = os.environ.get("OPENAI_UPSTREAM_API_KEY", "")
print("OPENAI_UPSTREAM_API_KEY set:", bool(key))
print("prefix:", key[:7] + "..." if key else "<missing>")
PY
```

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
