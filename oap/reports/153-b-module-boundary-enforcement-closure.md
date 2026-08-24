# OAP report — 153-b module boundary enforcement closure

- Objective: `153-b`
- Active selector: `153-b`
- PR: #289
- Branch: `oap/153-client-server-module-architecture`
- Base: `main @ 05f7b6deddea3f742acba686fbeedc9088c4b057`
- Implementation head: `fb2c0e1`
- Order/selector commit: `54904fd`
- Prior immutable report: `610e5e2ac6658aa72c255481b2bb41650c27c309`
- Report publication commit: SELF

## Closure delivered

- `normalize_default_client_request(...)` now resolves the default module through
  `get_client_module(DEFAULT_CLIENT_MODULE_ID)` before invoking `normalize`; the
  helper no longer bypasses the finite registry singleton.
- The architecture test parses every Python source under
  `app/slaif_gateway/modules/servers/` and rejects path-aware imports of
  Gateway authentication/dependencies, database, Redis, quota, accounting,
  pricing, audit, reconciliation, key, or dynamic-loading modules. Provider
  adapter, diagnostics, header, streaming, schema, settings, and pure contract
  imports remain allowed.
- AST/callsite guardrails prove the provider factory imports and calls
  `resolve_server_module`, `ensure_client_server_pair`, and
  `build_server_adapter`, while directly instantiating no provider/facial class
  and calling no legacy `get_module_adapter` production path.
- Focused truth checks prove immutable finite registries and pair metadata,
  unknown module/pair fail-closed behavior, the facial legacy path is
  re-export-only, and tracked Git paths contain no `__pycache__` entries.

These are executable enforcement tests; no module behavior, authority, provider
selection, URL validation, authentication, quota/accounting, facial behavior,
privacy, retry, or error shape was widened or changed.

## Verification

Local focused evidence passed with provider/database/upstream-test environment
variables unset:

- `git diff --check`.
- `python scripts/check_documentation.py` (`DOCUMENTATION_CHECK=OK`, 79 files).
- Ruff project-rule checks on the changed Python paths.
- Focused module architecture, module provider, provider factory, facial
  adapter, Chat/Responses forwarding/quota, OpenRouter streaming, and related
  registry tests.
- The focused PostgreSQL/provider tests from 153-a remain passing. No new
  PostgreSQL rerun was required by the order because 153-b changed only the
  pure client registry helper and architecture tests; final CI PostgreSQL
  verification was still required and passed.
- Existing focused official-client and mocked Chat/Responses evidence remains
  passing; final CI E2E verification passed.
- No real provider, credential, Local Coding, Qwen, Codex, OpenCode, migration,
  production data, deployment, email, release, or external discovery action.

The first 153-b unit CI attempt exposed only a test portability assumption:
the shallow GitHub checkout has no `origin/main` ref. The cache guard was
changed to inspect tracked paths with `git ls-files`, preserving the invariant.
The final implementation head rerun passed all ten checks:

- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL
- Docker Compose smoke
- Documentation hygiene
- OpenAI-compatible E2E tests
- Playwright browser smoke
- PostgreSQL integration tests
- Unit, lint, and migration head

Green CI is repository verification only. It is not production certification,
provider/model qualification, security or compliance certification, invoice
truth, support, or SLA evidence.

## Scope and topology

The continuation amends PR #289 only. Previous 153-a report history is
immutable. The report-only commit has implementation head `fb2c0e1` as its first
parent and must change only this report. Current-main ancestry and the exact
153-b selector/order bytes were verified before publication.

Codex 0.149, Local Coding, OpenCode, hosted tools, signed identity, dynamic
plugins, migrations, releases, deployment, certification, compliance, invoice,
support, and SLA work remain outside this objective.
