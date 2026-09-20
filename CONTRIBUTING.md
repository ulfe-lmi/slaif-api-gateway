# Contributing

> **Status:** Contributor entry point

SLAIF API Gateway is open source under the Apache License 2.0. Small, focused
patches are welcome. Repository maintainers use an internal orchestration
workflow for their own changes; it is not a prerequisite for community
patches.

## Development environment

- Python **3.12 or newer**, Git, and Docker with Compose v2 (for Compose
  validation and container-based checks).

Set up a virtualenv. On standard externally managed Linux Pythons (for
example Ubuntu 24.04), installing directly into the system interpreter is
refused, so use the venv for every command below:

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Focused checks

Run the focused set for your change before opening a pull request. The full
CI matrix (plus PostgreSQL integration, mocked E2E, browser smoke, Docker
Compose smoke, CodeQL, and documentation hygiene) runs on every PR, so a
documentation patch does not need the full local unit suite.

Documentation-only patches:

```bash
python scripts/check_documentation.py
git diff --check
```

Code or configuration patches add the focused local set:

```bash
python -m pytest tests/unit
python -m ruff check app tests
alembic heads
git diff --check
```

Compose validation needs the local template, because the development
Compose file references `.env` (`env_file`) and fails without it. Copy the
template first (never commit the copy), then validate:

```bash
cp .env.example .env
docker compose config --quiet
```

No provider credentials, running services, or database are needed for any
of the checks above.

Documentation changes must keep the repository link graph consistent: every
Markdown file must remain reachable from the root `README.md` or
`docs/README.md`, links and anchors must resolve, and the documentation
checker's brand and as-of-marker rules must pass.

## Pull request expectations

- Keep changes small and focused; one concern per pull request.
- Never commit secrets, provider keys, `.env` files, session material, or
  request content.
- User-facing examples must use only the standard OpenAI-compatible
  environment names (`OPENAI_API_KEY`, `OPENAI_BASE_URL`) with
  gateway-issued keys; do not introduce custom client variables.
- Tests must not require real OpenAI/OpenRouter keys; upstream calls are
  mocked except for the explicitly disabled real-provider test group.
- If your change touches documentation, run the focused checks above and
  mention the documentation impact in the pull request.

## Where to look

- [Documentation home](docs/README.md) — the full task navigation.
- [Module architecture](docs/module-architecture.md) and
  [database schema](docs/database-schema.md) for the internal design.
- [Testing parallelism](docs/testing-parallelism.md) and
  [HPC test preparation](docs/testing-hpc.md) for the verification harness.
- [Security reporting](SECURITY.md) — report vulnerabilities privately; do
  not open public issues with exploit details.
