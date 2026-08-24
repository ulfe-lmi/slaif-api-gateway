# OAP report — 151-c restore and interrupted-accounting closure

Objective: `151-c-restore-and-interrupted-accounting-closure`
PR: `#286`
Branch: `oap/151-production-appliance-closure`
Base: `main @ ce0cf95685796477685a3aab6edacb39def6c27b`
Starting remote head: `7f4bd49c5c4d4dbc0324ec5dea25486dae425611`
Implementation head: `bab4be5c99b5329870615f734744849923253214`
Migration head: `0024_quota_reservation_accounting_facts`
Report publication commit: SELF

Status: **COMPLETE — disposable qualification passed; no production-certification claim**

## Required final qualification

Exact command:

```text
.venv/bin/python scripts/production-qualification/run.py
```

Final no-keep project: `slaif-151-3878414-96a729`
Final result: `RESULT=OK`

All sixteen phases passed in one fresh invocation:

| Phase | Result |
| --- | --- |
| prepare | OK |
| tls | OK |
| compose | OK |
| operator-configuration | OK |
| async-worker-and-scheduler-liveness | OK |
| chat-and-responses | OK |
| provider-failures-and-disconnects | OK |
| redis-and-timeout-controls | OK |
| redis-concurrency | OK |
| api-termination-and-cli-reconciliation | OK |
| persistence | OK |
| backup-restore | OK |
| privacy-input-boundaries | OK |
| quota-and-key-controls | OK |
| admin-dashboard-session | OK |
| privacy | OK |

## Restore and accounting evidence

The documented backup and restore scripts were used against disposable
PostgreSQL state. The PostgreSQL-native verifier returned `RESULT=OK` and
bounded counts matched exactly:

```text
source:   gateway_keys=2 usage_ledger=15
restored: gateway_keys=2 usage_ledger=15
```

The `0024` reservation snapshot fields are nullable for legacy truth and are
populated for newly created ordinary reservations. Sanitized final evidence
included these representative rows:

| Surface | Ledger status | Reservation status | Provider / resolved model | Streaming | Total tokens |
| --- | --- | --- | --- | --- | ---: |
| Chat ordinary | finalized | finalized | qualification-double / qualification-model | false | 12 |
| Chat streaming | finalized | finalized | qualification-double / qualification-model | true | 12 |
| Responses ordinary | finalized | finalized | qualification-double / qualification-model | false | 12 |
| Responses interrupted by API termination | failed | expired | qualification-double / qualification-model | true | 0 |
| Bounded admitted overrun | finalized | finalized | qualification-double / qualification-model | false | 32 |

The interrupted row retained `success=false`, zero actual usage/cost, the
persisted provider/resolved-model/streaming facts, expired-reservation audit
identity, and repaired PostgreSQL reservation counters. Legacy fallback remains
explicitly marked rather than inferred from mutable route state. External-tool
fence reservations remained excluded from ordinary stale reconciliation.

The quota phase admitted the bounded overrun with a 20-token reservation and a
24-token remaining cap, then finalized the provider double's authoritative
32-token result. The immediately following request was denied before provider
forwarding. Token, cost, request, expiry, and revocation denials each captured
their own provider-call baseline; expiry was restored to a valid future window
before the real CLI revocation test, so revocation was independently proven.

## Dashboard, privacy, and cleanup

The authenticated dashboard session passed, including `/admin/usage` and
`/admin/audit`. The production metrics endpoint correctly returned the bounded
default `403` denial, and the privacy scan found no generated canary, gateway
key, provider secret, prompt, completion, URL credential, or plaintext copied
secret in logs, metrics, provider state, dashboard bodies, or inspected
database text.

Automatic and independent no-keep cleanup both passed:

```text
containers_by_compose_label=true
networks=true
remaining_networks=[]
volumes=true
remaining_volumes=[]
runtime=true
remaining runtime dump/key/log/secret files: absent
```

The run used only generated credentials, disposable PostgreSQL/Redis state,
the local qualification provider double, and disabled email delivery. No real
OpenAI/OpenRouter request, production/staging database, real email, or
production system was used.

## Verification and remote checks

Local focused checks included:

```text
env -u OPENAI_API_KEY -u OPENROUTER_API_KEY scripts/test-unit-parallel.sh
3448 passed, 49 warnings
.venv/bin/ruff check <changed Python files>
All checks passed
.venv/bin/python scripts/verify_production_compose.py
RESULT=OK static=true compose=false
.venv/bin/alembic heads
0024_quota_reservation_accounting_facts (head)
sudo -n docker compose -f docker-compose.production.yml config --quiet
passed
git diff --check
passed
```

GitHub PR #286 at implementation head reported success for all ten checks:
Unit/lint/migration, PostgreSQL integration, OpenAI-compatible E2E, Playwright
browser smoke, Docker Compose smoke, Documentation hygiene, CodeQL,
JavaScript/TypeScript analysis, Python analysis, and Analyze Python.

## Changed paths in this objective

Relative to the 151-b report head, the objective changed:

```text
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/quota.py
app/slaif_gateway/services/quota_service.py
app/slaif_gateway/services/reservation_reconciliation.py
docs/database-schema.md
docs/security-model.md
docs/verification/2026-08-24-production-appliance-qualification.md
migrations/versions/0024_quota_reservation_accounting_facts.py
oap/active
oap/orders/151-c-restore-and-interrupted-accounting-closure.md
scripts/production-qualification/provider_double.py
scripts/production-qualification/run.py
scripts/verify_restore.py
tests/integration/test_gateway_key_prefix_migration_postgres.py
tests/integration/test_reservation_reconciliation_postgres.py
tests/unit/test_alembic_accounting.py
tests/unit/test_alembic_email_jobs.py
tests/unit/test_alembic_external_tool_fence.py
tests/unit/test_alembic_key_prefix_default.py
tests/unit/test_alembic_provider_pricing.py
tests/unit/test_quota_accounting_invariants.py
tests/unit/test_quota_service.py
tests/unit/test_reservation_reconciliation_service.py
tests/unit/test_schema_status.py
tests/unit/test_verify_restore.py
```

The migration-head and quota-invariant fixture updates are direct regression
fixtures required by the full repository CI suite after adding `0024` and the
three reservation snapshot arguments. No endpoint matrix, provider adapter,
pricing, external-tool behavior, dependency, workflow, release, or production
claim was changed.

This report is immutable after publication. The coding agent does not merge
the PR.
