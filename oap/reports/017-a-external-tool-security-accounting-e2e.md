# OAP 017-a Execution Report

Status: implementation complete; PR #242 remains open and unmerged.

Implementation head SHA: e96fb0580df4efe8daa0d545813317400b9293b0
Report publication commit: SELF

## Scope

Activated the exact fenced OpenAI Responses `web_search` contract. The round
adds request admission and canonical forwarding, full-balance PostgreSQL fence
reservation, per-call pricing and token accounting, content-free success
metadata, durable unknown-outcome holds, bounded streaming validation, admin
and CLI status, documentation, PostgreSQL evidence, and OpenAI Python client
E2E evidence. Other hosted families, remote MCP, connectors, and OpenRouter
hosted tools remain denied.

## Verification

Local focused checks:

- `python -m ruff check` over all changed implementation and test files: passed.
- `git diff --check`: passed.
- `python -m compileall -q app/slaif_gateway`: passed.
- Required focused unit groups: passed locally; the local Responses E2E and
  PostgreSQL integration invocations correctly skipped because no
  `TEST_DATABASE_URL` was configured.
- No broad local suite, real provider call, real email, production action, or
  destructive database setup was run.

Final GitHub CI for implementation head:

- Unit, lint, and migration head: 3159 passed.
- PostgreSQL integration tests: 192 passed, 35 warnings.
- OpenAI-compatible E2E tests: 44 passed, 44 warnings.
- Playwright browser smoke: passed.
- Docker Compose smoke: passed.
- Documentation hygiene: passed.
- Analyze Python and Analyze (python): passed.
- Analyze (javascript-typescript): passed.
- CodeQL: passed.

The E2E repair addressed cleanup ordering after external-tool reservations
began retaining their foreign-key route identity. The fixture now removes
content-free ledgers, clears the key fence, removes reservations, and only
then removes the test route. The final E2E run passed all 44 tests.

## PostgreSQL and accounting evidence

The CI integration job used its disposable PostgreSQL service and completed
192 tests. The new external-tool integration evidence covers full remaining
balance reservation, active/held fence state, reservation counters, and
content-free hold metadata. PostgreSQL remains the hard quota/fence authority;
Redis is not used as accounting authority.

Unknown provider outcomes retain the complete reservation in a durable hold.
Successful finalization resolves the fence only after usage, call evidence,
cost, ledger, and reservation terminal state are available. No prompt,
provider response, query, URL, source, citation, credential, or raw tool ID is
stored in the new report or accounting metadata.

## Privacy and security

Forwarding uses server-side provider authentication and the canonical
web-search fragment only. Gateway policy, key metadata, pricing, quota facts,
fence facts, and diagnostics are not forwarded. Errors and operator summaries
remain fixed-shape and content-free. No secrets or real provider credentials
were printed or committed.

## Scope and merge confirmation

No migration was added. No production or release action was taken. No real
upstream provider call or real email was made. Exactly one Objective-017 PR is
used: [PR #242](https://github.com/ulfe-lmi/slaif-api-gateway/pull/242).
The coding agent did not merge or enable auto-merge.
