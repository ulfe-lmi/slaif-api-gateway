# PostgreSQL Pool Exhaustion And Readiness Failure

## Symptoms

- `/readyz` reports database or schema not ok.
- Logs show pool timeout, connection timeout, statement timeout, or slow query
  errors.
- Admin pages or `/v1` requests stall while waiting for a database connection.
- Migrations or `slaif-gateway db current` fail.

## Relevant Environment Variables

- `DATABASE_URL`
- `DATABASE_POOL_SIZE`
- `DATABASE_MAX_OVERFLOW`
- `DATABASE_POOL_TIMEOUT_SECONDS`
- `DATABASE_POOL_RECYCLE_SECONDS`
- `DATABASE_POOL_PRE_PING`
- `DATABASE_CONNECT_TIMEOUT_SECONDS`
- `DATABASE_STATEMENT_TIMEOUT_MS`

## Immediate Diagnostics

```bash
curl -fsS http://localhost:8000/readyz
docker compose ps postgres api worker scheduler
docker compose logs api
docker compose logs postgres
```

Inspect database activity with an operator-approved account:

```bash
docker compose exec -T postgres psql -U slaif -d slaif_gateway \
  -c "select pid, state, wait_event_type, wait_event, now() - query_start as age from pg_stat_activity order by query_start nulls last limit 20;"
```

## Mitigation

- Restart API workers if the pool is wedged:

  ```bash
  docker compose up -d api
  ```

- Restart worker/scheduler if background jobs are exhausting connections:

  ```bash
  docker compose up -d worker scheduler
  ```

- Increase `DATABASE_POOL_SIZE` or `DATABASE_MAX_OVERFLOW` cautiously only after
  checking PostgreSQL `max_connections` and total processes.
- Investigate long-running transactions and slow queries before raising pool
  limits.
- Set or tune `DATABASE_STATEMENT_TIMEOUT_MS` carefully if runaway statements
  are a recurring problem.
- Avoid running concurrent destructive integration tests against the same
  database. Use `TEST_DATABASE_URL` for tests.

## Migration And Schema Checks

```bash
docker compose run --rm api slaif-gateway db current
alembic heads
```

Run `slaif-gateway db upgrade` only as an explicit migration step after backup
and release review.

## Before Risky DB Work

Take a backup or confirm a recent managed backup exists before terminating
sessions, changing pool settings, altering schema, or restoring data.
