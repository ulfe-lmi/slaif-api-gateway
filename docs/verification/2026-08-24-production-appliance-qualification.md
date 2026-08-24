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

## 151-e evidence review

The 151-d implementation repaired the product boundary, but its immutable
report was rejected as evidence closure for three reporting defects. The
recorded qualification project string omitted the final character of the
actual run's identifier, so the external cleanup audit used a truncated
label; the metrics assertion checked HELP/TYPE registration metadata rather
than requiring positive samples from each exercised family; and the
authenticated landing HTML was not included in the later privacy-body set.

Objective 151-e preserves the accepted 151-d behavior and closes only these
evidence-correlation defects. It remains disposable qualification evidence,
not a production certification, security certification, compliance claim, or
provider-invoice qualification.

## 151-f evidence review

Objective 151-e closed the positive-metrics and privacy-body implementation
gaps, but its first final-matrix attempt exposed that the Redis-concurrency
phase accepted a request ID without proving a live HTTP-200 stream, provider
forward, Redis slot, or pending PostgreSQL reservation. The run was then
rerun without repairing that synchronization defect. Its report also
truncated the project identifier used for the independent cleanup claim.

Objective 151-f makes the concurrency overlap evidence deterministic and
mechanically correlates the exact final project token through the report and
cleanup audit. It remains disposable qualification evidence, not a production
certification, release, provider-invoice qualification, or SLA claim.

## 151-g evidence review

The single 151-f run proved the deterministic Redis-concurrency boundary, but
then exposed the same request-ID-only prerequisite in the API-termination
phase. That phase could proceed to a ten-second PostgreSQL lookup without
proving that the captured request was an HTTP-200 live stream, had one provider
forward, held one Redis slot, and had its exact pending Responses reservation.
Objective 151-g strengthens only that qualification harness boundary. It keeps
the actual API-container interruption and documented CLI reconciliation proof,
adds bounded termination evidence, and requires one fresh no-keep run. A
failed fresh phase remains a failed qualification result; it is not converted
to a production certification, release, provider-invoice qualification, or SLA
claim.

## 151-i evidence review

Objective 151-h stopped before public-denial evidence because the installed
Compose CLI rejected the qualification probe's `--network` option. Its initial
loopback readiness observation passed, but that did not qualify the remaining
lifecycle or public boundary. Objective 151-i replaces only that incompatible
probe command with inspected raw Docker network operations and retains the
same one-fresh-run and exact-correlation requirements. It remains disposable
qualification evidence, not a production certification, release,
provider-invoice qualification, or SLA claim.

## 151-h evidence review

Objective 151-g passed the complete matrix and proved the active Responses
termination correlation, including the live HTTP-200 stream, provider forward,
Redis slot, pending PostgreSQL reservation, API interruption, and documented
CLI reconciliation. Strategic review rejected its public HTTPS `/healthz` plus
direct Redis ping as proof that the API process itself had current database
schema and Redis readiness, and found no assertion that the interrupted client
thread had terminated after the API container kill. Objective 151-h strengthens
only those qualification-harness evidence boundaries. It remains disposable
evidence, not a production certification, release, provider-invoice
qualification, or SLA claim.
