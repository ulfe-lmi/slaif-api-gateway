# OAP Objective 194-b — final report: catalog renderer identity upgrade (183.1 → 194.1)

Work order: `oap/orders/194-b-renderer-identity-upgrade.md`
(strategic-authored, committed unchanged on the objective branch with
`oap/active` = `194-b`; order sha256
`6e2e7da51dc99de96fe3a324557b8cbfab31717f02507b304171067201b2a57d`;
published to the shared filesystem atomically BEFORE the single control
OK, per the permanent handoff rules).
Branch: `oap/194-numbered-tables-and-metric-columns`, continuation base:
the 194-a report SELF `3487352e1e5a9d0a8b27a1ae6db14a8425414dc2`;
remote `main` `90a114a236a80469780fb9341b751520d5a3f964` at activation
(re-verified unchanged at execution start).
PR mode: AMEND_EXISTING_PR (Objective 194 = exactly one PR, #346,
https://github.com/ulfe-lmi/slaif-api-gateway/pull/346).
The coding agent never merges; no auto-merge is enabled; root reviews
independently and guard-merges.

Implementation head SHA: 10d5b29590230aaf8f25c6728b262a351177e7d0
Report publication commit: SELF

## Implementation commits (branch order)

1. `5708b848661c67e3f902e02331f2f46d5e5c5315` — "Number admin table rows
   and separate usage and quota columns (194-a)" (40 files) — unchanged.
2. `3487352e1e5a9d0a8b27a1ae6db14a8425414dc2` — "Report publication
   commit: SELF" (the immutable 194-a report) — unchanged.
3. `10d5b29590230aaf8f25c6728b262a351177e7d0` — "Version review reports
   to renderer 194.1 and document the upgrade path (194-b)": the
   bounded metadata repair, tests, and docs, together with the
   unchanged activated 194-b order and `oap/active` (11 files).

## Process honesty

This report closes the SAME continuously activated objective-194
execution: the 194-a immutable handoff was independently accepted; the
194-b order + `oap/active` bytes were atomically published to the
shared filesystem (18:06:22Z) BEFORE the single control OK, which was
consumed exactly once by the one mandated control waiter
(18:07:43Z, `CONTROL_OK_EXACT`) — no re-signal, no duplicate control
reader, no profile/model/effort change, no 195 activation. The 194-a
order (sha256 `1f0d1a175023347d10a59ea638f2480537d584a29190950bc24e05e6b5d6f0be`)
and 194-a report (sha256
`0dd8d533db667292d6bf78816da4ab2bef2c09c435ed2f3ec551d46478ef9086`)
remain immutable and verified unchanged at the remote head. Protected
untracked artifacts (`CODEX-SESSIONS.md`, `codex.sh`; gitignored
`.codex/`, `.local-provider-catalog/`) preserved untouched. Unrelated
open PRs #345, #343, #319 preserved; none touched.

## What changed

Renderer identity metadata and its verification/documentation surface
only (194-b; no UI rework — all 194-a functional evidence stands):

1. **R1 renderer identity.** `app/slaif_gateway/schemas/
   catalog_refresh.py` ONLY: `RENDERER_VERSION = "194.1"` and
   `SUPPORTED_RENDERER_VERSIONS = ("194.1",)`, with the adjacent
   version commentary updated to state exactly why pre-194 sealed
   artifacts are not byte-stable under the 194 renderer (the structural
   first-position ordinal column and the `Plan #` relabel). `SCHEMA_
   VERSION = "1"`, `POLICY_VERSION = 1`, `APPLY_PLAN_SCHEMA_VERSION =
   "1"`, the extractor/research identities (`slaif-collector/181.1`,
   `slaif-research/183.1`, `slaif-research-output/1`, research template
   `183.1`), every model field/shape, and all policy/accounting/
   authentication/plan/apply behavior are UNCHANGED. No database schema
   change or migration.
2. **R2 legacy refusal proven.** A correctly AUTHENTICATED (digests ok,
   HMAC ok) sealed context of the previous renderer generation
   (`183.1`) is refused by the EXISTING distinguishable
   unsupported-renderer guard — fixed reason
   `unsupported renderer version in sealed context; re-run the review
   under the current CLI`, never echoing the sealed value — before
   semantic recomputation and before any database connection/query in
   BOTH `apply_reviewed_run` and `apply_status`, with every sealed byte
   untouched. The `181.1`/unknown (`999.9`)/malicious canaries, the
   wrong-key refusal, and the legacy-missing-context refusal are
   preserved and re-asserted. No permissive fallback, no re-derivation,
   no re-sealing, no historical renderer fleet.
3. **R3 bounded upgrade path.** Old proposal/baseline SOURCE data is
   regenerated into a NEW run under the current CLI (`review` or
   `collect`), verified, then used through the normal apply/
   apply-status workflow; old sealed archives and original source
   dates/provenance remain untouched; re-review does not refresh source
   freshness; historical `183.1` revision/tool_version text inside new
   artifacts stays labeled supplied provenance while the new run's
   authenticated context binds `194.1`.
4. **R4 documentation.** `docs/catalog-refresh.md`: the obsolete
   "subsystem is not yet merged into main" sentence corrected (it is
   merged), the renderer version history extended through `182`/`183`
   and `194.1`, and a new "Renderer version upgrade (183.1 → 194.1)"
   section with the refusal contract, exact operator commands
   (review/collect → verify → apply/apply-status), and rollback limits.
   `docs/admin-usability.md` and `docs/first-time-operator-guide.md`:
   narrow crosslink/upgrade-accuracy additions pointing at that
   section. `docs/verification/2026-10-25-
   admin-numbered-tables-and-metric-columns.md`: honest clarification
   only — the permanent PG metric-sort coverage is every column
   ascending, the quota-tokens and budget columns descending, and Enter
   activation on the usage-requests header (the all-six-columns-
   both-directions matrix is root's separate actual-template/mock-HTTP/
   Chromium probe, not permanent PG-suite coverage); old results
   preserved.
5. **R5 PR description accuracy.** The final PR title/body describe
   the final change (numbered/split tables plus renderer upgrade); the
   shared sort script is described by its final form (no explicit
   column-mapping feature in the committed script) rather than as a
   removal of a base-main feature (that feature existed only in
   uncommitted 194-a WIP).

## Explicit non-changes

No schema, migration, model, field-shape, dependency, provider/adapter,
Responses-compatibility, transport, content-capture, auth/admission, or
accounting change. No table/filter/style/CLI-behavior change (194-b
touches no admin UI file). `tests/unit/test_catalog_refresh_research.py`
(historical research `183.1` declarations) unchanged per the order.
`services/catalog_refresh/*` implementations (sealing/apply/CLI/
rendering) reused unchanged. No production DB/SSH/deploy/release/tag;
no real provider/model/email/credential use.

## Verification (this continuation; focused; ALL synthetic data)

Environment: venv `/tmp/slaif192-coding-venv`, `PYTHONPATH=app` for
pytest; the installed `slaif-gateway` CLI for the direct proof; one
fresh owned, labeled, 127.0.0.1-loopback, tmpfs-backed disposable
PostgreSQL 16 container (owner label
`slaif194b-pg-b37631f106a14cfb830b764b938448b8`, identity inspected
BEFORE use, removed by exact ID after use); explicit `TEST_DATABASE_URL`
set BEFORE collection (import-time skip guard). No ambient
`DATABASE_URL`, no foreign containers. Real pytest exits captured via
`PIPESTATUS[0]`; JUnit under `/tmp/slaif194b/`.

### Layer 1 — focused unit (no DB; pure / mocked)

- Five affected modules — `test_catalog_refresh_seal.py`,
  `test_catalog_refresh_apply.py`,
  `test_catalog_refresh_execution_identity.py`,
  `test_catalog_refresh_collection.py`,
  `test_catalog_refresh_report.py`:
  **167 passed / 0 failed / 0 error / 0 skipped**
  (`unit-focused.xml`, real exit 0), including:
  - `test_resealed_unsupported_renderer_version_is_refused[183.1]` —
    a correctly re-signed (authenticated) `183.1` context refused with
    `digests=ok`, `hmac=ok`, the fixed reason, no forged-value echo;
    restored run re-verifies valid. The `181.1`/`999.9`/malicious
    parameters preserved;
  - NEW `test_authenticated_old_183_1_renderer_refuses_before_
    database` — forged `183.1` context re-signed with the runner key;
    BOTH `apply_reviewed_run` and `apply_status` refuse with the fixed
    reason while `create_async_engine` and `lock_catalog_tables` are
    patched to fail (NO database engine opened, NO catalog lock taken),
    no database-credential leakage in the errors, and every run
    directory byte identical before/after both refusals (read-only).
- `tests/unit/test_oap_governance.py`: 9 passed (real exit 0,
  `governance.xml`).

### Layer 2 — real CLI, offline (no PG, no provider)

- `slaif-gateway catalog-refresh review tests/fixtures/catalog_
  refresh/bundle-first-install.json --first-install ...` → exit 10
  (the documented READY_WITH_WARNINGS new-model-exposure code); the
  freshly generated run's authenticated execution context binds
  exactly `{"extractor_version": "slaif-collector/181.1",
  "policy_version": 1, "renderer_version": "194.1",
  "schema_version": "1"}`;
- `slaif-gateway catalog-refresh verify --run-dir ... --seal-key ...`
  → exit 0: `valid: yes`, `digests: ok`, `hmac: ok`, `report: ok`,
  `correspondence: ok`, `artifacts: ok`, `validation: ok`,
  `sql_evidence: replayed from sealed bytes (no SQL executed during
  verification)` — the byte-correspondence pass proves the semantic
  bundle/artifact fields (supplied source provenance included) are
  preserved while the current `194.1` identity is bound. This layer is
  mock-CLI/offline evidence, not PG/provider evidence.

### Layer 3 — one real owned PostgreSQL 16 node (real CLI / atomic apply)

- `tests/integration/test_catalog_refresh_apply_postgres.py::
  test_bootstrap_apply_is_atomic_and_retry_is_idempotent` on a FRESH
  qualified owned PG16 (explicit `TEST_DATABASE_URL` set before
  collection; the session fixture applied `alembic upgrade head` to the
  fresh database): **1 passed / 0 failed / 0 skipped**, real exit 0
  (test time 2.259 s, `pg-bootstrap.xml`). Checks the new current
  identity through the real CLI review → atomic apply → committed-
  outcome lookup → idempotent retry path. Container removed by exact
  ID after the run (cleanup label-verified).

### Layer 4 — static checks

- `ruff check app tests`: clean (exit 0). `git diff --check`: clean.
- `python scripts/check_documentation.py` (the Documentation hygiene
  CI check): `DOCUMENTATION_CHECK=OK files=118` (exit 0) — the new
  section, anchor links, and index entry are structurally valid.
- Product diff is exactly the two renderer constants plus their
  adjacent commentary.

### Honest layer separation

Layer 1 does NOT prove the broad matrix; Layer 2 does NOT prove PG
behavior; Layer 3 proves the ONE named atomic-apply node only. The
194-a browser/branding/UI suites were deliberately NOT re-run
(metadata/commentary/docs-only continuation, order A4); all 194-a
functional evidence stands as recorded. Routine CI supplies the broad
matrix at the final head. No actual Codex/live-provider/backend
qualification claim.

## CI status at the implementation head (10d5b29)

All ten check-runs for the literal implementation head
`10d5b29590230aaf8f25c6728b262a351177e7d0` are SUCCESS (observed
2026-10-25 between 18:34:25Z and 18:38:55Z via the GitHub check-runs
API):

| Check | State |
| --- | --- |
| Unit, lint, and migration head | success |
| PostgreSQL integration tests | success |
| Playwright browser smoke | success |
| OpenAI-compatible E2E tests | success |
| Docker Compose smoke | success |
| Documentation hygiene | success |
| CodeQL | success |
| Analyze Python | success |
| Analyze (python) | success |
| Analyze (javascript-typescript) | success |

No failures, cancelled, or missing checks were observed for that head.
Pushing the report-only commit triggers a new CI run at the report
head; checks for the report-containing commit are pending/not observed
at the moment this report is published and remain the strategic/root
gate before acceptance/merge. All final-head merge gates remain
required; nothing in this report claims final-head checks passed.

## Honest limits / skips

- No full local unit/browser/all-layer matrix or 128-worker sharded
  run; routine CI supplies the broad matrix at the PR head.
- The `183.1` refusal is proven with a real sealed run forged and
  re-signed with the runner key (unit layer, both apply and status
  paths); no pre-194 historical archive was edited, re-derived, or
  re-sealed anywhere.
- Screenshot/review directories (`/tmp/slaif194b/`) are local review
  artifacts, not repository content.

## Docs impact statement

Updated: `docs/catalog-refresh.md` (merged-subsystem correction;
version history through `194.1`; new "Renderer version upgrade
(183.1 → 194.1)" section — refusal contract, exact operator commands,
regeneration/rollback limits, normal upgrade/restart with no database
migration or key/policy change), `docs/admin-usability.md` and
`docs/first-time-operator-guide.md` (narrow crosslinks/upgrade
accuracy), `docs/verification/2026-10-25-admin-numbered-tables-and-
metric-columns.md` (honest clarification of the permanent metric-sort
coverage; old results preserved), `docs/verification/README.md`
(194-a entry count corrected to the final 131; 194-b entry added).
New: `docs/verification/2026-10-25-catalog-renderer-upgrade.md`
(bounded verification record with exact commands, JUnit counts,
layer separation, owned-PG facts, and honest skips). Deployment: a
normal image/code upgrade and service restart; no schema/migration/
key change.

## Safe boundary statement

- No schema/migration/model/field-shape change; no quota/accounting/
  reservation/cost/ledger change; no provider/adapter, Responses-
  compatibility, transport, content-capture, dependency, auth/
  admission, or CLI-behavior change.
- HMAC, semantic byte correspondence, freshness, locks, directory-
  handle lifecycle/binding, atomic apply, idempotency, and readonly
  status semantics are unchanged; the refusal path is read-only and
  precedes all database work.
- No secrets printed or committed; all data synthetic; the fixed error
  text never echoes the sealed (untrusted) value.
- The 194-a order and report are immutable and verified unchanged. The
  coding agent never merged and did not enable auto-merge; PR #346
  remains open for strategic review, final-head check verification,
  and guarded merge. Objective 195 is NOT activated by this execution.
