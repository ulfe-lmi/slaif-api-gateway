# OAP Work Order — 177-a

PR mode: `CREATE_NEW_PR`

## Objective

Publish the final release-candidate identity record: a dated,
verification-only record that binds the Objective-173 full integrated
qualification (executed on candidate
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1`) to the exact current
`main` that will receive the RC tag
(`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`), by mechanically proving
zero runtime/deployment/dependency delta, classifying every
intervening change, and re-proving current-main CI, scope closure, and
SBOM correspondence. This is identity derivation — explicitly NOT a
second full clean-room qualification. No capability, code,
dependency, or build-input change of any kind.

## Strategic rationale (machine-verified 2026-09-20)

The maintainer's release direction (2026-09-20) requires: "After
release hygiene is clean, prefer an RC tag on the exact then-current
`main`, supported by an exact qualification/identity record"; "Do not
repeat the expensive integrated qualification merely for ceremony if
runtime/deployment identity plus existing qualification evidence makes
that unnecessary"; and a final record that "binds the existing
Objective-173 qualification to the exact then-current release commit"
with an explicit derivation and a verdict consistent with repository
doctrine. The strategic model machine-verified on 2026-09-20 that the
precondition holds: between the qualified candidate `2b61312e` and
current `main` `db0bd3a`, the diff is exactly the Objectives 173/174/
175/176 publication and hygiene set (workflow action lines, dated
records, RC2 scope reclassification, supply-chain doc, two stdlib
SBOM tooling scripts, regenerated SBOM, OAP records); the
runtime/deployment/dependency surface is byte-identical (re-verified
this phase); `pyproject.toml`, `Dockerfile`, Compose files, `nginx/`,
`Makefile`, `alembic.ini` unchanged; the Dockerfile COPY list does not
include `scripts/` or `sbom/`. Every intervening merge
(174 `845695f`, 175 `37df166`, 176 `db0bd3a`) was CI-verified at
merge time and re-verified today.

## Reconciled authority and current state

Verified by the strategic model on 2026-09-20 from live GitHub and the
shared worktree:

- Canonical repository: `ulfe-lmi/slaif-api-gateway`.
- Remote `main` (the release candidate):
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (merge of PR #313 /
  Objective 176); the `CI` run on that commit has all six jobs
  `success`, `CodeQL` and the dynamic `Code Quality: Push on main`
  run `success` (verified 2026-09-20 ~10:50 UTC).
- Qualified anchor: `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`
  (`RESULT=QUALIFIED-RC-POSTURE`, dated record
  `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`,
  immutable).
- Open PRs: none. `oap/active`: `176-a` (terminal); this order
  activates `177-a` and creates a new PR.
- RC2 scope closed by 175: summary 27 / 0 / 21 / 3 / 0 with zero
  `NEEDS_MAINTAINER_DECISION` rows.

## PR contract

- New PR (branch `oap/177-release-identity-db0bd3ae`) from
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`; no existing PR is
  amended.
- Round commits on the branch:
  1. activation commit: the unchanged strategic-authored 177-a order +
     `oap/active` set to `177-a`;
  2. implementation commit: the dated record + README index row;
  3. report-only commit:
     `oap/reports/177-a-release-identity-db0bd3ae.md`.

## Required work (exact)

All work is mechanical verification plus publication of the evidence
record. No local test suites, clean room, disposable database, or
harness run is required or authorized.

1. **P0 — Ancestry and complete diff classification.**
   - Prove `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` is an ancestor
     of the candidate
     `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (`git merge-base
     --is-ancestor` + the merge-base SHA recorded).
   - `git diff --name-status 2b61312e...<candidate>`: record the full
     path list and classify EVERY path into exactly one of:
     (a) CI-only infrastructure (`.github/workflows/*` action-version
     lines and the `ci.yml` SBOM step; `scripts/generate_sbom.py`,
     `scripts/check_sbom.py`); (b) release metadata/SBOM only
     (`sbom/cyclonedx.json`, `docs/supply-chain.md`); (c)
     documentation/OAP evidence only (`docs/verification/*`,
     `docs/rc2-feature-scope.md`, `oap/*`).
   - Prove the runtime/deployment/dependency surface is
     byte-identical: `git diff --name-only 2b612e-range-corrected
     2b61312e0eb569aa7c6f953f52e35b44e84b91c1..<candidate> -- app
     tests migrations nginx Dockerfile docker-compose.yml
     docker-compose.production.yml Makefile pyproject.toml
     alembic.ini` is EMPTY (record the command and the empty output).
   - Record the `scripts/` and `sbom/` deltas exactly (the two new
     tooling scripts; the regenerated SBOM) and classify them per
     (a)/(b), with the Dockerfile `COPY` lines quoted verbatim as
     evidence that neither `scripts/` nor `sbom/` is shipped in the
     production image.
2. **P1 — SBOM correspondence.** `python scripts/check_sbom.py` on the
   candidate tree prints exactly `SBOM_CHECK=OK components=60`
   (record the line); quote the SBOM `metadata.timestamp`,
   `metadata.component`, and `metadata.tools.components`; state the
   component count and that the set is the frozen production
   resolution; quote the `docs/supply-chain.md` limitation lines
   (production-only scope; live-resolution at build time).
3. **P2 — Fresh current-main CI.** `gh api
   repos/ulfe-lmi/slaif-api-gateway/commits/<candidate>/check-runs`:
   all nine stable checks by exact name — `Unit, lint, and migration
   head`; `Documentation hygiene`; `OpenAI-compatible E2E tests`;
   `Playwright browser smoke`; `Docker Compose smoke`; `PostgreSQL
   integration tests`; `Analyze (javascript-typescript)`; `Analyze
   (python)`; `Analyze Python` — `completed`/`success` with run IDs
   recorded, plus the `CodeQL` suite rollup `completed`/`success`.
4. **P3 — Release-state predicates.** Open-PR count for the
   repository is zero (record the `gh pr list --state open` output);
   the RC2 scope document's Classification Summary block is quoted
   verbatim and reads exactly 27 / 0 / 21 / 3 / 0; a
   `grep -n "NEEDS_MAINTAINER_DECISION" docs/rc2-feature-scope.md`
   output is recorded showing the label-list line and the zero
   summary count only (no row usage).
5. **P4 — Exact known limitations.** The record lists, verbatim, at
   least: (i) the qualification provider was the harness's
   socket-level OpenAI-compatible double (mocked upstream) — no
   real-provider run, no provider credentials used or present; (ii)
   no independent penetration test or formal vulnerability
   assessment exists; (iii) no production certification, SLA,
   compliance, security, or scale claim is made; (iv) the two
   labeled environment-only test non-passes (VM `codex-cli 0.154.0`
   vs fixture `0.148.0` unit case; local-VM `pg_dump` CLI skip with
   in-container backup/restore re-proven in both 173 P2 runs); (v)
   the Docker image live-resolves the unpinned direct production
   dependencies at build time (documented limitation; pinning is
   post-RC); (vi) the SBOM is a point-in-time frozen production
   dependency record — not signed provenance, not a vulnerability
   scan.
6. **P5 — Publish the dated record and index row.**
   - New file
     `docs/verification/2026-09-20-release-identity-db0bd3ae.md`:
     dated (2026-09-20), names the exact candidate
     `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`, carries the verdict
     line `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`, and contains P0
     through P4 with the machine evidence, the classification table,
     and this derivation statement (verbatim or semantically exact):
     "The full integrated qualification was executed on
     `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (Objective 173,
     `RESULT=QUALIFIED-RC-POSTURE`). The exact release candidate
     inherits that runtime/deployment qualification because the
     runtime/deployment/dependency tree is byte-identical, and every
     intervening change is classified and separately verified above.
     This record is an identity derivation, not a second full
     clean-room qualification." It must also state the post-merge
     relationship: after this PR merges, `main` will differ from the
     named candidate only by this dated record, the README index row,
     and the OAP order/report/active files (documentation/OAP
     evidence only), and is therefore likewise runtime-identical; the
     RC tag may name either the exact candidate or that post-merge
     successor.
   - `docs/verification/README.md`: add exactly one index row for the
     new record, matching the existing index style (link, one-line
     summary, verdict, and the not-a-release-decision boundary
     note).
7. **AP-7 — Immutable report** with the SELF topology: report commit
   is the PR head, first parent is this round's implementation head,
   report commit changes only the report file, report contains the
   literal candidate SHA, the literal qualified-anchor SHA, the single
   verdict line, and the merge-not-performed statement; the remote PR
   head is verified as the report commit and the P2 re-query on the
   final head passes before the two-byte `OK` is written to the
   response FIFO.

## Allowed paths

- `docs/verification/2026-09-20-release-identity-db0bd3ae.md` (new)
- `docs/verification/README.md` (exactly one index row)
- `oap/orders/177-a-release-identity-db0bd3ae.md` (unchanged
  strategic work order)
- `oap/active` (`177-a`)
- `oap/reports/177-a-release-identity-db0bd3ae.md` (new immutable
  report)

Nothing else.

## Explicit exclusions (non-goals)

- No application, test, script, workflow, migration, nginx, Docker,
  Compose, Makefile, or dependency change of any kind (the two 176
  scripts are already on `main` and are NOT modified here).
- No clean room, no production-appliance harness run, no local full
  unit/integration/E2E suite, no disposable database, no browser run
  beyond CI.
- No SBOM regeneration or modification (already merged in 176).
- No RC2 scope document modification (already closed in 175).
- No tag, release, publication, or deployment of any kind; no real
  provider calls; no secrets; no GitHub-settings action; no PR
  interaction beyond this PR; no Dependabot action.

## Acceptance criteria

- **AP-1 — Identity proof (decisive).** The P0 ancestry proof
  (merge-base SHA recorded), the complete classified path table
  (every path exactly one class; no path unclassified or
  runtime/deployment/dependency), the EMPTY runtime/deployment/
  dependency-surface diff over the explicit path set, and the
  verbatim Dockerfile COPY evidence are all in the dated record.
- **AP-2 — SBOM correspondence.** The exact `SBOM_CHECK=OK
  components=60` line, the quoted SBOM metadata, the component count,
  and the quoted supply-chain limitation lines are in the record.
- **AP-3 — Fresh CI.** P2 on the exact candidate: nine stable checks
  by exact name + CodeQL rollup `completed`/`success` with run IDs in
  the record; and the re-query on the final PR head (after the report
  commit) passes with run IDs — the nine stable names plus CodeQL
  rollup, all `success`.
- **AP-4 — Release-state predicates.** Open-PR count zero (recorded
  output); RC2 summary block verbatim 27 / 0 / 21 / 3 / 0; the
  `NEEDS_MAINTAINER_DECISION` grep output shows no row usage.
- **AP-5 — Limitations.** All six P4 limitation categories present
  verbatim in the record; the record makes no certification,
  compliance, SLA, security, scale, real-provider, or
  production-readiness claim.
- **AP-6 — Publication.** The dated record exists at the exact path
  with the exact candidate SHA, the exact verdict line
  `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`, the derivation
  statement, and the post-merge relationship statement; the README
  index row is exactly one line added in the existing style;
  `python scripts/check_documentation.py` prints
  `DOCUMENTATION_CHECK=OK` (file count 85 = 84 + the new record).
- **AP-7 — Immutable report and final-head gate.** Per Required work
  7: SELF topology, literal SHAs, single verdict line,
  merge-not-performed, remote PR head verified, final-head P2
  re-query green before the two-byte `OK`.

## Verification and evidence commands

- P0: `git merge-base --is-ancestor
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1 db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7
  && echo ANCESTOR_OK`; `git merge-base
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`; `git diff --name-status
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1 db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`;
  `git diff --name-only 2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 -- app tests migrations
  nginx Dockerfile docker-compose.yml docker-compose.production.yml
  Makefile pyproject.toml alembic.ini` (record the empty output);
  `git show db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7:Dockerfile |
  grep -n COPY`.
- P1: `python scripts/check_sbom.py`; `python -c
  "import json; m=json.load(open('sbom/cyclonedx.json'))['metadata'];
  print(m['timestamp'], m['component'], m['tools'])"`.
- P2: `gh api
  repos/ulfe-lmi/slaif-api-gateway/commits/db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7/check-runs`
  (and the final-head equivalent after the report commit).
- P3: `gh pr list --repo ulfe-lmi/slaif-api-gateway --state open
  --json number` (record the output); `sed -n '/Classification
  Summary/,/## RC2 Scope Matrix/p' docs/rc2-feature-scope.md`; `grep
  -n "NEEDS_MAINTAINER_DECISION" docs/rc2-feature-scope.md`.
- P6: `python scripts/check_documentation.py`.
- AP-7: `git log --format='%H %P %s' -1` on the report commit;
  `git show --stat <report commit>` (only the report file).

## Security, privacy, accounting, and boundaries

Verification and documentation-publication only. No runtime
dependency, no schema, no migration, no configuration surface, no
trust/identity/secret/content boundary is touched. No
production/staging system, no real provider, no real email, no
external call beyond the GitHub API. The record contains SHAs, run
IDs, check names, and quoted document text only (no secrets).

## Stop / escalation conditions

- If the P0 diff contains ANY path not classifiable into the three
  non-runtime classes (i.e., an unexpected runtime, deployment, or
  dependency path): do not publish the record; STOP and report the
  exact path list for strategic reassessment of qualification scope.
- If the RC2 scope document shows any `NEEDS_MAINTAINER_DECISION`
  row or a summary count other than 27 / 0 / 21 / 3 / 0: STOP and
  report (scope is not closed).
- If any stable check or the CodeQL rollup is missing, renamed, or
  failing on the candidate or final head for a cause other than a
  labeled environment-only item: record the failing check name and
  redacted log excerpt, classify, and report; do not force green.
- If `check_documentation.py` reports a count other than 85 or a
  hygiene failure: record the output and report; do not edit other
  documentation files to force a pass (only the two allowed paths
  may change).
- Suffix rounds (`177-b`...) are for bounded correction of this
  objective only; none are anticipated.

## Setup authority

Standard shared-worktree execution per the coding-agent protocol:
create the branch from `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`
(fetch and verify before committing). No clean room, no disposable
database, no extra tooling required or authorized; no network access
beyond the GitHub API.

## Report obligations

Per `OAP-COMMUNICATION-coding-agent.md`: work-order identifier and
file, PR mode (`CREATE_NEW_PR`), status, the single verdict line,
executive summary, authoritative GitHub state (PR number, URL, state,
base SHA = candidate SHA, implementation head SHA, report publication
commit `SELF`, merge-not-performed), full changed-file list, the
complete P0 classified path table, the empty runtime-surface diff
output, the verbatim Dockerfile COPY lines, the P1 outputs (exact
`SBOM_CHECK` line and quoted metadata), the P2 run-ID tables on the
candidate and the final head, the P3 recorded outputs, the P4
limitations list, the verbatim new dated record and the README row
diff, per-AP evidence, local verification output, negative evidence
(no code/test/script/workflow/dependency/SBOM/scope-doc change; no
harness run; no tag/release/deploy; no PR/Dependabot/GitHub-settings
action; no secrets), CI gate state on the final head, and
environment-only labels (none expected).

## Merge prohibition

The coding agent never merges and never enables auto-merge. The PR is
left OPEN for strategic review and the delegated merge authority. The
strategic model merges the unique PR only after the final-head gates
pass.
