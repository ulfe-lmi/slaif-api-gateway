# Verification Evidence

This directory indexes durable verification records for specific repository
commits and execution environments. A record describes what one bounded run
actually proved; it is not permanent certification of later commits, production
fitness, security, compliance, provider behavior, or scale.

- [`2026-08-17 current-main baseline`](2026-08-17-current-main-baseline.md) —
  one 24-worker full current-machine matrix, classified `RESULT=FAIL` because
  one of 2,534 tests failed. The separate post-PR-220 128-worker HPC
  qualification remains not run.
