# OAP Objective 154-a Report — Versioned Codex client modules

Report publication commit: SELF

## Immutable execution identity

- Objective: `154-a`
- Active selector SHA-256: `039462e4cc95c2fc3605df8142718c039278cc8a2d3cd76508b14ab5f0eef7ce`
- Work-order SHA-256: `4bf1561ada41dc505ed357166983804b2ec447ce02b428be95d3d5121de18b33`
- Base: `main @ 4b04d6519c11c684b2eac70dc1757c515d2ea4ab`
- Activation commit: `3a32e6e0c79098a7da1d77e2b464cbd507ea8d3b`
- Implementation commit: `cfd80c826f78aa10740a87e0350f9a09afbbcafe`
- Branch: `oap/154-versioned-codex-client-modules`
- PR: #290, `obj154: move Codex protocols into versioned client modules`

The implementation commit contains the required exact order and active
selector. This report is intended to be the only later report-only commit.

## Implementation result

The client-module contract now exposes pure Responses normalization,
stream-profile, bounded candidate, profile-fact, and transient identity-hint
hooks. The static registry contains ordinary `openai-default`, qualified
`codex-0.147-responses-v1`, and structurally captured
`codex-0.149-responses-v1` modules. Codex-specific Responses constants and
taxonomies moved into pure client support under `modules/clients/codex_*`.

The exact qualified 0.147 profile remains bound to fixture SHA-256
`436ea530b9f984807dfc73ccce0b5233d0a3047ceb10ef942fbc8d12cac47432` and has
one reviewed server pair: OpenAI. Existing complete legacy Codex key policy
metadata without an explicit module ID derives only this 0.147 module; it
does not infer from request input, user-agent, headers, or model names.

The exact 0.149 artifact was obtained from the official npm source
distribution `@openai/codex@0.149.0`. The verified raw output was
`codex-cli 0.149.0`; the tarball SHA-512 was
`8b876bca3d98d63fb4d0c6f99fed27ef51189d32bdfca0dcd9c745a3f7570f4775a13a20d9b854b2c2831083a72a69c47f9d4fd19fc72535af4cac3f507c8ebd`.
The private disposable binary, CODEX_HOME, workspace, and npm cache were
removed after capture.

The retained fixture is
`tests/fixtures/codex/0.149.0/responses-structural.json`, SHA-256
`a93a08766d2f3d3cd702425b52120fc28c9154012dc68e05467536b821ed1ae2`.
It contains only canonical structural field/type/count facts and fixed safe
findings. It contains no prompts, outputs, descriptions, schemas/property
names, arguments/results, IDs, paths, URLs, headers, credentials, or raw
bodies. Capture used a private disposable CODEX_HOME, empty workspace,
synthetic token, and a fake numeric-loopback Responses server; no model call,
provider key, plugin, MCP server, or network tool was used.

The 0.149 module recognizes exact `web_search` and `tool_search` shapes as
`adapter_managed_codex_search` candidate facts. They do not activate hosted
tool policy, external-tool fencing, pricing, accounting, or provider routing.
Explicit search choices, preview aliases, MCP/connectors, provider
URLs/auth/headers, file search, code execution, computer/shell/patch
authority, unknown fields, and malformed shapes fail closed. No compatible
server module pair exists for 0.149, and the Responses handler rejects the
module before policy, Redis, quota reservation, accounting, or provider work.

Module ID/version/digest are exposed only as safe profile/admin facts. Raw
Codex identity hints remain transient and untrusted; they are not stored,
logged, audited, exported, hashed, or forwarded.

## Verification

Local focused verification passed:

| Area | Result |
| --- | --- |
| Focused unit/profile/architecture/policy/admin/docs command | `827 passed in 24.17s` |
| PostgreSQL: new 0.149 side-effect proof plus existing Codex accounting/replay tests | `3 passed`; isolated disposable DB; reservation and ledger counts unchanged on pair denial |
| Mocked official OpenAI Python Responses E2E | `1 passed`; respx upstream mock and localhost pass-through assertion workaround; no real provider |
| Documentation checker | `DOCUMENTATION_CHECK=OK files=79` |
| Alembic head | `0024_quota_reservation_accounting_facts (head)` |
| Ruff focused E4/E7/E9/F check, `git diff --check` | pass |
| Final GitHub checks on PR #290 | all ten successful: Unit/lint/migration, PostgreSQL integration, OpenAI-compatible E2E, Playwright, Docker Compose, Documentation hygiene, CodeQL, Analyze Python, Analyze python, Analyze javascript-typescript |

The focused unit command was:

```text
PYTHONPATH=.:app uv run --offline --no-project --with-requirements requirements-dev.txt pytest -o addopts='' -q tests/unit/test_codex_client_modules.py tests/unit/test_module_architecture.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_codex_protocol_capture.py tests/unit/test_codex_gateway_e2e_verifier.py tests/unit/test_responses_request_policy.py tests/unit/test_responses_codex_envelope.py tests/unit/test_responses_codex_client_tools.py tests/unit/test_responses_codex_streaming_tools.py tests/unit/test_responses_codex_multiturn_replay.py tests/unit/test_responses_codex_compaction.py tests/unit/test_admin_key_create_routes.py tests/unit/test_key_template_service.py tests/unit/test_cli_codex.py tests/unit/test_admin_catalog_routes.py tests/unit/test_documentation_contract_drift.py tests/unit/test_documentation_inventory.py tests/unit/test_product_scope_docs.py tests/unit/test_rc2_feature_scope_docs.py
```

The existing isolated current-0.147 gateway verifier was attempted with a
disposable PostgreSQL database and its private Redis/loopback setup. It
returned `RESULT=FAIL`, `ERROR_CODE=cli_preflight_failed`, and
`REAL_PROVIDER_CALLED=false` before running scenarios. This is recorded as a
local verifier preflight limitation, not as a passing 0.147 gateway E2E claim;
the focused verifier unit suite and the existing 0.147 profile/capture/policy,
PostgreSQL, and mocked-client evidence passed. No real upstream, Local Coding,
Qwen, OpenCode, production Compose, email, release, certification, or 128-
worker HPC verification was run by this objective.

## GitHub and publication audit

At report preparation, PR #290 was open, non-draft, `MERGEABLE`,
`mergeStateStatus=CLEAN`, and `autoMergeRequest=null`. The remote branch head
matched implementation commit `cfd80c8` before this report was added. The
report-only commit must have `cfd80c8` as its first parent and change only this
report path; the coding agent does not merge or enable auto-merge.
