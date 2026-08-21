# OAP Work Order — 018-c

## Objective and reason

Amend only PR #244. Objective 018-b correctly overrides
`OpenAICompatibleProviderAdapter._configured_api_key()`, but twelve inherited
Responses/lifecycle/conversation/stream methods in `openai.py` still bypass the
accessor and directly evaluate
`self._api_key or self._settings.OPENAI_UPSTREAM_API_KEY`. A directly
constructed or future generic adapter can therefore use the built-in OpenAI
secret outside the one Chat method tested. The provider service/factory also
construct the reserved client env-var name by string concatenation to evade an
overbroad source-safety assertion. Close these exact issues without feature
expansion.

Implement immediately after inspecting `openai.py` and the named tests once.
No broad reconnaissance or broad suite.

## Verified continuation state

- Sole PR #244; branch `oap/018-generic-openai-compatible-backend-runtime`;
  base `main`.
- Current report head: `3cf27c92057cb1299f16373de8b0561674122922`.
- 018-b implementation head:
  `48de32fe13f6aacdb0e23425dc113de66e4d822a`.
- All ten checks are green; PR is open/clean/mergeable; no review threads.
- Reuse this PR. Do not edit prior orders/reports, create another PR, merge, or
  enable auto-merge.

## Required repairs

1. Replace every direct method-level OpenAI-key fallback in
   `OpenAIProviderAdapter` with the single overridable key accessor. The only
   remaining direct reference to `Settings.OPENAI_UPSTREAM_API_KEY` in that
   class may be inside the built-in accessor itself.
2. Preserve built-in OpenAI behavior exactly. Generic adapters must require
   their own `_api_key` across Chat, Responses create/stream, input-token/
   compact, stored lifecycle, Conversations, items, Audio, Embeddings, and
   Realtime methods.
3. Add direct focused negative proof across representative distinct method
   families, including at least Chat, Responses non-stream, Responses stream,
   and one lifecycle/conversation method, with a populated built-in OpenAI
   secret. Every path must fail under the generic provider slug without making
   a request or revealing the secret.
4. Define one clearly named central constant for the client gateway-key env-var
   name in the existing configuration module (which already owns that
   semantic), and use it in factory/service rejection. Do not concatenate
   string fragments, weaken/remove the source-safety test, or duplicate the
   literal in provider config modules.
5. Add a focused assertion that provider modules contain no split-string or
   direct client-key literal workaround and that the central constant is the
   rejected value.

## Allowed paths and non-goals

Only:

```text
app/slaif_gateway/config.py
app/slaif_gateway/providers/factory.py
app/slaif_gateway/providers/openai.py
app/slaif_gateway/providers/openai_compatible.py
app/slaif_gateway/services/provider_config_service.py
tests/unit/test_config.py
tests/unit/test_provider_factory.py
tests/unit/test_openai_provider_adapter.py
tests/unit/test_openai_provider_streaming.py
tests/unit/test_cli_routing_pricing_safety.py
oap/active
oap/orders/018-c-close-all-generic-secret-fallback-paths.md
oap/reports/018-c-close-all-generic-secret-fallback-paths.md
```

Use fewer paths if possible. No docs change is required unless behavior wording
was inaccurate. No migration, UI/CLI behavior change, discovery, Qwen/Codex,
real endpoint, unrelated refactor, or broad local suite.

## Acceptance and focused verification

- `rg`/source test proves all provider request methods use the accessor and no
  split-string workaround remains.
- Generic missing-key tests cover the required method families; built-in
  OpenAI adapter/stream tests remain green.
- The reserved client env-var is centrally defined and rejected by both service
  and factory.
- Run the smallest focused provider/config/source-safety tests, scoped Ruff,
  compileall, Alembic heads, and `git diff --check`. No full suite or real
  provider.

## Publication duties

Commit exact `oap/active=018-c` and this order on the same PR, publish one
immutable `oap/reports/018-c-close-all-generic-secret-fallback-paths.md` in a
final report-only commit with literal implementation head and
`Report publication commit: SELF`, push/verify it as PR head, send exact FIFO
`OK`, and return to one control wait. Coding agent never merges.
