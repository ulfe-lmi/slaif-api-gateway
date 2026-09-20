# Release Notes

Release notes for tagged SLAIF API Gateway release candidates and releases.

- [`v0.1.0-rc.1`](v0.1.0-rc.1.md)

## Verification evidence

- [`2026-08-17 current-main baseline`](../verification/2026-08-17-current-main-baseline.md)
  — `RESULT=FAIL` from one full 24-worker current-machine matrix; this is
  evidence for a specific commit/environment, not a release, tag decision,
  production certification, or completed 128-worker HPC qualification. Focused
  OAP continuation `001-b` repairs the brittle governance assertion without a
  second harness run; the original run remains failed history, while focused
  checks and standard PR CI evaluate the corrected candidate separately. Later
  GitHub evidence shows PR #226 report head
  `24431512a993df81f15de4e0268c40ad61e0ad57` completed all ten final-head
  checks successfully and PR #226 merged as
  `adaefdc45ddd13e172955c14e02cb6c97d49b629`; this does not change the original
  `RESULT=FAIL` classification or the still-NOT-RUN 128-worker qualification.
- [`2026-08-24 production-appliance qualification`](../verification/2026-08-24-production-appliance-qualification.md)
  — later disposable production-path evidence. It does not create a release,
  update the historical `v0.1.0-rc.1` tag, or certify production use.
- [`2026-09-17 current-main integrated requalification (candidate 2b61312e)`](../verification/2026-09-17-current-main-integrated-requalification-2b61312e.md)
  — mocked-upstream integrated RC-posture requalification of `main`
  `2b61312e0eb569aa7c6f953f52e35b44e84b91c1` (PR #309 merge), verdict
  `RESULT=QUALIFIED-RC-POSTURE`. It does not create a release, tag, or
  production certification.
- [`2026-09-20 release-candidate identity record (candidate db0bd3ae)`](../verification/2026-09-20-release-identity-db0bd3ae.md)
  — identity derivation binding the Objective-173 qualification to exact
  `main` `db0bd3aeaaadee71ba40a16ee0dddf7a35e0a4b7` (PR #313 merge), verdict
  `RESULT=QUALIFIED-RC-POSTURE-BY-IDENTITY`. Identity derivation only; not a
  second full clean-room qualification, release decision, or production
  certification.
