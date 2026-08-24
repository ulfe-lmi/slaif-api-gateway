# SME sizing guidance

> **Status:** Unbenchmarked starting points, not capacity guarantees
> **Authority:** PostgreSQL and Redis configuration details live in
> [configuration](configuration.md)

| Illustrative profile | Concurrent activity | Starting resources | PostgreSQL pool starting point | Redis |
|---|---:|---|---|---|
| Workshop burst | About 10 active users | 2 vCPU / 4 GB RAM / 1 API worker | pool size 10, overflow 5 | 256 MB |
| SME daily use | About 50 employees | 4 vCPU / 8 GB RAM / 2 API workers | pool size 20, overflow 10 | 512 MB |
| Sequential agent loop | One sequential tool loop | 2 vCPU / 2 GB RAM / 1 API worker | pool size 5, no assumed overflow | 128 MB |

These figures are planning hypotheses. They have not been established as
throughput, latency, maximum-user, or availability claims by a published load
benchmark. Provider latency, streaming duration, request shape, database
storage, worker/scheduler use, and reconciliation backlog can dominate capacity.

Before rollout, measure the actual workload and watch API latency/error rate,
PostgreSQL pool pressure, Redis availability, pending reservations, unresolved
holds, and host saturation. Increase workers only with enough PostgreSQL
connections and after exercising concurrent accounting. Concurrency must not
bypass PostgreSQL `FOR UPDATE` accounting or external-tool fences.

See [observability](observability.md) for the metrics that are actually wired
and [production deployment](deployment-production.md) for topology. No value on
this page is an SLA or a substitute for workload testing.
