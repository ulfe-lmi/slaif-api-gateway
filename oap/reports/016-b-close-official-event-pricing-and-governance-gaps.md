# OAP execution report — 016-b

## Result

Continuation `016-b` amended the existing Objective 016 PR #241:

<https://github.com/ulfe-lmi/slaif-api-gateway/pull/241>

Implementation head SHA: a727549efcd2eea212deb6440c07d7fa4fe66602
Report publication commit: SELF

The PR remains open, with auto-merge disabled. No merge, release, runtime
activation, provider call, production access, migration, or external service
was performed.

## Repairs delivered

- Replaced the split-name policy import with explicit readable imports and
  narrowly added the pure web-search contract to the existing intentional
  policy-consumer allowlist. The source scan remains active and still rejects
  unapproved runtime, gateway, provider, and migration consumers.
- Enforced bounded `item_id`, `output_index`, and `sequence_number` facts for
  official web-search lifecycle events. `response.output_item.done` takes its
  index and sequence from the event and its web-search identity/status/action
  from the item; matching completion evidence is merged once and conflicting
  or non-monotonic facts become non-authoritative.
- Made completed zero-call non-stream and stream outcomes authoritative when
  tool choice is absent/`auto` and exact valid pricing is present, with exact
  zero fee. Incomplete, failed, malformed, over-cap, or missing-terminal calls
  remain hold-required.
- Added strict `ExternalToolPricing` validation for canonical currency,
  finite non-negative Decimal amount, and the exact published source. Missing
  or invalid pricing can never produce authoritative evidence.
- Added official-shape bounds, zero-call, pricing, conflict, tool-choice, and
  private-canary privacy tests. Safe evidence remains limited to low-cardinality
  provider/capability, cap, count, pricing, authority, and reason facts.

No runtime, provider adapter, request policy, database, migration, Redis,
admin/CLI, browser, deployment, or documentation surface was changed.

## Verification

The exact focused command required by the order passed:

```text
PYTHONPATH=app /home/ubuntu/codex-work/slaif-api-gateway/.venv/bin/python -m pytest \
  tests/unit/test_openai_web_search_contract.py \
  tests/unit/test_pricing.py \
  tests/unit/test_documentation_contract_drift.py::test_external_tool_contract_is_wired_only_to_policy_surfaces_not_runtime_or_migrations \
  tests/unit/test_external_tool_policy_contract.py -q -ra
161 passed, 0 failed, 0 skipped
```

Scoped Ruff, targeted compileall, and `git diff --check` passed. The focused
coverage includes request and policy negatives, preview/unknown and duplicate
declarations, MCP/connectors and mixed authority, bool/zero/over-cap counts,
official lifecycle bounds, conflicting/out-of-order/non-monotonic events,
zero-call outcomes, missing/negative/non-finite/wrong-source/invalid-currency
pricing, cap overflow, missing terminals, and private-canary content absent
from results, reprs, errors, and safe evidence.

No local PostgreSQL setup was needed for this pure contract continuation. The
GitHub PostgreSQL integration job passed on the implementation head using its
CI-managed disposable database lifecycle; no production database or
`DATABASE_URL` was touched. No real upstream calls, email delivery, external
MCP server, credentials, or secrets were used.

## GitHub checks

All ten required implementation-head checks passed for
`a727549efcd2eea212deb6440c07d7fa4fe66602`:

- Unit, lint, and migration head
- PostgreSQL integration tests
- OpenAI-compatible E2E tests
- Playwright browser smoke
- Docker Compose smoke
- Documentation hygiene
- Analyze (javascript-typescript)
- Analyze (python)
- Analyze Python
- CodeQL

The earlier `016-a` initial-round governance wording failure is resolved by
moving `oap/active` to this continuation; `016-a` itself remains immutable.

## Privacy and publication evidence

The implementation retains no query, URL, source, result, citation, search
content, response text, tool arguments/results, OAuth token, provider secret,
or raw response/SSE payload. IDs and sequence/index facts are used only for
bounded in-memory validation and do not enter safe evidence.

The implementation commit was pushed before this report. The final report
commit will have the implementation head as its first parent and will change
only this report file. No repository mutation or push will occur after report
publication. No merge or auto-merge action was performed.
