# Contributing

> **Status:** Contributor entry point

SLAIF API Gateway is open source under the Apache License 2.0. Small, focused
patches are welcome. Repository maintainers use an internal orchestration
workflow for their own changes; it is not a prerequisite for community
patches.

## Development environment

- Python **3.12 or newer**, Git, and Docker with Compose v2 (for Compose
  validation and container-based checks).

```bash
git clone https://github.com/ulfe-lmi/slaif-api-gateway.git
cd slaif-api-gateway
python -m pip install -e ".[dev]"
```

## Focused checks

Run the focused set before opening a pull request. The full CI matrix
(plus PostgreSQL integration, mocked E2E, browser smoke, Docker Compose
smoke, CodeQL, and documentation hygiene) runs on every PR:

```bash
python -m pytest tests/unit
python -m ruff check app tests
alembic heads
docker compose config --quiet
python scripts/check_documentation.py
git diff --check
```

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
