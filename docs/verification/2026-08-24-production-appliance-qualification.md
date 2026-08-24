# Objective 151 production-appliance qualification

Date: 2026-08-24 (Europe/Ljubljana)

Status: **COMPLETE — disposable qualification passed; no production-certification claim**

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

Project: `slaif-151-3781840-2fba2a`

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
source snapshot. The interrupted streamed request reconciled with the saved
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
