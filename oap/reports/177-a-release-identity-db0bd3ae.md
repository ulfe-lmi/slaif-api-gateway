# OAP Coding-Agent Report — 177-a

## Work order
- Identifier: 177-a
- Work-order file: `oap/orders/177-a-release-identity-db0bd3ae.md`
- Numeric objective: 177
- PR mode: CREATED_NEW_PR

## Status
COMPLETE

## Verdict
`OUTCOME=A`

## Executive summary
Published the final release-candidate identity record, a
documentation-only change in exactly two allowed paths. The new dated
record `docs/verification/2026-09-20-release-identity-db0bd3ae.md`
(verdict `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`) binds the
Objective-173 full integrated qualification (executed on qualified
anchor 2b61312e0eb569aa7c6f953f52e35b44e84b91c1, `RESULT=QUALIFIED-RC-POSTURE`, immutable dated
record) to the exact current `main` candidate
db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 (merge of PR #313 / Objective 176) by mechanical proof:
P0 — the anchor is the exact merge base of the candidate (strict
forward ancestry, `ANCESTOR_OK`), the complete 20-path diff
anchor→candidate is classified into exactly the three non-runtime
classes (CI-only infrastructure; release metadata/SBOM only;
documentation/OAP evidence only), the runtime/deployment/dependency
surface diff over `app tests migrations nginx Dockerfile
docker-compose.yml docker-compose.production.yml Makefile
pyproject.toml alembic.ini` is EMPTY, and the verbatim Dockerfile COPY
list proves neither `scripts/` nor `sbom/` is shipped; P1 —
`python scripts/check_sbom.py` on the candidate tree prints exactly
`SBOM_CHECK=OK components=60` with the SBOM metadata quoted (frozen
production resolution of 2026-09-20T10:30:45+00:00, generator
`slaif-generate-sbom` 1.0 + Python 3.12.3); P2 — fresh CI on the
candidate: all nine stable checks by exact name plus the `CodeQL`
suite rollup `completed`/`success` with run IDs; P3 — zero open PRs,
RC2 Classification Summary verbatim 27 / 0 / 21 / 3 / 0, and the
`NEEDS_MAINTAINER_DECISION` grep shows only the label-list line and the
zero summary count (no row usage); P4 — the six exact known
limitations stated verbatim (mocked-upstream provider, no pentest, no
certification/SLA/compliance/security/scale claim, the two labeled
environment-only non-passes, Dockerfile live-resolution limitation with
pinning post-RC, SBOM as point-in-time frozen record — not signed
provenance, not a vulnerability scan). The record carries the
derivation statement and the post-merge relationship statement
(required verbatim/semantically-exact). `docs/verification/README.md`
gained exactly one index row in the existing style;
`python scripts/check_documentation.py` prints
`DOCUMENTATION_CHECK=OK files=85` (84 + the new record). This is
identity derivation — explicitly NOT a second full clean-room
qualification — and makes no release decision. All nine stable checks
plus the `CodeQL` rollup are `success` on the exact implementation
head, and the final-head re-query is the mandatory gate before the
response FIFO `OK` (see CI gate state).

## Authoritative GitHub state
- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: 314
- PR URL: https://github.com/ulfe-lmi/slaif-api-gateway/pull/314
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/177-release-identity-db0bd3ae`
- Base SHA (the exact release candidate): `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (remote
  `main`, merge of PR #313 / Objective 176; all six CI jobs plus the
  `CodeQL` suite rollup and the dynamic `Code Quality: Push on main`
  suite `success`, re-queried 2026-09-20 ~10:55 UTC)
- Qualified anchor SHA: `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge / Objective 173,
  `RESULT=QUALIFIED-RC-POSTURE`)
- Implementation head SHA: `1f75d3ab68136e72b2f6254498f99bd1443efbef`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived
  from GitHub)
- Implementation commits pushed before the report commit:
    - `82fe445f304df7d35d9a00c907ff2773f0e83c4c` `oap: activate 177-a release identity db0bd3ae` (carries the strategic-authored order and `oap/active`; order file byte-identical, md5 `e550ec3ef6ada8a434b4389f126fe0f1` verified against the worktree source)
    - `1f75d3ab68136e72b2f6254498f99bd1443efbef` `obj177: publish release-candidate identity record for db0bd3ae` (the two functional paths)
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: yes
- Amended existing PR this turn: no
- Merge performed: NO

## Changes made
- `docs/verification/2026-09-20-release-identity-db0bd3ae.md` (NEW):
  the dated identity record — P0 through P4 with the machine evidence
  quoted above, the complete classified path table, the derivation
  statement, and the post-merge relationship statement; verbatim
  document below (AP-6).
- `docs/verification/README.md`: exactly one index row appended in the
  existing style (link, one-line summary, verdict
  `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`, and the
  not-a-release-decision boundary note); verbatim diff below (AP-6).
- `oap/orders/177-a-release-identity-db0bd3ae.md`: strategic work order
  committed unchanged (byte-identical; md5
  `e550ec3ef6ada8a434b4389f126fe0f1` verified against the worktree
  source).
- `oap/active`: `177-a` (activated order pointer).
- `oap/reports/177-a-release-identity-db0bd3ae.md`: this report
  (report-only commit).

## Files changed (full, including the report commit)
- `docs/verification/2026-09-20-release-identity-db0bd3ae.md`
- `docs/verification/README.md`
- `oap/active`
- `oap/orders/177-a-release-identity-db0bd3ae.md`
- `oap/reports/177-a-release-identity-db0bd3ae.md`

`git diff --name-only db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 1f75d3ab68136e72b2f6254498f99bd1443efbef` lists exactly the first four
paths (the report file appears only in the report commit); nothing
else.

## P0 — Ancestry and complete diff classification (decisive identity proof)

- `git merge-base --is-ancestor 2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` → exit 0 (`ANCESTOR_OK`).
- `git merge-base 2b61312e0eb569aa7c6f953f52e35b44e84b91c1 db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` →
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` — the qualified anchor is the exact merge base: the
  candidate is a strict forward descendant.
- Complete path list, `git diff --name-status 2b61312e0eb569aa7c6f953f52e35b44e84b91c1 db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` — 20
  paths, every path exactly one class (full table reproduced in the
  dated record, quoted verbatim below):

```text
M   .github/workflows/ci.yml                        (a) CI-only infrastructure   [174-a/b action lines + 176 SBOM step]
M   .github/workflows/codeql.yml                    (a) CI-only infrastructure   [174-b checkout v7 line]
M   docs/rc2-feature-scope.md                       (c) documentation/OAP evidence only [175]
M   docs/supply-chain.md                            (b) release metadata/SBOM only      [176]
A   docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md  (c) [173]
M   docs/verification/README.md                     (c) documentation/OAP evidence only [173]
M   oap/active                                      (c) documentation/OAP evidence only [173->176 pointer progression]
A   oap/orders/173-a-current-main-integrated-requalification-2b61312e.md  (c) [173]
A   oap/orders/174-a-ci-actions-v7-bump.md          (c) documentation/OAP evidence only [174-a]
A   oap/orders/174-b-codeql-checkout-v7-line.md     (c) documentation/OAP evidence only [174-b]
A   oap/orders/175-a-rc-scope-closure.md            (c) documentation/OAP evidence only [175]
A   oap/orders/176-a-reproducible-release-sbom.md   (c) documentation/OAP evidence only [176]
A   oap/reports/173-a-current-main-integrated-requalification-2b61312e.md (c) [173]
A   oap/reports/174-a-ci-actions-v7-bump.md         (c) documentation/OAP evidence only [174-a]
A   oap/reports/174-b-codeql-checkout-v7-line.md    (c) documentation/OAP evidence only [174-b]
A   oap/reports/175-a-rc-scope-closure.md           (c) documentation/OAP evidence only [175]
A   oap/reports/176-a-reproducible-release-sbom.md  (c) documentation/OAP evidence only [176]
M   sbom/cyclonedx.json                             (b) release metadata/SBOM only      [176]
A   scripts/check_sbom.py                           (a) CI-only infrastructure   [176]
A   scripts/generate_sbom.py                        (a) CI-only infrastructure   [176]
```

- Empty runtime/deployment/dependency surface diff (recorded command,
  recorded empty output):

```text
$ git diff --name-only 2b61312e0eb569aa7c6f953f52e35b44e84b91c1 db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 -- app tests migrations nginx Dockerfile docker-compose.yml docker-compose.production.yml Makefile pyproject.toml alembic.ini
(empty output)
```

- Verbatim Dockerfile `COPY` lines at the candidate (evidence that
  neither `scripts/` nor `sbom/` is shipped in the production image):

```text
13:COPY pyproject.toml README.md LICENSE alembic.ini ./
14:COPY app ./app
15:COPY migrations ./migrations
16:COPY deploy/production/load-secrets.sh /usr/local/bin/load-production-secrets
```

## P1 — SBOM correspondence

- `python scripts/check_sbom.py` on the candidate tree — exact output:

```text
SBOM_CHECK=OK components=60
```

- SBOM metadata (verbatim): timestamp `2026-09-20T10:30:45+00:00`;
  component `{'name': 'slaif-api-gateway', 'version': '0.1.0', 'type': 'application'}`; tools `{'components': [{'type': 'application', 'name': 'slaif-generate-sbom', 'version': '1.0'}, {'type': 'library', 'name': 'Python', 'version': '3.12.3'}]}`.
- Component count 60 = the frozen production dependency resolution
  (21 direct + transitive) captured by the 176 generator's stage-1
  freeze; structural validity enforced in CI (`Check SBOM validity`
  step in `Unit, lint, and migration head`).
- `docs/supply-chain.md` limitation lines quoted in the record:
  production-only scope; live-resolution at image build time
  (deliberately post-RC pinning).

## P2 — Fresh current-main CI (run-ID tables)

Candidate `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (merge commit on `main`; same check topology as the
previously verified baseline merge commit `37df166`):

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| `Unit, lint, and migration head` | completed | success | 106065831065 |
| `Documentation hygiene` | completed | success | 106065830905 |
| `OpenAI-compatible E2E tests` | completed | success | 106065831048 |
| `Playwright browser smoke` | completed | success | 106065831015 |
| `Docker Compose smoke` | completed | success | 106065831017 |
| `PostgreSQL integration tests` | completed | success | 106065830960 |
| `Analyze (javascript-typescript)` | completed | success | 106065831635 |
| `Analyze (python)` | completed | success | 106065831384 |
| `Analyze Python` | completed | success | 106065830887 |
| `CodeQL` suite rollup (check suite `96139591916`, carrying `Analyze (javascript-typescript)` + `Analyze (python)`) | completed | success | suite-level |

(On merge commits the CodeQL rollup is expressed at check-suite level,
as on the baseline `37df166`; the CI suite `96139592705` and the
dynamic `Code Quality: Push on main` suite `96139592707` are likewise
`completed`/`success`.)

Implementation head `1f75d3ab68136e72b2f6254498f99bd1443efbef` (PR head; the CodeQL suite additionally
emits its `CodeQL`-named rollup check run):

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| `Unit, lint, and migration head` | completed | success | 106067072325 |
| `Documentation hygiene` | completed | success | 106067072305 |
| `OpenAI-compatible E2E tests` | completed | success | 106067072281 |
| `Playwright browser smoke` | completed | success | 106067072263 |
| `Docker Compose smoke` | completed | success | 106067072264 |
| `PostgreSQL integration tests` | completed | success | 106067072316 |
| `Analyze (javascript-typescript)` | completed | success | 106067069811 |
| `Analyze (python)` | completed | success | 106067069706 |
| `Analyze Python` | completed | success | 106067072421 |
| `CodeQL` suite rollup (check run `CodeQL`) | completed | success | 106067204148 |

## P3 — Release-state predicates

- Open-PR count (recorded output, before this objective's own PR):

```text
$ gh pr list --repo ulfe-lmi/slaif-api-gateway --state open --json number
[]
```

- RC2 Classification Summary block (verbatim; reads exactly
  27 / 0 / 21 / 3 / 0):

```text
## Classification Summary

| Classification | Row count |
| --- | ---: |
| `RC2_REQUIRED_IMPLEMENTED` | 27 |
| `RC2_REQUIRED_MISSING` | 0 |
| `RC2_EXPLICITLY_DEFERRED` | 21 |
| `RC2_UNSUPPORTED_BY_POLICY` | 3 |
| `NEEDS_MAINTAINER_DECISION` | 0 |
```

- `grep -n "NEEDS_MAINTAINER_DECISION" docs/rc2-feature-scope.md`:

```text
22:- `NEEDS_MAINTAINER_DECISION`
32:| `NEEDS_MAINTAINER_DECISION` | 0 |
```

  line 22 = the classification-label list; line 32 = the zero summary
  count; no matrix row uses the label.

## P4 — Exact known limitations

The dated record states verbatim (AP-5; full text in the record and
quoted below): (i) mocked-upstream socket-level provider double — no
real-provider run, no provider credentials used or present; (ii) no
independent penetration test or formal vulnerability assessment; (iii)
no production certification, SLA, compliance, security, or scale
claim; (iv) the two labeled environment-only test non-passes (VM
`codex-cli 0.154.0` vs fixture `0.148.0` unit case; local-VM `pg_dump`
CLI skip with in-container backup/restore re-proven in both 173 P2
runs); (v) the Docker image live-resolves the unpinned direct
production dependencies at build time (documented limitation; pinning
is post-RC); (vi) the SBOM is a point-in-time frozen production
dependency record — not signed provenance, not a vulnerability scan.

## Verbatim publication artifacts (AP-6)

### `docs/verification/README.md` index row (verbatim diff; exactly one entry added)

```diff
diff --git a/docs/verification/README.md b/docs/verification/README.md
index ee561d3..b170cc6 100644
--- a/docs/verification/README.md
+++ b/docs/verification/README.md
@@ -73,3 +73,17 @@ fitness, security, compliance, provider behavior, or scale.
   named candidate commit only; mocked-upstream qualification, not a
   real-provider run, release decision, security certification, or
   production approval.
+- [`2026-09-20 release-candidate identity record (candidate db0bd3ae)`](2026-09-20-release-identity-db0bd3ae.md)
+  - verification-only identity derivation binding the Objective-173
+  full integrated qualification
+  (`2b61312e0eb569aa7c6f953f52e35b44e84b91c1`,
+  `RESULT=QUALIFIED-RC-POSTURE`) to exact `main`
+  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge): empty
+  runtime/deployment/dependency-surface diff, every intervening path
+  classified CI-only / release-metadata-SBOM / documentation-OAP,
+  fresh 9/9 stable checks plus CodeQL suite rollup `success`, RC2 scope
+  closure 27/0/21/3/0, and SBOM correspondence
+  `SBOM_CHECK=OK components=60`. Verdict
+  `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`. Dated evidence for the
+  named candidate commit only; identity derivation, not a second full
+  clean-room qualification, and not a release decision.
```

### `docs/verification/2026-09-20-release-identity-db0bd3ae.md` (verbatim new dated record)

```markdown
# Objective 177 release-candidate identity record (candidate db0bd3ae)

Date: 2026-09-20 (Europe/Ljubljana; UTC timestamps as recorded by the
queries)

Candidate (evidence boundary): `main`
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (merge of PR #313 / Objective
176), verified remote `main` at execution time.

Qualified anchor: `main`
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge; Objective
173), `RESULT=QUALIFIED-RC-POSTURE`, dated record
[`2026-09-17-current-main-integrated-requalification-2b61312e.md`](2026-09-17-current-main-integrated-requalification-2b61312e.md)
(immutable; referenced, not rewritten).

This is a dated, verification-only record that binds the Objective-173
full integrated qualification (executed on the qualified anchor) to the
exact current `main` that will receive the RC tag, by mechanically
proving zero runtime/deployment/dependency delta, classifying every
intervening change, and re-proving current-main CI, scope closure, and
SBOM correspondence. This is identity derivation — explicitly NOT a
second full clean-room qualification. It implements no capability,
changes no code, dependency, or build input, and makes no release
decision. All evidence below was re-queried live on 2026-09-20.

## Verdict

`RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`

The full integrated qualification was executed on
`2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (Objective 173,
`RESULT=QUALIFIED-RC-POSTURE`). The exact release candidate inherits
that runtime/deployment qualification because the
runtime/deployment/dependency tree is byte-identical, and every
intervening change is classified and separately verified above. This
record is an identity derivation, not a second full clean-room
qualification.

## P0 — Ancestry and complete diff classification

Ancestry proof (shared worktree; candidate is a strict forward
descendant of the anchor — the anchor is the exact merge base):

- `git merge-base --is-ancestor
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` → exit 0 (`ANCESTOR_OK`)
- `git merge-base
  2b61312e0eb569aa7c6f953f52e35b44e84b91c1
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` →
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (the anchor itself)

Complete path list — `git diff --name-status
2b61312e0eb569aa7c6f953f52e35b44e84b91c1
db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (20 paths; every path
classified into exactly one of the three non-runtime classes):

| Path | Status | Class | Source |
| --- | --- | --- | --- |
| `.github/workflows/ci.yml` | M | (a) CI-only infrastructure | 174-a/b action-version lines + 176 one-step `Check SBOM validity` |
| `.github/workflows/codeql.yml` | M | (a) CI-only infrastructure | 174-b checkout v7 line |
| `scripts/generate_sbom.py` | A | (a) CI-only infrastructure | 176 (stdlib SBOM generator; not shipped, not runtime-imported) |
| `scripts/check_sbom.py` | A | (a) CI-only infrastructure | 176 (stdlib SBOM validator; invoked by the CI step only) |
| `sbom/cyclonedx.json` | M | (b) release metadata/SBOM only | 176 (regenerated 60-component frozen production SBOM) |
| `docs/supply-chain.md` | M | (b) release metadata/SBOM only | 176 (SBOM scope/mechanism/attestation-boundary doc) |
| `docs/rc2-feature-scope.md` | M | (c) documentation/OAP evidence only | 175 (RC2 scope closure reclassification) |
| `docs/verification/2026-09-17-current-main-integrated-requalification-2b61312e.md` | A | (c) documentation/OAP evidence only | 173 (immutable qualification record) |
| `docs/verification/README.md` | M | (c) documentation/OAP evidence only | 173 (index row) |
| `oap/active` | M | (c) documentation/OAP evidence only | 173→176 pointer progression (`173-a`→`176-a`) |
| `oap/orders/173-a-current-main-integrated-requalification-2b61312e.md` | A | (c) documentation/OAP evidence only | 173 |
| `oap/orders/174-a-ci-actions-v7-bump.md` | A | (c) documentation/OAP evidence only | 174-a |
| `oap/orders/174-b-codeql-checkout-v7-line.md` | A | (c) documentation/OAP evidence only | 174-b |
| `oap/orders/175-a-rc-scope-closure.md` | A | (c) documentation/OAP evidence only | 175 |
| `oap/orders/176-a-reproducible-release-sbom.md` | A | (c) documentation/OAP evidence only | 176 |
| `oap/reports/173-a-current-main-integrated-requalification-2b61312e.md` | A | (c) documentation/OAP evidence only | 173 |
| `oap/reports/174-a-ci-actions-v7-bump.md` | A | (c) documentation/OAP evidence only | 174-a |
| `oap/reports/174-b-codeql-checkout-v7-line.md` | A | (c) documentation/OAP evidence only | 174-b |
| `oap/reports/175-a-rc-scope-closure.md` | A | (c) documentation/OAP evidence only | 175 |
| `oap/reports/176-a-reproducible-release-sbom.md` | A | (c) documentation/OAP evidence only | 176 |

No path is unclassified; no path is a runtime, deployment, or
dependency path. The intervening changes are exactly the Objectives
173/174/175/176 publication and hygiene set.

Runtime/deployment/dependency surface — byte-identical proof
(recorded command with its empty output):

```text
$ git diff --name-only 2b61312e0eb569aa7c6f953f52e35b44e84b91c1 \
    db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 -- app tests migrations \
    nginx Dockerfile docker-compose.yml docker-compose.production.yml \
    Makefile pyproject.toml alembic.ini
(empty output)
```

Dockerfile `COPY` evidence at the candidate (verbatim):

```text
13:COPY pyproject.toml README.md LICENSE alembic.ini ./
14:COPY app ./app
15:COPY migrations ./migrations
16:COPY deploy/production/load-secrets.sh /usr/local/bin/load-production-secrets
```

Neither `scripts/` nor `sbom/` is in the COPY list: the two new
tooling scripts and the regenerated SBOM are CI/release tooling and
release metadata respectively — not shipped in the production image.

## P1 — SBOM correspondence

- `python scripts/check_sbom.py` on the candidate tree prints exactly:

```text
SBOM_CHECK=OK components=60
```

  (exit 0).
- SBOM `sbom/cyclonedx.json` metadata (verbatim):
  - `metadata.timestamp`: `2026-09-20T10:30:45+00:00`
  - `metadata.component`: `{'name': 'slaif-api-gateway', 'version': '0.1.0', 'type': 'application'}`
  - `metadata.tools.components`: `[{'type': 'application', 'name': 'slaif-generate-sbom', 'version': '1.0'}, {'type': 'library', 'name': 'Python', 'version': '3.12.3'}]`
- Component count: **60** — the set is the frozen production
  dependency resolution (the 21 direct production dependencies parsed
  from `pyproject.toml` plus their transitive closure) captured by the
  stage-1 freeze; structural validity is enforced in CI by
  `scripts/check_sbom.py` inside the `Unit, lint, and migration head`
  job.
- `docs/supply-chain.md` limitation lines (verbatim):
  - "The release SBOM at `sbom/cyclonedx.json` is a scoped,
    point-in-time record of the **production runtime dependencies
    only**."
  - "It is **not an attestation of build-time resolution**: the
    `Dockerfile` live-resolves the unpinned direct production
    dependencies at image build time, so an image built later may
    resolve different versions than the frozen record."

## P2 — Fresh current-main CI (candidate)

`gh api repos/ulfe-lmi/slaif-api-gateway/commits/
db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7/check-runs` on 2026-09-20
(~10:55 UTC): all nine stable checks by exact name
`completed`/`success`:

| Check | Status | Conclusion | Run ID |
| --- | --- | --- | --- |
| `Unit, lint, and migration head` | completed | success | 106065831065 |
| `Documentation hygiene` | completed | success | 106065830905 |
| `OpenAI-compatible E2E tests` | completed | success | 106065831048 |
| `Playwright browser smoke` | completed | success | 106065831015 |
| `Docker Compose smoke` | completed | success | 106065831017 |
| `PostgreSQL integration tests` | completed | success | 106065830960 |
| `Analyze (javascript-typescript)` | completed | success | 106065831635 |
| `Analyze (python)` | completed | success | 106065831384 |
| `Analyze Python` | completed | success | 106065830887 |

`CodeQL` suite rollup: on this merge commit the CodeQL suite rollup is
expressed at check-suite level, as on the previously verified baseline
merge commit `37df1661087ddc423086290d66a170f2e9c0cfda` (same topology:
9 check runs, 3 suites): the CodeQL check suite
(`96139591916`, carrying `Analyze (javascript-typescript)` and
`Analyze (python)`) is `completed`/`success`; the CI check suite
(`96139592705`, carrying the six CI jobs) is `completed`/`success`; the
dynamic `Code Quality: Push on main` check suite (`96139592707`,
carrying `Analyze Python`) is `completed`/`success`. On PR heads the
same CodeQL suite additionally emits a `CodeQL`-named rollup check run;
that rollup run is re-queried on this objective's final PR head (see
the immutable report for this objective).

## P3 — Release-state predicates

- Open-PR count: `gh pr list --repo ulfe-lmi/slaif-api-gateway
  --state open --json number` →

```text
[]
```

  (zero open PRs at record time, before this objective's own PR).
- `docs/rc2-feature-scope.md` Classification Summary block (verbatim):

```text
## Classification Summary

| Classification | Row count |
| --- | ---: |
| `RC2_REQUIRED_IMPLEMENTED` | 27 |
| `RC2_REQUIRED_MISSING` | 0 |
| `RC2_EXPLICITLY_DEFERRED` | 21 |
| `RC2_UNSUPPORTED_BY_POLICY` | 3 |
| `NEEDS_MAINTAINER_DECISION` | 0 |
```

  reads exactly 27 / 0 / 21 / 3 / 0.
- `grep -n "NEEDS_MAINTAINER_DECISION" docs/rc2-feature-scope.md`:

```text
22:- `NEEDS_MAINTAINER_DECISION`
32:| `NEEDS_MAINTAINER_DECISION` | 0 |
```

  line 22 is the classification-label list, line 32 the zero summary
  count; no matrix row uses the label — scope is closed.

## P4 — Exact known limitations

This record and the qualification it inherits carry, verbatim, at
least these limitations:

- (i) The qualification provider was the harness's socket-level
  OpenAI-compatible double (mocked upstream) — no real-provider run,
  no provider credentials used or present.
- (ii) No independent penetration test or formal vulnerability
  assessment exists.
- (iii) No production certification, SLA, compliance, security, or
  scale claim is made.
- (iv) The two labeled environment-only test non-passes (VM
  `codex-cli 0.154.0` vs fixture `0.148.0` unit case; local-VM
  `pg_dump` CLI skip with in-container backup/restore re-proven in
  both 173 P2 runs).
- (v) The Docker image live-resolves the unpinned direct production
  dependencies at build time (documented limitation; pinning is
  post-RC).
- (vi) The SBOM is a point-in-time frozen production dependency
  record — not signed provenance, not a vulnerability scan.

## Post-merge relationship

After this PR merges, `main` will differ from the named candidate
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` only by this dated record,
the `docs/verification/README.md` index row, and the OAP
order/report/active files (documentation/OAP evidence only), and is
therefore likewise runtime-identical; the RC tag may name either the
exact candidate or that post-merge successor.
```

## Acceptance-criteria evidence

- **AP-1 (decisive identity proof)**: P0 ancestry proof with
  merge-base SHA `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` recorded; complete classified path table
  (20/20 paths, each exactly one of the three non-runtime classes; no
  unclassified or runtime/deployment/dependency path); EMPTY
  runtime/deployment/dependency-surface diff over the explicit path
  set; verbatim Dockerfile COPY evidence — all present in the dated
  record (quoted above).
- **AP-2 (SBOM correspondence)**: exact `SBOM_CHECK=OK components=60`
  line, quoted SBOM metadata, component count 60 = frozen production
  resolution, and the quoted supply-chain limitation lines — all in
  the record.
- **AP-3 (fresh CI)**: P2 tables above on the exact candidate (nine
  stable by exact name + CodeQL suite rollup, all `completed`/`success`
  with run IDs) and on the implementation head (nine stable + `CodeQL`
  rollup run `106067204148`); the final-head re-query after this
  report-only commit is the mandatory gate before the response-FIFO
  `OK` (see CI gate state).
- **AP-4 (release-state predicates)**: open-PR count zero (recorded
  `[]`); RC2 summary block verbatim 27 / 0 / 21 / 3 / 0; the
  `NEEDS_MAINTAINER_DECISION` grep output shows the label-list line
  and the zero summary count only (no row usage).
- **AP-5 (limitations)**: all six P4 limitation categories present
  verbatim in the record; the record makes no certification,
  compliance, SLA, security, scale, real-provider, or
  production-readiness claim.
- **AP-6 (publication)**: the dated record exists at the exact path
  `docs/verification/2026-09-20-release-identity-db0bd3ae.md` with the
  exact candidate SHA (`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7`, 7 occurrences), the exact verdict
  line `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`, the derivation
  statement (semantically exact, as permitted), and the post-merge
  relationship statement; the README index row is exactly one entry
  added in the existing style; `python scripts/check_documentation.py`
  printed `DOCUMENTATION_CHECK=OK files=85` (84 + the new record).
- **AP-7 (immutable report and final-head gate)**: SELF topology —
  this report commit is the PR head, its first parent is the
  implementation head `1f75d3ab68136e72b2f6254498f99bd1443efbef`, and it changes only
  `oap/reports/177-a-release-identity-db0bd3ae.md`; the report
  contains the literal candidate SHA and the literal qualified-anchor
  SHA, the single verdict line, and the merge-not-performed statement;
  the remote PR head is verified as this report commit after
  publication; the final-head P2 re-query must pass before the
  two-byte `OK` is written to the response FIFO.

## Local verification (shared worktree)

All commands run in the shared worktree checked out at the candidate
`db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (implementation head after the two commits); no clean room,
no disposable database, no harness run, no local test suite (none
authorized — verification and documentation publication only):

- P0 commands (ancestry, merge-base, `git diff --name-status`, the
  empty runtime-surface diff, `git show db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7:Dockerfile | grep -n
  COPY`) — verbatim outputs quoted above; full log
  `/tmp/obj177-p0.log`.
- P1: `python scripts/check_sbom.py` → `SBOM_CHECK=OK components=60`
  (exit 0); SBOM metadata one-liner output quoted above —
  `/tmp/obj177-p1p3.log`.
- P3: `gh pr list ... --state open --json number` → `[]`; RC2 summary
  `sed` block; `NEEDS_MAINTAINER_DECISION` grep — `/tmp/obj177-p1p3.log`.
- P2: `gh api .../commits/<sha>/check-runs` on the candidate, the
  implementation head, and (after publication) the final head —
  `/tmp/obj177-p2-candidate.log`, `/tmp/obj177-p2-impl.log`.
- `python scripts/check_documentation.py` → `DOCUMENTATION_CHECK=OK
  files=85`.
- `git diff --check 82fe445f304df7d35d9a00c907ff2773f0e83c4c 1f75d3ab68136e72b2f6254498f99bd1443efbef` — clean; `git diff --name-only
  db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7 1f75d3ab68136e72b2f6254498f99bd1443efbef` — exactly the four non-report paths; per-excluded-path
  diffs (`app tests migrations nginx Dockerfile docker-compose.yml
  docker-compose.production.yml Makefile pyproject.toml alembic.ini
  sbom scripts .github docs/rc2-feature-scope.md
  docs/supply-chain.md`) — all empty.

## Negative evidence
- No application, test, script, workflow, migration, nginx, Docker,
  Compose, Makefile, or dependency change of any kind: all of `app/`,
  `tests/`, `scripts/`, `.github/`, `migrations/`, `nginx/`,
  `Dockerfile`, `docker-compose*.yml`, `Makefile`, `pyproject.toml`,
  `alembic.ini` byte-identical to the base candidate (per-path empty
  diffs).
- No SBOM regeneration or modification (the 176 artifact is
  unmodified on the candidate and untouched here); no RC2 scope
  document modification (closed in 175); the two 176 scripts are
  already on `main` and NOT modified.
- No clean room, no production-appliance harness run, no local full
  unit/integration/E2E suite, no disposable database, no browser run
  beyond CI.
- No tag, release, publication (beyond this record), or deployment of
  any kind; no real provider calls; no real email; no secrets in this
  report or the PR (only SHAs, run IDs, check names, suite IDs, and
  quoted document text).
- No PR interaction beyond this PR; no Dependabot action; no
  GitHub-settings action; no merge, no auto-merge.
- Environment-only labels: none expected and none observed (all nine
  stable checks and the CodeQL rollup passed on the GitHub runners).

## CI gate state on the final head
- Implementation head `1f75d3ab68136e72b2f6254498f99bd1443efbef` (first parent of the final report-only
  head, which adds only this report file and touches no path covered
  by any check): all nine stable checks SUCCESS plus the `CodeQL`
  suite rollup run `106067204148` SUCCESS (run-ID table above). Per
  AP-7, the final head's check runs are re-queried after publication
  of this report-only commit, and that re-query is a mandatory gate
  before the response-FIFO `OK` signal is sent (a report commit cannot
  carry the run IDs of its own commit; the re-query result is part of
  this objective's execution record and is independently re-verified
  on GitHub).

## Merge-not-performed statement
The coding agent never merges. PR #314 was left OPEN for strategic
review and the human maintainer's delegated merge authority; no merge
was performed, and no merge-related GitHub action of any kind was taken
by this objective. The strategic model merges the unique PR only after
the final-head gates pass.
