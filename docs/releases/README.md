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
