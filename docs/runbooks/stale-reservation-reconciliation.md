# Stale Reservation Reconciliation

## What Stale Pending Reservations Are

A stale reservation is a `quota_reservations` row that remains `pending` after
its expiry time, usually because the process crashed or was interrupted before
normal finalization or release completed.

## Why They Matter

Pending reservations keep reserved request, token, and cost counters on the
gateway key. If stale reservations are not reconciled, a key may appear to have
less remaining quota than it should.

## Detection

Manual inspection:

```bash
docker compose run --rm api slaif-gateway quota list-expired-reservations --limit 100 --json
```

Scheduled inspection can be enabled with `ENABLE_SCHEDULED_RECONCILIATION=true`.
The scheduled task is dry-run/reporting by default. Metrics and optional generic
webhook alerts can report backlog counts when configured.

## Dry Run

```bash
docker compose run --rm api slaif-gateway quota reconcile-expired-reservations \
  --limit 100 \
  --dry-run \
  --json
```

For one reservation:

```bash
docker compose run --rm api slaif-gateway quota reconcile-reservation \
  <reservation-uuid> \
  --dry-run \
  --json
```

## Execute

```bash
docker compose run --rm api slaif-gateway quota reconcile-expired-reservations \
  --limit 100 \
  --execute \
  --reason "expired reservation reconciliation" \
  --json
```

For one reservation:

```bash
docker compose run --rm api slaif-gateway quota reconcile-reservation \
  <reservation-uuid> \
  --execute \
  --reason "expired reservation reconciliation" \
  --json
```

## Expected Effects

- Reserved counters are decremented on the gateway key.
- The reservation is marked `expired`.
- A safe failed ledger row is created if no ledger row exists.
- An audit row is written.

Provider-completed finalization-failed rows must not be repaired through stale
reservation reconciliation as zero-cost failures. Use the provider-completed
runbook for those rows.

## Safety

- No provider calls are made.
- Prompt and completion content is not stored.
- Reconciliation uses service-layer logic covered by idempotency and invariant
  tests.

## Rollback Considerations

There is no general automatic rollback for executed reconciliation. Review the
dry-run output first. If an operator reconciles the wrong reservation, preserve
the audit trail and decide whether a manual quota adjustment or new key is
appropriate.

## Verification Checklist

- Re-run `list-expired-reservations`.
- Check key safe metadata:

  ```bash
  docker compose run --rm api slaif-gateway keys show <gateway-key-uuid> --json
  ```

- Review `/admin/audit` for the reconciliation action.
