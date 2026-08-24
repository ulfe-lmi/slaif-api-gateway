# OAP Coding-Agent Report — 151-b

## Work order

- Identifier: `151-b`
- Work-order file: `oap/orders/151-b-production-qualification-proof-closure.md`
- Numeric objective: 151
- PR mode: `AMENDED_EXISTING_PR`

## Status

BLOCKED

## Executive summary

The existing PR #286 was amended with proof-harness repairs, production worker
egress/concurrency corrections, cleanup assertions, and a corrected
verification record. A fresh no-keep run passed every phase through
PostgreSQL persistence, including HTTPS Chat/Responses traffic, disconnects,
real Redis outage and concurrency controls, API termination/reconciliation,
worker/Beat liveness, and persistence. The run then invoked the documented
backup, restore, and verification scripts and failed at the repository's
PostgreSQL-incompatible `PRAGMA integrity_check` statement.

The run did not qualify the appliance. Later privacy, quota, dashboard, and
full privacy-scan phases were not run after the blocking failure. The
reconciled API-termination row also exposes `provider=unknown` and
`streaming=false`, so that accounting metadata is not sufficient for the
required interrupted-request proof.

## Authoritative GitHub state

- Repository: `ulfe-lmi/slaif-api-gateway`
- PR number: [#286](https://github.com/ulfe-lmi/slaif-api-gateway/pull/286)
- PR state at report time: OPEN
- Base branch: `main`
- Head branch: `oap/151-production-appliance-closure`
- Starting remote SHA: `00c591fbc51e486905575d01458032f081db554e`
- Implementation head SHA: `81506538c77384f4704a27f99a582292a257af4c`
- Report publication commit: SELF
- Remote PR head after report publication: SELF (literal SHA derived from GitHub)
- Implementation commits pushed before the report commit: `09c7a147`, `d64e7629`, `69d86260`, `05fd282f`, `81506538`
- Report commit first parent: same as Implementation head SHA
- Created a new PR this turn: no
- Amended existing PR this turn: yes
- Merge performed: NO

## Changes made

- Preserved diagnostic/request headers and correlated PostgreSQL reservation and ledger evidence by exact gateway request ID.
- Added Chat and Responses disconnect accounting, slow-stream Redis concurrency, API termination/restart plus documented CLI reconciliation, Redis outage snapshots, overrun controls, liveness checks, authenticated dashboard checks, privacy/canary checks, documented backup/restore invocation, and exact no-keep cleanup checks to the qualification harness.
- Added a dedicated concurrency key, bounded worker concurrency of one, and explicit worker egress networking.
- Added content-free provider-double completion/canary behavior.
- Corrected the stale 2026-08-24 verification document to remove the invalid 151-a success and `SELF` claims.
- Retained the exact interrupted request in final sanitized evidence when the client connection dies during API termination.

## Files changed

- `docker-compose.production.yml`
- `scripts/production-qualification/run.py`
- `scripts/production-qualification/provider_double.py`
- `scripts/production-qualification/qualification-compose.yml`
- `docs/verification/2026-08-24-production-appliance-qualification.md`
- `oap/orders/151-b-production-qualification-proof-closure.md` (strategic bytes committed unchanged)
- `oap/active` (strategic bytes committed unchanged)

## Acceptance-criteria evidence

### Fresh no-keep qualification

- Command: `.venv/bin/python scripts/production-qualification/run.py`
- Result: **FAIL**
- Project: `slaif-151-3605141-179932`
- Evidence log: `/tmp/slaif-151b-qualification-23.log`
- Passed phases: prepare, TLS, Compose, operator configuration, async worker and scheduler liveness, Chat and Responses, provider failures and disconnects, Redis and timeout controls, Redis concurrency, API termination and CLI reconciliation, persistence.
- Failed phase: `backup-restore`.
- Not reached after the blocking failure: privacy input boundaries, quota/key controls, authenticated dashboard session, and full privacy scan.

### Per-request accounting evidence captured before the blocker

The following rows are the sanitized final evidence for the 15 request IDs
that reached a terminal reservation/ledger state. All ordinary rows used the
configured `qualification-double/qualification-model` route; the persisted
schema does not expose an ordinary per-row route ID. `—` means the streaming
HTTP connection ended before a terminal HTTP status was available.

| Gateway request ID | Endpoint | Stream | HTTP | Ledger / reservation | Tokens | Actual / reserved EUR | Reserved tokens | Provider |
| --- | --- | :---: | :---: | --- | ---: | ---: | ---: | --- |
| `gw-78925d50-b566-4ca2-a09d-53056c283643` | Chat | no | 200 | finalized / finalized | 12 | 0.000019 / 0.000065 | 49 | qualification-double |
| `gw-fdf4d58b-055c-40fc-a0d4-c146c0760b35` | Chat | yes | 200 | finalized / finalized | 12 | 0.000019 / 0.000106 | 90 | qualification-double |
| `gw-602954f1-947a-43c2-86fc-17395886efad` | Responses | no | 200 | finalized / finalized | 12 | 0.000019 / 0.000047 | 31 | qualification-double |
| `gw-4daafdf0-8f71-45b1-9b66-f59a900e12a8` | Responses | yes | 200 | finalized / finalized | 12 | 0.000019 / 0.000047 | 31 | qualification-double |
| `gw-ec0b21c0-9f5d-413e-a384-437bfe66e0ed` | Chat | no | 503 | failed / released | 0 | 0 / 0.000065 | 49 | qualification-double |
| `gw-f635d1a8-aa16-411d-985f-9970dc64ad59` | Chat | no | — | failed / released | 0 | 0 / 0.000065 | 49 | qualification-double |
| `gw-a29e28f5-17dc-47a4-87ac-e0869a0e2b22` | Chat | yes | — | failed / released | 0 | 0 / 0.000106 | 90 | qualification-double |
| `gw-363ff203-7a40-4718-b351-1aa6f4bad551` | Chat | yes | — | estimated / finalized | 94 | 0.000114 / 0.000114 | 90 | qualification-double |
| `gw-8075d8e1-a6ee-4cb2-8c99-329b395d91a7` | Chat | yes | — | estimated / finalized | 94 | 0.000114 / 0.000114 | 90 | qualification-double |
| `gw-7f90d0b4-5a6d-4dc6-be24-ea607aa02359` | Responses | yes | — | failed / released | 0 | 0 / 0.000047 | 31 | qualification-double |
| `gw-950c2b83-8722-4c5e-869d-c154b53211d0` | Chat | no | — | failed / released | 0 | 0 / 0.000049 | 41 | qualification-double |
| `gw-3935778f-5905-4517-b48f-870ad961fb93` | Chat | no | 200 | finalized / finalized | 12 | 0.000019 / 0.000049 | 41 | qualification-double |
| `gw-df8164dd-b4c2-4752-8fd4-20fb7500d775` | Chat | yes | 200 | finalized / finalized | 12 | 0.000019 / 0.000106 | 90 | qualification-double |
| `gw-bfebad22-ad3f-4e47-872d-1362e4b22218` | Chat | no | 200 | finalized / finalized | 12 | 0.000019 / 0.000049 | 41 | qualification-double |
| `gw-ca171d8d-1e1e-463e-b122-958145fb6c4d` | Responses | ledger row after API kill | — | failed / expired | 0 | 0 / 0.000047 | 31 | unknown |

The Chat client-abort request is `gw-8075d8e1-a6ee-4cb2-8c99-329b395d91a7`;
the Responses client-abort request is
`gw-7f90d0b4-5a6d-4dc6-be24-ea607aa02359`. The API-termination request is
`gw-ca171d8d-1e1e-463e-b122-958145fb6c4d`; its reservation was observed
pending before API termination, then deterministically expired and reconciled
through the documented CLI path with an objective-151 audit entry and zero
reserved key counters. Its final ledger metadata is the limitation noted
above.

### Redis and concurrency boundaries

- Redis outage: PASS in the run. The harness compared PostgreSQL reservation count, pending reservation count, ledger count, pending ledger count, and primary-key reserved counters before and after the denied request; the snapshot was unchanged and the provider-double request count did not increase.
- Redis concurrency: PASS in the run. The slow stream was `gw-df8164dd-b4c2-4752-8fd4-20fb7500d775`; the overlapping request was rejected by the real Redis-backed limit, and `gw-bfebad22-ad3f-4e47-872d-1362e4b22218` succeeded after release.

### Backup/restore blocker

- `scripts/backup.sh`: invoked against disposable PostgreSQL state.
- `scripts/restore.sh`: invoked against a disposable restore database.
- `scripts/verify_restore.py`: invoked and failed.
- Bounded error excerpt:

  ```text
  asyncpg.exceptions.PostgresSyntaxError: syntax error at or near "PRAGMA"
  [SQL: PRAGMA integrity_check]
  ```

  The statement is SQLite-only, while the verifier uses SQLAlchemy's
  PostgreSQL `asyncpg` dialect. `scripts/verify_restore.py` is outside the
  151-b allowed paths and was not modified.

### Cleanup and safety

- Automatic no-keep cleanup: PASS — `containers_by_compose_label=true`, `networks=true`, `volumes=true`, `runtime=true`, with no remaining project networks or volumes.
- Independent post-exit check: PASS — no containers, networks, volumes, or `.qualification-runtime-slaif-151-3605141-179932` remained.
- Provider: isolated local socket double only.
- Real upstream calls: no.
- Real email: no.
- Production/staging systems or credentials: no.
- Secrets/canaries: runner redacted generated values from logs and report output; no secret values were committed.

## Local verification

- `git diff --check`: PASSED
- `.venv/bin/ruff check scripts/production-qualification/run.py scripts/production-qualification/provider_double.py`: PASSED
- `.venv/bin/pytest tests/unit/test_production_compose_contract.py -q`: PASSED — 3 passed
- `.venv/bin/python scripts/verify_production_compose.py`: PASSED — `RESULT=OK static=true compose=false`
- `sudo -n docker compose -f docker-compose.production.yml config --quiet`: PASSED
- `.venv/bin/python scripts/production-qualification/run.py`: FAILED at documented restore verification as described above
- Independent exact absence checks: PASSED
- Broader focused existing tests for application accounting/reconciliation/backup verifier: NOT RUN after the active order's out-of-scope verifier defect stopped the qualification; no application code was changed.

## GitHub CI / required checks

Observed for implementation head `81506538c77384f4704a27f99a582292a257af4c`:

- `Unit, lint, and migration head`: IN_PROGRESS
- `Analyze (javascript-typescript)`: IN_PROGRESS
- `Analyze Python`: IN_PROGRESS
- `Analyze (python)`: IN_PROGRESS
- `PostgreSQL integration tests`: QUEUED
- `OpenAI-compatible E2E tests`: QUEUED
- `Playwright browser smoke`: IN_PROGRESS
- `Docker Compose smoke`: IN_PROGRESS
- `Documentation hygiene`: QUEUED

All required checks green for the implementation head at report drafting: **no**.
The report-only commit may trigger fresh checks; the strategic model must verify
the `SELF` commit without rewriting this report.

## Documentation

`docs/verification/2026-08-24-production-appliance-qualification.md` now
marks the 151-a record superseded and records the fresh blocked no-keep run.
It does not claim qualification or OAP `SELF` publication. Documentation
impact: the stale verification record was corrected to match the actual
151-b evidence and preserve the RC-beta/non-certification boundary.

## Safety and scope confirmations

- Unrelated files changed: no.
- Production secrets accessed: no.
- Production systems accessed: no.
- Required tests skipped/not run: yes — the qualification stopped at the documented verifier defect; later privacy/quota/dashboard phases and broader focused tests were not run in the final attempt.
- Scope deviation: no. The verifier defect and interrupted-ledger metadata are reported; no out-of-scope file was modified.
- Extra PR created for same numeric objective: NO
- PR merged by coding agent: NO
- Activated order and `oap/active` edited by coding agent: NO; committed unchanged.
- Report-publication commit changes only this report file: yes, required for the next commit.

## Known limitations / blockers

1. `scripts/verify_restore.py:40` executes `PRAGMA integrity_check` against PostgreSQL. This is outside 151-b's allowed path set and blocks the required documented restore proof.
2. The reconciled API-termination ledger row lacks authoritative provider and streaming metadata (`unknown`/`false`), so interrupted-request accounting is not fully proven.
3. Final privacy, quota-overrun, dashboard, and full privacy-scan phases were not reached in the final run.
4. GitHub checks were not complete at report drafting.

## Recommended strategic follow-up

Activate a 151-c continuation for the narrow restore-verifier repair and the
interrupted-request accounting metadata decision/fix, then rerun one fresh
no-keep qualification from the amended PR. The coding agent does not decide
whether those changes are accepted or whether PR #286 is merged.
