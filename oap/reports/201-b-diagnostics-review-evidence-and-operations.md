# OAP Objective 201-b — final report: diagnostics review evidence and operations

Work order: `oap/orders/201-b-diagnostics-review-evidence-and-operations.md`
(strategic-authored, committed UNCHANGED on the objective branch with
`oap/active` = `201-b` (5 bytes, no trailing newline); order sha256
`08302a0861d1df2ed94412cdccb84e52050ae218e0da65eecd392543532d3384`
(15,060 bytes), active pointer sha256
`71d3793696e08791a4398d4215a8b5551ef46d828d79fc4c24d0baed5a22ab0e`,
both verified before committing and re-verified at HEAD after the
implementation commit).
Branch: `oap/201-content-free-request-diagnostics`; base: `main`
`7cf8a7dbf02c8a5934ff25d3b28ad88b66f81afa` (merged 200 PR #356;
unchanged).
PR mode: AMEND_EXISTING_PR — the ONE existing PR for objective 201,
#357, https://github.com/ulfe-lmi/slaif-api-gateway/pull/357, base
`main`. 201-a remains immutable: IMPL
`98d7b01111027663251f4f5bb9b37492225c3641`, SELF
`1ba0b30edd85b45d04519ffa3e25aeb57fd59317`, report sha256
`3e7207229e2eedc7e9e31f2d6d45064f2c1e649c5a4b476174c721dfab9290c4`.
The coding agent never merges; no auto-merge; root reviews
independently and guard-merges.

Implementation head SHA: 5a67de30eeffbbe36defa9f716cb87c298db20f6
Report publication commit: SELF

## Implementation commit (this round)

1. `5a67de30eeffbbe36defa9f716cb87c298db20f6` — "Repair diagnostics
   CI, complete accounting evidence, and correct documentation
   (201-b)": the strategic order (bytes verified unchanged, sha256
   above) + exact `oap/active` = `201-b` + the allowed changes listed
   below (10 files total). First parent is the 201-a SELF
   `1ba0b30edd85b45d04519ffa3e25aeb57fd59317`.

## What changed (allowed paths only)

- `app/slaif_gateway/main.py` — CI repair: 87 -> 83 lines by removing
  FOUR redundant middleware-order comments only (the
  `install_request_*` docstrings already document the ordering).
  Full executable AST verified identical to 201-a SELF `1ba0b30`;
  root independently confirmed the full executable AST unchanged and
  all 456 other tracked product/migration/settings paths
  byte-identical to `1ba0b30`.
- `app/slaif_gateway/services/request_diagnostics.py` — docstrings
  ONLY: `record_failure` qualifies "never raises" (ordinary internal
  failures become typed drop outcomes; an externally propagated
  `asyncio.CancelledError` propagates by design), and `_record`
  states the accurate two-phase bounded prune/drop/drain semantics
  with at most three bounded nonblocking capacity-lock attempts with
  10 ms retries inside the single configured awaited-write budget.
  AST with docstrings removed verified identical to `1ba0b30`; the
  only two line ranges changed are the two docstring blocks.
- `tests/unit/test_request_diagnostics.py` — ONE new focused case: an
  externally propagated `asyncio.CancelledError` is NOT swallowed by
  enabled `record_failure` (controlled `_record` double, no DB).
- `tests/unit/test_request_diagnostics_middleware.py` — one
  consistent import style for the middleware module (the Code
  Quality finding); no semantic change.
- `tests/integration/test_request_diagnostics_api_postgres.py` —
  strengthened accounting oracles: `_key_state` also selects the five
  external-tool fence columns; the stream failure test compares
  per-request reserved-counter deltas across
  disabled/enabled/failing-writer modes, verifies the released
  reservation leaves ZERO residual reserved quota, and asserts the
  fence boundary stays `none`/unbound in every mode; the
  pre-admission 401 and slow-write timeout tests assert the COMPLETE
  before/after accounting state (all six counters zero, no
  ledger/reservation rows, fence none/unbound). Exact response-ID
  correlation and the fail-closed mock-egress guard preserved; no
  production accounting changes.
- `docs/configuration.md`, `docs/observability.md` — accuracy
  corrections (never-raises qualification; two-phase bounded
  semantics replacing "one bound minus one row"; no
  zero-latency/performance claim; "no remote exporter / extra
  content logs / admin UI / metrics pipeline"; status =
  calling-process setting, not live worker inspection).
- `docs/verification/2026-10-29-cli-request-diagnostics.md` — the
  201-b addendum (what changed; 201-b evidence with exact layers;
  explicit corrections to the 201-a report overclaims; the operator
  deployment and operation recipe with actual `docker compose` and
  `slaif-gateway` syntax, 0026/33-tables expectation, no
  key/policy migration, disable/lookup/cleanup loop, rollback) plus
  in-place corrections: the 201-a per-file unit paragraph no longer
  attributes the repository capacity/eviction/repeat/resolve/
  status/cleanup algorithms to the unit file (they are proven at the
  owned-PG service layer, CLI layer, and by the root probes) and
  names the 71-char overlong known-param specimen against the
  64-char column bound; the recipe `.env` block is labeled as
  file edits/additions (dotenv, preserving other settings), not
  shell assignments; cleanup uses `--json` repeated while
  `store_available=true` and `deleted_count > 0` until 0, with the
  explicit statement that `status` alone cannot prove physical
  cleanup (retained_records excludes expired rows; text status while
  OFF shows no expiry state); rollback clarifies retained history
  stays readable for a diagnostics-capable reader/re-upgrade while
  an OLDER CLI has no `diagnostics` command at all even though the
  older runtime ignores the extra table. Root independently
  verified all five recipe CLI `--help` commands (exit 0) and the
  final recipe wording.
- `oap/active` = `201-b` + the strategic order file committed
  unchanged.

No production behavior changes: no schema, settings, accounting,
replay, rate, or Redis changes; no new migration; no full-capture
arming; the 205 installed-wheel transcript remains outstanding and
unclaimed. Objectives 202-205 are NOT activated or completed by
this PR.

## Old failure and resulting evidence

- 201-a SELF `1ba0b30` final head: nine of the ten checks
  succeeded; `Unit, lint, and migration head` FAILED solely on
  `tests/unit/test_main_app_structure.py::
  test_main_app_only_wires_app_and_routes` (CI job 123253291013 /
  run 40814708847: 6217 passed / 1 failed / 1 skipped) — the
  unchanged structural guard requires the wiring module to stay
  under 84 lines and 201-a landed at 87. Root independently
  reproduced 4 passed / 1 failed with the unchanged file (root
  receipt `/tmp/slaif201-root/main-structure-before-b.xml`); root
  evidence, not an agent rerun. The same review round left one Code
  Quality COMMENT (mixed import styles for the same middleware
  module in the new test file).
- Resulting evidence: the comments-only `main.py` repair
  (87 -> 83 lines, full AST identical to `1ba0b30`) makes the
  UNCHANGED `tests/unit/test_main_app_structure.py` pass 5/5,
  including the `< 84` guard; the middleware test file now uses ONE
  consistent import style. No other product byte changed.

## Verified evidence (exact layers, commands, exits)

Environment for every agent run: existing Python 3.12 venv
(`/tmp/slaif192-coding-venv`), ambient `DATABASE_URL`/
`TEST_DATABASE_URL` unset, `-p no:cacheprovider`. No real
provider/model/client/SMTP/Redis contact; the API layer's upstream
provider is a respx mock behind a fail-closed
`assert_all_mocked` module guard.

Agent runs (JUnit-derived; root independently verified the unit
and API/PG JUnits):

1. Unit batch — JUnit `tests=126 failures=0 errors=0 skipped=0`,
   actual exit 0 (artifact `/tmp/slaif201/unit-201b.xml`):
   62 new diagnostics units (`test_request_diagnostics` 26 = 25
   from 201-a plus the ONE NEW cancellation case;
   `test_request_diagnostics_middleware` 24;
   `test_cli_diagnostics` 8; `test_alembic_request_diagnostics` 4),
   5 unchanged `test_main_app_structure` (now passing), 4
   `test_request_id_middleware` + 15 `test_responses_stream_
   failures` (unchanged consumers), and 40 governance
   (`test_documentation_inventory` 16 + `test_oap_governance` 9 +
   `test_documentation_contract_drift` 15).
2. Owned-PostgreSQL-16 real-app API layer re-run — JUnit
   `tests=11 failures=0 errors=0 skipped=0`, actual exit 0 (~20 s;
   artifact `/tmp/slaif201/pg-api-201b.xml`): the SAME 11 API/PG
   tests with the strengthened accounting oracles; fresh owned
   container (prefix `slaif201a`, owner label `slaif201a.owner`,
   loopback, tmpfs, identity inspected before migration) removed by
   exact container ID; zero owned containers remaining.
3. Governance trio re-run AFTER the final documentation edits —
   JUnit `tests=40 failures=0 errors=0 skipped=0`, actual exit 0
   (artifact `/tmp/slaif201/gov-trio-rerun.xml`: drift 15 +
   inventory 16 + OAP 9).
4. Static gates: `ruff check app/ tests/` all checks passed;
   `python3 scripts/check_documentation.py` ->
   `DOCUMENTATION_CHECK=OK files=128`; `git diff --check` clean.
5. AST/byte identity vs `1ba0b30`: `main.py` full AST identical
   (comments-only delta, 87 -> 83 lines);
   `services/request_diagnostics.py` AST with docstring statements
   removed identical (exactly two docstring blocks changed); root
   independently confirmed all other tracked product/migration/
   settings paths byte-identical.
6. 201-a owned-PG storage-layer proof (`/tmp/slaif201/pg-service-
   4.xml`, 11 PASS) remains valid without rerun: the storage PG
   algorithms are unchanged by 201-b; the 201-b API/PG and unit
   runs overlap the same tests with strengthened oracles.

Root evidence (credited to root, not re-run by the agent):

- 201-a final-head CI state and the exact CI failure (above).
- The 14-check projection probe = 13 behavior checks + 1
  source-stability check (probe assertions, not 14 pytest tests).
- All five recipe CLI `--help` commands exit 0 on the current
  executable; the full executable AST and 456 other tracked
  product/migration/settings paths unchanged vs `1ba0b30`.

Prior versus new counts (JUnit-derived; the earlier "71 tests"
terminal prose was a partial count and is superseded): 201-a
introduced 83 UNIQUE new cases (61 unit + 11 storage PG + 11 API PG
across distinct runs). 201-b adds exactly ONE unique new case (the
cancellation regression; 84 total). Every other 201-b run is a rerun
of the same tests with strengthened oracles and counts as OVERLAP,
not additional unique evidence. The unit Typer/CliRunner CLI cases
are typed-service boundary tests; the actual CLI+PG subprocess
evidence is the API/PG layer's real-CLI test plus the root probes.
The 205 installed-wheel transcript remains outstanding and
unclaimed.

## Explicit corrections to the 201-a report overclaims (old report stays immutable)

- "6 new test files (71 tests)" -> 83 unique new cases (61 unit +
  11 storage PG + 11 API PG); 201-b adds 1 (84 total).
- "14/14 probe" -> 14 probe checks = 13 behavior + 1
  source-stability (probe assertions, not 14 pytest tests).
- "drains at up to one bound minus one row" -> two-phase bounded
  semantics: the expiry-prune and oldest-eviction phases each have
  their own bound; a capacity drop COMMITS the bounded prune without
  inserting; at most three bounded nonblocking lock attempts with
  10 ms retries inside the single awaited-write budget; pre-existing
  excess drains across subsequent non-repeat writes, never by an
  unbounded sweep.
- "record_failure never raises" -> ordinary internal failures
  become typed drop outcomes; an external `CancelledError`
  propagates by design (no catch-BaseException anywhere in the
  write path).
- "NO new telemetry channels" -> this is an authorized PostgreSQL
  index; no remote exporter / extra content logs / admin UI /
  metrics pipeline is added. The independent full-capture section
  and its privacy boundary are unchanged.
- "rather than slowing the response" -> removed; the awaited
  bounded completion latency is disclosed with no
  zero-latency/performance claim.
- The 25 service UNIT cases prove projection/masking/default-off/
  route-fact boundaries; the repository capacity/eviction/repeat/
  resolve/status/cleanup algorithms are proven at the owned-PG
  service layer, the CLI layer, and by the root probes — not by
  the unit file. (The 201-a verification paragraph is corrected in
  place in the 201-b addendum round; the immutable 201-a report is
  NOT rewritten.)

## Schema / key migration / rollback

- No NEW migration in 201-b. The only schema change for the whole
  objective remains 201-a's already-authorized single migration
  `0026_request_diagnostics` (head after
  `0025_catalog_refresh_applications`; 33 tables; verified up/down
  on real PG16).
- No gateway-key/module identity or policy migration; no key
  recreation/rotation; no accounting-data rewrite.
- Rollback (full recipe in the verification document): disable
  recording (`REQUEST_DIAGNOSTICS_ENABLED=false`) and recreate the
  api containers FIRST — the retained table stays readable for a
  diagnostics-capable reader/re-upgrade while the rolled-back code
  ignores it (an OLDER CLI has no `diagnostics` command at all).
  An explicit `0026_request_diagnostics` downgrade irreversibly
  deletes only the diagnostic history and must be coordinated with
  the old code and stopped writers. Disabling never erases
  retained records; no all-record delete command exists.

## Limitations and current CI state

- The NEW 201-b SELF requires ALL ten final-head checks on its head;
  they are PENDING at this publication and remain the root-gated
  merge gate. No all-green claim is made here; skipped, missing,
  pending, cancelled, and unavailable are NOT passes.
- The unit CLI cases are typed-service boundary tests (Typer/
  CliRunner); actual CLI+PG subprocess evidence is the API/PG
  layer plus the root probes. The 205 installed-executable
  acceptance transcript (all eleven commands) remains outstanding
  and unclaimed; no hosted-tool/hold/reconciliation qualification
  is claimed from the strict-mode checks.
- No production deployment, merge, auto-merge, release, or tag
  occurs from this PR. Release remains `v0.1.0-rc.1` only.
  Objectives 202-205 are not activated; no next-objective
  completion is claimed.

## Changed paths (implementation commit `5a67de3`)

`app/slaif_gateway/main.py` (comments only),
`app/slaif_gateway/services/request_diagnostics.py` (docstrings
only), `tests/unit/test_request_diagnostics.py`,
`tests/unit/test_request_diagnostics_middleware.py`,
`tests/integration/test_request_diagnostics_api_postgres.py`,
`docs/configuration.md`, `docs/observability.md`,
`docs/verification/2026-10-29-cli-request-diagnostics.md`,
`oap/active`, `oap/orders/201-b-diagnostics-review-evidence-and-
operations.md` (strategic order, unchanged).

Documentation updated: docs/configuration.md, docs/observability.md, docs/verification/2026-10-29-cli-request-diagnostics.md
