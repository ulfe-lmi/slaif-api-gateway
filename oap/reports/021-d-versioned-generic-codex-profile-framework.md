# OAP 021-d execution report

Objective 021 continuation completed on PR #247 only. No merge or auto-merge
was performed.

Implementation head SHA: 3fcde10fafe25c999838da8f0e460bde21faed92
Report publication commit: SELF

## Corrections delivered

- Profile image coherence now uses the authoritative Responses
  `image_input` capability constant. Vision profiles pass
  `image_input_requested=True` through the existing runtime capability
  enforcer; text-only profiles reject a declared image capability. No
  `responses_image_input` profile gate remains.
- Replacement catalogs now require the exact Codex root shape
  `{"models":[one model]}`. Context window, client-local auto-compaction
  threshold, and input modalities are required on that exact model entry;
  unknown root fields and invented schema/context/threshold/modalities roots
  fail closed. The finite optional safe vocabulary, canonical JSON, bounds,
  and privacy exclusions remain enforced.
- Replacement profile TOML emits `model_catalog_json` as a root key before
  `[features]`; no `[model_catalog]` table is emitted. Legacy default TOML
  remains byte-identical and omits the replacement key.
- Human profile output uses `artifacts.profile_config_target` for the complete
  file target while retaining the legacy `$CODEX_HOME/slaif.config.toml`
  target for the legacy artifact. Generic profiles therefore show distinct
  profile-specific targets and catalog targets.
- Added focused synthetic text/vision qualification, authoritative parser,
  exact catalog-root, parsed-TOML, generic-target, and legacy-byte tests.

## Focused verification

Exact command:

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py
```

Result: 88 passed, 0 failed, 0 skipped. One existing Starlette/httpx
deprecation warning was emitted; it is unrelated to this objective.

Additional bounded checks:

```text
.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py
.venv/bin/python -m compileall -q app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py
git diff --check
```

All three passed. The focused tests parse replacement TOML with `tomllib` and
assert root `model_catalog_json`, exact `features.remote_compaction_v2=false`,
and no `model_catalog` table. They assert the legacy base/profile TOML bytes
exactly, and verify generic text uses each artifact's profile-specific target.
No full local suite, Codex process, capture, network/backend, provider, LAN,
or real-email test was run.

No local PostgreSQL database was created, changed, or cleaned up. GitHub's
PostgreSQL integration check passed using its CI-managed isolated test
lifecycle; no `DATABASE_URL` or production database was used. No Redis setup
was required locally.

## GitHub and review evidence

PR #247 remains open on branch
`oap/021-versioned-generic-codex-profile-framework`, based on `main`. All ten
routine checks passed on implementation head: CodeQL, both Analyze jobs,
Analyze Python, Docker Compose smoke, Documentation hygiene,
OpenAI-compatible E2E, Playwright browser smoke, PostgreSQL integration tests,
and Unit/lint/migration head.

The two existing review threads remain resolved and outdated:

- `PRRT_kwDOSLm-qM6bD9kE` — unused `compatible_ids`.
- `PRRT_kwDOSLm-qM6bD9kK` — unused `_REQUIRED_FIELDS`.

No new review threads or comments were present. The unchanged `oap/active`
selector and activated 021-d order are included on the PR branch.

## Privacy and scope

Catalog validation continues to reject credentials, API/backend/gateway URLs,
environment/header material, prompts, outputs, arbitrary instructions, tool
schemas/arguments/results, reasoning, and encrypted content. Rendered
artifacts remain credential-free and deterministic. No registry entry, Qwen or
vLLM work, request-policy widening, migration, runtime path-resolution
redesign, production claim, release action, or merge was made.

## Publication boundary

This report is intended to be the only file changed by the final report-only
commit. That commit must have the implementation SHA above as its first
parent, be the remote PR head, and be followed by no repository mutation. The
coding agent did not merge PR #247 or enable auto-merge.
