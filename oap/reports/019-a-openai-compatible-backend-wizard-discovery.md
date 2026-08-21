# OAP Report — 019-a

Implementation head SHA: 11d8259438c7747167e90a1ec44c22ff25b1cdb1
Report publication commit: SELF

## Scope

Implemented the bounded, explicit setup workflow for existing generic
`openai_compatible` providers. The implementation adds one authenticated
operator discovery call, safe model-ID preview, CLI and CSRF-protected admin
surfaces, server-generated conservative Chat/Responses presets, explicit
local pricing modes, exact route/pricing conflict preflight, and caller-owned
PostgreSQL atomic route/pricing/audit creation. The activated `019-a` order and
`oap/active=019-a` were committed unchanged. No migration, public `/v1` route,
provider catalog artifact, real provider call, or production action was added.

## Focused tests and counts

- `tests/unit/test_openai_compatible_discovery.py`: 10 passed, covering exact
  URL/method/headers, no redirects, no mutation, secret-like/URL/duplicate/
  oversize/content-type/disabled/built-in/missing-secret negatives.
- `tests/unit/test_openai_compatible_setup.py`: 7 passed, covering all three
  endpoint presets, conservative capability snapshots, exact pricing metadata,
  and unsafe/incomplete confirmation rejection.
- `tests/unit/test_cli_providers.py`: 6 passed, including the
  `providers discover-models --json` safe preview.
- Affected existing unit/config/admin/template/documentation tests passed in
  the focused command; the final GitHub unit job collected the full unit suite
  and reported 3,201 passed and 1 failed.
- Scoped Ruff passed for all changed Python files.
- Jinja parsing passed for `providers/detail.html`, `discover.html`, and
  `discover_preview.html`.
- `python -m compileall -q app/slaif_gateway` passed.
- `python -m alembic heads` passed with exactly
  `0015_external_tool_exclusive_fence (head)`.
- `git diff --check` passed.

## PostgreSQL

The new integration file
`tests/integration/test_openai_compatible_setup_postgres.py` passed 1/1
against the exact disposable database `slaif_oap_019_a_test_<pid>` using
Unix-socket `TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/<database>`.
Alembic upgraded that database, the test proved four disabled routes, four EUR
pricing rows, setup audit state, and conflict rejection without additional
rows, and the database was dropped by an exact-name cleanup trap. No
`DATABASE_URL` was used for destructive setup. An initial TCP connection
attempt failed with the local PostgreSQL peer/password policy; it was not an
application test failure and the required Unix-socket run passed.

## GitHub checks

PR #245 is open, ready, based on `main`, and points to implementation head
`11d8259438c7747167e90a1ec44c22ff25b1cdb1`.

Completed checks:

- Analyze (javascript-typescript): passed.
- Analyze (python): passed.
- Analyze Python: passed.
- Docker Compose smoke: passed.
- Documentation hygiene: passed.
- OpenAI-compatible E2E tests: passed.
- Playwright browser smoke: passed.
- PostgreSQL integration tests: passed.
- CodeQL: passed.

`Unit, lint, and migration head` completed with 3,201 passed and 1 failed.
The sole failure is `tests/unit/test_oap_governance.py::test_initial_round_declares_new_pr_and_one_objective_one_pr`, which requires the
literal `PR mode: \`CREATE_NEW_PR\`` in the activated `019-a` order. The order
contains the equivalent required new-PR contract but not that literal. The
activated order was not edited because the coding-agent protocol prohibits
editing an activated order; this is therefore an unresolved orchestration
input defect, not an implementation failure. No skipped or pending GitHub
check is described as passed.

## Privacy, security, and safety evidence

- Discovery reads only the configured server-side bearer environment variable;
  it never accepts or returns the secret and sends only Authorization and
  `Accept: application/json` after clearing HTTPX defaults.
- Discovery uses exact `/v1/models`, no redirects, no retries, bounded response
  bytes/JSON shape/nesting/fields/model count/identifier length, and safe
  content-free errors. Raw body, headers, metadata, URLs, credentials, and
  cookies are not persisted, logged, or rendered.
- Preview is read-only and does not persist session, cookie, URL, hidden raw
  JSON, provider, route, pricing, FX, key, usage, or audit state. Execution
  reloads and re-probes the provider before mutation.
- Setup creates only explicit conservative capability objects. Hosted tools,
  media, stateful Responses, Codex, external tools, and provider authority are
  false. Routes default disabled unless separately confirmed.
- Pricing is Decimal-based operator-local metadata and is labeled as not
  provider invoice truth. No FX fetch or provider pricing call occurs.
- Tests use mocked numeric/example hosts only. No real OpenAI, OpenRouter,
  Qwen, vLLM, email, or production calls were made; no secrets were printed
  or committed.

## Documentation impact

Updated the current contracts in `AGENTS.md`, `README.md`, configuration,
deployment, database schema, forwarding, compatibility, and security docs to
describe explicit discovery/setup, LAN HTTP risk, server-side secrets,
local-pricing semantics, no automatic mutation, and Objective 020
qualification ownership.

## Publication and merge

This report is intended to be the only changed file in the final report-only
commit. The coding agent did not merge PR #245 and did not enable auto-merge.
