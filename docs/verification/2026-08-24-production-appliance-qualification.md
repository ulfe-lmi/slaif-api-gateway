# Objective 151 production-appliance qualification

Date: 2026-08-24 (Europe/Ljubljana)

Status: **HISTORICAL — the apparent 151-c pass was rejected by 151-d boundary review**

This document records the fresh 151-c no-keep qualification after the restore
verifier and interrupted-accounting repairs. It is qualification evidence for
the RC-beta appliance surface only. It does not certify production readiness,
security, compliance, SLA performance, provider-invoice accuracy, or any real
upstream deployment.

The earlier 151-b run remains historical evidence: it reached restore
verification but failed because the verifier sent SQLite `PRAGMA
integrity_check` through PostgreSQL. The 151-c run repaired that defect and
also proved that interrupted ordinary reservations retain provider, resolved
model, and streaming facts. The prior report was not rewritten.

## Fresh run evidence

Command:

```text
.venv/bin/python scripts/production-qualification/run.py
```

Project: `slaif-151-3878414-96a729`

Result: `RESULT=OK`

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
| documented backup/restore/verification | OK |
| privacy input boundaries | OK |
| quota and key controls | OK |
| admin dashboard session | OK |
| privacy | OK |

The run used disposable PostgreSQL state, the isolated qualification provider
double, generated credentials and canaries, and disabled email delivery. The
restore verifier emitted bounded table counts and those counts matched the
source snapshot exactly: `gateway_keys=2` and `usage_ledger=15` in both the
source and restored databases. The interrupted streamed request reconciled with the saved
`qualification-double` provider, `qualification-model` resolved model, and
`streaming=true` reservation facts.

The quota phase admitted one bounded request with a 24-token remaining cap,
received 32 authoritative provider-reported tokens, finalized that usage, and
verified that the next request was denied before provider forwarding. Expiry,
revocation, token, cost, and request denials were each checked against their
own provider-request baseline. The privacy phase also confirmed the expected
production metrics denial (`403`) without exposing generated values.

Automatic no-keep cleanup passed all independent checks:

```text
containers_by_compose_label=true
networks=true
remaining_networks=[]
volumes=true
remaining_volumes=[]
runtime=true
```

No real OpenAI/OpenRouter request, real email delivery, production/staging
database, or production system was used.

## 151-d boundary review

The 151-c result above remains immutable historical evidence, but it is not
accepted as production-appliance closure. Its qualification boundaries were
too weak in four material ways:

- the dashboard phase disabled redirect handling and accepted the intermediate
  `303`, so it did not prove that a normal HTTPS client could follow login to
  the exact `/admin` landing page through Nginx;
- the privacy phase treated an unallowlisted `403` response body as metrics
  evidence instead of reading the real Prometheus exposition through an
  explicitly authorized in-container loopback path;
- the restore verifier accepted deceptive database names containing a safe
  substring, checked table existence without fixing the `public` schema, and
  did not execute a read-only query against every required table;
- the 151-c test/fixture scope exceeded its exact change boundary and lacked a
  focused upgrade/downgrade contract for migration `0024`.

Objective 151-d repairs these boundaries and records the fresh no-keep result
in its immutable report. It does not convert this historical 151-c record into
a production certification, security certification, compliance claim, or
provider-invoice qualification.
