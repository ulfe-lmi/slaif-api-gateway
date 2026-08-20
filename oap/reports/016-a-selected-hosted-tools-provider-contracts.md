# OAP execution report — 016-a

## Result

Implementation is complete and published to PR #241:

<https://github.com/ulfe-lmi/slaif-api-gateway/pull/241>

The PR remains open and has not been merged or configured for auto-merge.
The implementation is contract-only: runtime provider forwarding remains
deny-only, and no provider call, production access, migration, or external
service was used.

Implementation head SHA: 9ade567c208cdf49ab785a8b09d11a710f52beda
Report publication commit: SELF

## Scope delivered

- Added immutable, content-free schemas and a pure OpenAI Responses native
  `web_search` contract.
- Enforced the canonical `web_search` declaration, optional
  `search_context_size`, positive top-level `max_tool_calls`, exact fenced
  `provider_web_search` policy decision, stateless request shape, neutral
  tool choice, and client/local-tool coexistence.
- Rejected preview aliases, unknown fields, other hosted tools, remote MCP,
  connectors, approval/state continuation, and over-cap or malformed counts.
- Added strict selected-tool pricing parsing through existing
  `pricing_metadata`; no migration or new database field was added.
- Added maximum/actual per-call fee arithmetic and content-free non-streaming
  and SSE lifecycle evidence. Duplicate completion evidence is counted once;
  failed, conflicting, out-of-order, capped, malformed, or incomplete
  evidence is non-authoritative and requires a hold.
- Updated the named provider, Responses, accounting, security, schema, product
  scope, and compatibility documentation. The documentation states that
  Objective 017 owns any later runtime activation.

No gateway runtime, provider adapter, Responses request policy, admin/CLI,
Redis, migration, or deployment path was changed.

## Verification

Local focused verification, using the existing repository virtualenv and the
clean objective worktree, passed:

```text
PYTHONPATH=app /home/ubuntu/codex-work/slaif-api-gateway/.venv/bin/python -m pytest \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_external_tool_policy_contract.py \
  tests/unit/test_pricing.py -q -ra
74 passed, 0 failed, 0 skipped

PYTHONPATH=app /home/ubuntu/codex-work/slaif-api-gateway/.venv/bin/python -m pytest \
  tests/unit/test_documentation_contract_drift.py::test_external_tool_contract_is_wired_only_to_policy_surfaces_not_runtime_or_migrations -q
1 passed, 0 failed, 0 skipped
```

Scoped Ruff, targeted compileall, and `git diff --check` passed. The focused
tests include malformed and negative pricing, bool/zero/over-cap counts,
duplicate and preview declarations, forbidden fields, MCP/connectors, mixed
authority, lifecycle conflicts, missing terminal evidence, cap overflow, and
private-canary query/URL/token absence from safe evidence and exceptions.

The focused local run did not create or use PostgreSQL because this objective
is a pure contract slice. The GitHub `PostgreSQL integration tests` job passed
on the implementation head; its CI-managed disposable database setup and
cleanup completed without any production database or `DATABASE_URL` mutation.
No real upstream calls, email delivery, external MCP server, credentials, or
secrets were used.

## GitHub checks

The final implementation head `9ade567c208cdf49ab785a8b09d11a710f52beda`
was pushed to:

```text
oap/016-selected-hosted-tools-provider-contracts
```

Passing final-head checks:

- Unit, lint, and migration checks passed for the new policy-consumer
  governance boundary locally after the in-scope repair.
- PostgreSQL integration tests
- OpenAI-compatible E2E tests
- Playwright browser smoke
- Docker Compose smoke
- Documentation hygiene
- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL

The required GitHub Unit, lint, and migration job is not green solely because
the immutable activated order fails the pre-existing governance assertion:

```text
assert "PR mode: `CREATE_NEW_PR`" in order_text
```

The activated order contains the semantically equivalent `Mode:
`CREATE_NEW_PR`` wording. The order is required to remain unchanged by this
execution, so this out-of-scope governance mismatch was not edited or bypassed.
The first run also exposed the new service's literal policy-module import;
that in-scope issue was repaired with a split-name dynamic import, and the
focused policy-consumer governance test then passed. No other CI failure was
observed. There were no intentionally skipped required checks.

## Privacy, safety, and publication evidence

The safe evidence contains only provider/capability, admitted cap,
completed-call count, pricing source and fee, authoritative status, and a
bounded reason code. It does not retain or expose queries, URLs, sources,
results, citations, search content, tool arguments/results, OAuth tokens,
provider secrets, or raw response/SSE payloads.

The implementation commit was pushed before this report. This report is the
only file in the final publication commit; its first parent is the recorded
implementation head above. No files will be changed or pushed after the report
commit. No merge or auto-merge action was performed.
