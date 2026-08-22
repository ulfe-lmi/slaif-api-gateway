# OAP Work Order — 132-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/132-scaling-performance-concurrency-qualification`
Base: main @ cf94f47a1e4b

## Objective and reason

Prove the gateway can enforce policy/accounting under realistic concurrent SME
and Codex workloads. Define workload profiles, load-test API/workers/PostgreSQL/
Redis, and document sizing guidance.

## Verified state

- main = cf94f47a1e4b; no open non-Dependabot PR.
- Objectives 118–131 merged. Phase 5 underway.

## Scope

1. Workload profiles:
   - Workshop bursts (10 concurrent users).
   - SME daily load (50 employees, mixed chat/responses/Codex).
   - Codex loops (sequential tool calls with streaming).
2. Load tests:
   - API throughput and latency under each profile.
   - PostgreSQL connection pool behavior under concurrent reservations.
   - Redis rate limiting accuracy under burst.
3. Sizing documentation:
   - Resource requirements per organization size.
   - Safe concurrency limits per deployment profile.

## Exact requirements

1. Target workload profiles meet documented latency/error/accounting correctness thresholds.
2. Concurrency cannot overspend or bypass external-tool fences.
3. Capacity guidance maps organization size to resources.

## Allowed paths

```
tests/load/
docs/sizing.md
oap/orders/132-a-scaling-performance-concurrency-qualification.md
oap/reports/132-a-scaling-performance-concurrency-qualification.md
oap/active
```

## Non-goals

No internet-scale or multi-region claims. No disabling locks/tests for throughput.

## Observable acceptance

- Load tests complete without accounting errors under all profiles.
- Sizing documentation maps org size → resources.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/load/
git diff --check
```

## OAP contract

Objective 132-a creates one PR; remediation uses 132-b–z same PR.
Coding agent never merges.
