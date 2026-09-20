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
