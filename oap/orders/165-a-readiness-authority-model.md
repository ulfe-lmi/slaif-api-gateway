# OAP Work Order — 165-a

PR mode: `CREATE_NEW_PR`

## Objective and business reason

Establish a defensible readiness documentation authority model so that no
repository document labelled as current verification/readiness authority can
silently stay pinned to a historical commit.

`docs/beta-readiness.md` currently carries the line
`**Authority:** Current verification/readiness summary for merged code` while
its evidence is pinned to 2026-08-24 / main commit
`8f2813bf745b90221da33a7cfaf40726c5b1b480`, which is 134 commits behind the
verified current main. Five other current-facing pointer phrases in
`README.md`, `docs/README.md`, `docs/rc-beta.md`, and `docs/support-policy.md`
present that dated record as current. The Documentation hygiene CI job
(`scripts/check_documentation.py`) performs only structural, link, anchor,
orphan, and brand checks, so CI is fully green while a stale current-authority
claim sits on main. This is truth/governance debt: the fix is the authority
model, not a refresh of numbers.

The repair, in one bounded documentation/objective:

1. Re-frame `docs/beta-readiness.md` as an explicitly **dated** verification
   record for its named commit, with a machine-readable as-of marker, while
   keeping its entire historical evidence body byte-identical.
2. Correct the six current-facing pointer phrases across four other documents
   so they point to dated evidence, and make `docs/rc2-feature-scope.md`
   (already the canonical feature-status document) plus `docs/verification/`
   plus GitHub CI the named current-status surface.
3. Add a small mechanical freshness invariant to
   `scripts/check_documentation.py` with unit tests: any non-archive
   document claiming `current verification/readiness` authority, and
   `docs/beta-readiness.md` itself, must carry exactly one valid
   `<!-- readiness-record-as-of: <40-hex-sha> -->` marker whose SHA appears in
   the document prose. This makes every such record's evidence boundary
   machine-auditable and prevents regression of the observed failure mode.

This order changes documentation honesty and one pure-Python checker. It
implements no product capability, runs no verification matrix, makes no claim
about current main being re-qualified, and touches no application code.

Complete one coherent Objective-165 PR through implementation, focused
verification, all required CI, skeptical self-review, and one immutable
report. A test failure, stale fixture, or documentation conflict is work to
resolve in this round, not a reason to publish an intermediate failure report
or ask the human for routine decisions. No provider call, Local mutation,
deployment, release, GitHub settings, or production action is authorized.

## Reconciled authority and current state

Verified 2026-09-17 by the strategic model against live GitHub and the shared
worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Verified remote `main`:
  `65666f5886832034c52211fdd7604046557e6ada`, merge tree
  `06946cf96dcb24c56a4560f8299271cb9c4d60fb`, app tree
  `3cf53dec5abde686d3903f234f05207faf9d5996`.
- All nine emitted main-branch checks on `65666f5` are SUCCESS (CI job set:
  Unit/lint/migration head, Documentation hygiene, OpenAI-compatible E2E,
  Playwright browser smoke, Docker Compose smoke, PostgreSQL integration;
  Code Quality Analyze js/ts and python; CodeQL Analyze Python). Post-merge
  CI unit run: `4032 passed, 1 skipped`; E2E job: `54 passed`.
- Objective 164 is terminally merged and verified (PR #301, merged
  2026-09-13 04:05:49 Europe/Ljubljana). Shared `oap/active` starts at
  terminal `164-a`. Objective 165 is unused: no `165-*` order, report,
  branch, or PR exists.
- Open PRs are exactly #250 and #224 (Dependabot dependency bumps). They are
  unrelated and must remain untouched. PR #291 (obj155) was closed as
  superseded by the strategic model at 2026-09-16T23:58:19Z with a permanent
  supersession comment; its branch
  `oap/155-local-coding-signed-server-module` is retained as a historical
  evidence store. It is not a merge vehicle and must not be referenced as an
  open PR.
- The only release is historical prerelease `v0.1.0-rc.1`; no
  release/deployment action follows this objective.
- Stale current-facing claims verified on `65666f5`:
  - `docs/beta-readiness.md` line 3:
    `**Authority:** Current verification/readiness summary for merged code`;
    evidence pinned to `8f2813bf745b90221da33a7cfaf40726c5b1b480`
    (2026-08-24 review), 134 commits behind current main.
  - `README.md` line 157: `[current readiness](docs/beta-readiness.md)`.
  - `docs/README.md` lines 15, 43, 48: `current readiness`, `Current
    verification and release-readiness evidence`, `Current beta readiness`.
  - `docs/rc-beta.md` line 4: `**Current readiness:** See beta-readiness.md`;
    line 21 section `## Current verification evidence` names the 2026-08-24
    record as latest without stating that current main has not been
    re-qualified since.
  - `docs/support-policy.md` line 4: `see [current readiness](beta-readiness.md)`.
- `docs/verification/README.md` is deliberately a dated archive of
  commit-specific verification records and is correctly framed; it needs only
  a cross-reference row to the dated readiness record.
- `scripts/check_documentation.py` (172 lines) currently validates Markdown
  structure, internal links/anchors, single-H1 and heading-step rules
  (exempting `docs/releases/v*`, `docs/security/reviews/2026-*`, and
  `docs/verification/2026-*` historical bodies), orphan navigation, and
  README brand fragments. It contains no freshness or authority-claim check.
- `docs/rc2-feature-scope.md` remains the canonical RC2 feature-status
  document per `AGENTS.md` section 0.1 and is current; it is not modified.

## PR contract

- Base: `main` at `65666f5886832034c52211fdd7604046557e6ada`.
- Branch: `oap/165-readiness-authority-model`.
- Title: `obj165: establish defensible readiness authority model`.
- One new PR for `165-a`; later `165-b`... rounds amend the same PR.

## Allowed paths

Exactly these application-facing paths (plus the OAP protocol files):

- `docs/beta-readiness.md`
- `README.md`
- `docs/README.md`
- `docs/rc-beta.md`
- `docs/support-policy.md`
- `docs/verification/README.md`
- `scripts/check_documentation.py`
- `tests/unit/test_documentation_asof.py` (new file)
- `oap/orders/165-a-readiness-authority-model.md` (unchanged strategic
  bytes), `oap/active`, `oap/reports/165-a-*.md`

No other path may appear in the diff. The README top SLAIF logo/link block
must remain first and byte-identical.

## Required documentation changes

1. `docs/beta-readiness.md`:
   - Replace the two-line authority blockquote
     (`> **Authority:** Current verification/readiness summary for merged
     code` / `> **Not:** Release, production, security, compliance, or SLA
     approval`) with dated-record framing that states the document is a dated
     verification/readiness record whose evidence boundary is main commit
     `8f2813bf745b90221da33a7cfaf40726c5b1b480` reviewed 2026-08-24, and that
     it is NOT a current-state claim about later main commits and not a
     release, production, security, compliance, or SLA approval.
   - Keep the `Current review date: 2026-08-24` line.
   - Add exactly one machine marker line, outside any code fence, directly
     under the blockquote:
     `<!-- readiness-record-as-of: 8f2813bf745b90221da33a7cfaf40726c5b1b480 -->`
   - Add one short `## Current status` section immediately after the header
     block, stating: current merged-code feature status is governed by
     `docs/rc2-feature-scope.md`; dated verification records live in
     `docs/verification/`; current main verification state is the GitHub CI
     state of the current main commit; and this record remains an accurate
     description only of its named commit.
   - Every line from `## Current merged-main summary` to end of file must
     remain byte-identical. The 2026-08-24 and 2026-05-01 historical bodies
     are immutable.
2. `README.md`: change the line-157 pointer phrase `current readiness` to
   `readiness record (dated; evidence as-of the named commit)`. No other
   change; the line-32 `readiness evidence` phrase already reads as dated
   evidence and stays.
3. `docs/README.md`: line 15 `current readiness` → `dated readiness record`;
   line 43 `Current verification and release-readiness evidence` → `Dated
   verification and release-readiness records`; line 48 `Current beta
   readiness` → `Beta readiness record (dated 2026-08-24)`. Links unchanged.
4. `docs/rc-beta.md`: line 4 `**Current readiness:** See
   [beta-readiness.md](beta-readiness.md)` → `**Readiness record:** See
   [beta-readiness.md](beta-readiness.md) (dated; evidence as-of the named
   commit)`; retitle `## Current verification evidence` to `## Dated
   verification evidence (latest on record)` and insert one sentence after
   the heading stating the section names the latest recorded production-path
   qualification and does not assert that current main has been re-qualified
   after that date. Remainder of the file byte-identical.
5. `docs/support-policy.md`: line 4 `see [current readiness](beta-readiness.md)`
   → `see the dated readiness record (beta-readiness.md)`. Remainder
   byte-identical.
6. `docs/verification/README.md`: add one index row for
   `[2026-08-24 RC-beta readiness record](../beta-readiness.md)` framed as a
   dated record for main `8f2813bf745b90221da33a7cfaf40726c5b1b480`
   (reviewed 2026-08-24), historical/dated, not a current-state claim. Do not
   reorder or rewrite existing rows.

## Required checker and test changes

7. `scripts/check_documentation.py`:
   - Refactor so the structure/orphan/as-of checks are callable against an
     explicit root (`check(root: Path | None = None)` defaulting to the real
     repository root), while the README brand-fragment check still applies to
     the real root. Behavior on the real root must remain identical for all
     pre-existing rules.
   - Add the as-of marker contract:
     * `AS_OF_MARKER_RE` matching exactly
       `<!-- readiness-record-as-of: <40 lowercase hex> -->` (whitespace
       tolerant around the colon).
     * Rule R1: for every non-archive Markdown file in the checked set whose
       body (outside code fences) contains the case-insensitive phrase
       `current verification/readiness`, the file must contain exactly one
       valid marker and the marker's 40-hex SHA must occur at least once
       elsewhere in the file text (binding the machine marker to the stated
       prose baseline).
     * Rule R2: `docs/beta-readiness.md` must contain exactly one valid
       marker whose 40-hex SHA occurs at least once elsewhere in the file
       text, regardless of phrasing.
     * Zero valid markers, two or more markers, a non-40-hex payload, or a
       marker SHA absent from the prose each produce a distinct,
       file-and-rule-labelled error in the existing error style, and
       `DOCUMENTATION_CHECK=FAIL` with non-zero exit.
   - No other rule changes: links, anchors, H1/heading-step, archive
     exemptions, orphan navigation, and brand fragments remain as they are.
   - Do not add GitHub network calls, ancestry/history checks, or
     workflow-file changes. An as-of ancestry check against HEAD is
     deliberately deferred (CI checkouts are shallow) and is not part of
     this order.
8. `tests/unit/test_documentation_asof.py` (new):
   - Synthetic-tree tests (build minimal Markdown trees under `tmp_path` and
     run the refactored root-parameterized checks): claim phrase without
     marker fails; claim phrase with one valid marker whose SHA appears in
     prose passes; two markers fails; marker payload not 40-hex fails;
     marker SHA absent from prose fails; a `docs/verification/2026-...`
     archive file with the claim phrase and no marker passes (archive
     exemption); a `docs/beta-readiness.md` without a marker fails under
     R2; a file with no claim phrase and no marker passes.
   - Real-repository tests: the checked file set passes all structural and
     as-of rules at the PR head; `docs/beta-readiness.md` contains exactly
     one marker for `8f2813bf745b90221da33a7cfaf40726c5b1b480` and that SHA
     appears in its prose; the phrase
     `Current verification/readiness summary for merged code` occurs nowhere
     in the checked file set.

## Source-grounded contract decisions

- Authority model: dated records plus a machine-readable as-of boundary,
  with current status delegated to the already-canonical
  `docs/rc2-feature-scope.md`, the `docs/verification/` archive, and GitHub
  CI. A document called "current" must name the commit it describes; CI
  mechanically enforces the naming and validity, and staleness is then
  visible and auditable by comparing the marker commit with current main.
- `docs/beta-readiness.md` is re-framed in place, not moved under
  `docs/verification/`: the path is load-bearing (README, `docs/README.md`,
  `docs/rc-beta.md`, `docs/support-policy.md` link it), and moving it is a
  larger, non-essential change.
- The checker does not enforce recency (e.g., as-of within N commits): that
  would couple every unrelated PR to a documentation refresh and violate the
  project's CI/test economy. The invariant enforces honesty of the claim
  surface, not freshness.
- `docs/verification/README.md` remains the dated archive index; the new row
  cross-references the top-level dated record without moving it.

## Non-goals

- No application code, migration, dependency, or workflow-file changes.
- No re-run of any verification matrix, HPC harness, appliance
  qualification, browser, PostgreSQL, E2E, or provider evidence; no new
  qualification claims about current main.
- No edits to the historical evidence bodies in `docs/beta-readiness.md`, to
  `docs/rc2-feature-scope.md`, `docs/product-scope.md`, compatibility,
  accounting, or security documents.
- No Dependabot PR interaction (#250, #224 untouched), no PR management
  actions, no GitHub settings/branch-protection changes (human/admin domain),
  no release/tag/deploy, no Local service or protected qualification.

## Verification and evidence

Run and report exactly:

- `python scripts/check_documentation.py` (must print
  `DOCUMENTATION_CHECK=OK files=<n>`).
- `python -m pytest tests/unit/test_documentation_asof.py -v`
- `python -m pytest tests/unit/test_documentation_inventory.py
  tests/unit/test_documentation_contract_drift.py -q`
- `python -m pytest tests/unit -q` (full unit; report passed/failed/skipped
  exactly; environment-only skips are recorded honestly, not counted as
  passes of product behavior)
- `python -m ruff check scripts/check_documentation.py
  tests/unit/test_documentation_asof.py`
- `git diff --check`
- Negative probes (already covered by the new unit tests, report their
  pass/fail identities explicitly): the checker must FAIL on a claim without
  a marker, on two markers, on a malformed marker, on a marker SHA absent
  from prose, and on a `docs/beta-readiness.md` without a marker.
- No PostgreSQL/Redis/E2E/browser/provider evidence is required: the change
  set is documentation plus a pure-Python static checker and its unit tests,
  with no state, accounting, network, or streaming boundary touched. State
  that reasoning in the report.

## Security, privacy, accounting, and boundaries

- No secrets, keys, prompts, completions, or provider data in any changed
  file; no new external calls; no configuration surface change.
- PostgreSQL remains quota/accounting truth; no accounting code or schema
  touched. Local/hosted tool boundaries untouched. No trust, identity,
  secret, or content boundary widened.
- Documentation must not claim certification, compliance, production
  readiness, or current-main re-qualification anywhere; the new text states
  limitations honestly.

## Documentation and immutable report

- Documentation-impact statement required in the report per `AGENTS.md`
  section 5.1: list each changed document and the exact authority-model
  effect; state that the 2026-08-24 and 2026-05-01 historical bodies of
  `docs/beta-readiness.md` are byte-preserved (include the diff hunk
  boundary proof) and that no verification numbers were rewritten.
- One immutable report `oap/reports/165-a-<slug>.md` for this objective,
  with literal implementation head SHA and `Report publication commit:
  SELF`; the final report-only commit changes only that report file and has
  the recorded implementation head as first parent, pushed and verified as
  the remote PR head before signalling `OK` to the response FIFO.
