# OAP 021-c execution report

Objective 021 continuation completed on PR #247 only. No merge or auto-merge
was performed.

Implementation head SHA: 60534765e4bd20419833b025bd0b3f6c2e730e25
Report publication commit: SELF

## Scope

- Extended the immutable profile definition with finite text/image modalities,
  client-local compaction thresholds, finite runtime gates, and coherent
  `none`/`client_local`/`remote_v1` invariants.
- Replaced substring catalog checks with a bounded allowlisted schema derived
  from the committed Codex catalog vocabulary. Replacement catalogs require
  one exact model and matching context, threshold, and modality facts; bundled
  profiles cannot carry replacement artifacts.
- Hardened fixture sanitization with caller-supplied immutable structural type
  vocabulary, key-specific scalar validation, deterministic ordering, bounded
  IDs/nodes, placeholder IDs, and computed digest.
- Made replacement artifacts profile-specific, catalog-referencing,
  credential-free, and explicit about targets; all rendered profiles emit
  `remote_compaction_v2 = false`.
- Preserved legacy v1 qualification and default renderer output, added
  text-only/image capability fail-closed checks, and carried live-provider-E2E
  truth into the admin DTO and escaped v2 wording.
- Updated the Codex compatibility documentation and focused regression tests.

## Verification

Focused command:

```text
.venv/bin/python -m pytest -q tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py tests/unit/test_admin_catalog_routes.py tests/unit/test_admin_catalog_templates_safety.py tests/unit/test_codex_gateway_e2e_verifier.py tests/unit/test_documentation_contract_drift.py
```

Result: 148 passed, 0 failed, 0 skipped. One existing Starlette/httpx
deprecation warning was emitted; it is unrelated to this objective.

Additional bounded checks:

```text
.venv/bin/ruff check app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/services/admin_catalog_dashboard.py app/slaif_gateway/schemas/admin_catalog.py app/slaif_gateway/api/admin.py tests/unit/test_codex_profile_registry.py tests/unit/test_codex_qualification.py tests/unit/test_cli_codex.py tests/unit/test_admin_catalog_routes.py tests/unit/test_admin_catalog_templates_safety.py
.venv/bin/python -m compileall -q app/slaif_gateway/services/codex_profile_registry.py app/slaif_gateway/services/codex_qualification.py app/slaif_gateway/services/admin_catalog_dashboard.py app/slaif_gateway/schemas/admin_catalog.py app/slaif_gateway/api/admin.py
git diff --check
```

All three passed. Jinja/template safety coverage was included in the focused
pytest command. No full local suite, Codex process, capture, network/backend,
provider, LAN, or real-email test was run.

The synthetic replacement qualification uses context window 150,000 and
client-local threshold 125,000. Two synthetic replacement profiles render
distinct provider/profile/catalog targets; the named profile references its
catalog target, and the bundle/CLI JSON/text checks contain no upstream URL,
upstream model credential, or provider environment variable. The artifact
checks also prove `remote_compaction_v2=false`. Text-only image capability,
unknown catalog fields, malformed catalog structure, arbitrary one-word
fixture types, wrong scalar types, privacy classes, unregistered profile
selection, and live-E2E admin wording are covered by focused negatives.

No local PostgreSQL database was created, changed, or cleaned up in this
round. GitHub's PostgreSQL integration check passed using its CI-managed
isolated test lifecycle; no `DATABASE_URL` or production database was used.
No Redis setup was required locally.

## GitHub and review evidence

PR #247 remains open, based on `main`, on branch
`oap/021-versioned-generic-codex-profile-framework`, with remote head equal to
the implementation SHA above before report publication. All ten routine
checks passed on the implementation head: CodeQL, both Analyze jobs, Analyze
Python, Docker Compose smoke, Documentation hygiene, OpenAI-compatible E2E,
Playwright browser smoke, PostgreSQL integration tests, and Unit/lint/migration
head.

The two existing review threads are both resolved and outdated:

- `PRRT_kwDOSLm-qM6bD9kE` — unused `compatible_ids`.
- `PRRT_kwDOSLm-qM6bD9kK` — unused `_REQUIRED_FIELDS`.

No new review threads or comments were present. The implementation commit
also carries the unchanged `oap/active` selector and activated 021-c order.

## Privacy, security, and scope

The replacement catalog schema rejects credentials, API/backend/gateway URLs,
environment/header material, prompts, outputs, arbitrary instructions, tool
schemas/arguments/results, reasoning, and encrypted content. Provider
credentials remain absent from artifacts and logs. Catalog/profile mappings and
provider fields remain immutable; admin artifacts require ready registered
profiles and a validated configured SLAIF gateway URL. PostgreSQL remains the
hard accounting authority. No runtime request-policy widening, schema
migration, hosted tool, image forwarding, Qwen/vLLM registry entry, production
claim, or release action was made.

## Publication and merge boundary

This report is the only file changed by the final report-only commit. The final
report commit must have the implementation commit above as its first parent,
be the remote PR head, and be followed by no repository mutation. The coding
agent did not merge PR #247 and did not enable auto-merge.
