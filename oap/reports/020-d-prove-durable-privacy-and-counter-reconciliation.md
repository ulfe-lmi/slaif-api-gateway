# OAP 020-d execution report

Implementation head SHA: a1c0c9826b6a2a9571205914add4090c881a5892
Report publication commit: SELF

## Scope and PR state

Objective 020 continuation 020-d amended the existing PR #246 on branch
`oap/020-generic-backend-chat-responses-conformance`, based on `main`.
The PR is open and unmerged. No merge or auto-merge was performed. The change
is test-only, except for the required versioned OAP selector/order state.

The focused PostgreSQL conformance matrix now proves durable post-outcome
state, rather than only the response-path result. It reloads the gateway key,
checks that reserved cost/tokens/requests are zero, and reconciles used cost,
tokens, and requests against the charged ledger rows. It also checks exact
zero-cost ledger values, single charging, and the missing-usage interruption
classification and estimate.

The matrix serializes only an explicit projection of durable ledger and audit
fields. It asserts that the projection contains none of the request/provider
canaries, request content, inline image/base64 data, tool schema/arguments/
results, client or backend keys, Authorization/cookie/internal headers, or raw
request/response fields. No request or provider payload is persisted by these
assertions.

## Verification

Local focused command, using a newly created disposable PostgreSQL database
whose name contained `test`:

```text
TEST_DATABASE_URL="postgresql+asyncpg://ubuntu@/<disposable-db>?host=/var/run/postgresql" ENABLE_EMAIL_DELIVERY=false .venv/bin/python -m pytest -q tests/integration/test_openai_compatible_conformance_postgres.py
```

Result: **2 passed**, 1 Alembic warning, 0 skipped. The disposable database
and temporary database role were removed by the cleanup trap. No production
`DATABASE_URL` was used and no destructive setup targeted a configured
application database.

Additional local checks:

```text
.venv/bin/ruff check tests/integration/test_openai_compatible_conformance_postgres.py  # passed
python -m compileall -q tests/integration/test_openai_compatible_conformance_postgres.py  # passed
git diff --check  # passed
```

The matrix covered five ledger rows: three successful/finalized outcomes and
two non-success/non-final outcomes (provider failure and missing usage). The
durable assertions verify no pending reservations, exact counter reconciliation,
one charge per outcome, and exact zero EUR/native cost for the local-zero
route. The missing-usage row has a non-null estimated/interrupted accounting
outcome and no normal-success completion metadata.

GitHub required checks for implementation head `a1c0c9826b6a2a9571205914add4090c881a5892`:

```text
Analyze (javascript-typescript)       pass
Analyze (python)                      pass
Analyze Python                        pass
CodeQL                                pass
Docker Compose smoke                  pass
Documentation hygiene                 pass
OpenAI-compatible E2E tests           pass
Playwright browser smoke               pass
PostgreSQL integration tests          pass
Unit, lint, and migration head        pass
```

The CI unit/lint/migration job passed its unit, Ruff, and migration-head
checks. No broad local suite, real provider call, real email, production
deployment, secret, or credential was used.

## Documentation, privacy, and merge status

No documentation or production behavior was changed. The implementation is
limited to the named PostgreSQL integration test and OAP state/report files.
The test uses mocked provider responses and an isolated disposable database;
provider credentials remain absent, and no sensitive request, response, key,
header, cookie, tool, or image data is printed or committed.

This report records implementation evidence only. Strategic acceptance,
merge, release, and any production-certification decision remain outstanding.
