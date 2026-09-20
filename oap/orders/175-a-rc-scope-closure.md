# OAP Work Order — 175-a

PR mode: `CREATE_NEW_PR`

## Objective

Close the RC feature-scope debt with a documentation-only change:
reclassify the six rows currently labeled `NEEDS_MAINTAINER_DECISION` in
`docs/rc2-feature-scope.md` per the maintainer's explicit decision of
2026-09-20, so that the release scope contains zero unresolved
maintainer decisions and zero implication that those endpoint families
are supported. No product capability is added, removed, or changed.

## Strategic rationale (machine-verified 2026-09-20)

The repository is in release closure after Objective 174 (merged
2026-09-17T17:46:54Z; remote `main`
`845695f03c41233754f276e99c8bf7014d5c21a0`). The maintainer's release
direction, given 2026-09-20, is:

1. Freeze RC feature scope.
2. The six `NEEDS_MAINTAINER_DECISION` rows are NOT to be implemented
   for this RC.
3. They are explicitly outside/deferred from this RC.
4. No new endpoint families may be introduced to make the release look
   more complete.

Decision quote (authoritative for this order):

> Do not add these capabilities. They are outside the declared RC scope
> and must not be implied as supported.

The strategic model machine-verified on 2026-09-20: the six rows exist
exactly at lines 83-88 of `docs/rc2-feature-scope.md` on
`origin/main`; the classification summary reads
`RC2_REQUIRED_IMPLEMENTED 27 / RC2_REQUIRED_MISSING 0 /
RC2_EXPLICITLY_DEFERRED 17 / RC2_UNSUPPORTED_BY_POLICY 1 /
NEEDS_MAINTAINER_DECISION 6`; the existing label semantics are
`RC2_EXPLICITLY_DEFERRED` = "explicitly not an RC2 target" (used by the
MCP/file-search/code-interpreter/image-generation rows) and
`RC2_UNSUPPORTED_BY_POLICY` = "RC2 requires explicit fail-closed
behavior until X exists" (used by the Chat streaming audio output
row). The four not-implemented families (files, uploads, legacy
completions, other unlisted families) fit `RC2_EXPLICITLY_DEFERRED`
without distorting the label; the two already-fail-closed families
(Responses audio, Responses multimodal output) fit
`RC2_UNSUPPORTED_BY_POLICY`. The doc-contract test
`tests/unit/test_rc2_feature_scope_docs.py` requires all five labels to
remain present in the document and requires the row names to remain
present; it does not assert the six rows' classification or the
deferred/unsupported/decision counts. `tests/unit/
test_documentation_contract_drift.py` asserts only
`RC2_REQUIRED_IMPLEMENTED` rows. No test or code change is therefore
required or authorized.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-20 from live GitHub and the
shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main`: `845695f03c41233754f276e99c8bf7014d5c21a0`
  (merge of PR #311 / Objective 174); all nine stable checks plus the
  CodeQL suite rollup `completed`/`success` on that commit (re-queried
  2026-09-20).
- Qualified RC candidate: `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
  (`RESULT=QUALIFIED-RC-POSTURE`, dated record
  `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`).
  The runtime/deployment/dependency surface of current `main` is
  byte-identical to that candidate (strategic machine verification,
  explicit path set
  `app tests scripts migrations nginx Dockerfile docker-compose.yml
  docker-compose.production.yml Makefile pyproject.toml sbom`; 0 diff
  lines).
- Open PRs: none. `oap/active`: `174-b` (terminal); this order
  activates `175-a` and creates a new PR.

## PR contract

- New PR (branch `oap/175-rc-scope-closure`) from
  `845695f03c41233754f276e99c8bf7014d5c21a0`; no existing PR is
  amended.
- Round commits on the branch:
  1. activation commit: the unchanged strategic-authored 175-a order +
     `oap/active` set to `175-a`;
  2. implementation commit: the `docs/rc2-feature-scope.md` change (and
     any cross-doc correction found by AP-3, if any);
  3. report-only commit: `oap/reports/175-a-rc-scope-closure.md`.

## Required change (exact)

Only `docs/rc2-feature-scope.md` changes, as follows. No other line of
the document changes unless required by AP-1 consistency.

1. Row `/v1/files` list/create/retrieve/delete/content: classification
   cell becomes `` `RC2_EXPLICITLY_DEFERRED` ``; the decision/note cell
   becomes: Maintainer decision 2026-09-20: outside this RC scope; not
   implemented; must not be implied as supported (error-shape only).
2. Row `/v1/uploads` and upload parts: same treatment as 1.
3. Row Legacy `POST /v1/completions`: same treatment as 1.
4. Row Other public OpenAI-compatible endpoint families not listed
   above: same treatment as 1.
5. Row Responses audio: classification cell becomes
   `` `RC2_UNSUPPORTED_BY_POLICY` ``; note cell becomes: Maintainer
   decision 2026-09-20: remains fail-closed for this RC; no
   implementation planned.
6. Row Responses multimodal output: same treatment as 5.
7. Classification Summary table becomes exactly:
   `RC2_REQUIRED_IMPLEMENTED | 27`, `RC2_REQUIRED_MISSING | 0`,
   `RC2_EXPLICITLY_DEFERRED | 21`, `RC2_UNSUPPORTED_BY_POLICY | 3`,
   `NEEDS_MAINTAINER_DECISION | 0`.
8. The Classification Labels list keeps all five labels
   (mechanically required by the doc-contract test; the label remains
   valid for future rows).
9. Add one new short section `## Maintainer scope decisions`
   immediately after the Classification Summary section, containing one
   dated entry (2026-09-20) recording: the maintainer decided the six
   previously undecided endpoint families (files, uploads, legacy
   Completions, Responses audio, Responses multimodal output, other
   unlisted public OpenAI-compatible endpoint families) are outside the
   declared scope of this release candidate and must not be implied as
   supported; they are reclassified as `RC2_EXPLICITLY_DEFERRED`
   (not-implemented families) and `RC2_UNSUPPORTED_BY_POLICY`
   (already fail-closed families); no capability is added or removed;
   runtime fail-closed/error-shape behavior is unchanged; this closes
   all open maintainer scope decisions for this release without
   changing the RC2 scope lock.
10. AP-3 cross-document check (see acceptance): verify the current
    behavior documents do not imply support for any of the six
    families; correct only genuine misstatements, minimally.

## Allowed paths

- `docs/rc2-feature-scope.md` (the primary change above)
- `README.md`, `docs/compatibility-matrix.md`,
  `docs/openai-compatibility.md`, `docs/beta-readiness.md`,
  `docs/rc-beta.md`, `docs/release-decision-brief.md` (ONLY if AP-3
  finds a genuine misstatement implying support for one of the six
  families; each such correction must be line-level and recorded in the
  report; expected: none)
- `oap/orders/175-a-rc-scope-closure.md` (unchanged strategic work
  order)
- `oap/active` (`175-a`)
- `oap/reports/175-a-rc-scope-closure.md` (new immutable report)

Nothing else.

## Explicit exclusions (non-goals)

- No application, test, script, migration, nginx, Docker, Compose,
  Makefile, or dependency (`pyproject.toml`) change of any kind.
- No new endpoint, route, capability, or configuration surface; no
  behavior change; fail-closed/error-shape runtime behavior stays
  exactly as implemented.
- No change to `docs/verification/2026-*` files (historical evidence is
  immutable); no new dated record in this objective.
- No SBOM change (`sbom/` byte-identical; that is Objective 176).
- No workflow change (`.github/` byte-identical).
- No PR interaction beyond this PR; no Dependabot action; no
  GitHub-settings action (branch protection, rulesets, required
  checks, environments); no release, tag, or deployment; no real
  provider calls; no secrets.
- No clean room, disposable database, or local full-suite run beyond
  the focused doc-contract commands in Verification.

## Acceptance criteria

- **AP-1 — Exact reclassification.** The six rows carry the
  classifications and dated decision notes specified in Required
  change 1-6; the summary table carries exactly 27 / 0 / 21 / 3 / 0;
  the `## Maintainer scope decisions` section exists with the dated
  entry; all five labels remain present in the document; the
  `| `RC2_REQUIRED_MISSING` | 0 |` line is intact; the 43 row names
  asserted by `tests/unit/test_rc2_feature_scope_docs.py` remain
  present verbatim.
- **AP-2 — Doc contract green (local, focused).**
  `.venv/bin/python -m pytest tests/unit/
  test_rc2_feature_scope_docs.py tests/unit/
  test_documentation_contract_drift.py -q` passes on the final tree,
  and `.venv/bin/python scripts/check_documentation.py` prints
  `DOCUMENTATION_CHECK=OK` with the file count unchanged from
  `845695f` (no documentation files added or removed).
- **AP-3 — No-support implication audit (negative evidence).** The
  report contains, for each of the six families, the exact current
  wording (quote with line reference) of every current-facing document
  that mentions it (`README.md`, `docs/compatibility-matrix.md`,
  `docs/openai-compatibility.md`, `docs/beta-readiness.md`,
  `docs/rc-beta.md`, `docs/release-decision-brief.md`, and the
  reclassified row itself), demonstrating no document implies the
  family is supported; any minimal correction made under Allowed paths
  is diffed verbatim (expected: none needed).
- **AP-4 — Diff scope.** `git diff --name-only <base>..<implementation
  head>` touches only `docs/rc2-feature-scope.md` (plus any
  AP-3-corrected file, if any) and the OAP order/active files; the
  report commit changes only the report file; `git diff --check` clean;
  `sbom/`, `.github/`, `pyproject.toml`, `app/`, `tests/`, `scripts/`
  all byte-identical to the base.
- **AP-5 — Check-set invariance (decisive).** On the exact final PR
  head, the nine stable checks by exact name — `Unit, lint, and
  migration head`; `Documentation hygiene`; `OpenAI-compatible E2E
  tests`; `Playwright browser smoke`; `Docker Compose smoke`;
  `PostgreSQL integration tests`; `Analyze (javascript-typescript)`;
  `Analyze (python)`; `Analyze Python` — are each `completed`/`success`
  with run IDs recorded, and the `CodeQL` suite rollup is
  `completed`/`success`. The `Unit, lint, and migration head` job runs
  the doc-contract tests within the full unit suite, so its green
  conclusion is the in-CI proof of AP-2.
- **AP-6 — Immutable report.** One report
  `oap/reports/175-a-rc-scope-closure.md` with the SELF topology:
  report commit is the PR head, first parent is this round's
  implementation head, report commit changes only the report file,
  report contains the literal base SHA, the single verdict line, and
  the merge-not-performed statement; the remote PR head is verified as
  the report commit and the AP-5 re-query on the final head passes
  before the two-byte `OK` is written to the response FIFO.

## Verification and evidence commands

- AP-1: `git diff <base>..<implementation head> --
  docs/rc2-feature-scope.md` (full verbatim diff in the report);
  `grep -n "NEEDS_MAINTAINER_DECISION" docs/rc2-feature-scope.md`
  (must show only the label-list line, no summary count > 0, no row
  usage); `grep -c "RC2_EXPLICITLY_DEFERRED" docs/
  rc2-feature-scope.md` and the summary block quoted verbatim.
- AP-2: the focused pytest command and `scripts/
  check_documentation.py` above.
- AP-3: `git grep -in -E "/v1/files|/v1/uploads|/v1/completions|
  responses audio|multimodal" README.md docs/compatibility-matrix.md
  docs/openai-compatibility.md docs/beta-readiness.md docs/rc-beta.md
  docs/release-decision-brief.md` with each hit classified supported /
  not-supported / context, quoted in the report.
- AP-4: `git diff --name-only <base>..<implementation head>`,
  `git diff --check`, and per-excluded-path
  `git diff <base>..<implementation head> -- sbom .github
  pyproject.toml app tests scripts` (all empty).
- AP-5: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/<PR-head>/check-runs` (every
  run ID + conclusion recorded; re-queried on the final head after the
  report commit).

## Security, privacy, accounting, and boundaries

Documentation-only change. No runtime dependency, no schema, no
migration, no configuration surface, no trust/identity/secret/content
boundary is touched. No production/staging system, no real provider,
no real email, no external call of any kind beyond the GitHub API.

## Stop / escalation conditions

- If AP-3 finds a misstatement whose correction would require more
  than line-level wording fixes or would alter the meaning of any
  implemented-surface description: do not push it; STOP and report the
  finding for strategic decision.
- If any focused doc-contract command fails for a cause other than the
  intended reclassification: do not modify any test or script to force
  green (tests and scripts are outside Allowed paths); STOP and report
  the exact failure.
- If the implementation diff would touch any path outside Allowed
  paths: do not push it; STOP and report the discrepancy.
- Suffix rounds (`175-b`...) are for bounded correction of this
  objective only; none are anticipated.

## Setup authority

Standard shared-worktree execution per the coding-agent protocol:
create the branch from `845695f03c41233754f276e99c8bf7014d5c21a0`
(fetch and verify before committing). No clean room, no disposable
database, no extra tooling required or authorized.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and
file, PR mode (`CREATE_NEW_PR`), status, the single verdict line,
executive summary, authoritative GitHub state (PR number, URL, state,
base SHA, implementation head SHA, report publication commit `SELF`,
merge-not-performed), full changed-file list, the verbatim
`docs/rc2-feature-scope.md` diff, the complete AP-3 audit table (six
families x documents, exact quotes and line references), per-AP
evidence, local verification output, negative evidence (no code/test/
script/workflow/dependency/SBOM change; no capability added; no
PR/Dependabot/GitHub-settings action; no secrets; no release/deploy),
CI gate state on the final head with run IDs, and environment-only
labels (none expected).

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is
left OPEN for strategic review and the delegated merge authority. The
strategic model merges the unique PR only after the final-head gates
pass.
