# OAP Coding-Agent Report — 165-a

## Work order
- Identifier: 165-a
- Work-order file: `oap/orders/165-a-readiness-authority-model.md`
- Numeric objective: 165
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Executive summary
Established a defensible readiness documentation authority model. `docs/beta-readiness.md` is re-framed in place as an explicitly dated verification/readiness record for `main` commit `8f2813bf745b90221da33a7cfaf40726c5b1b480` (reviewed 2026-08-24) carrying one machine-readable `<!-- readiness-record-as-of: <40-hex-sha> -->` marker and a short `## Current status` section that delegates current status to `docs/rc2-feature-scope.md`, the `docs/verification/` dated archive, and GitHub CI. The six current-facing pointer phrases across `README.md`, `docs/README.md`, `docs/rc-beta.md`, and `docs/support-policy.md` were re-pointed to dated evidence; `docs/verification/README.md` gained one appended cross-reference row. `scripts/check_documentation.py` gained a root-parameterized `check()` plus mechanical as-of marker invariants (rule R1 for non-archive documents claiming `current verification/readiness`, rule R2 for `docs/beta-readiness.md`), each condition producing a distinct file-and-rule-labelled error. Eleven new unit tests in `tests/unit/test_documentation_asof.py` cover all required synthetic-tree negative/positive probes and real-repository state. Historical evidence bodies are byte-preserved; no product capability, application code, migration, workflow file, or dependency was changed; no verification matrix was re-run and no current-main re-qualification claim is made.

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 302
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/302
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/165-readiness-authority-model`
- Starting remote SHA: `65666f5886832034c52211fdd7604046557e6ada`
- Implementation head SHA: 016d0fb01e0839523a4e94cade2f56b17c87dade
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit:
  - `6ff34e81713ba365471a611e40f46d8d04a50154` `obj165: establish defensible readiness authority model`
  - `016d0fb01e0839523a4e94cade2f56b17c87dade` `oap: activate 165-a readiness authority model` (carries the strategic-authored order and `oap/active` unchanged)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `docs/beta-readiness.md`: replaced the two-line authority blockquote with dated-record framing (evidence boundary `main` `8f2813bf745b90221da33a7cfaf40726c5b1b480`, reviewed 2026-08-24; not a current-state claim about later `main` commits; not a release/production/security/compliance/SLA approval); added exactly one machine marker line directly under the blockquote, outside any code fence; added a short `## Current status` section immediately after the header block; kept the `Current review date: 2026-08-24` line.
- `README.md`: line-157 pointer phrase `current readiness` → `readiness record (dated; evidence as-of the named commit)`; link target unchanged; top brand block byte-identical; line-32 `readiness evidence` phrase unchanged.
- `docs/README.md`: line 15 `current readiness` → `dated readiness record`; line 43 `Current verification and release-readiness evidence` → `Dated verification and release-readiness records`; line 48 `Current beta readiness` → `Beta readiness record (dated 2026-08-24)`; all links unchanged.
- `docs/rc-beta.md`: line 4 `**Current readiness:**` → `**Readiness record:**` with `(dated; evidence as-of the named commit)`; `## Current verification evidence` → `## Dated verification evidence (latest on record)` with one inserted sentence stating the section names the latest recorded production-path qualification and does not assert that current `main` has been re-qualified after that date.
- `docs/support-policy.md`: line 4 `see [current readiness](beta-readiness.md)` → `see the dated readiness record ([beta-readiness.md](beta-readiness.md))`.
- `docs/verification/README.md`: appended one index row `[2026-08-24 RC-beta readiness record](../beta-readiness.md)` framed as a dated record for `main` `8f2813bf745b90221da33a7cfaf40726c5b1b480` (reviewed 2026-08-24), historical/dated, not a current-state claim; existing rows not reordered or rewritten.
- `scripts/check_documentation.py`: refactored `check(root: Path | None = None)` (defaults to the real repository root) so structure/orphan/as-of checks run against an explicit root; README brand-fragment check still applies to the real root; added `AS_OF_MARKER_RE` (exactly `<!-- readiness-record-as-of: <40 lowercase hex> -->`, whitespace tolerant around the colon), a marker-candidate regex, and rule R1 (non-archive file with case-insensitive `current verification/readiness` in body must carry exactly one valid marker whose SHA occurs in the prose) and rule R2 (`docs/beta-readiness.md` always); zero valid markers, multiple markers, non-40-hex payload, and SHA-absent-from-prose each produce distinct file-and-rule-labelled errors and `DOCUMENTATION_CHECK=FAIL` with non-zero exit. No other rule changed; no network calls, no ancestry checks, no workflow changes.
- `tests/unit/test_documentation_asof.py` (new): 11 tests — synthetic-tree probes (claim without marker fails; claim with one valid marker + prose SHA passes; two markers fails; non-40-hex payload fails; marker SHA absent from prose fails; `docs/verification/2026-...` archive with claim and no marker passes; `docs/beta-readiness.md` without marker fails under R2; no-claim/no-marker file passes) plus real-repository tests (full checked set passes at the PR head; `docs/beta-readiness.md` has exactly one marker for the pinned SHA bound to prose; the stale phrase `Current verification/readiness summary for merged code` occurs nowhere in the checked set).
- `oap/orders/165-a-readiness-authority-model.md`, `oap/active`: committed and pushed with the objective implementation, strategic bytes unchanged.

## Files changed
- `docs/beta-readiness.md`
- `README.md`
- `docs/README.md`
- `docs/rc-beta.md`
- `docs/support-policy.md`
- `docs/verification/README.md`
- `scripts/check_documentation.py`
- `tests/unit/test_documentation_asof.py` (new)
- `oap/orders/165-a-readiness-authority-model.md` (new, unchanged strategic bytes)
- `oap/active` (strategic update 164-a → 165-a, unchanged strategic bytes)
- `oap/reports/165-a-<slug>.md` (this report, report-only final commit)

## Acceptance-criteria evidence
### Criterion 1 — dated reframing of docs/beta-readiness.md, byte-identical body
- Result: pass
- Evidence: `git diff docs/beta-readiness.md` shows a single hunk ending before `## Current merged-main summary`; the replacement script asserted the exact 7-line original top block and preserved `rest` byte-for-byte (`rest.startswith("## Current merged-main summary")` True). Marker line is directly under the blockquote, outside any code fence; `Current review date: 2026-08-24` kept; `## Current status` section states all four required delegations.
### Criterion 2 — six pointer phrases corrected, named current-status surface
- Result: pass
- Evidence: exact single-occurrence replacements verified by assertion for `README.md` (line 157), `docs/README.md` (lines 15/43/48), `docs/rc-beta.md` (line 4 + heading + inserted sentence), `docs/support-policy.md` (line 4); `docs/verification/README.md` row appended only.
### Criterion 3 — mechanical freshness invariant + unit tests
- Result: pass
- Evidence: `AS_OF_MARKER_RE` matches exactly `<!-- readiness-record-as-of: <40 lowercase hex> -->` (whitespace tolerant around the colon); R1/R2 implemented with distinct error labels (`[asof-R1]`/`[asof-R2]`); `python -m pytest tests/unit/test_documentation_asof.py -v`: 11 passed, including all five required negative probes (claim-without-marker, two markers, malformed payload, SHA-absent-from-prose, beta-readiness-without-marker) and the archive exemption.
### Criterion 4 — one coherent PR, allowed paths only
- Result: pass
- Evidence: PR #302 from remote `main` `65666f58...`; `git diff --name-only` against base lists only the allowed application-facing paths plus OAP protocol files; README brand block first and byte-identical (enforced by the checker's brand fragment rule, which passed).

## Local verification
- `python scripts/check_documentation.py`: PASSED — `DOCUMENTATION_CHECK=OK files=79` (identical file count to pre-change behavior: 3 root docs + 76 docs/**/*.md)
- `python -m pytest tests/unit/test_documentation_asof.py -v`: PASSED — 11 passed
- `python -m pytest tests/unit/test_documentation_inventory.py tests/unit/test_documentation_contract_drift.py -q`: PASSED — 21 passed
- `python -m pytest tests/unit -q`: 4043 passed, 1 failed, 0 skipped (total 4044 = 4033 main-baseline tests + 11 new). The single failure, `tests/unit/test_qwen38_text_codex_candidate.py::test_live_branch_uses_codex_slaif_and_numeric_loopback_plumbing`, is a pre-existing local-environment mismatch, not caused by this diff: the machine's `/usr/bin/codex` reports `codex-cli 0.154.0` while the fixture pins `CODEX_VERSION = "0.148.0"` (`VerificationError: codex_version_mismatch`). The identical failure reproduces on the pristine `origin/main` base (`65666f5`) in a detached read-only worktree. The diff touches no application, test-fixture, or verifier code.
- `python -m ruff check scripts/check_documentation.py tests/unit/test_documentation_asof.py`: PASSED — all checks passed
- `git diff --check`: PASSED — clean
- Negative probes (explicit test identities, all PASSED in `test_documentation_asof.py`): `test_claim_phrase_without_marker_fails`; `test_two_valid_markers_fail`; `test_marker_payload_not_40_hex_fails`; `test_marker_sha_absent_from_prose_fails`; `test_beta_readiness_without_marker_fails_under_r2`; plus positive/identity probes `test_claim_phrase_with_valid_marker_and_prose_sha_passes`, `test_archive_file_with_claim_and_no_marker_passes`, `test_file_without_claim_phrase_and_without_marker_passes`.
- PostgreSQL/Redis/E2E/browser/provider evidence: NOT RUN — deliberately not required by this order: the change set is documentation plus one pure-Python static checker and its unit tests, with no state, accounting, network, streaming, or secret boundary touched.

## GitHub CI / required checks
## GitHub CI / required checks
- Check state observed for implementation head `016d0fb01e0839523a4e94cade2f56b17c87dade` (observed 2026-09-17 02:45 Europe/Ljubljana, `gh pr checks 302`):
- Unit, lint, and migration head: SUCCESS (1m36s)
- Documentation hygiene: SUCCESS (5s)
- OpenAI-compatible E2E tests: SUCCESS (1m42s)
- Playwright browser smoke: SUCCESS (1m24s)
- Docker Compose smoke: SUCCESS (57s)
- PostgreSQL integration tests: SUCCESS (2m38s)
- Code Quality Analyze (javascript-typescript): SUCCESS (46s)
- Code Quality Analyze (python): SUCCESS (2m3s)
- CodeQL Analyze Python: SUCCESS (1m8s)
- CodeQL (aggregate): SUCCESS (2s)
- All required checks green for the implementation head at report drafting: yes
- Report-only commit may trigger fresh checks: strategic model must verify the `SELF` commit without rewriting this report

## Local setup / dependencies
- Packages/tools/services installed or configured: none. Used the existing repository virtualenv (`.venv`, Python 3.12.3, pytest 9.0.3).
- `sudo`-level setup performed: none.
- Durable setup changes committed/documented: none.

## Documentation
- Documentation-impact statement (per `AGENTS.md` section 5.1):
  - `docs/beta-readiness.md`: authority surface changed from an undated "current verification/readiness summary for merged code" claim to a dated-record framing explicitly bound to `main` commit `8f2813bf745b90221da33a7cfaf40726c5b1b480` (reviewed 2026-08-24) with a machine-auditable as-of marker; a `## Current status` section now names `docs/rc2-feature-scope.md`, `docs/verification/`, and GitHub CI as the current-status surface. The 2026-08-24 and 2026-05-01 historical bodies are byte-preserved — proof: the single diff hunk for this file ends at the line before `## Current merged-main summary` (diff boundary `@@ -1,10 +1,23 @@`), so every line from `## Current merged-main summary` to end of file is unchanged, and no verification numbers were rewritten.
  - `README.md`: one pointer phrase now describes the target as a dated readiness record; no status claims added or removed.
  - `docs/README.md`: three pointer phrases now describe dated records; authority-map row re-labelled "Dated verification and release-readiness records".
  - `docs/rc-beta.md`: readiness pointer now names the dated record; the verification-evidence section is titled as dated/latest-on-record and explicitly disclaims current-main re-qualification.
  - `docs/support-policy.md`: release-state pointer now references the dated readiness record.
  - `docs/verification/README.md`: index now cross-references the top-level dated readiness record (dated, not a current-state claim) without moving the file.
  - `scripts/check_documentation.py` + `tests/unit/test_documentation_asof.py`: the Documentation hygiene CI job now mechanically enforces the as-of marker contract (R1/R2), making future stale current-authority claims a CI failure instead of silent debt.
  - No other contract documents changed; `docs/rc2-feature-scope.md`, `docs/product-scope.md`, compatibility, accounting, and security documents untouched.

## Safety and scope confirmations
- Unrelated files changed: no — diff limited to the allowed paths plus OAP protocol files.
- Production secrets accessed: no
- Production systems accessed: no
- Required tests skipped/not run: no local skips; PostgreSQL/Redis/E2E/browser/provider evidence deliberately not run per the order's explicit non-requirement (reason stated in Local verification)
- Scope deviation: no
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO
- Report-publication commit changes only this report file: yes

## Known limitations / blockers
- The local full-unit result contains one pre-existing environment failure (local `codex-cli 0.154.0` vs pinned `0.148.0` fixture), reproduced identically on the pristine `origin/main` base; it is unrelated to this diff and should be evaluated against GitHub CI state.
- The checker deliberately does not enforce recency (as-of within N commits) or ancestry against HEAD (CI checkouts are shallow); staleness is made visible/auditable via the marker vs current main, per the order's contract decisions.

## Recommended strategic follow-up
None beyond standard strategic review and merge-gate verification. If desired in a later objective, an ancestry check of the marker SHA against `main` could be added where a deep checkout is available.
