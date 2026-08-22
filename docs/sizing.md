# SME sizing guidance

| Profile | Concurrency | Minimum resources | PostgreSQL pool guidance | Redis |
|---|---:|---|---|---|
| Workshop burst | 10 users | 2 vCPU / 4 GB RAM / 1 API worker | pool_size 10, max_overflow 5 | 256 MB |
| SME daily | 50 employees | 4 vCPU / 8 GB RAM / 2 API workers | pool_size 20, max_overflow 10 | 512 MB |
| Codex loop | sequential tool calls | 2 vCPU / 2 GB RAM / 1 worker | pool_size 5 | 128 MB |

Concurrency must never bypass PostgreSQL `FOR UPDATE` accounting or external-tool
fences. These figures are operational starting points, not SLAs or maximums.
