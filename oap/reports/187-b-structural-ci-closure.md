# OAP Execution Report — Objective 187-b: structural CI closure

Report status: IMMUTABLE (finalized at the exact implementation head
`32fc43109840c0168383108800a20d153b5b256a`; published atomically as the immutable report; the
report-only SELF commit with message `Report publication commit: SELF` is
its publication commit, first parent = this implementation head; only
this report path differs).

- Implementation head SHA: 32fc43109840c0168383108800a20d153b5b256a
- Report publication commit: SELF

## 1. Work order and PR identity

- Work order: `oap/orders/187-b-structural-ci-closure.md`
  (strategic-authored; committed unchanged by the activation commit);
  `oap/active` = `187-b`.
- PR: #325 `feat: add operator branding overrides` (AMEND_EXISTING_PR —
  the same unique 187 PR as 187-a):
  https://github.com/ulfe-lmi/slaif-api-gateway/pull/325.
- Branch: `oap/187-operator-branding`; base `main` at
  `de75744f2c5a518a513a49a7b34582c87c5bbcbf` (unchanged).
- Activation commit: 530ca6e027d469ddd73fcd4e73741f9694be4ca6 (order + `oap/active` bytes
  unchanged).
- Commit chain: `de75744f` (base) → `849f873` (187-a activation) →
  `abae4ed` (187-a runtime) → `2f86d78` (187-a tests/docs) → `ba4ee11`
  (187-a report SELF) → `530ca6e` (187-b activation) → `32fc43109840c0168383108800a20d153b5b256a`
  (187-b implementation head: comment-only `main.py` trim + verification
  record update).
- The 187-a order and report remain untouched immutable history
  (prior report SHA256 `1304519eae890692a42ac68a00f82a012b8f070222ee50aab67cbca5efed464a`;
  original 187-a order SHA256
  `6aa15f339c6f4434e9fbd8e11fcde551b05f6ea31b0a6c5ffbeda99438c27ce7`).

## 2. Scope of this round (structural closure only)

Two root-authored structural checks failed on the 187-a implementation
head `2f86d78` (CI run 38980771822, unit job 117240865834: 2 failed /
4796 passed / 1 skip / 12 warnings; all other completed jobs PASS,
PostgreSQL integration pending as of the 187-a report):

1. `tests/unit/test_oap_governance.py::test_active_identifier_resolves_
   exactly_one_matching_order` — the activated 187-a order's first line
   carried a descriptive suffix
   (`# OAP Work Order — 187-a: operator branding parity`) while the test
   requires exactly `# OAP Work Order — 187-a`. Strategic authoring
   deviation; the 187-a order bytes are preserved as history, and this
   round's order carries the exact canonical first line.
2. `tests/unit/test_main_app_structure.py::test_main_app_only_wires_app_
   and_routes` — the 187-a branding router registration left
   `app/slaif_gateway/main.py` at 72 lines vs the required < 70.

Both are closed here with no executable change, no test edit, and no
protocol/dependency/runtime/financial/auth/provider/schema change.

## 3. Exact changes in this round

- `app/slaif_gateway/main.py`: 72 → 68 lines by removing one two-line
  explanatory comment and one two-line explanatory comment pair reduced to
  one line, plus one redundant blank line before the module-level
  `app = create_app()`. No code moved; router registration order,
  settings, lifespan, middleware, and error-handler wiring are exactly
  as in `2f86d78`.
- `docs/verification/operator-branding.md`: appended the precise 187-b
  structural closure proof and corrected the compose merge command to
  the exact executed form:
  `docker compose --env-file /dev/null -p slaif187-review -f
  docker-compose.yml -f docker-compose.branding.yml config
  --no-env-resolution --no-interpolate --format json` (and the
  production-base equivalent). The immutable 187-a report is preserved
  as-is, including its original command wording.
- OAP: this order + exact `oap/active` (`187-b`) committed unchanged;
  this report only. No other product, test, or protocol path touched.

## 4. Equivalence proof (main.py vs 2f86d78 bytes)

- Normalized AST dump (`ast.dump(ast.parse(src), annotate_fields=True,
  include_attributes=False)`) is byte-identical between the `2f86d78`
  file and the trimmed file.
- For every code object (3 total: module, `create_app`, nested
  `app_lifespan`), the raw instruction stream (`co_code`), non-code
  constants, `co_names`, `co_varnames`, and `co_freevars` are identical;
  only line-number tables moved.
- Focused execution: `pytest
  tests/unit/test_oap_governance.py tests/unit/test_main_app_structure.py
  tests/unit/test_documentation_inventory.py tests/unit/test_documentation_asof.py
  -o addopts= -q` → 40 passed (the existing exact-header and <70
  assertions pass unchanged).
- `ruff check app/slaif_gateway/main.py` → clean; `git diff --check` →
  clean; `scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK
  files=95`.
- All other qualified source hashes match
  `review-artifacts/187-a-review/qualified-source-hashes.json`
  byte-for-byte (main.py is the only changed file among them); the
  packaged SVG blob, the 187-a order/report, and all inherited evidence
  are unchanged.

## 5. Verification economy (per order)

No real DB/browser/container/unit matrices were repeated: the 187-a
evidence remains source-bound to the unchanged files. Inherited
qualifications stand as recorded in the 187-a report and in
`docs/verification/operator-branding.md` (root proofs: reader 24 PASS,
PNG/admin 26 PASS, corrected ancillary case PASS, all 3 native
Chromium/owned-PG browser cases PASS, all 4 real nonroot read-only-mount
container cases PASS with exact-ID cleanup verified absent, both actual
compose merges PASS, 12 CSS / 15 SVG negatives PASS; counts overlap and
are not a unique-suite total). No provider execution; the container
bootstrap remains test-only with lifespan off.

## 6. GitHub CI state at publication

Run At publication, a non-blocking snapshot via `gh pr view 325 --json
headRefOid,statusCheckRollup` observed `headRefOid`
`32fc43109840c0168383108800a20d153b5b256a` with all ten checks
COMPLETED/SUCCESS: Unit, lint, and migration head; Analyze Python;
Analyze (python); Analyze (javascript-typescript); CodeQL;
OpenAI-compatible E2E tests; Docker Compose smoke; Documentation
hygiene; PostgreSQL integration tests; Playwright browser smoke.
An earlier non-blocking snapshot (taken while this report was being
drafted) showed the same eight checks SUCCESS with PostgreSQL
integration tests and Playwright browser smoke still IN_PROGRESS;
those two checks completed SUCCESS before the publication snapshot.
No check is claimed beyond its observed state; the report-only SELF
commit published below triggers its own final-head run, whose result
is still pending at publication.

## 7. Limitations and pending state

- No check that is pending or skipped is claimed as passing; the final
  all-green requirement applies to the exact final SELF (this commit)
  before strategic review and guarded merge.
- Pending: completion of the final-SELF check matrix, strategic review,
  and the guarded merge of PR #325. No release/tag, production,
  certification, or accounting guarantee is claimed; 188 (final SLAIF
  styling) is not started by this coder.
