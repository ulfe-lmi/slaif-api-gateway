# Verification Evidence

This directory indexes durable verification records for specific repository
commits and execution environments. A record describes what one bounded run
actually proved; it is not permanent certification of later commits, production
fitness, security, compliance, provider behavior, or scale.

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
  - fresh RC-posture requalification of `main`
  `1043c3f42fb46f06a8d7952273739cefb9de6cc7` (PR #305 merge / Objective
  168): clean-room P1 freeze, two consecutive production-appliance
  harness runs — Run A `RESULT=OK` (16/16) and Run B `RESULT=FAIL`
  (phase 9 `redis-concurrency`, non-deterministic transient 503 on the
  following request, classified P2.3) — full local unit/integration/E2E
  matrix, and CI 9/9 SUCCESS on the candidate with the PR head's
  `Unit, lint, and migration head` FAILED on the candidate's brittle
  OAP governance test (P4.1). Verdict `RESULT=NOT-QUALIFIED` (AP-1
  requires two consecutive `RESULT=OK`; AP-3 requires nine PR-head
  checks `success`). Dated evidence for the named candidate commit
  only; mocked-upstream qualification, not a real-provider run, release
  decision, security certification, or production approval.
