# Quickstart

> **Status:** Canonical short quickstart
> **Goal:** Boot SLAIF API Gateway with no provider credentials, log in as
> admin, then send one bounded model call using an explicitly configured
> server-side provider credential — in one sitting.

SLAIF API Gateway sits between your users and upstream LLM providers. Users
keep using standard OpenAI-compatible clients with `OPENAI_API_KEY` and
`OPENAI_BASE_URL`; the gateway checks local keys, quotas, routing, pricing,
and audit rules before forwarding allowed requests with server-side provider
credentials.

This quickstart has two milestones:

- **Milestone 1 — provider-free boot.** Clone, configure, build, start,
  migrate, create an admin, and log into the dashboard. No provider key and
  no host Python are needed.
- **Milestone 2 — first model call.** Add one server-side provider
  credential, create local provider/route/pricing metadata, issue a narrow
  gateway key, verify **local** model discovery, and send one bounded
  `chat.completions` call. Only that final inference call is **external**:
  it contacts the upstream provider and consumes key quota/cost.

For the detailed tutorial (placeholder-pricing branch, FX metadata, secret
rotation, non-interactive admin, real-provider smoke test, troubleshooting)
see the [first-time operator guide](docs/first-time-operator-guide.md); for
installation, upgrades, and production topology see [INSTALL.md](INSTALL.md).

## What you need

Milestone 1 (provider-free boot): a **Linux** host (written and tested for
Linux; no macOS/Windows claim), **Git**, **Docker** with **Compose v2**,
**Bash**, and **curl**.

Milestone 2 (first model call) additionally needs: host **Python 3.12 or
newer**, used only for a disposable client virtualenv that talks to the
Gateway, and one real server-side provider credential for the selected
upstream — `OPENAI_UPSTREAM_API_KEY` here — set in `.env` at Milestone 2,
step 1. Only the external inference call uses it.

Mailpit (local fake email sink) catches test email at
`http://localhost:8025` instead of sending real email. The development
Compose file publishes host ports on host interfaces; it is a trusted local
evaluation environment, not a hardened public deployment.

## Milestone 1: Provider-free boot

### 1. Clone the repository

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
```

### 2. Create and protect the local environment file

`.env.example` is a curated local template, not a catalog of every setting;
never commit the result:

```bash
cp .env.example .env
chmod 600 .env
```

### 3. Build the local images

```bash
docker compose build
```

### 4. Generate the three runtime secrets

The secrets protect HMAC key signing, admin sessions, and encrypted
one-time key deliveries. Generate them with the Gateway CLI inside the
`api` image; it writes your host `.env` through a bind mount, so Milestone
1 needs no host Python. Define this helper once in your shell session:

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

`--write` is a clear-text local bootstrap convenience, not a production
secret-management system; rotation cautions and non-interactive
alternatives live in the operator guide.

### 5. Start the infrastructure and run migrations explicitly

```bash
docker compose up -d postgres redis mailpit

docker compose run --rm api slaif-gateway db upgrade
```

API, worker, and scheduler containers never run migrations automatically;
you should see Alembic apply migrations through the latest head.

### 6. Start the Gateway

```bash
docker compose up -d api worker scheduler
```

### 7. Check health and readiness

```bash
curl --fail http://localhost:8000/healthz
curl --fail http://localhost:8000/readyz
```

`/healthz` answers `{"status":"ok"}`; `/readyz` reports database and schema
status. If the first readiness probe races startup, wait a few seconds and
retry; a persistent schema or migration message means re-run step 5.

### 8. Create the first administrator

Create the admin with the interactive hidden prompt; type a strong password
twice (the password never appears in shell history or output):

```bash
docker compose run --rm api slaif-gateway admin create \
  --email admin@example.org \
  --display-name "Gateway administrator"
```

### 9. Log in to the dashboard

Open `http://localhost:8000/admin/login` and sign in with the email and
password you just created. Login errors are intentionally generic.

Milestone 1 is complete: a running, provider-free Gateway with a working
admin login.

## Milestone 2: First model call

Two different kinds of calls happen here, and the distinction matters:

- `GET /v1/models` is **LOCAL** discovery, served from local route
  metadata; it never contacts the provider.
- `POST /v1/chat/completions` is **EXTERNAL** inference, forwarded to the
  upstream provider with your server-side credential; it consumes the
  key's quota and cost limits.

### 1. Configure the server-side provider credential

Put the real upstream key in `.env` — the only step that needs a real key —
then apply it:

```env
OPENAI_UPSTREAM_API_KEY=<your real upstream provider key>
```

```bash
./scripts/docker-refresh.sh --env-only
```

If a health probe fails immediately after this refresh, the single retry
window in [INSTALL's health-probe recovery](INSTALL.md#health-probe-after-recreation)
distinguishes a startup race from a persistent failure.

Keep the two key worlds distinct: `OPENAI_API_KEY` is always the
**gateway-issued** client key; `OPENAI_UPSTREAM_API_KEY` is server-side and
never appears in client examples.

### 2. Bootstrap local catalog metadata with reviewed pricing

Copy the example pricing file (EUR, placeholder values) and replace the
placeholder prices with operator-reviewed pricing assumptions:

```bash
cp docs/examples/openai-completions-pricing.example.csv local-openai-pricing.csv
# edit local-openai-pricing.csv: set EUR per-million-token prices
```

Then apply the catalog with the reviewed pricing file (the command reads the
CSV from your working directory, so it runs through the mounted `run-cli`
helper from Milestone 1, step 4):

```bash
run-cli slaif-gateway bootstrap openai-completions-catalog \
  --pricing-file local-openai-pricing.csv \
  --apply
```

Evaluation setup friction: the default catalog has ten models
(`gpt-5.2` through `gpt-4o-mini`, listed by `routes list`), and the
bootstrap requires a pricing row for **every** selected model even if your
key will use only one; there is no single-model bootstrap switch today.
The [operator guide](docs/first-time-operator-guide.md#pricing) documents
the placeholder-pricing alternative and how to replace pricing rows
afterwards.

Before sending any request, verify the local metadata:

```bash
run-cli slaif-gateway providers list
run-cli slaif-gateway routes list
run-cli slaif-gateway pricing list
```

Reapplying an identical bootstrap is idempotent (rows report `exists`); a
pricing file whose prices differ from existing enabled rows reports
`conflict` and blocks until you replace the existing rows.

### 3. Create an owner and a narrow key

Owners record who is accountable for a key; institutions and cohorts are
optional groupings. Create a minimal owner, then a key with a narrow
model/endpoint policy and a finite evaluation quota (replace `<owner-id>`):

```bash
run-cli slaif-gateway owners create \
  --name Ada \
  --surname Lovelace \
  --email ada@example.org
```

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

The plaintext gateway key is shown **once**; the gateway stores only an
HMAC digest and cannot show it again.

### 4. Verify local model discovery

Set up a disposable host virtualenv with the repository's qualified SDK
version, point the standard client variables at the Gateway, and list the
models your key allows:

```bash
python3 -m venv .venv-client
. .venv-client/bin/activate
python -m pip install -q openai==3.14.1

export OPENAI_API_KEY="sk-slaif-..."   # the gateway-issued key from step 3
export OPENAI_BASE_URL="http://localhost:8000/v1"

python - <<'PY'
from openai import OpenAI

client = OpenAI()
print([model.id for model in client.models.list().data])
PY
```

Expected outcome: the list contains `gpt-4o-mini`. This request is
**LOCAL** and never contacts the provider. If the list is empty, use the
["No models are visible" checklist](docs/first-time-operator-guide.md#troubleshooting).

### 5. Send one bounded model call (external)

With the same client environment, send one small Chat Completions request:

```bash
python - <<'PY'
from openai import OpenAI

client = OpenAI()
resp = client.chat.completions.create(
    model="gpt-4o-mini",
    max_completion_tokens=100,
    messages=[{"role": "user", "content": "Say hello from SLAIF."}],
)
print(resp.choices[0].message.content)
PY
```

This is the **EXTERNAL** step: the gateway forwards it to the upstream
provider with your server-side credential, and the completed usage is
finalized against the key's quota and cost limits. For streaming, the
checked-in real-provider smoke script, and full troubleshooting, continue
with the [first-time operator guide](docs/first-time-operator-guide.md).

## Stop and clean up

`docker compose down` stops the containers and preserves the named
`postgres-data` and `redis-data` volumes. **Destructive:**
`docker compose down -v` also deletes those volumes and with them all local
gateway data (keys, quotas, usage, audit); use it only to intentionally
wipe the local Gateway. [INSTALL.md](INSTALL.md) documents the full
stop/cleanup semantics.

## Where to go next

- [INSTALL.md](INSTALL.md) — installation overview, persistence, production
  topology, upgrades, and stop/cleanup semantics.
- [First-time operator guide](docs/first-time-operator-guide.md) — the full
  detailed tutorial: placeholder-pricing branch, FX metadata, secret
  rotation, non-interactive admin, real-provider smoke, troubleshooting.
- [Documentation home](docs/README.md) — configuration, compatibility
  contracts, security, and operations.
- [CONTRIBUTING.md](CONTRIBUTING.md) — development environment and checks.
