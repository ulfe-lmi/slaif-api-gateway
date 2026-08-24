# Objective 151 production-appliance qualification

Date: 2026-08-24 (Europe/Ljubljana)

Status: **BLOCKED — no production-appliance qualification claim**

This document supersedes the earlier 151-a verification text. The earlier
`--keep` run and its `91ebb924`/`00c591f` references were not valid final
qualification evidence: they did not prove the required boundaries and this
document is not an OAP report. It must not claim `Report publication commit:
SELF`.

The fresh 151-b no-keep run reached the repository's documented restore
verifier and exposed a pre-existing out-of-scope defect. Therefore the run did
not qualify the appliance, and no RC-beta production certification, security,
compliance, SLA, or provider-invoice claim follows.

## Fresh run evidence

Command:

```text
.venv/bin/python scripts/production-qualification/run.py
```

Project: `slaif-151-3575828-b9f8a9`

| Phase | Result |
| --- | --- |
| prepare | OK |
| TLS generation | OK |
| Compose config/build/start and health | OK |
| CLI operator/provider/route/pricing/key setup | OK |
| async worker and scheduler liveness | OK |
| Chat and Responses normal/streaming | OK |
| provider failures and disconnects | OK |
| Redis and timeout controls | OK |
| Redis concurrency | OK |
| API termination and CLI reconciliation | OK |
| PostgreSQL persistence | OK |
| documented backup/restore/verification | **FAIL** |
| later privacy/quota/dashboard phases | NOT RUN after blocking failure |

The run's automatic no-keep cleanup passed all independent checks:

```text
containers_by_compose_label=true
networks=true
volumes=true
runtime=true
```

## Blocking defect

The harness successfully invoked the repository's `scripts/backup.sh` and
`scripts/restore.sh` against disposable PostgreSQL state, then invoked
`scripts/verify_restore.py`. The verifier executes the SQLite-only statement
`PRAGMA integrity_check` through the PostgreSQL `asyncpg` dialect at line 40,
which fails with:

```text
asyncpg.exceptions.PostgresSyntaxError: syntax error at or near "PRAGMA"
[SQL: PRAGMA integrity_check]
```

`scripts/verify_restore.py` is outside the 151-b allowed-path set. It was not
modified. A 151-c continuation is required to repair or replace that verifier
before a fresh no-keep qualification can proceed beyond this boundary.

The run used only the isolated provider double, no real provider credentials,
no real email, no production/staging database, and no production systems.
