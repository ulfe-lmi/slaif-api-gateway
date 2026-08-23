# OAP execution report — 141-a

Implementation head SHA: e32974f61c5af28b50fa4c3fcb6fcb204e59c64c
Report publication commit: SELF

## Scope

Resolved the worker/scheduler packaging inconsistency and performed the ordered
documentation truth pass:

- added optional `worker` and `scheduler` services to
  `docker-compose.production.yml` behind Compose profile `async`;
- default production remains API + PostgreSQL + Redis + Nginx only;
- documented that async reconciliation/email require `--profile async`;
- documented that CLI reconciliation remains available without async services;
- reconciled the compatibility matrix so Celery/Celery Beat are described as
  available in the optional production `async` profile;
- added objective 140 real-provider adapter qualification evidence to the
  compatibility matrix, replacing stale caveats that lacked immutable evidence.

No worker/scheduler was added unconditionally. No capability was overclaimed.
No code behavior outside deployment packaging changed.

## Verification

```text
docker compose -f docker-compose.production.yml config --quiet
# BASE_OK

docker compose -f docker-compose.production.yml --profile async config --quiet
# ASYNC_OK

git diff --check
# passed
```

All ten final-head GitHub checks were verified successful on implementation head
`e32974f61c5af28b50fa4c3fcb6fcb204e59c64c`.

The report is the sole file in this subsequent report-publication commit. No merge was performed.
