# OAP Work Order — 153-c

PR mode: `AMEND_EXISTING_PR`
PR: `#289`
Branch: `oap/153-client-server-module-architecture`
Base: `main @ 05f7b6deddea3f742acba686fbeedc9088c4b057`
Current remote head: `7200f30ea18b7a7cedd7e2a3415a52ad3bbaf920`

## Objective and reason

Close the remaining false-negative paths in the server-module authority-import
guard. Independent review of 153-b confirmed the guard is path-aware, but its
forbidden prefix list does not match several real repository namespaces named
by the order:

- `slaif_gateway.services.auth_service` is not matched by
  `slaif_gateway.api.auth`;
- top-level `redis` / `redis.asyncio` is not forbidden;
- `slaif_gateway.services.rate_limit_service` is not forbidden; and
- `slaif_gateway.services.reservation_reconciliation` is not matched by
  `slaif_gateway.services.reconciliation`.

A future server module could therefore import authentication, Redis/rate-limit,
or reservation-reconciliation authority while the architecture test remained
green. Repair only the guard and prove it against representative actual module
paths. Runtime behavior is unchanged.

## Verified starting state

- PR #289 is open, non-draft, mergeable, and has no auto-merge.
- Report head `7200f30ea18b7a7cedd7e2a3415a52ad3bbaf920` has implementation head
  `fb2c0e1262267972f70b25915e37f2064447671d` as first parent and changes only
  the 153-b report.
- All ten final-head checks passed. Prior 153-a and 153-b reports are immutable.
- The current production module implementation is acceptable; only the test's
  namespace coverage is incomplete.

## Required implementation

- Refactor the forbidden-import decision into a small pure test helper or
  equivalent precise structure.
- Ensure it rejects at least these representative imports and all children:

  ```text
  redis
  redis.asyncio
  slaif_gateway.api.dependencies
  slaif_gateway.db
  slaif_gateway.db.repositories.keys
  slaif_gateway.services.auth_service
  slaif_gateway.services.admin_session_service
  slaif_gateway.services.accounting
  slaif_gateway.services.quota_service
  slaif_gateway.services.rate_limit_service
  slaif_gateway.services.reservation_reconciliation
  slaif_gateway.services.external_tool_fence
  slaif_gateway.services.external_tool_hold
  slaif_gateway.services.key_service
  slaif_gateway.services.pricing
  slaif_gateway.services.fx_service
  slaif_gateway.services.audit_service
  importlib
  importlib.util
  pkg_resources
  ```

- Keep safe provider adapter/transport/error/diagnostic/header/streaming,
  schema, settings, pure module-contract, standard-library, and `httpx` imports
  allowed for server implementations.
- Add a parametrized regression test over representative forbidden and allowed
  names so correctness does not depend only on today's server files.
- Continue scanning every Python file under `modules/servers/` with the same
  helper.
- Do not change production code, docs, module behavior, or prior reports.

## Exact allowed paths

```text
tests/unit/test_module_architecture.py
oap/orders/153-c-server-authority-namespace-guard-closure.md
oap/reports/153-c-server-authority-namespace-guard-closure.md
oap/active
```

## Required verification

```text
git diff --check
.venv/bin/python -m ruff check tests/unit/test_module_architecture.py
.venv/bin/python -m pytest -q tests/unit/test_module_architecture.py tests/unit/test_module_provider.py tests/unit/test_provider_factory.py
python scripts/check_documentation.py
```

Do not run broad local suites. Final GitHub CI/CodeQL, including PostgreSQL and
E2E, must pass on the report head.

## Anti-false-positive acceptance

- Merely adding the four examples from this review without a reusable
  module-or-child predicate and parametrized proof fails.
- A loose substring test that rejects safe modules accidentally fails.
- Any production or documentation change fails scope.
- Prior green CI does not satisfy final-head checks.

## Boundaries and publication

- No Codex, Local Coding, OpenCode, hosted tools, signed identity, module
  behavior, provider, accounting, migration, live call, deployment, release,
  certification, compliance, invoice, support, or SLA work.
- Amend only PR #289; coding agent never merges or enables auto-merge.
- Publish one immutable
  `oap/reports/153-c-server-authority-namespace-guard-closure.md` in a
  report-only commit with the implementation head as first parent. Record the
  exact regression matrix, focused checks, final-head checks, and boundaries;
  then send exact `OK` to the response FIFO.
