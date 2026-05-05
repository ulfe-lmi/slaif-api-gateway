# Ambiguous Email Delivery Handling

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

Or enqueue through Celery:

```bash
docker compose run --rm api slaif-gateway email send-pending-key \
  --one-time-secret-id <one-time-secret-uuid> \
  --email-delivery-id <email-delivery-uuid> \
  --enqueue \
  --reason "enqueue pending key delivery"
```

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
