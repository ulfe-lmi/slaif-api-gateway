# 2026-10-25 Objective 194-b catalog renderer identity upgrade verification

Recorded 2026-10-25 (UTC) in the OAP coding worktree for objective 194,
continuation **194-b** (`oap/194-numbered-tables-and-metric-columns`,
SAME PR #346, continuation base the 194-a report SELF
`3487352e1e5a9d0a8b27a1ae6db14a8425414dc2`). This record describes what
the focused runs below actually proved. It is not a full-matrix rerun,
not a release/production claim, and it does not re-run or supersede the
194-a functional evidence (`2026-10-25-admin-numbered-tables-and-metric-columns.md`).

## Scope under test (194-b)

- R1: advance ONLY the report renderer identity metadata —
  `RENDERER_VERSION = "194.1"` and
  `SUPPORTED_RENDERER_VERSIONS = ("194.1",)` in
  `app/slaif_gateway/schemas/catalog_refresh.py`, plus the adjacent
  version commentary. `SCHEMA_VERSION = "1"`, `POLICY_VERSION = 1`,
  `APPLY_PLAN_SCHEMA_VERSION = "1"`, the extractor/research identities
  (`slaif-collector/181.1`, `slaif-research/183.1`,
  `slaif-research-output/1`, research template `183.1`), all model
  fields/shapes, and all policy/accounting/authentication/plan/apply
  behavior are UNCHANGED. No database schema change or migration.
- R2: a correctly authenticated (digests ok, HMAC ok) sealed context of
  the previous renderer generation (`183.1`) is refused by the
  EXISTING distinguishable unsupported-renderer guard — fixed reason,
  never echoing the sealed value — before semantic recomputation and
  before any database contact, in both `apply` and `apply-status`,
  with the sealed bytes untouched. The `181.1` / unknown / malicious
  canaries and the wrong-key / legacy-context refusals are preserved.
- R3/R4: bounded upgrade path and docs — current-only support,
  explicit old-review refusal, exact operator commands to regenerate
  into a NEW run, rollback limits, normal upgrade/restart with no
  database migration or key/policy change; the obsolete "not yet
  merged" catalog versioning sentence corrected.

## Environment

- Python: `/tmp/slaif192-coding-venv` (project venv), `PYTHONPATH=app`
  for pytest; the installed `slaif-gateway` CLI for the direct
  review→verify proof.
- Database: ONE fresh owned, labeled, 127.0.0.1-loopback, tmpfs-backed
  disposable PostgreSQL 16 container (owner label
  `slaif194b-pg-b37631f106a14cfb830b764b938448b8`, identity inspected
  BEFORE use; removed by exact ID after the run). Explicit
  `TEST_DATABASE_URL` set BEFORE collection (the integration module
  has an import-time skip guard). No ambient `DATABASE_URL`, no
  foreign containers.
- Synthetic fixture data only — no real provider/model/email, no
  production DB/SSH/deploy.

## Layer 1 — focused unit (no DB; pure / mocked)

Command: `PYTHONPATH=app pytest
tests/unit/test_catalog_refresh_seal.py
tests/unit/test_catalog_refresh_apply.py
tests/unit/test_catalog_refresh_execution_identity.py
tests/unit/test_catalog_refresh_collection.py
tests/unit/test_catalog_refresh_report.py -q -p no:cacheprovider
--junitxml=/tmp/slaif194b/unit-focused.xml` — **167 passed / 0 failed /
0 error / 0 skipped**, real pytest exit `0` (captured via
`PIPESTATUS[0]`).

New/strengthened assertions in this layer:

- `test_resealed_unsupported_renderer_version_is_refused` now
  parameterizes `183.1` (the concrete pre-194 boundary — a correctly
  re-signed, i.e. correctly AUTHENTICATED, legacy context) alongside
  the preserved `181.1`, `999.9`, and `CANARY-SECRET-…malicious`
  values: refused with `digests=ok`, `hmac=ok`, and the fixed
  `unsupported renderer version in sealed context; re-run the review
  under the current CLI` reason; the forged value never reaches any
  error output; the restored run re-verifies valid.
- NEW
  `test_authenticated_old_183_1_renderer_refuses_before_database`:
  forges the sealed context to `renderer_version="183.1"` and re-signs
  the run with the runner key, then proves BOTH `apply_reviewed_run`
  and `apply_status` raise the seal-authentication refusal (fixed
  reason, `digests=ok`, `hmac=ok`, no database-credential leakage)
  with `create_async_engine` and `lock_catalog_tables` patched to
  fail — i.e. NO database engine is opened and NO catalog lock is
  taken — and that every byte of the run directory is identical after
  both refusals (read-only refusal).
- The current-context tests bind `RENDERER_VERSION` (now `194.1`)
  through the same constant: `test_new_sealed_run_binds_authenticated_
  execution_context` (fresh CLI run verifies clean, context binds the
  running code's constants) and the generator-versions tests in
  execution-identity/collection.
- `tests/unit/test_catalog_refresh_research.py` (historical research
  `183.1` declarations) is UNCHANGED per the order.

Also focused and green: `tests/unit/test_oap_governance.py` — 9
passed, real exit 0 (`/tmp/slaif194b/governance.xml`).

## Layer 2 — real CLI, offline (no PG, no provider)

Exact commands (installed `slaif-gateway` CLI, synthetic fixture
bundle, tmp run root with operator-restrictive permissions):

```
slaif-gateway catalog-refresh review \
  tests/fixtures/catalog_refresh/bundle-first-install.json --first-install \
  --run-root <tmp>/runs --seal-key <tmp>/seal.key     # exit 10 (READY_WITH_WARNINGS)
slaif-gateway catalog-refresh verify --run-dir <tmp>/runs/fixture-first-install-001 \
  --seal-key <tmp>/seal.key                           # exit 0
```

Observed: the freshly generated run's authenticated execution context
binds exactly `{"extractor_version": "slaif-collector/181.1",
"policy_version": 1, "renderer_version": "194.1",
"schema_version": "1"}`; `verify` reports `valid: yes`,
`digests: ok`, `hmac: ok`, `report: ok`, `correspondence: ok`,
`artifacts: ok`, `validation: ok`, and
`sql_evidence: replayed from sealed bytes (no SQL executed during
verification)` — the report byte-correspondence pass proves the
semantic bundle/artifact fields (including the supplied source
provenance text) are preserved while the current renderer identity is
bound. Exit 10 is the documented READY_WITH_WARNINGS code for the
fixture's new-model exposure warning. This is unit/mock-CLI-layer
evidence (no PG, no provider).

## Layer 3 — one real owned PostgreSQL 16 node (real CLI / atomic apply)

Command: `TEST_DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1:<port>/test
PYTHONPATH=app pytest
tests/integration/test_catalog_refresh_apply_postgres.py::test_bootstrap_
apply_is_atomic_and_retry_is_idempotent -q -p no:cacheprovider
--junitxml=/tmp/slaif194b/pg-bootstrap.xml` — **1 passed / 0 failed /
0 skipped**, real pytest exit `0` (test time 2.259 s). The session
fixture applied `alembic upgrade head` to the FRESH owned database
before the test. This checks the new current identity
(`194.1`) through the real CLI review → atomic apply → committed-
outcome lookup → idempotent retry path on real PostgreSQL 16. The
container was removed by exact ID after the run (cleanup label-
verified).

## Layer 4 — static checks

- `ruff check app tests`: clean (exit 0).
- `git diff --check`: clean.
- Product diff is exactly the two renderer constants plus their
  adjacent commentary in `schemas/catalog_refresh.py` — no other
  product file changed.

## Honest layer separation and limits

- Layer 1 (pure/mocked) does NOT prove browser behavior or the broad
  matrix; Layer 2 (real CLI, offline) does NOT prove PG behavior;
  Layer 3 proves the ONE named atomic-apply node, not the whole
  integration/browser matrix. Routine CI supplies the broad matrix at
  the final head.
- The 194-a browser/branding/UI suites were deliberately NOT re-run:
  this continuation changes metadata, commentary, tests, and docs
  only (order A4). All 194-a functional evidence stands as recorded
  (with its same-day honest clarification of the permanent
  metric-sort coverage: every column ascending, quota-tokens and
  budget descending, Enter on the usage-requests header; the
  all-six-columns-both-directions matrix is root's separate
  actual-template/mock-HTTP/Chromium probe, not permanent PG-suite
  coverage).
- The `183.1` refusal is proven at the unit layer with a real sealed
  run (forged + re-signed with the runner key) and at the real-PG
  layer's fresh run by the current-identity acceptance; no pre-194
  historical archive was edited, re-derived, or re-sealed anywhere.
- No actual Codex/live-provider/backend qualification claim; no
  database migration, no schema or field-shape change, no
  key/policy change.

## GitHub / CI state at recording time

The implementation commit of this continuation and its report
publication are recorded in the OAP report for 194-b (the report's
`SELF` commit). Final-head check verification remains the
strategic/root gate; nothing here claims checks that have not been
observed.
