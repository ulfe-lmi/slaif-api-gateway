# OAP Work Order — 179-a

PR mode: `CREATE_NEW_PR`

## Objective and reason

Publish a small verification-only identity record for the exact post-
documentation release candidate. The maintainer explicitly anticipated this
after successful Objective 178: bind the final public documentation commit to
the existing expensive qualification by executable/deployment/dependency byte
identity, confirm scope/SBOM/CI, then stop for human tag/release authority.
Do not repeat integrated qualification or reopen product scope.

## Verified state and PR contract

Strategic reconciliation 2026-09-20 (recheck at execution):
- Canonical repository `ulfe-lmi/slaif-api-gateway`.
- Candidate/current main:
  `71092fefee74649bad71dbb5b7a7106115e9f545`.
- Objective 178 terminal: PR #315 merged at 2026-09-20T19:28:39Z after
  rounds 178-a through 178-e. Final report head
  `5b9fc59a6f1040ced62624ccfcf2e1e5effc9b19` had all ten checks SUCCESS.
  Final implementation head `b26ed802f97ea51f06b202255941afa9d4ee0afb`
  had the literal provider-free quickstart executed from a fresh clone.
- Merge tree and accepted PR tree both
  `a226e9df6add137e3708338f352ec66e8889a239` (GitHub verified).
- No open PRs after merge. Current active `178-e` is terminal, with unique
  immutable order/report. Shared checkout remains the accepted report head;
  strategy has not switched/reset coding Git state. Preserve ignored state.
- Original integrated qualified anchor:
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`, dated record
  `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md`.
- Previous identity anchor/candidate:
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`, dated record
  `docs/verification/2026-09-20-release-identity-db0bd3ae.md`.
- Independent GitHub root-tree/subtree comparison already found all 15
  runtime/deployment/dependency inputs listed below identical across all
  three anchors. SBOM and .github identical since the previous identity
  candidate. Reproduce with repository Git and record exact outputs.
- RC2 required scope remains closed: 27 implemented, 0 missing, 21 deferred,
  3 unsupported, 0 maintainer decisions. SBOM check OK components=60.
- No classic required-check/review protection; active ruleset protects
  deletion/non-fast-forward. Strategic final-head CI/review gates still apply.
- Only published release remains v0.1.0-rc.1; no tag/release authorization.

Before activation strategy will verify the nine post-merge main checks are
green and record that in its timing ledger. Independently re-query them for
the candidate record. Do not substitute pre-merge PR checks for main checks.

Create one new PR from exact candidate main above:
- Branch `oap/179-post-documentation-release-identity`.
- Base `main`.
- Suggested title `verify: bind the documentation-complete release candidate`.
Commit this order and active pointer unchanged. One objective, one PR; any
continuation amends it. Coding agent never merges/auto-merges.

## Exact allowed paths

- `docs/verification/2026-09-20-post-documentation-release-identity-71092fef.md`
  (new dated record)
- `docs/verification/README.md` (one newest/current-evidence entry linking it;
  retain all old evidence links/outcomes)
- `docs/rc-beta.md` (only current latest-record paragraph/link: direct readers
  to the new identity record/current index so the old 177 record is not
  incorrectly called latest; retain the September 17 full qualification
  link, all historical body/outcomes and qualification limitations)
- `oap/orders/179-a-post-documentation-release-identity.md` (unchanged)
- `oap/active` (unchanged strategic bytes `179-a`)
- `oap/reports/179-a-post-documentation-release-identity.md` (new immutable)

Nothing else: no README/QUICKSTART/INSTALL edits, no checker/test/scripts/
runtime/deployment/dependency/workflow/SBOM changes, no prior report/record edits.

## Required verification and record

### P0 — Exact chain and complete classified delta

Prove both prior anchors are ancestors of candidate 71092fef using
`git merge-base --is-ancestor` and record merge bases. Record exact candidate
SHA, parents and tree; compare merge tree to accepted 178 final PR tree.

Record `git diff --name-status` for previous identity candidate db0bd3ae to
71092fef and classify EVERY path (39 expected from live GitHub compare, but
derive, do not assume): public/reference/navigation docs; documentation
checker and three documentation-specific tests; new identity/OAP evidence.
README gets its explicit descriptive-packaging classification below. No
unclassified path. Also inspect the complete original qualified-anchor delta:
earlier .github action/SBOM CI tooling and release metadata are already recorded
in 177; reference that immutable classification and verify nothing new escaped.

Decisive empty diff, from BOTH anchors to candidate:

```text
git diff --name-only <anchor> 71092fefee74649bad71dbb5b7a7106115e9f545 -- app migrations Dockerfile docker-compose.yml docker-compose.production.yml deploy nginx pyproject.toml requirements.txt requirements-dev.txt Makefile alembic.ini .env.example .dockerignore VERSION
```

Record explicit empty output. Hash/subtree proof is welcome alongside it.
Verify LICENSE unchanged. Inspect all scripts/tests/.github/sbom separately:
since db0bd3ae only scripts/check_documentation.py and the three documentation
unit tests changed; .github and sbom are byte-identical. Never exclude a broad
tests/scripts tree silently and then claim it is wholly byte-identical.

README.md is copied by Dockerfile and used as the package description in
pyproject.toml; its descriptive bytes changed. Quote the relevant COPY and
readme inputs and state plainly: executable runtime, deployment configuration
and dependency INPUTS are byte-identical; README/project-description metadata
is intentionally different. This is not whole-image equality, reproducible
image identity or frozen dependency resolution at future build time.

### P1 — Documentation productization acceptance

Verify PR #315 merged, exact merge and final report/implementation identities,
and the new root entry points. Reference the immutable 178-e report for the
literal final-implementation quickstart (provider-free build/migrate/start/
health/readiness/admin/login/cleanup); reference 178-b mocked model/pricing
evidence and 178-d command-mechanics fixture as inherited evidence on unchanged
inputs. Cite, do not re-run or reproduce pages of logs. Prior reports have
corrections in later reports; use the latest corrected facts. No live provider
inference or live production upgrade was performed in 178.

### P2 — Scope and scoped SBOM correspondence

Re-read RC2 classification summary from candidate: exact 27/0/21/3/0 and no
remaining NEEDS_MAINTAINER_DECISION matrix row. Confirm scope doc is unchanged
since previous identity anchor. Do not alter scope or reinterpret deferred
features as implemented.

Run `python scripts/check_sbom.py` -> `SBOM_CHECK=OK components=60`.
Record unchanged artifact blob/hash and metadata timestamp/component/tools.
State it remains valid for its documented point-in-time frozen PRODUCTION
DEPENDENCY scope because dependency inputs and the artifact are unchanged.
It is not an attestation of current/future image resolution, signed provenance,
vulnerability scan, invoice accuracy or complete environment inventory. Do not
regenerate, install dependencies or call external providers for this proof.

### P3 — Fresh candidate/main CI, then final PR gate

On exact 71092fef, record query time/check-run IDs and success for all nine
stable names: Unit, lint, and migration head; Documentation hygiene;
OpenAI-compatible E2E tests; Playwright browser smoke; Docker Compose smoke;
PostgreSQL integration tests; Analyze (javascript-typescript); Analyze (python);
Analyze Python. Verify CodeQL suite success (main may express its rollup as a
suite rather than the extra PR check-run). Record zero open PRs BEFORE this
objective's own PR and no tag/release change. Re-query final implementation
and report PR head, including CodeQL rollup. Pending/missing/skipped/failed is
not success. Report actual state; strategy independently gates merge.

### P4 — Verdict, limitations, final candidate and successor relationship

If and only if P0–P3 hold, use:
`RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`.

Name `71092fefee74649bad71dbb5b7a7106115e9f545` as the exact
documentation-complete taggable candidate. Explain that original integrated
qualification was executed on 2b61312e, 177 previously bound db0bd3ae, and
this record derives the later candidate's qualification by byte identity plus
reviewed/classified non-runtime changes and green CI. It is not another
integrated or production qualification run and not human release approval.

Retain exact relevant limitations: mocked-upstream integrated qualification;
no independent penetration-test/formal vulnerability assessment or security/
compliance/production/SLA/scale certification; the two labeled environment-only
exceptions in the integrated record (Codex CLI version mismatch and host
pg_dump skip with in-container backup/restore evidence); unpinned live image
dependency resolution; scoped point-in-time SBOM; descriptive README/package
metadata difference. Do not reopen old HPC history as a fresh gate.

Post-publication identity: this objective itself adds only this record, tiny
current evidence navigation and OAP files. It does not change the candidate's
executable/deployment/dependency tree or README. A future merge successor may
inherit the same qualification only after strategy verifies that exact delta
and fresh final checks; do not fabricate its not-yet-known merge SHA. The
report SELF convention does not magically name a future merge. Strategy will
report the literal merged successor and stop for human tag/release decision.

## Acceptance and economical checks

- AP-1: Exact ancestry and complete classified deltas; empty decisive runtime
  comparisons; README descriptive exception explicit; no hidden changed path.
- AP-2: Documentation pass proven merged and correct inherited clean-room/
  mocked evidence referenced; new public docs present without front-door edits.
- AP-3: Scope closed, SBOM unchanged/check green, limits truthful.
- AP-4: Exact candidate nine stable main checks/CodeQL suite green; final PR
  checks independently gate merge (no prediction of completion).
- AP-5: New dated identity record + navigation pointers only, exact candidate
  named, no tag/release claim, historical records immutable.
- AP-6: docs checker links/anchors/reachability and cumulative diff --check
  green; immutable report-only SELF topology and bounded allowed-path proof.

No new clean-room, Docker, DB, browser, model call, provider call, local full
suite or integrated harness. Only focused read-only Git/GitHub inspection,
stdlib docs/SBOM checks and ordinary CI. Existing local tooling suffices.
If an unexpected runtime delta, open objective, changed main, scope decision,
SBOM failure or unresolved actual CI failure appears, stop and report rather
than widen scope or manufacture a positive verdict. Correct only in-scope
evidence/link errors. Preserve all unrelated worktrees/local state and secrets.

## Report and signal

State exact start/candidate/qualified-anchor/prior-identity/implementation SHAs,
single PR/base/branch, changed paths, every AP outcome with safe commands and
outputs, classification and empty diffs, README exception, scope/SBOM proof,
current CI IDs/states and limitations. Record no merge/tag/release/provider/
production action. No vague all-qualified assertions beyond the exact evidence.

Publish all claimed implementation GitHub state first, then atomically publish
one immutable report with literal implementation SHA and `Report publication
commit: SELF`; final commit changes only that report, its first parent equals
implementation head, and pushed PR head is SELF at signal time. Inspect
report-head CI without rewriting the report. Send exact two-byte OK to response
FIFO. Coding agent leaves the PR open; strategy reviews/merges and stops for
human release authority. Do not activate another objective.
