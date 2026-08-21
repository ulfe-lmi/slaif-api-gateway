# OAP execution report — 018-c

## Result

Continuation `018-c` amended the sole Objective 018 PR #244:

<https://github.com/ulfe-lmi/slaif-api-gateway/pull/244>

Implementation head SHA: f234230cbcf73999e983a8ce740f33a53fc43641
Report publication commit: SELF

The PR remains open, ready for review, and auto-merge disabled. No merge,
release, production access, migration, real provider call, or real email was
performed.

## Repairs delivered

- Replaced every remaining method-level `self._api_key or
  self._settings.OPENAI_UPSTREAM_API_KEY` expression in the OpenAI adapter
  with the single overridable `_configured_api_key()` accessor. Generic Chat,
  Responses, streaming, lifecycle, Conversations, Audio, Embeddings, and
  Realtime paths now require their exact configured key.
- Added direct generic-provider missing-secret tests for Chat, Responses
  non-streaming, Responses streaming, and stored-response lifecycle retrieval.
  Each uses a populated built-in OpenAI secret, fails under the generic slug,
  and performs no upstream request or secret disclosure.
- Added `CLIENT_GATEWAY_KEY_ENV_VAR` in the configuration module and used that
  central constant for service, factory, and configuration-boundary rejection.
  Removed the prior split-string workaround and added a direct constant/source
  safety assertion.
- No endpoint, policy, accounting, migration, UI, CLI behavior, or provider
  discovery scope was expanded.

## Verification

The exact focused command passed:

```text
.venv/bin/python -m pytest -q tests/unit/test_config.py tests/unit/test_provider_factory.py tests/unit/test_openai_provider_adapter.py tests/unit/test_openai_provider_streaming.py tests/unit/test_cli_routing_pricing_safety.py
99 passed, 0 failed, 0 skipped
```

Scoped Ruff, compileall, `git diff --check`, and
`.venv/bin/python -m alembic heads` passed. Alembic reported the single head
`0015_external_tool_exclusive_fence`. The source scan showed no remaining
method-level direct fallback or split-string client-key workaround.

No local PostgreSQL setup was required. GitHub PostgreSQL integration used its
CI-managed disposable database lifecycle and passed; no `DATABASE_URL` or
production database was touched. No real upstream provider, email, or
external service was contacted, and no credentials or secrets were printed or
committed.

## GitHub checks

All ten required checks passed on implementation head
`f234230cbcf73999e983a8ce740f33a53fc43641`:

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

## Scope, privacy, and handoff

Only the activated `018-c` order was executed. Generic adapters retain their
configured provider slug in safe failures. The built-in OpenAI secret remains
server-side and is never used as a generic fallback, returned in diagnostics,
stored in audit values, or exposed in logs or responses.

The implementation commit was pushed before this report. The final report
commit has the implementation head as its first parent and changes only this
new report file. No repository mutation or push will occur after publication.
No merge or auto-merge action was performed.
