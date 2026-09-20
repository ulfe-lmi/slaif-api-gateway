# Quickstart

> **Status:** Canonical short quickstart
> **Goal:** Boot SLAIF API Gateway with no provider credentials, log in as
> admin, then make your first ordinary OpenAI-client request — in one sitting.

SLAIF API Gateway sits between your users and upstream LLM providers. Users
keep using standard OpenAI-compatible clients with `OPENAI_API_KEY` and
`OPENAI_BASE_URL`; the gateway checks local keys, quotas, routing, pricing, and
audit rules before forwarding allowed requests with server-side provider
credentials.

This quickstart has two milestones:

- **Milestone 1 — provider-free boot.** Clone, configure, build, start,
  migrate, create an admin, and log into the dashboard. No provider key is
  needed.
- **Milestone 2 — first OpenAI-client request.** Create local provider
  metadata, issue a narrow gateway key, and list the models your key can see
  with the official OpenAI client. Still no live provider inference.

For the full detailed tutorial (including real-provider calls, email in
Mailpit, testing, and troubleshooting), see the
[first-time operator guide](docs/first-time-operator-guide.md). For
installation, upgrades, and production topology, see
[INSTALL.md](INSTALL.md).

## What you need

- A **Linux** host. This quickstart is written and tested for Linux; we do not
  claim macOS or Windows support.
- **Git**, to clone the repository.
- **Docker** with **Compose v2**, to run PostgreSQL, Redis, Mailpit, and the
  Gateway containers.
- **Bash** and **curl** for the commands below.
- No real provider key for either milestone. No host Python installation just
  to boot.

Mailpit is a local fake email sink: it catches test email in a local web inbox
at `http://localhost:8025` instead of sending real email.

The development Compose file publishes host ports for Postgres, Redis, the
API, and Mailpit. It is a trusted local evaluation environment, not a hardened
public deployment; use the production topology in [INSTALL.md](INSTALL.md)
for real deployments.

## Milestone 1: Provider-free boot

### 1. Clone the repository

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
```

### 2. Create and protect the local environment file

`.env.example` is a curated local template, not a catalog of every setting.
Copy it and restrict permissions on shared systems:

```bash
cp .env.example .env
chmod 600 .env
```

Never commit `.env`.

### 3. Build the local images

```bash
docker compose build
```

### 4. Generate the three runtime secrets

The three runtime secrets protect HMAC key signing, admin sessions, and
encrypted one-time key deliveries. Generate them with the Gateway CLI inside
the `api` container. The container writes your host `.env` file through a
real bind mount, so no host Python installation is needed.

Define this helper once in your shell session. It runs a `slaif-gateway`
command inside the `api` image with the current directory mounted as the
working directory:

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

`--write` writes generated values into your clear-text local `.env` for
bootstrap convenience. It does not print generated values, refuses
`.env.example`, and will not replace an existing non-placeholder value unless
you pass `--force`. It is a bootstrap convenience, not a complete production
secret-management system. Rotation cautions: changing
`TOKEN_HMAC_SECRET_V1` invalidates gateway keys signed with that version,
changing `ADMIN_SESSION_SECRET` logs active admins out, and changing
`ONE_TIME_SECRET_ENCRYPTION_KEY` can make existing encrypted one-time key
deliveries undecryptable.

### 5. Start the infrastructure

```bash
docker compose up -d postgres redis mailpit
```

PostgreSQL stores durable gateway data, Redis stores temporary rate-limit and
broker state, and Mailpit catches local test email.

### 6. Run database migrations explicitly

API, worker, and scheduler containers never run migrations automatically:

```bash
docker compose run --rm api slaif-gateway db upgrade
```

You should see Alembic apply migrations through the latest head.

### 7. Start the Gateway

```bash
docker compose up -d api worker scheduler
```

### 8. Check health and readiness

```bash
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
```

`/healthz` answers `{"status":"ok"}`. `/readyz` reports database and schema
status. If the first readiness probe races startup, wait a few seconds and
retry; Compose only starts the API after PostgreSQL and Redis report healthy,
so a retry should succeed. If readiness keeps failing with a schema or
migration message, re-run the migration command from step 6 and retry.

### 9. Create the first administrator

Create the admin with the interactive hidden prompt. Run the command in a
terminal and type a strong password twice at the hidden prompts (the password
never appears in shell history or output):

```bash
docker compose run --rm api slaif-gateway admin create \
  --email admin@example.org \
  --display-name "Gateway administrator"
```

For non-interactive automation, `--password-stdin` reads the password from
standard input **to end of input**; it is not an interactive prompt. See the
[first-time operator guide](docs/first-time-operator-guide.md) for details.

### 10. Log in to the dashboard

Open `http://localhost:8000/admin/login` and sign in with the email and
password you just created. Login errors are intentionally generic.

Milestone 1 is complete: a running, provider-free Gateway with a working
admin login.

## Milestone 2: First OpenAI-client request

This milestone creates local metadata and one narrow key, then performs one
real request through the Gateway with the official OpenAI client. The request
(`GET /v1/models` through the client) exercises authentication, key policy,
and the local model catalog. It does **not** call a provider: local metadata
operations and `/v1/models` never contact OpenAI or OpenRouter.

### 1. Add reviewed local pricing and route metadata

Set the server-side upstream provider key in `.env` now so the provider
configuration is complete (you will not need it for this milestone's request,
but real provider calls require it):

```env
OPENAI_UPSTREAM_API_KEY=your-real-upstream-provider-key
```

Keep the value out of client examples: `OPENAI_API_KEY` is always the
**gateway-issued** client key, `OPENAI_UPSTREAM_API_KEY` is the server-side
provider key. After changing `.env`, apply it with
`./scripts/docker-refresh.sh --env-only` (or
`docker compose up -d --force-recreate api worker scheduler`).

Bootstrap the local OpenAI Chat Completions catalog. Copy the example pricing
file (EUR prices) and replace the zero placeholder prices with
operator-reviewed pricing assumptions before applying:

```bash
cp docs/examples/openai-completions-pricing.example.csv local-openai-pricing.csv
# edit local-openai-pricing.csv: set real EUR per-million-token prices
```

Then apply the catalog with the reviewed pricing file. The command reads the
CSV from your working directory, which is why it runs through the mounted
`run-cli` helper from step 4:

```bash
run-cli slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

For a fast local wiring smoke test you may instead use placeholder pricing,
but placeholder pricing is demo wiring only — never reviewed pricing, spend
protection, or invoice truth:

```bash
run-cli slaif-gateway bootstrap openai-completions-catalog \
  --pricing-mode placeholder \
  --confirm-placeholder-pricing \
  --apply
```

Before sending any request, verify the local metadata:

```bash
run-cli slaif-gateway providers list
run-cli slaif-gateway routes list
run-cli slaif-gateway pricing list
```

Reapplying an identical bootstrap is idempotent (rows report `exists`).
Reapplying a pricing file whose prices differ from existing enabled rows
reports `conflict` and blocks; update the existing pricing rows first (see the
[first-time operator guide](docs/first-time-operator-guide.md#pricing)) and
rerun. If any imported pricing used a non-EUR currency, add an FX row, for
example:

```bash
run-cli slaif-gateway fx add --base-currency USD --quote-currency EUR --rate 0.920000000
```

The example file is EUR, so no FX row is needed for it.

### 2. Create an owner and a narrow key

Owners record who is accountable for a key. Institutions and cohorts are
optional groupings, not required setup. Create a minimal owner:

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

The plaintext gateway key is shown **once**. Save it. The gateway stores only
an HMAC digest and cannot show the key again.

### 3. Perform one request with the OpenAI client

Use the standard OpenAI-compatible environment variables. You need a client
Python environment with the `openai` package; the cleanest option is a
disposable virtualenv on the host (or an equivalent disposable client
container). Set up the client environment:

```bash
python3 -m venv .venv-client
. .venv-client/bin/activate
python -m pip install -q openai
```

Point the client at the Gateway and issue one request:

```bash
export OPENAI_API_KEY="sk-slaif-..."   # the gateway-issued key from step 2
export OPENAI_BASE_URL="http://localhost:8000/v1"

python - <<'PY'
from openai import OpenAI

client = OpenAI()
models = client.models.list()
print([model.id for model in models.data])
PY
```

Expected outcome: the list includes `gpt-4o-mini` (the model your key
allows). If the list is empty, follow the
["No models are visible" checklist](docs/first-time-operator-guide.md#troubleshooting)
in the operator guide.

To go further — real `chat.completions` calls, streaming, mailpit email,
pricing deep-dive, and full troubleshooting — continue with the
[first-time operator guide](docs/first-time-operator-guide.md).

## Stop and clean up

Stop the containers and keep your data (the named `postgres-data` and
`redis-data` volumes are preserved):

```bash
docker compose down
```

**Destructive:** delete the local data volumes as well. This deletes all local
gateway data (keys, quotas, usage, audit):

```bash
docker compose down -v
```

Use the last command only when you intentionally want to wipe the local
Gateway.

## Where to go next

- [INSTALL.md](INSTALL.md) — installation overview, persistence, production
  topology, upgrades, and stop/cleanup semantics.
- [First-time operator guide](docs/first-time-operator-guide.md) — the full
  detailed tutorial: real-provider calls, Mailpit email, local testing,
  refresh workflows, and troubleshooting.
- [Documentation home](docs/README.md) — configuration, compatibility
  contracts, security, and operations.
- [CONTRIBUTING.md](CONTRIBUTING.md) — development environment and checks.
