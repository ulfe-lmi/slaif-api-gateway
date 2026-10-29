# Ambiguous Email Delivery Handling

> **Status:** Current operator runbook
> **Safety:** Never resend an ambiguous one-time secret; rotate when receipt is uncertain

## States

Key email delivery rows may be `pending`, `sending`, `sent`, `failed`,
`ambiguous`, or `cancelled`.

- `pending`: a one-time secret exists and delivery has not started.
- `sending`: SMTP delivery has started or was prepared.
- `failed`: SMTP failed before acceptance; the secret may still be retryable.
- `ambiguous`: SMTP may have accepted the email, but database finalization did
  not complete.

## SMTP Success Plus DB Finalization Failure

Email is not mathematically exactly-once. The gateway records `sending` before
SMTP and consumes the one-time secret only after SMTP success. If SMTP may have
accepted the message but the database update fails, the row is marked
`ambiguous` and automatic retry is blocked to avoid duplicate key emails.

## Inspection

Use `/admin/email-deliveries` to filter delivery rows and
`/admin/email-deliveries/<email-delivery-uuid>` to inspect one row. The page
shows safe metadata only and does not render email bodies or plaintext keys.

The CLI exposes the same bounded metadata for operators who must not use
database queries. Both commands are READ-ONLY (no decrypt, render, send,
consume, audit insertion, or enqueue) and report allowlisted fields only:

```bash
docker compose run --rm api slaif-gateway email list \
  --owner-email <exact email> --status failed --json
docker compose run --rm api slaif-gateway email show <email-delivery-uuid> --json
```

- `email list` filters combine with `AND` in SQL before deterministic
  `(created_at DESC, id DESC)` paging (`--limit` 1..100, `--offset` up to
  1000000); `--owner-email` is exact after strip/lower normalization, never
  a substring identity. Persisted statuses only: `pending`, `sending`,
  `sent`, `failed`, `ambiguous`, `cancelled`.
- `email show <delivery-uuid>` resolves the EXACT UUID and adds the
  service-derived secret lifecycle (`present` = pending usable material,
  NOT proof the email was sent; `consumed`; `expired`; `unavailable`),
  `can_send`/blocking reason, and the safe last-recorded failure (finite
  known error code, action, time, provenance `last recorded audit error`;
  unknown codes report `unavailable`).

CLI send/enqueue help:

```bash
docker compose run --rm api slaif-gateway email send-pending-key --help
```

## When To Rotate

Rotate the gateway key when:

- The delivery is `ambiguous` and recipient receipt cannot be confirmed.
- The one-time secret is missing, expired, consumed, or invalid.
- The replacement key was shown once and lost.

```bash
docker compose run --rm api slaif-gateway keys rotate <gateway-key-uuid> \
  --email-delivery pending \
  --reason "replace uncertain key email delivery"
```

## When To Retry Pending Or Failed Delivery

Retry only when the row is eligible and backed by a valid pending one-time
secret. Use the dashboard send-now/enqueue actions, or the CLI:

```bash
docker compose run --rm api slaif-gateway email send-pending-key \
  --one-time-secret-id <one-time-secret-uuid> \
  --email-delivery-id <email-delivery-uuid> \
  --send-now \
  --reason "retry pending key delivery"
```

An existing `failed` delivery requires the explicit `--retry-failed` flag
AND a nonblank bounded `--reason` in both `--send-now` and `--enqueue`
modes; the CLI refuses the missing flag, blank reason, or the flag on a
non-failed row BEFORE any send or queue. `sent`, `sending`, `ambiguous`,
and `cancelled` rows are never blindly retried.

Or enqueue through Celery:

```bash
docker compose run --rm api slaif-gateway email send-pending-key \
  --one-time-secret-id <one-time-secret-uuid> \
  --email-delivery-id <email-delivery-uuid> \
  --enqueue \
  --reason "enqueue pending key delivery"
```

## IDless (Initial) Send Safety

Omitting `--email-delivery-id` is a genuine FIRST-creation path only:

- If the one-time secret has ANY prior delivery history (including a
  retained `failed` row), the send is refused and the operator must select
  an existing delivery UUID explicitly (with `--retry-failed` when failed).
- If the same secret has another `sending`, `sent`, or `ambiguous` attempt,
  the send is refused even when a different retryable row is selected —
  never a silent new row around a block.
- A supplied delivery UUID that is missing, or backed by a different
  one-time secret, is a fixed selection refusal: no substitute delivery is
  created, and no other secret is decrypted, consumed, or sent.

## Exact `queued` And `sent` Meanings

- `queued` (CLI enqueue result) means the Celery broker accepted the task
  submission only. It is NOT a persisted delivery status and NOT a worker
  acknowledgement. The delivery row remains `pending` until the worker
  runs and revalidates actual sendability.
- `sent` (persisted status) means SMTP acceptance plus database
  finalization were recorded. It is NOT confirmed inbox arrival.
- A queue failure after the committed enqueue-REQUEST intent audit is
  reported nonzero and leaves only the honest intent; it never marks the
  delivery sent/queued or consumes the secret.
## Why Old Plaintext Cannot Be Resent

Plaintext gateway keys are not stored after creation/rotation. The only
recoverable copy for pending delivery is the encrypted one-time secret. Once it
is consumed, expired, missing, or unsafe to retry, rotate the key.

## Payload Policy

Email bodies, plaintext keys, encrypted payloads, and nonces must not be placed
in Celery payloads, logs, tickets, or audit reasons. Celery key-delivery tasks
carry IDs only.

## Mailpit Local Test Note

Use Mailpit for local testing. It catches email locally and avoids real external
delivery.

## Verification Checklist

- Delivery row status is expected.
- One-time secret status is pending before retry or consumed after sent.
- Mailpit or SMTP logs show the expected test delivery in local environments.
- No plaintext key appears in logs, Celery payloads, or audit metadata.
