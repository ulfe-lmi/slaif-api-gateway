# OAP 015-d execution report

Objective: prove that external-tool hold reconciliation controls following
ordinary quota admission, and prove the changed-input race's durable outcome,
on the existing PR #240.

Implementation head SHA: 1a44dc71edc62ec4914515caa52b53ca99efa455
Report publication commit: SELF

## Implementation scope

This continuation is tests-only. No production code was changed. The allowed
changes are the unchanged `oap/active` selector, the activated 015-d order,
and the two named PostgreSQL integration files. Existing unrelated maintainer
changes in `AGENTS.md`, `OAP-COMMUNICATION-coding-agent.md`,
`ARCHITECTURE-for-agents.md`, and `oap/strategic-instructions/` were preserved
and were not staged.

## Focused verification

The exact command used against one generated disposable PostgreSQL database was:

```text
set -euo pipefail
PY=.venv/bin/python
DB_NAME="slaif_gateway_test_oap015d_<timestamp>_<pid>"
DB_URL="postgresql+asyncpg://ubuntu@/${DB_NAME}?host=/var/run/postgresql"
createdb "$DB_NAME"
trap 'dropdb --if-exists "$DB_NAME" >/dev/null' EXIT
DATABASE_URL="$DB_URL" $PY -m alembic upgrade head
DATABASE_URL="$DB_URL" TEST_DATABASE_URL="$DB_URL" $PY -m pytest tests/integration/test_external_tool_hold_postgres.py tests/integration/test_external_tool_hold_concurrency_postgres.py -q -ra
```

Result: 38 passed, 0 failed, 0 skipped. The disposable database used the
`slaif_gateway_test_oap015d_` prefix and was dropped by the EXIT trap. No
pre-existing or production database was used for destructive setup.

The direct ordinary `QuotaService.reserve_for_chat_completion` evidence proves:

1. A real held transition rejects both bearer authentication and a
   pre-authenticated ordinary quota reservation with the held-fence error.
2. Explicit no-charge reconciliation clears the hold and allows a fitting
   ordinary reservation, which is asserted pending before rollback.
3. Within-limit actual finalization allows a fitting ordinary reservation.
4. Overrun finalization rejects the following ordinary reservation through the
   normal `QuotaLimitExceededError`; after rollback, pending reservations and
   reserved counters are unchanged.
5. The changed-input two-worker race has one winner and one fixed conflict.
   Final assertions prove exactly one finalized reservation and ledger, fence
   state `none`, winner cost/token usage once, zero reserved counters, exactly
   one reconciliation audit, winning actor/reason/facts, and no loser mutation.

The existing external-fence follow-up assertions remain in place. Both
concurrency paths use a 30-second `asyncio.wait_for` timeout; the retained
eight-worker exact race remains covered by the same focused files.

Additional scoped checks passed:

- Python compileall for the application and two changed integration files;
- `git diff --check`;
- CI Unit/lint/migration check, including lint.

The temporary `/tmp/slaif-api-gateway-014c-venv` Ruff executable was absent;
the repository `.venv` had no Ruff executable, so local Ruff was not run. The
GitHub Unit, lint, and migration check completed successfully.

## GitHub evidence

PR #240 is the sole objective-015 PR. The implementation commit was pushed to
`oap/015-external-tool-accounting-hold-reconciliation`; PR #240 remained OPEN
and MERGEABLE, targeted `main`, and had no auto-merge request. All ten final
head checks for `1a44dc71edc62ec4914515caa52b53ca99efa455` completed
successfully:

- Unit, lint, and migration head
- PostgreSQL integration tests
- OpenAI-compatible E2E tests
- Playwright browser smoke
- Docker Compose smoke
- Documentation hygiene
- Analyze (javascript-typescript)
- Analyze Python
- Analyze (python)
- CodeQL

No check was skipped, cancelled, pending, or represented as passed without a
successful conclusion.

## Safety and privacy

No real provider calls, real email, production access, or secrets were used.
The tests used only bounded identifiers and accounting facts; no prompts,
responses, tool arguments/results, URLs, credentials, media, or provider
content were exposed or committed. PostgreSQL remained authoritative for hard
accounting. No broad local suite, provider, email, Redis-authority,
production, schema, migration, runtime, E2E, browser, Docker, or HPC suite was
run locally.

The coding agent did not merge PR #240, enable auto-merge, create another PR,
or push to `main`. This report-only commit must have the implementation commit
as its first parent and this report as its only changed path.
