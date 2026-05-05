# Redis Outage And Rate-Limit Degradation

## Redis Role

Redis stores temporary operational state:

- request and estimated-token rate-limit counters;
- active concurrency slots for supported `/v1` traffic;
- Celery broker state when `CELERY_BROKER_URL` or `REDIS_URL` points at Redis.

PostgreSQL hard quota and accounting remain authoritative.

## Failure Policy

`RATE_LIMIT_FAIL_CLOSED` controls Redis failure behavior for rate limiting. When
unset, production fails closed and development/test fails open. The checked-in
`.env.example` sets `RATE_LIMIT_FAIL_CLOSED=false` for local development.

Choose fail-open or fail-closed deliberately:

- fail-closed protects upstream spend but can reject valid traffic;
- fail-open preserves availability but removes Redis operational throttles.

## Symptoms

- `/readyz` reports Redis not ok when Redis rate limits are enabled.
- `/v1/chat/completions` returns rate-limit unavailable errors in fail-closed
  mode.
- Celery worker or scheduler cannot connect to broker.
- Streaming concurrency slots stop heartbeating or releasing until TTL cleanup.

## Immediate Actions

1. Check readiness:

   ```bash
   curl -fsS http://localhost:8000/readyz
   ```

2. Inspect Redis:

   ```bash
   docker compose ps redis
   docker compose logs redis
   ```

3. Restart Redis if appropriate:

   ```bash
   docker compose up -d redis
   ```

4. Restart workers if Celery broker connections did not recover:

   ```bash
   docker compose up -d worker scheduler
   ```

5. Change `RATE_LIMIT_FAIL_CLOSED` only through a deliberate incident decision
   and restart API workers afterward.

## Effects On Streaming Concurrency

Active stream slots are heartbeated while streams are open and released during
cleanup. If Redis is unavailable, concurrency enforcement is degraded according
to fail-open/fail-closed policy. Existing durable PostgreSQL quota reservations
are not stored in Redis and are not repaired by resetting Redis.

## Verification

- `/readyz` is healthy.
- A controlled rate-limit smoke behaves as expected.
- Worker and scheduler logs show broker connectivity.
- Reconciliation backlog is normal.

## Do Not

- Do not reset PostgreSQL quota counters to fix a Redis outage.
- Do not delete usage ledger rows.
- Do not treat Redis rate-limit counters as authoritative usage data.
