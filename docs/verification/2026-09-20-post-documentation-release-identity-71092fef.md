# Objective 179 post-documentation release-identity record (candidate 71092fef)

Date: 2026-09-20 (Europe/Ljubljana; UTC timestamps as recorded by the
queries)

Candidate (evidence boundary): `main`
`71092fefee74649bad71dbb5b7a7106115e9f545` (merge of PR #315 / Objective
178, "Merge pull request #315 from
ulfe-lmi/oap/178-documentation-productization"), verified as remote `main`
at execution time (`git ls-remote origin refs/heads/main`).

Qualified anchor: `main`
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge; Objective
173), `RESULT=QUALIFIED-RC-POSTURE`, dated record
[`2026-09-17-current-main-integrated-requalification-2b61312e.md`](2026-09-17-current-main-integrated-requalification-2b61312e.md)
(immutable; referenced, not rewritten).

Prior identity anchor/candidate: `main`
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge; Objective
176), `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`, dated record
[`2026-09-20-release-identity-db0bd3ae.md`](2026-09-20-release-identity-db0bd3ae.md)
(immutable; referenced, not rewritten).

This is a dated, verification-only record that binds the exact
documentation-complete post-Objective-178 candidate to the existing
integrated qualification by executable/deployment/dependency byte identity,
classifies every intervening change since the prior identity anchor, and
re-proves current-main CI, RC2 scope closure, and scoped SBOM
correspondence. This is identity derivation — explicitly NOT a second
integrated or production qualification run, NOT a release decision, and NOT
tag/release authorization. All evidence below was re-queried live on
2026-09-20.

## Verdict

`RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`

The full integrated qualification was executed on
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (Objective 173,
`RESULT=QUALIFIED-RC-POSTURE`). Objective 177 previously bound
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` by the same mechanism. This
record derives the later candidate
`71092fefee74649bad71dbb5b7a7106115e9f545` because the executable,
deployment, and dependency inputs are byte-identical from both anchors,
every intervening change is classified and separately verified above, and
the candidate's fresh main CI is green. This record is an identity
derivation, not a second integrated qualification and not human release
approval.

## P0 — Exact chain and complete classified delta

Ancestry proofs (shared worktree; candidate is a strict forward
descendant of both anchors — each anchor is the exact merge base):

- `git merge-base --is-ancestor
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  71092fefee74649bad71dbb5b7a7106115e9f545` → exit 0 (`ANCESTOR_OK`)
- `git merge-base
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  71092fefee74649bad71dbb5b7a7106115e9f545` →
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (the anchor itself)
- `git merge-base --is-ancestor
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7
  71092fefee74649bad71dbb5b7a7106115e9f545` → exit 0 (`ANCESTOR_OK`)
- `git merge-base
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7
  71092fefee74649bad71dbb5b7a7106115e9f545` →
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (the anchor itself)

Candidate identity (recorded exactly):

- SHA: `71092fefee74649bad71dbb5b7a7106115e9f545`
- Parent 1 (main): `70f16102d975e3d59268f71de8ff1efd37432d3c`
  ("Merge pull request #314 from
  ulfe-lmi/oap/177-release-identity-db0bd3ae" — the Objective-177
  identity record merge)
- Parent 2 (PR #315 head): `5b9fc59a6f1040ced62624ccfcf2e1e5effc9b19`
  (Objective 178 final report head)
- Tree: `a226e9df6add137e3708338f352ec66e8889a239` (`git cat-file -t` →
  `tree`). This is exactly the merge tree and the accepted 178 final PR
  tree both verified on GitHub; local `git rev-parse
  71092fefee74649bad71dbb5b7a7106115e9f545^{tree}` resolves to the same
  object (`TREE_MATCH=EXACT`).

Complete path list — `git diff --name-status
db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7
71092fefee74649bad71dbb5b7a7106115e9f545` (39 paths; every path
classified into exactly one of the four non-runtime classes; no
unclassified path):

| Path | Status | Class | Source |
| --- | --- | --- | --- |
| `CONTRIBUTING.md` | A | (a) new public/reference documentation | 178 |
| `INSTALL.md` | A | (a) new public/reference documentation | 178 |
| `QUICKSTART.md` | A | (a) new public/reference documentation | 178 |
| `docs/first-time-operator-guide.md` | A | (a) new public/reference documentation | 178 |
| `README.md` | M | (b) modified public/reference/navigation documentation (descriptive bytes; packaging exception below) | 178 |
| `docs/README.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/cli-reference.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/compatibility-matrix.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/configuration.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/demo-journey.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/deployment-production.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/deployment.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/onboarding.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/product-scope.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/quickstart.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/rc-beta.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/release-decision-brief.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/release-notes.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/releases/README.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/support-policy.md` | M | (b) modified public/reference/navigation documentation | 178 |
| `docs/verification/README.md` | M | (b) modified public/reference/navigation documentation | 177/178 |
| `docs/verification/2026-09-20-release-identity-db0bd3ae.md` | A | (d) identity/OAP evidence | 177 (immutable identity record) |
| `oap/active` | M | (d) identity/OAP evidence | 176→177→178 pointer progression (`176-a`→`177-a`→`178-e`) |
| `oap/orders/177-a-release-identity-db0bd3ae.md` | A | (d) identity/OAP evidence | 177 |
| `oap/orders/178-a-documentation-productization.md` | A | (d) identity/OAP evidence | 178-a |
| `oap/orders/178-b-complete-model-workflow-and-command-truth.md` | A | (d) identity/OAP evidence | 178-b |
| `oap/orders/178-c-production-upgrade-and-owned-cleanup.md` | A | (d) identity/OAP evidence | 178-c |
| `oap/orders/178-d-final-upgrade-command-correction.md` | A | (d) identity/OAP evidence | 178-d |
| `oap/orders/178-e-version-and-failure-state-truth.md` | A | (d) identity/OAP evidence | 178-e |
| `oap/reports/177-a-release-identity-db0bd3ae.md` | A | (d) identity/OAP evidence | 177 |
| `oap/reports/178-a-documentation-productization.md` | A | (d) identity/OAP evidence | 178-a |
| `oap/reports/178-b-complete-model-workflow-and-command-truth.md` | A | (d) identity/OAP evidence | 178-b |
| `oap/reports/178-c-production-upgrade-and-owned-cleanup.md` | A | (d) identity/OAP evidence | 178-c |
| `oap/reports/178-d-final-upgrade-command-correction.md` | A | (d) identity/OAP evidence | 178-d |
| `oap/reports/178-e-version-and-failure-state-truth.md` | A | (d) identity/OAP evidence | 178-e |
| `scripts/check_documentation.py` | M | (c) documentation checker and three documentation-specific unit tests | 178 (front-door rules for the new entry points; not shipped, not runtime-imported) |
| `tests/unit/test_documentation_asof.py` | M | (c) documentation checker and three documentation-specific unit tests | 178 |
| `tests/unit/test_documentation_contract_drift.py` | M | (c) documentation checker and three documentation-specific unit tests | 178 |
| `tests/unit/test_documentation_inventory.py` | M | (c) documentation checker and three documentation-specific unit tests | 178 |

Class counts: (a) 4 + (b) 17 + (c) 4 + (d) 14 = 39.

Complete original qualified-anchor delta: the
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` →
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` delta was already fully
classified in the immutable Objective-177 record
([`2026-09-20-release-identity-db0bd3ae.md`](2026-09-20-release-identity-db0bd3ae.md)).
Verification that nothing new escaped since that classification:

- `git diff --name-status 2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 -- .github sbom` → exactly the
  177-recorded set: `.github/workflows/ci.yml` (M),
  `.github/workflows/codeql.yml` (M), `sbom/cyclonedx.json` (M).
- `git diff --name-status db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7
  71092fefee74649bad71dbb5b7a7106115e9f545 -- .github sbom` → **empty
  output** (byte-identical since the prior identity anchor).

Therefore the total `.github`/`sbom` delta from the original qualified
anchor to the candidate is exactly the 177-classified set; nothing new
escaped.

Decisive empty diff, from BOTH anchors to candidate (recorded command with
its empty output):

```text
$ git diff --name-only 2b61312e0eb569aa7c6f953f52e35b44e84b91c1 \
    71092fefee74649bad71dbb5b7a7106115e9f545 -- app migrations \
    Dockerfile docker-compose.yml docker-compose.production.yml deploy \
    nginx pyproject.toml requirements.txt requirements-dev.txt Makefile \
    alembic.ini .env.example .dockerignore VERSION
(empty output)

$ git diff --name-only db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 \
    71092fefee74649bad71dbb5b7a7106115e9f545 -- app migrations \
    Dockerfile docker-compose.yml docker-compose.production.yml deploy \
    nginx pyproject.toml requirements.txt requirements-dev.txt Makefile \
    alembic.ini .env.example .dockerignore VERSION
(empty output)
```

Hash/subtree corroboration (`git rev-parse <rev>:<path>` for all three
revisions — identical object hash in every row):

| Path | Object hash (A = B = C) |
| --- | --- |
| `app` | `5ea15d3e3196...` |
| `migrations` | `7aebf68d7abb...` |
| `Dockerfile` | `df1a6fe40f9a...` |
| `docker-compose.yml` | `22c010309b1b...` |
| `docker-compose.production.yml` | `0db7ab9ebfd5...` |
| `deploy` | `a533f8201681...` |
| `nginx` | `55145f54cba7...` |
| `pyproject.toml` | `848850ddc8a4...` |
| `requirements.txt` | `a8586865cf6f...` |
| `requirements-dev.txt` | `bff7fe397bb3...` |
| `Makefile` | `a2eba7898442...` |
| `alembic.ini` | `1437f8c5c0cb...` |
| `.env.example` | `bf5fdccf27b0...` |
| `.dockerignore` | `f6a259fdccc2...` |
| `VERSION` | `8d2d58b61062...` |

(A = `2b61312e0eb569aa7c6f953f52e35b44e84b91c1`, B =
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`, C =
`71092fefee74649bad71dbb5b7a7106115e9f545`.)

LICENSE: `git diff --name-only <anchor>
71092fefee74649bad71dbb5b7a7106115e9f545 -- LICENSE` → empty output from
BOTH anchors — unchanged.

Individual inspection of the broad trees (no silent exclusion):

- `scripts/`: only `scripts/check_documentation.py` changed since the
  prior identity anchor (documentation checker; not shipped in the image).
- `tests/`: only the three documentation-specific unit tests listed above
  changed since the prior identity anchor; no other test path.
- `.github/`: byte-identical since the prior identity anchor (empty diff).
- `sbom/`: byte-identical since the prior identity anchor (empty diff).

README.md descriptive-packaging exception (explicit): `README.md` is a
packaging input, quoted verbatim at the candidate:

```text
Dockerfile line 13:  COPY pyproject.toml README.md LICENSE alembic.ini ./
pyproject.toml line 9:  readme = "README.md"
```

Its descriptive bytes changed between the anchors (README object hash
`a416f671a358...` at both anchors, `1339a4e86da4...` at the candidate).
Stated plainly: the executable runtime, deployment configuration, and
dependency INPUTS are byte-identical from both anchors to the candidate;
README/project-description metadata is intentionally different. This is
not whole-image equality, not reproducible image identity, and not frozen
dependency resolution at future build time.

## P1 — Documentation productization acceptance

- PR #315 (Objective 178) re-queried live: `state=MERGED`,
  `mergedAt=2026-09-20T19:28:39Z`, `mergedBy=jpers1`,
  `headRefName=oap/178-documentation-productization`,
  `headRefOid=5b9fc59a6f1040ced62624ccfcf2e1e5effc9b19`,
  `mergeCommit.oid=71092fefee74649bad71dbb5b7a7106115e9f545` (the
  candidate), `baseRefName=main`.
- Final report head `5b9fc59a6f1040ced62624ccfcf2e1e5effc9b19`: all ten
  check runs re-queried live with conclusion `success` (including the
  `CodeQL` rollup check run on the PR head).
- Final implementation head `b26ed802f97ea51f06b202255941afa9d4ee0afb`:
  the literal provider-free quickstart (build/migrate/start/health/
  readiness/admin/login/cleanup, milestone 1) was executed from a fresh
  disposable clone per the immutable 178-e report
  ([`oap/reports/178-e-version-and-failure-state-truth.md`](../../oap/reports/178-e-version-and-failure-state-truth.md));
  clean-room log `/tmp/obj178e-cleanroom-run.log` (local artifact, cited,
  not re-run); task-owned networks removed and all obj178-prefix state
  arrays verified empty after cleanup.
- Inherited evidence on unchanged inputs (cited, not re-run or
  reproduced): 178-b mocked model/pricing evidence
  (`MOCK_HARNESS=OK`; verified placeholder-to-reviewed pricing procedure)
  in the immutable 178-b report; 178-d command-mechanics synthetic
  fixture, 51 PASS / 0 FAIL
  (`/tmp/obj178d-fixture-run.log`, local artifact), accepted production
  command block md5 `279554084a5c160baa3d27fc9e1851c0` byte-identical at
  the 178-d and 178-e heads.
- Latest corrected facts are used (prior rounds' corrections are recorded
  in the later immutable reports; this record cites the terminal 178-e
  state). No live provider inference and no live production upgrade were
  performed in Objective 178.
- New root entry points verified present at the candidate (read-only
  `git rev-parse`): `INSTALL.md` `48fb5caa3a2f...`, `QUICKSTART.md`
  `030e74381c08...`, `CONTRIBUTING.md` `5b34e3a040f5...`,
  `docs/first-time-operator-guide.md` `826aa0cd8403...`; linked from
  `README.md` at lines 31, 35, 114, 115, and 120 at the candidate.

## P2 — Scope and scoped SBOM correspondence

- `docs/rc2-feature-scope.md` is unchanged since the prior identity
  anchor: `git diff --name-status db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7
  71092fefee74649bad71dbb5b7a7106115e9f545 -- docs/rc2-feature-scope.md`
  → empty output.
- Matrix rows counted at the candidate (51 endpoint rows in the RC2 Scope
  Matrix): `RC2_REQUIRED_IMPLEMENTED=27`,
  `RC2_REQUIRED_MISSING=0`, `RC2_EXPLICITLY_DEFERRED=21`,
  `RC2_UNSUPPORTED_BY_POLICY=3`, `NEEDS_MAINTAINER_DECISION=0`. The
  Classification Summary block reads exactly 27 / 0 / 21 / 3 / 0 and no
  matrix row uses the `NEEDS_MAINTAINER_DECISION` label — scope remains
  closed; no deferred feature was reinterpreted as implemented.
- `python scripts/check_sbom.py` on the objective branch tree (whose
  `sbom/cyclonedx.json` is byte-identical to the candidate) prints
  exactly:

```text
SBOM_CHECK=OK components=60
```

  (exit 0).
- Unchanged artifact: `sbom/cyclonedx.json` object hash
  `d58182ab2cda...` is identical at the candidate, at the prior identity
  anchor, and in the working tree. Metadata (verbatim):
  `metadata.timestamp = 2026-09-20T10:30:45+00:00`;
  `metadata.component = {name: slaif-api-gateway, version: 0.1.0,
  type: application}`; tools `slaif-generate-sbom 1.0` and
  `Python 3.12.3`; 60 components; CycloneDX specVersion 1.5.
- The artifact remains valid for its documented point-in-time frozen
  PRODUCTION DEPENDENCY scope because the dependency inputs and the
  artifact are unchanged. It is not an attestation of current/future
  image resolution, signed provenance, a vulnerability scan, invoice
  accuracy, or a complete environment inventory. No regeneration, no
  dependency installation, and no external provider calls were performed
  for this proof.

## P3 — Fresh candidate/main CI, then final PR gate

`gh api repos/ulfe-lmi/slaif-api-gateway/commits/
71092fefee74649bad71dbb5b7a7106115e9f545/check-runs` queried
2026-09-20T19:43:11Z: all nine stable checks by exact name
`completed`/`success`:

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| `Unit, lint, and migration head` | completed | success | 106135265853 |
| `Documentation hygiene` | completed | success | 106135266023 |
| `OpenAI-compatible E2E tests` | completed | success | 106135266004 |
| `Playwright browser smoke` | completed | success | 106135266168 |
| `Docker Compose smoke` | completed | success | 106135266070 |
| `PostgreSQL integration tests` | completed | success | 106135266054 |
| `Analyze (javascript-typescript)` | completed | success | 106135267666 |
| `Analyze (python)` | completed | success | 106135267629 |
| `Analyze Python` | completed | success | 106135265757 |

`CodeQL` suite rollup: on this merge commit the CodeQL suites are
expressed at check-suite level (no extra PR-style rollup check run):
the `check-suites` query (2026-09-20T19:43:20Z) shows all three suites
`completed`/`success` — suite `96205747311` (carrying `Analyze
(javascript-typescript)` and `Analyze (python)`), suite `96205747650`
(carrying `Analyze Python`), and suite `96205747676` (carrying the six CI
jobs). On this objective's PR heads the same CodeQL suite additionally
emits a `CodeQL`-named rollup check run; the final implementation and
report PR-head check states, including that rollup, are recorded in the
immutable report for Objective 179
(`oap/reports/179-a-post-documentation-release-identity.md`, published in
this objective's report-only commit).

Release-state predicates at record time:

- Open-PR count before this objective's own PR: `gh pr list --state open
  --json number,title,headRefName` → `[]` (zero open PRs) at
  2026-09-20T19:39:13Z.
- Tags: exactly one — `v0.1.0-rc.1` (annotated tag object
  `b614163fa901fb2f7a2e51268b7023c11b5864d0`, peeling to commit
  `328b5c19a584414f04d4ef5590a168f30aaf850c`). No tag added or moved.
- Releases: exactly one — `v0.1.0-rc.1` (published
  2026-05-01T21:33:27Z). No release added or changed. No tag/release
  authorization exists or is claimed here.

## P4 — Verdict, limitations, final candidate and successor relationship

With P0–P3 holding, the verdict stands:

`RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`

`71092fefee74649bad71dbb5b7a7106115e9f545` is the exact
documentation-complete taggable candidate. Derivation chain: the original
integrated qualification was executed on
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (Objective 173); Objective 177
previously bound `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` by identity;
this record derives the later candidate by byte identity of
executable/deployment/dependency inputs plus reviewed and classified
non-runtime changes and green fresh main CI. This is not another
integrated or production qualification run and it is not human release
approval; tag/release authority remains with the human maintainer.

Exact retained limitations:

- (i) The inherited qualification's provider was the harness's
  socket-level OpenAI-compatible double (mocked upstream) — no
  real-provider run, no provider credentials used or present.
- (ii) No independent penetration test or formal vulnerability
  assessment exists.
- (iii) No production certification, SLA, compliance, security, or scale
  claim is made.
- (iv) The two labeled environment-only non-passes in the 2026-09-17
  integrated record stand as labeled: the VM-only
  `codex_version_mismatch` unit case (`codex-cli 0.154.0` on the VM vs
  fixture pin `codex-cli 0.148.0`) and the local-VM `pg_dump` CLI skip on
  the `TEST_DATABASE_URL` form, with in-container backup/restore
  re-proven in both P2 runs of that record.
- (v) The Docker image live-resolves the unpinned direct production
  dependencies at build time (documented limitation; pinning is
  post-RC).
- (vi) The SBOM is a scoped point-in-time frozen production dependency
  record — not signed provenance, not a vulnerability scan, not a
  complete environment inventory.
- (vii) README/project-description metadata differs intentionally from
  the anchors (descriptive packaging input; not a runtime, deployment, or
  dependency input).

Old HPC history is not reopened as a fresh gate by this record.

Post-publication identity: this objective itself adds only this dated
record, the one newest-evidence entry in
`docs/verification/README.md`, the current latest-record pointer in
`docs/rc-beta.md`, and the OAP order/report/active files —
documentation/OAP evidence only. It does not change the candidate's
executable/deployment/dependency tree or `README.md`. A future merge
successor of this PR may inherit the same qualification only after
strategy verifies that exact delta and fresh final checks on the actual
merge; its merge SHA is not yet known and is deliberately not stated
here. The report `SELF` convention does not magically name a future
merge.
