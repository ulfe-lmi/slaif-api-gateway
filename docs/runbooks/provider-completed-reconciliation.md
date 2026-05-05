# Provider-Completed Finalization Recovery

## What It Means

`provider_completed_finalization_failed` means the provider returned final usage
and the client may have received streamed content, but the gateway failed while
finalizing PostgreSQL quota/accounting. This is not a zero-cost provider
failure.

## Why It Matters

The provider-completed row contains stored usage and cost metadata needed to
finalize accounting. Releasing it as a failed provider request would undercharge
the key and break quota integrity.

## List Recovery Rows

```bash
docker compose run --rm api slaif-gateway quota list-provider-completed-recovery \
  --limit 100 \
  --json
```

Optional filters:

```bash
docker compose run --rm api slaif-gateway quota list-provider-completed-recovery \
  --provider openai \
  --model gpt-test-mini \
  --json
```

## Dry Run

Batch dry-run:

```bash
docker compose run --rm api slaif-gateway quota reconcile-provider-completed \
  --limit 100 \
  --dry-run \
  --json
```

Single row dry-run:

```bash
docker compose run --rm api slaif-gateway quota reconcile-provider-completed \
  --usage-ledger-id <usage-ledger-uuid> \
  --dry-run \
  --json
```

## Execute

```bash
docker compose run --rm api slaif-gateway quota reconcile-provider-completed \
  --usage-ledger-id <usage-ledger-uuid> \
  --execute \
  --reason "provider-completed finalization recovery" \
  --json
```

Batch execution is also available with `--limit`, but review the dry-run output
first.

## Expected Effects

- The existing usage ledger row is finalized.
- Reserved counters are moved to used counters.
- The recovery marker is cleared.
- The quota reservation is finalized.
- An audit row is written.
- No duplicate ledger row is created.

## Safety

- No provider calls are made.
- The repair uses stored usage and cost metadata.
- Missing or non-positive usage/cost metadata fails closed.
- The service validates gateway key, reservation, and ledger consistency before
  mutation.

## Verification Checklist

- Re-run `list-provider-completed-recovery`.
- Check the key counters through `keys show`.
- Review `/admin/usage` for the finalized request.
- Review `/admin/audit` for `provider_completed_reconciliation`.

## Scheduled Task Behavior

Scheduled reconciliation is disabled by default. With
`ENABLE_SCHEDULED_RECONCILIATION=true`, Celery Beat inspects backlog safely.
Automatic provider-completed mutation requires
`RECONCILIATION_AUTO_EXECUTE_PROVIDER_COMPLETED=true` and
`RECONCILIATION_DRY_RUN=false`.
