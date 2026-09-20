# First-Time Operator Guide

> **Status:** Current detailed local tutorial for first-time operators
> **Short path:** The [QUICKSTART](../QUICKSTART.md) is the canonical one-sitting
> short quickstart; this guide is the detailed variant with the same steps plus
> real-provider wiring, Mailpit, testing, and troubleshooting.
> **Not:** Production deployment or real-provider qualification

This guide starts SLAIF API Gateway on your computer and walks through the
first admin, local metadata, gateway-key setup, an optional real-provider
smoke, Mailpit, local tests, and troubleshooting. You do not need real OpenAI
or OpenRouter keys for the basic local admin smoke checks. You need a real
upstream provider key only when you want the gateway to forward a real `/v1`
request.

SLAIF API Gateway sits between users and upstream LLM providers. Users keep
using normal OpenAI-compatible clients with `OPENAI_API_KEY` and
`OPENAI_BASE_URL`; the gateway checks local keys, quotas, routing, pricing, and
audit rules before it forwards allowed requests with the server-side provider
key.

## What You Need

- A **Linux** host. This guide is written and tested for Linux; we do not claim
  macOS or Windows support.
- **Git**, to clone the repository.
- **Docker** with **Compose v2**, to run PostgreSQL, Redis, Mailpit, the API,
  and background workers locally.
- **Bash** and **curl** for the commands below.
- Host **Python 3.12** or newer, only for the real-provider client smoke
  (disposable venv) and for tests outside Docker (see
  [Contributing](../CONTRIBUTING.md)).
- No real provider key for the local dashboard smoke.
- A real upstream provider key only for real provider calls.

Mailpit is included for local fake email. It catches email in a local web
inbox instead of sending real external email.

The development Compose file publishes host ports for Postgres, Redis, the
API, and Mailpit. It is a trusted local evaluation environment, not a
hardened public deployment; use the production topology in
[INSTALL.md](../INSTALL.md) for real deployments.

## Clone The Repository

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
```

You should now be inside the repository directory.

## Create A Local Environment File

```bash
cp .env.example .env
chmod 600 .env
```

`.env.example` contains development placeholders. They are useful for trying
the project locally, but they are not production secrets. Before any real
deployment you must replace HMAC, session, database, SMTP, encryption, and
provider secrets. The local template enables Redis rate limiting and DEBUG
console logs so first-time Docker failures are easier to see. Production
should switch back to INFO logging with structured JSON. `.env` is a
clear-text local runtime configuration file; never commit it.

For a real OpenAI provider call later, put the server-side upstream key in
`.env` as:

```env
OPENAI_UPSTREAM_API_KEY=replace-with-real-upstream-provider-key
```

This is different from the user's client key. Users set `OPENAI_API_KEY` to a
gateway-issued key.

## Build The Local Image

Build the local image (the secret-generation helper below runs inside the
`api` image, so build it first):

```bash
docker compose build
```

## Generate Local Runtime Secrets

`.env.example` has placeholders for server runtime secrets. Generate them with
SLAIF's CLI instead of writing ad hoc Python snippets. These values protect
server-side HMAC signing, admin sessions, and encrypted one-time key
deliveries. They are not user gateway keys.

The recommended workflow is Docker-only: the CLI runs inside the `api` image
and writes your host `.env` through a real bind mount, so no host Python
installation is needed. Define this helper once in your shell session:

```bash
run-cli() {
  docker compose run --rm --no-deps \
    --user "$(id -u):$(id -g)" \
    -v "$PWD:/workspace" \
    -w /workspace \
    api "$@"
}
```

Then generate and validate:

```bash
run-cli slaif-gateway secrets generate hmac --version 1 --env-file .env --write
run-cli slaif-gateway secrets generate admin-session --env-file .env --write
run-cli slaif-gateway secrets generate one-time --env-file .env --write
run-cli slaif-gateway secrets validate-env --env-file .env
```

The explicit bind mount makes the container update your host `.env` file.

The `--write` option intentionally writes generated runtime secrets into the
local clear-text `.env` file for bootstrap convenience. It does not print the
generated value, refuses `.env.example`, and will not replace existing
non-placeholder values unless you pass `--force`. The generator is not a
complete production secret-management system; production deployments should
use platform secret managers, Docker secrets, or equivalent operational
secret management where available.

Keep these rotation cautions in mind:

- Changing `TOKEN_HMAC_SECRET_V1` invalidates existing gateway keys signed
  with that secret unless the old secret remains configured.
- Changing `ADMIN_SESSION_SECRET` logs active admins out.
- Changing `ONE_TIME_SECRET_ENCRYPTION_KEY` can make existing encrypted
  one-time key deliveries undecryptable.


## Start Local Services

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

You should see JSON with healthy database and schema status. If readiness
fails with a schema or migration message, run
`docker compose run --rm api slaif-gateway db upgrade` again and retry.

## Update Or Restart The Docker Install

Use the bundled refresh script for common local maintenance. It is
non-destructive: it does not run `docker compose down -v`, delete volumes,
overwrite `.env`, or reset git state.

After changing `.env`:

```bash
./scripts/docker-refresh.sh --env-only
```

Manual equivalent:

```bash
docker compose up -d --force-recreate api worker scheduler
```

After pulling fresh code. This requires a **clean tracked worktree on
`main`** (the script refuses otherwise); it fetches and fast-forwards
`main`, then builds, runs migrations, recreates the services, and
health-checks:

```bash
./scripts/docker-refresh.sh --pull
```

Manual equivalent:

```bash
git pull --ff-only
docker compose build api worker scheduler
docker compose run --rm api slaif-gateway db upgrade
docker compose up -d --force-recreate api worker scheduler
docker compose ps
curl -fsS http://localhost:8000/healthz
curl -fsS http://localhost:8000/readyz
```

The final health curls are single attempts and can race service startup
right after `--force-recreate`; if one fails immediately after a refresh,
retry with a bounded wait (see the refresh section in
[INSTALL.md](../INSTALL.md)) rather than assuming failure.

After local code changes, run the script without flags:

```bash
./scripts/docker-refresh.sh
```

Do not run `docker compose down -v` unless you intentionally want to delete
local PostgreSQL and Redis volumes.

## Create The First Admin

Create the admin account with the interactive hidden prompt. Run the command
in a terminal and type a strong password twice at the hidden prompts (the
password never appears in shell history or output):

```bash
docker compose run --rm api slaif-gateway admin create \
  --email admin@example.org \
  --display-name "Gateway administrator"
```

The command also accepts `--password` for explicit automation, but the
preferred path is the hidden prompt because the password never appears in a
shell command line.

`--password-stdin` is a separate non-interactive mode: it reads the password
from standard input **to end of input** (it does not stop at the first
newline, and it never echoes the password). Use it only from pipelines or
automation that can guarantee EOF-delimited input; do not present it as an
interactive password prompt.

Open the dashboard:

```text
http://localhost:8000/admin/login
```

Log in with `admin@example.org` and the password you supplied. Login errors
are intentionally generic.

## Pricing

The gateway needs local pricing metadata before cost-limited requests can be
admitted. There are two supported bootstrap modes, both local metadata
operations only: they do not call OpenAI, fetch pricing, read provider key
values, create gateway keys, or alter `.env`.

### Placeholder pricing (demo wiring only)

A fast local wiring smoke test can use explicit placeholder pricing:

```bash
run-cli slaif-gateway bootstrap openai-completions-catalog \
  --pricing-mode placeholder \
  --confirm-placeholder-pricing \
  --apply
```

Placeholder pricing is **demo wiring only**. It is never reviewed pricing,
never spend protection, and never invoice truth. Before sending real
provider calls with a cost limit, replace it with reviewed pricing.

### Reviewed pricing (required before real calls)

1. Copy the example file.
2. Replace placeholder prices with operator-reviewed pricing assumptions.
   The default catalog has ten models (`gpt-5.2` through `gpt-4o-mini`),
   and the bootstrap requires a pricing row for **every** selected model —
   even if your key will use only one. There is no single-model bootstrap
   switch today; a bounded single-model evaluation bootstrap is a
   reasonable future improvement, not a supported option.
3. Run the bootstrap command in the default `require-file` mode.

```bash
cp docs/examples/openai-completions-pricing.example.csv local-openai-pricing.csv
# edit local-openai-pricing.csv with reviewed local pricing assumptions

run-cli slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

The command reads the CSV from the working directory, which is why it runs
through the mounted `run-cli` helper defined above. A plain
`docker compose run --rm api ... --pricing-file local-openai-pricing.csv`
without the mount would not see your host CSV.

The required pricing CSV columns are:

```text
provider,model,endpoint,currency,input_price_per_1m,output_price_per_1m
```

### Reapplying the bootstrap

- Reapplying an identical bootstrap is idempotent: matching rows report
  `exists` and the run completes.
- Reapplying a pricing file whose prices differ from existing enabled rows
  reports `conflict` and blocks. Replace the existing rows first (next
  section), then rerun.
- Row statuses are `created`, `exists`, `conflict`, `missing`, and
  `not_implemented`; any `conflict` or `missing` row fails the run.

### Replacing existing pricing rows

When a bootstrap used placeholder or now-outdated prices, replace the rows
with reviewed prices through the admin dashboard. The `pricing` CLI group
has `add`, `list`, `show`, `disable-model`, and `import`, but no
row-update command, and the CLI `import` creates rows only (a duplicate
against an existing rule fails), so row replacement goes through the
dashboard.

Batch path (recommended for a reviewed CSV):

1. Open the pricing import page:
   `http://localhost:8000/admin/pricing/import`.
2. Paste or upload the revised CSV (same columns as
   `docs/examples/openai-completions-pricing.example.csv`).
3. Preview: each row is classified against the existing enabled rows; rows
   matching an existing rule are classified `update`.
4. Enter an audit reason and confirm; execute applies the updates.

Per-row path: from the pricing list, open a row and its **Edit** page
(`/admin/pricing/<pricing-rule-id>/edit`), set the reviewed per-million-token
prices, and submit with the required reason.

After replacing, verify with `run-cli slaif-gateway pricing list` that the
effective prices are the reviewed values you intended.

### FX metadata

Add FX metadata if any imported pricing uses a non-EUR currency. The example
file is EUR, so no FX row is needed for it. The command below is a manual
local assumption, not a fetched FX rate:

```bash
run-cli slaif-gateway fx add \
  --base-currency USD \
  --quote-currency EUR \
  --rate 0.920000000
```

### Verify the metadata

Verify provider, route, and pricing metadata before creating or testing a
key:

```bash
run-cli slaif-gateway providers list
run-cli slaif-gateway routes list
run-cli slaif-gateway pricing list
```

The provider config stores only the env var name `OPENAI_UPSTREAM_API_KEY`.
`OPENAI_API_KEY` remains the client-side gateway key variable.

## Create An Owner And A Gateway Key

Owners record who is accountable for a key. Institutions and cohorts are
optional groupings, not required setup. Institutions attach to owners
(`owners create --institution-id`); cohorts attach to keys
(`keys create --cohort-id`). If your organization wants them, create them
first (`institutions create`, `cohorts create`); the beginner path uses a
bare owner:

```bash
run-cli slaif-gateway owners create \
  --name Ada \
  --surname Lovelace \
  --email ada@example.org
```

Create a key with a narrow model/endpoint policy and a finite evaluation
quota. Replace `<owner-id>` with the owner ID printed by the previous command:

```bash
run-cli slaif-gateway keys create \
  --owner-id <owner-id> \
  --valid-days 30 \
  --cost-limit-eur 5.00 \
  --request-limit-total 100 \
  --allowed-endpoint /v1/models \
  --allowed-endpoint /v1/chat/completions \
  --allowed-model gpt-4o-mini
```

The plaintext gateway key is shown **once**. Save it. The gateway does not
store plaintext keys and cannot show old keys again. To group a key by
cohort, pass `--cohort-id <cohort-id>` to `keys create`.

You may allow every catalog model by editing the key policy through the
dashboard or service workflows, or list only the selected catalog model IDs
with repeated `--allowed-model` options.

If a key policy is wrong, open the admin dashboard key detail page and use
**Update Request Policy**. Allowed models are model IDs such as `gpt-4o-mini`;
allowed endpoints are `/v1` paths such as `/v1/models` and
`/v1/chat/completions`. The form validates implemented endpoints and existing
enabled routes so endpoint paths cannot be saved as models, and model IDs
cannot be saved as endpoints.

### Verify model visibility with the standard client variables

`OPENAI_API_KEY` is the gateway-issued key, not the upstream OpenAI provider
key. `OPENAI_BASE_URL` points the client at your local gateway.

```bash
export OPENAI_API_KEY="sk-slaif-..."   # the gateway-issued key from above
export OPENAI_BASE_URL="http://localhost:8000/v1"

curl -fsS "$OPENAI_BASE_URL/models" \
  -H "Authorization: Bearer $OPENAI_API_KEY" | python3 -m json.tool
```

Expected outcome: the returned `data` array should include `gpt-4o-mini`, or
whichever catalog model the key allows. If `data` is empty, use the
["No Models Are Visible"](#no-models-are-visible) troubleshooting checklist
below.

## Real-Provider Smoke Test

This step requires a real `OPENAI_UPSTREAM_API_KEY` in `.env` (applied with
`./scripts/docker-refresh.sh --env-only`) and reviewed pricing applied as in
[Pricing](#pricing). If either is missing, real provider forwarding fails
safely; the local dashboard, database, migrations, key creation, and `/v1/models`
checks still work without a real provider key.

Install the OpenAI client in a disposable host environment, pinned to the
repository's qualified SDK version:

```bash
python3 -m venv .venv-client
. .venv-client/bin/activate
python -m pip install -q openai==3.14.1
```

Run the checked-in example:

```bash
python examples/openai_gateway_smoke.py
```

Optional model override:

```bash
SLAIF_SMOKE_MODEL=gpt-5.2 python examples/openai_gateway_smoke.py
```

`client.models.list()` tests key endpoint policy and route visibility.
`chat.completions.create()` tests route resolution, pricing/quota reservation,
provider forwarding, and accounting finalization.

## Check Fake Email In Mailpit

Mailpit is available at:

```text
http://localhost:8025
```

If you create or rotate a key with a pending/enqueued local email delivery,
test messages appear there instead of being sent to the internet.

## Run Local Tests

Unit tests do not need PostgreSQL, Redis, Docker, real provider keys, or
email. The focused checks are documented in
[Contributing](../CONTRIBUTING.md); the short form:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests/unit
python -m ruff check app tests
alembic heads
git diff --check
```

Database-backed tests use `TEST_DATABASE_URL`, not `DATABASE_URL`; the
parallel-safety analysis is in
[testing-parallelism.md](testing-parallelism.md). The normal tests mock
upstream providers. They do not need real OpenAI or OpenRouter keys and do
not send real external email.

## Stop Or Clean Up

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

The default API port is `8000`, Mailpit web port is `8025`, PostgreSQL host
port is `15432`, and Redis host port is `16379`. Change the matching value in
`.env`, for example:

```env
API_HOST_PORT=18000
```

Then refresh with `./scripts/docker-refresh.sh --env-only`.

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

Make sure you created the admin account after migrations, and use the email
and password from the `admin create` command. Login errors are intentionally
generic.

### No Models Are Visible

`/v1/models` only returns local enabled, visible routes allowed by the
gateway key policy. Check each item directly:

1. Did you run `slaif-gateway bootstrap openai-completions-catalog ... --apply`?
2. Does `slaif-gateway providers list` show `openai`?
3. Does `slaif-gateway routes list` show `gpt-4o-mini`, or the model you are
   requesting?
4. Does `slaif-gateway pricing list` show rows for `openai`, the model, and
   `chat.completions`?
5. Does the gateway key allow `/v1/models`?
6. Does the gateway key allow `/v1/chat/completions`?
7. Does the gateway key allow the requested model, or allow all catalog
   models?
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
- [Production Compose deployment](deployment-production.md)
- [Security model](security-model.md)
- [OpenAI compatibility](openai-compatibility.md)
- [Provider forwarding contract](provider-forwarding-contract.md)
- [Compatibility matrix](compatibility-matrix.md)
- [RC-beta release checklist](rc-beta.md)
- [Verification index](verification/README.md)

RC-beta status means the implemented and documented scope has been verified.
It is not a production certification, compliance attestation, or
penetration-test report. Real deployments still need operator-managed
secrets, HTTPS/Nginx hardening, backups, monitoring, and incident response
plans.
