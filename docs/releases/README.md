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
  checks and standard PR CI evaluate the corrected candidate separately.
