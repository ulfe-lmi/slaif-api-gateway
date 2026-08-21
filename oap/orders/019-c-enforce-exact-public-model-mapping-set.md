# OAP Work Order — 019-c

PR mode: `AMEND_EXISTING_PR`

## Objective

Amend only PR #245. The 019-b admin/CLI parsers reject mappings for unselected
models, but `OpenAICompatibleSetupService` accepts a direct `SetupRequest` whose
`public_model_ids` contains every selected model plus extra discovered-but-
unselected keys. The extras are ignored rather than rejected. Make the service
contract exact so every caller receives the same fail-closed answer.

## Verified state

- PR #245, branch `oap/019-openai-compatible-backend-wizard-discovery`, base
  `main`.
- Current report head `1fa2075e9f6e797a92fe48a889e389d42e596017`;
  019-b implementation head `8802b2acff74508af29e7f96d00b6a0c1d25f854`.
- 019-b report topology is valid; report-head checks are running/green.
- Do not edit prior orders/reports, create another PR, merge, or enable
  auto-merge.

## Required change and evidence

1. When `public_model_ids` is supplied, require its key set to equal the exact
   selected-model set—no missing and no extra mappings—before discovery or
   mutation. Preserve the no-mapping default behavior.
2. Add direct unit tests for missing, extra discovered, extra unknown, duplicate
   public IDs, and valid exact mapping. Keep admin/CLI mapping tests green.
3. Run only focused setup/admin/CLI tests, scoped Ruff/compileall, governance,
   Alembic head, and diff check. No PostgreSQL rerun unless the service change
   breaks its focused file; no broad suite or real network.

## Allowed paths

```text
app/slaif_gateway/services/openai_compatible_setup.py
tests/unit/test_openai_compatible_setup.py
tests/unit/test_cli_providers.py
tests/unit/test_admin_provider_config_actions_routes.py
oap/active
oap/orders/019-c-enforce-exact-public-model-mapping-set.md
oap/reports/019-c-enforce-exact-public-model-mapping-set.md
```

## Publication

Commit this exact order and `oap/active=019-c` on existing PR #245. Publish one
immutable report-only final commit with literal implementation head and
`Report publication commit: SELF`, verify remote head/check state, send exact
FIFO `OK`, and return to one control wait. Coding agent never merges.
