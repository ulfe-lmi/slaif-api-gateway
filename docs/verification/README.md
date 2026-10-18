# Verification Evidence

This directory indexes durable verification records for specific repository
commits and execution environments. A record describes what one bounded run
actually proved; it is not permanent certification of later commits, production
fitness, security, compliance, provider behavior, or scale.

## Current evidence (newest first)

For current readers, these are the newest qualification and identity records
on record. They are dated, commit-specific evidence, not certifications.

- [`2026-09-20 post-documentation release-identity record (candidate 71092fef)`](2026-09-20-post-documentation-release-identity-71092fef.md)
  — `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY` for exact `main`
  `71092fefee74649bad71dbb5b7a7106115e9f545` (PR #315 merge): identity
  derivation that binds the Objective-173 integrated qualification to the
  documentation-complete candidate through empty
  runtime/deployment/dependency-surface diffs from both prior anchors
  (the Objective-177 `db0bd3ae` identity record and the 173 integrated
  record); not a second full clean-room run, and not a release decision.
- [`2026-09-20 release-candidate identity record (candidate db0bd3ae)`](2026-09-20-release-identity-db0bd3ae.md)
  — `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY` for exact `main`
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge): identity
  derivation from the Objective-173 qualification through an empty
  runtime/deployment/dependency-surface diff; not a second full clean-room
  run, and not a release decision.
- [`2026-09-17 current-main integrated requalification (candidate 2b61312e)`](2026-09-17-current-main-integrated-requalification-2b61312e.md)
  — `RESULT=QUALIFIED-RC-POSTURE` for `main`
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge): mocked-upstream
  production-appliance double with two labeled environment-only non-passes;
  not a real-provider run, release decision, or production certification.

## Records

- [`2026-10-18 Codex 0.162 file-backed compatibility profile DATA`](codex-file-compatibility-profiles.md) —
  Objective 190-b: shipped default profile DATA (revision 3, canonical
  digest `aa3de537...daf90bd`), bounded parser/immutable loader,
  data-revision module identity with frozen v1/v2 migration selectors,
  operator file override with no-silent-fallback bootstrap, audited
  `migrate-key-profile`, real 197-name regression fixture, fresh-process
  real-HTTP Gateway and owned-PostgreSQL evidence, and wheel packaging
  proof.
- [`2026-10-18 Codex 0.162 version-2 connector tool names`](codex-0162-connector-names.md) —
  Objective 190-a: registered `codex-0.162-responses-v1` v2 profile
  (namespace-scoped leading-underscore connector tool names, exact
  preservation), frozen 0162-v1 historical selector with the
  0162-v1 ↔ 0162-v2 audited migration hop (six legal edges), unit,
  real-PostgreSQL migration, and real-Gateway stream/replay E2E
  evidence; the full operator-supplied 197-name artifact remains
  pending.
- [`2026-10-18 Codex 0.162.1 additional-tools profile and Local-pair lowering`](codex-0162-local-tools.md) —
  Objective 189-a: registered `codex-0.162-responses-v1` v1 profile
  (finite 16/256/256/20,000/262,144/4,096 taxonomy), approved initial-prefix
  provider lowering for the exact Local pair, prompt-cache-key omission,
  and documented route/pricing prerequisites; unit, mocked, real-PostgreSQL
  E2E, and independent official-CLI evidence.
- [`2026-10-18 Codex 0.149-v5 additional-tools ID and audited module migration`](codex-additional-tools-id.md) —
  Objective 189-a: bounded optional declaration item ID on 0.149 (v4 → v5)
  with unknown-field rejection and existing gates preserved, and the
  audited four-edge key-module upgrade/rollback (frozen 0.149-v4 tuple,
  dry-run default, no schema change).

- [`2026-10-17 SLAIF visual design`](slaif-visual-design.md) —
  Objective 188-a: packaged admin theme, shared shell, named table
  regions, and branded error surfaces; twelve unit design tests plus
  four native-browser cases (owned PostgreSQL, no provider
  invocation) and inherited 187/185 browser regressions.
- [`2026-08-17 current-main baseline`](2026-08-17-current-main-baseline.md) —
  one 24-worker full current-machine matrix, classified `RESULT=FAIL` because
  one of 2,534 tests failed. The separate post-PR-220 128-worker HPC
  qualification remains not run.
- [`2026-08-24 production-appliance qualification`](2026-08-24-production-appliance-qualification.md)
  — disposable production Compose, NGINX/TLS, PostgreSQL, Redis, worker/
  scheduler, provider-double, accounting, failure, privacy, persistence,
  backup/restore, and cleanup evidence for the named candidate. It is not a real-
  provider run, release decision, security certification, or production approval.
- [`2026-08-24 documentation architecture and truth audit`](2026-08-24-documentation-audit.md)
  — repository-wide cross-document and documentation-versus-code baseline for
  the documentation-modernization PR.
- [`2026-08-24 RC-beta readiness record`](../beta-readiness.md)
  — dated readiness record for `main`
  `8f2813bf745b90221da33a7cfaf40726c5b1b480` (reviewed 2026-08-24).
  Historical/dated evidence for the named commit only; not a current-state
  claim.
- [`2026-09-17 OpenAI SDK 3.9.0 official-client compatibility qualification`](2026-09-17-openai-sdk3-qualification.md)
  - 54-test official OpenAI-client E2E matrix qualified under
  `openai==3.9.0` (`OUTCOME=A`): wire-identity capture evidence, one
  root-cause family (SDK 3.x `httpx2` transport escapes respx observation),
  harness adaptation only, no gateway change. Evidence boundary: base
  `main` `1fccaa746df6cd44f1ddf8c2ec5cf6ea9f18b1cb` and the Objective 166 PR
  head. Mocked-upstream qualification only; not a real-provider run, release
  decision, security certification, or production approval.
- [`2026-09-17 current-main integrated qualification`](2026-09-17-current-main-integrated-qualification.md)
  - fresh RC-posture qualification of `main`
  `9bb81cb960b6d3ba5373425cbe50cdcc670b93dc` (PR #303 merge): clean-room
  P1 freeze, production-appliance harness run 1 `RESULT=FAIL` (privacy
  metrics scrape) with run 2 reproduction `RESULT=OK`, full local unit/
  integration/E2E matrix, and 9/9 CI checks SUCCESS. Verdict
  `RESULT=NOT-QUALIFIED` on the non-deterministic per-worker
  metrics-exposure finding. Dated evidence for the named candidate commit
  only; mocked-upstream qualification, not a real-provider run, release
  decision, security certification, or production approval.
- [`2026-09-17 current-main integrated requalification`](2026-09-17-current-main-integrated-requalification.md)
  - fresh RC-posture integrated requalification of `main`
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` (PR #305 merge; repeat of the
  abandoned Objective 169): two consecutive no-keep production-appliance
  harness runs `RESULT=OK` 16/16, full local unit/integration/E2E matrix
  (modulo the two labeled environment-only non-passes), and 9/9 required
  CI checks SUCCESS on the PR head. Verdict
  `RESULT=QUALIFIED-RC-POSTURE`. Dated evidence for the named candidate
  commit only; mocked-upstream qualification, not a real-provider run,
  release decision, security certification, or production approval.
- [`2026-09-17 OpenAI Python SDK 3.14.1 official-client compatibility requalification`](2026-09-17-openai-sdk-3141-requalification.md)
  - deliberate requalification of the declared official-client
  compatibility contract under the current stable SDK
  `openai==3.14.1` from the qualified baseline `openai==3.9.0`
  (`OUTCOME=A`): Phase B soundness 54/0/0, Phase C 54/0/0 on a
  single-variable dependency delta, ripple check green modulo the two
  labeled environment-only non-passes, and 9/9 CI checks SUCCESS on the
  PR head. Dated evidence for the named base commit and candidate SDK
  version only; mocked-upstream qualification, not a real-provider run,
  release decision, security certification, or production approval.
- [`2026-09-17 current-main integrated requalification (candidate 2b61312e)`](2026-09-17-current-main-integrated-requalification-2b61312e.md)
  - fresh RC-posture integrated requalification of `main`
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge; repeats the
  strict 170 acceptance set plus the new P0 runtime-tree identity proof):
  the exact 12-path candidate-to-candidate delta is dev-pin/documentation/
  OAP-record paths only and the runtime-surface diff is empty; two
  consecutive no-keep production-appliance harness runs `RESULT=OK` 16/16,
  full local unit/integration/E2E matrix (modulo the two labeled
  environment-only non-passes), and 9/9 required CI checks SUCCESS on the
  PR head. Verdict `RESULT=QUALIFIED-RC-POSTURE`. Dated evidence for the
  named candidate commit only; mocked-upstream qualification, not a
  real-provider run, release decision, security certification, or
  production approval.
- [`2026-09-20 release-candidate identity record (candidate db0bd3ae)`](2026-09-20-release-identity-db0bd3ae.md)
  - verification-only identity derivation binding the Objective-173
  full integrated qualification
  (`2b61312e0eb569aa7c6f953f52e35b44e84b91c1`,
  `RESULT=QUALIFIED-RC-POSTURE`) to exact `main`
  `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge): empty
  runtime/deployment/dependency-surface diff, every intervening path
  classified CI-only / release-metadata-SBOM / documentation-OAP,
  fresh 9/9 stable checks plus CodeQL suite rollup `success`, RC2 scope
  closure 27/0/21/3/0, and SBOM correspondence
  `SBOM_CHECK=OK components=60`. Verdict
  `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`. Dated evidence for the
  named candidate commit only; identity derivation, not a second full
  clean-room qualification, and not a release decision.

- [`2026-10-15 objective 185-a lazy (waiting) throttling verification`](lazy-throttling.md)
  - focused objective record for per-key lazy throttling (PR #323): 14
  real owned-PostgreSQL/owned-Redis integration cases, 24 helper/route unit
  cases, and 3 actual-browser cases with exact new-versus-inherited test
  mapping. Mocked-upstream provider evidence only; not a release decision,
  production approval, or broad-matrix claim.
- [`2026-10-16 objective 187-a operator branding verification`](operator-branding.md)
  - focused objective record for optional operator branding (PR #187):
  62 new/affected unit cases (reader FD I/O, PNG framing, render,
  config, compose contract, docs gates), 3 actual-browser cases against
  a real owned PostgreSQL, and 4 owned-container cases with the read-only
  branding mount; test-only container bootstrap, no provider/model/email
  access; final-head CI, strategic review, and guarded merge pending.
