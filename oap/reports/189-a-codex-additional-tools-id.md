# OAP Execution Report — Objective 189-a: Codex additional-tools ID + 0.162.1 profile

Report status: IMMUTABLE (finalized at the exact implementation head
`73fd10567a6c2558f4ec233a90ba3818745bacca`; published atomically as the
immutable report; the report-only SELF commit with message
`Report publication commit: SELF` is its publication commit, first
parent = this implementation head; only this report path differs).

- Implementation head SHA: 73fd10567a6c2558f4ec233a90ba3818745bacca
- Report publication commit: SELF

## 1. Work order and PR identity

- Work order: `oap/orders/189-a-codex-additional-tools-id.md`
  (strategic-authored; committed unchanged by the activation commit
  `eecbc3d`); `oap/active` = `189-a`.
- PR: new single 189 PR, branch `oap/189-codex-additional-tools-id` →
  `main` (base `0380f62`, PR #326 merge), created after this report is
  published. The coding agent never merges; strategic review and
  final-head CI own acceptance/merge.
- Branch commit chain: `eecbc3d` (activation, order bytes unchanged) →
  `90ae4d6` (strategic scope decision `oap/strategic-instructions/189-codex-0162-scope-decision.md`
  committed unchanged) → `f632110` (strategic decision
  `oap/strategic-instructions/189-codex-0162-provider-lowering.md` committed
  unchanged) → `73fd105` (this implementation head; the only commit
  touching product code, tests, and docs).

## 2. Scope

Original ordered scope (unchanged, committed at activation):

1. Codex 0.149 client module version 4 → 5: accept an optional bounded
   `id` on the `additional_tools` declaration item, validated with the
   existing bounded item-ID conventions before canonicalization; preserve
   unknown-field rejection and all existing gates.
2. Bounded audited key-module upgrade/rollback for pinned 0.149-v4 keys:
   exact old/new tuples with frozen literal historical digest, four legal
   transition edges, dry-run-default CLI, atomic metadata+audit write, no
   schema change.

Human-authorized bounded expansions (per the two committed strategic
decisions):

3. New static `codex-0.162-responses-v1` module, version 1, for CLI
   0.162.1, with the finite additional-tools profile (strict
   `functions`/`multi_agent_v1` built-ins, `mcp__codex_apps__*` dynamic
   namespaces, 16/256/256 tool ceilings, 20,000-byte per-tool and
   262,144-byte total description limits, 4,096-property schema cap,
   pattern-validated function-only tool names), one exact
   `local-coding-v1` pair, and 0162-v1 as a second upgrade target.
4. Approved small provider seam for the exact 0162 × Local pair: lower the
   validated initial `additional_tools` prefix into the existing top-level
   namespace `tools` array before final serialization/HMAC, discard the
   item and its protocol ID, preserve remaining input, fail closed on
   wrong position/repetition/mixed shapes; extend the Local-pair
   `prompt_cache_key`/client-metadata omission to 0162; apply through both
   upstream-body builds (initial and refreshed-after-lazy-wait).
5. Documentation: forwarding contract, compatibility docs, CLI reference,
   accounting, upgrade runbook (deployment/drain/restart/key-migration/
   rollback with exact identities and the existing route/pricing
   prerequisites), and two dated verification records.

Not in scope and not performed: any merge, any deployment, any change to
permissions/pricing/quotas/route data outside owned test fixtures, any
schema migration, any other-repository edit, and any claim about current
backend versions, installed private plugins, full newer-Codex
compatibility, or production readiness.

## 3. Changes (implementation head vs base)

Product code:

- `app/slaif_gateway/modules/clients/codex_0149.py` — module version `4` →
  `5`; `id` added to the declaration field set with pre-canonicalization
  bounded validation; unknown fields still rejected.
- `app/slaif_gateway/modules/clients/codex_0162.py` (new) — static 0.162
  module/profile with version-owned profile facts, fixture digest
  `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`, and
  the pure initial-prefix lowering helper.
- `app/slaif_gateway/modules/clients/registry.py`,
  `app/slaif_gateway/modules/servers/registry.py` — 0162 module and the one
  exact Local pair registered; existing pairs untouched.
- `app/slaif_gateway/services/responses_request_policy.py` — 0.149-v5 ID
  validation seam; 0.162 taxonomy wired through the existing bounded
  declaration policy.
- `app/slaif_gateway/services/responses_gateway.py` — lowering wired
  through `_build_safe_responses_upstream_body` and both call sites
  (initial and post-lazy-wait rebuild); `prompt_cache_key`/client-metadata
  omission extended to the exact 0162 Local pair.
- `app/slaif_gateway/services/codex_module_upgrade.py` (new) — frozen
  0149-v4 tuple (literal digest
  `ca1e03a35de1eaeceb894cec9895af0c154e0d2fa0aa8da87f98716e1567f9ec`),
  target tuples, four legal edges, exact-target-first no-op ordering,
  atomic metadata+audit mutation.
- `app/slaif_gateway/cli/codex.py` — `codex upgrade-key-module` /
  `codex rollback-key-module` (dry-run default, `--apply`, `--json`);
  fixed safe errors for unsupported selectors; unexpected failures render
  the fixed generic `command_failed` message/code and never echo
  exception details (demonstrated `ValueError`/Pydantic-detail gap
  closed locally to the two new commands; no global CLI framework
  change).

Fixtures:

- `tests/fixtures/codex/0.149.0/additional-tools-id-v1.json`
  (SHA-256 `1a39db9dcc573dba2d0a10f33b4c333f27c774da2f72a4d09982d584238c00d1`)
- `tests/fixtures/codex/0.162.1/additional-tools-profile-v1.json`
  (SHA-256 `724ec7358a95e8820f02f7dd2d2b1b4ad1276d4065af2ecd329cc2ca52b5892e`)

Tests:

- `tests/unit/test_codex_additional_tools_id.py` (25) — omitted/null/valid/
  invalid ID classes, unknown-field and taxonomy invariants, upgrade
  service matrix, digest/selector rules.
- `tests/unit/test_codex_0162_client_tools.py` (30) — real registered
  module; exact synthetic 197 counts (11+5+181, labeled not-a-capture);
  ID states; invalid ID classes; unknown field/namespace/type/duplicate and
  missing-grant negatives; coherent version-owned profile facts; canonical
  fixture hash; pair registration; 256/257 tool, 16/17 namespace, and
  per-namespace boundaries; description/schema/byte ceilings with global
  limits intact.
- `tests/unit/test_upstream_payload_reconstruction.py` (82 total, +8) —
  lowering provider-body exactness, no-prefix unchanged, later-position
  safe failure, fail-closed matrix, input preservation, flag ownership,
  policy-result byte identity (declaration bytes stay in the conservative
  estimate).
- `tests/unit/test_cli_codex.py` (14) — no-configured-DB safe error,
  expected typed error code preserved, unsupported selector not echoed,
  parametrized injected unexpected `RuntimeError`/`ValueError` canary
  never echoed (fixed generic safe output, nonzero exit).
- `tests/integration/test_codex_module_upgrade_postgres.py` (14) — owned
  disposable PostgreSQL: repeat apply/rollback no-op (exact-target-first),
  source mismatch, all four legal edges, audit-failure rollback, full
  `gateway_keys` row preservation except the `client_module` JSON path and
  normal `updated_at`, stale-session row-lock refresh preserving unrelated
  policy/usage, concurrent duplicate apply = one mutation + one no-op.
- `tests/e2e/test_codex_0162_local_tools.py` (3) — real Gateway + owned
  PostgreSQL + mock loopback backend: synthetic 197 profile full gateway
  pass (lowered provider body exact, input preserved,
  `prompt_cache_key`/client metadata absent, HMAC verified over exact
  final provider bytes, two finalized ledger rows of 5 tokens with
  aggregate key total 10); all-four key grants without the fourth route
  grant → safe 400 before backend with no accounting; 0.149-v5 key
  rejects the 197 profile before accounting.
- `tests/e2e/test_openai_python_client_responses.py` — owned fixture
  extension only (neutral optional kwargs, default `False`/`None`):
  fourth route flag, `codex_limits`, and complete synthetic Codex pricing
  dimensions for the Codex-gated E2E route data; all pre-existing tests
  unchanged.

Docs: `docs/provider-forwarding-contract.md`,
`docs/responses-compatibility.md`, `docs/module-architecture.md`,
`docs/codex-compatibility.md`, `docs/compatibility-matrix.md`,
`docs/cli-reference.md`, `docs/accounting.md`, `docs/upgrade-runbook.md`
(deployment/build/drain/restart + exact key-migration/rollback sequence,
old/new identities, existing route/pricing prerequisites, stale-pin and
mixed-binary guidance, no auto-change of permissions/pricing/quotas),
`AGENTIC_CLIENT_INTEGRATION.md`, `docs/verification/README.md`, plus new
`docs/verification/codex-additional-tools-id.md` and
`docs/verification/codex-0162-local-tools.md`.

## 4. Verification evidence (this PR, exact counts)

- Unit (DB/network independent), one final focused JUnit run over the four
  codex unit files: `tests=151 failures=0 errors=0 skipped=0`
  (25 ID + 30 profile + 82 reconstruction + 14 CLI).
- Real PostgreSQL integration: `tests=14 failures=0 errors=0 skipped=0`
  (owned disposable instance via the existing `owned_pg_url` fixture;
  cleanup removed).
- E2E (real Gateway, owned PostgreSQL, mock backend): 3 passed (12.08s);
  pre-existing Codex E2E regressions in
  `tests/e2e/test_openai_python_client_responses.py` remain green.
- `ruff check app tests` clean; `git diff --check` clean.
- Historical/local legacy note: one earlier local run of the legacy 0.149
  Local streaming E2E pair was SKIPPED (environment), not a pass; the
  later independent root rerun with an explicitly owned PG URL passed both
  cases with 0 skips (external evidence, cited separately).

## 5. Independent external evidence (root/strategic; not CI)

- 21-case registered-module profile/policy probe (exact 197 counts, ID
  states, all invalid ID classes, unknown item/namespace/authority fields,
  hosted type, duplicate/missing relevant grants) —
  `strategic review-artifacts/189-a-review/independent-profile-probe.json`.
- Official 0.162.1 CLI → mock capture
  (`official-0162-policy-capture.json` + `capture-official-0162.py
  --validate-profile`): registered module normalization + policy pass.
- Official 0.162.1 CLI → real Gateway/auth/owned PG/admission/signed Local
  → real loopback HTTP mock backend: exit 0, one backend request (6.829s),
  exact 12 built-in definitions lowered, prefix removed, 3 messages
  preserved, raw client metadata/cache key absent, service Bearer
  substitution, opaque identity, HMAC over final bytes verified, ledger +
  reservation finalized (`official-0162-gateway.json` + source binding;
  `verify-official-0162-gateway.py`, explicit manual run outside pytest).
- Independent legacy 0.149 Local streaming E2E rerun: both PASS, 0 skips
  (`independent-legacy-local-e2e.xml/.json`).
- CLI unexpected-error probe demonstrating the `ValueError` echo gap
  (`cli-unexpected-error-probe.json`); closed by this implementation and
  covered by the parametrized unit tests.
- Missing-route-grant and missing-pricing negatives (archived
  `official-0162-gateway-missing-route-grant.json`,
  `official-0162-gateway-missing-pricing.json`): existing fail-closed
  gates, no backend calls; corrected with owned test fixture data only.
- Live deployed baseline (pre-change, official CLI against the deployed
  gateway): id still rejects as recorded
  (`live-client-baseline.json`). No deployed baseline is claimed fixed;
  no production deployment was performed or authorized.

## 6. Pending and honest limitations

- Final-head CI checks on the published commit are PENDING; strategy waits
  for CI and merges.
- The post-PR-220 128-worker HPC qualification remains NOT RUN.
- Pre-existing environmental gap (not introduced by this PR):
  `tests/integration/test_codex_client_modules_postgres.py` errors at
  fixture setup (global `async_test_session` → `migrated_postgres_url`
  default `postgresql+psycopg2://…` URL rejected by
  `_assert_safe_postgres_test_url`). File unmodified by this PR; it fails
  before any PR code runs. No fixture infrastructure was rebuilt.
- Evidence boundaries: unit tests are DB/network independent; E2E evidence
  uses the real Gateway with owned disposable PostgreSQL and a mock backend
  (synthetic 197-tool declaration labeled not-a-capture); official-CLI
  runs are external manual evidence; nothing here establishes
  current-backend-version qualification, installed-plugin behavior, full
  newer-Codex compatibility, or production readiness.
- No schema change; no Alembic migration in this PR. No key permissions,
  pricing, quotas, or route data are auto-changed by any code path in this
  PR; the migration writes `client_module` metadata plus one audit record
  only.
