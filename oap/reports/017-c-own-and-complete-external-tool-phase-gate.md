# OAP 017-c Execution Report

Status: implementation complete; PR #242 remains open and unmerged.

Implementation head SHA: e3c88ef0b642de305848e5e2c764c4f35dc0eb18
Report publication commit: SELF

## Scope

This continuation completes the bounded OpenAI Responses `web_search` phase
gate on the existing Objective-017 branch. The runtime now carries one
immutable model-pricing and FX decision from pre-Redis admission through
reservation and accounting; rejects `max_tool_calls` without an admitted
web-search declaration; uses only the exact resolved route UUID; separates
provider construction from post-start failure handling; creates durable
content-free holds for unexpected hosted failures; redacts provider-error
canaries; and bounds hosted streaming by the admitted call cap and absolute
event limits. Normal message output items and text events are accepted, while
actual provider search actions are validated before content-free projection.

## Local verification

Required focused unit command:

```text
.venv/bin/python -m pytest tests/unit/test_responses_request_policy.py tests/unit/test_openai_web_search_contract.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_v1_responses_quota.py tests/unit/test_usage_report_service.py -q -ra
```

Result: 365 passed, zero skips.

Additional fence/hold/pricing unit command:

```text
.venv/bin/python -m pytest tests/unit/test_external_tool_fence.py tests/unit/test_external_tool_hold.py tests/unit/test_pricing.py -q -ra
```

Result: 98 passed, zero skips. This covers the audited reconciliation and
counter invariants in the existing fence/hold service tests.

Mandatory gateway PostgreSQL matrix:

```text
TEST_DATABASE_URL=postgresql+asyncpg://ubuntu@/slaif_oap_017c_final_test_1787263500 .venv/bin/python -m pytest tests/integration/test_responses_external_tool_postgres.py -q -ra
```

Result: 9 passed, zero skips. The database was created as a uniquely named
disposable PostgreSQL database, migrated by the integration fixture, and
dropped successfully (`CLEANUP=dropdb status=0`). The matrix exercises the
ASGI `/v1/responses` route with real PostgreSQL fence, reservation, ledger,
and audit repositories plus official-shape mocked provider behavior. Named
coverage includes allowed atomic success, same-key fence rejection, actual
overrun followed by ordinary and hosted admission rejection, provider error,
missing usage, malformed output, hosted streaming success with terminal
withholding, malformed streaming hold, true streaming hold metadata, Redis
release observation, and content-free persistence scans.

Responses client E2E:

```text
TEST_DATABASE_URL=<safe disposable PostgreSQL URL> ENABLE_EMAIL_DELIVERY=false .venv/bin/python -m pytest tests/e2e/test_openai_python_client_responses.py -q -ra
```

Result: 13 passed, zero skips. No real provider or email delivery was used.

Scoped Ruff, compileall, and `git diff --check` passed. No full local unit,
browser, Compose, HPC, or provider suite was run.

## GitHub evidence

PR #242 is the sole Objective-017 PR on branch
`oap/017-external-tool-security-accounting-e2e`, based on `main`. At the
implementation head, Unit/lint/migration, PostgreSQL integration,
OpenAI-compatible E2E, Playwright, Docker Compose, documentation hygiene,
CodeQL, and Python/JavaScript analysis all passed. The PR remains open, has no
strategic review decision, and has no auto-merge request.

## Privacy, security, and accounting

Prompt, query, URL, source, result, action payload, provider-error, and raw ID
canaries were asserted absent from errors, ledgers, audits, and safe metadata.
Provider credentials were mocked/server-side only; no secret, real provider
call, real email, production data, migration, or deployment action was used.
PostgreSQL remains hard quota/fence/accounting authority. Redis was represented
in the ASGI matrix by a request-scoped operational reservation spy, with release
assertions on success, denial, hold, and terminal paths; Redis was not used as
quota or fence truth and no live Redis service was required for this focused
evidence.

## Completion and merge confirmation

The implementation commit contains the activated `017-c` order and unchanged
`oap/active=017-c`. Exactly one Objective-017 PR was used:
[PR #242](https://github.com/ulfe-lmi/slaif-api-gateway/pull/242). The coding
agent did not merge or enable auto-merge.
