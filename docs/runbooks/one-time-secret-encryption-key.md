# One-Time-Secret Encryption Key Handling

## Purpose

`ONE_TIME_SECRET_ENCRYPTION_KEY` encrypts short-lived recoverable payloads in
`one_time_secrets`, mainly newly generated or rotated gateway keys waiting for
email delivery. It is separate from gateway-key HMAC storage.

## Affected Workflows

- Key create and rotate email delivery modes: `pending`, `send-now`, and
  `enqueue`.
- Pending email deliveries backed by `one_time_secrets`.
- Bulk key creation with `pending` or `enqueue` delivery modes.

## If The Encryption Key Is Lost

Pending encrypted one-time secrets cannot be decrypted. The old plaintext
gateway key was not stored elsewhere. Operators should expire or abandon those
pending deliveries and rotate the affected gateway keys if a recipient still
needs a key.

Already consumed/sent deliveries do not need the one-time secret for key
validation. Gateway key validation uses HMAC secrets, not this encryption key.

## Rotation Policy

The database stores `encryption_key_version`, and new rows use
`ONE_TIME_SECRET_KEY_VERSION`, but the current decryption path uses the single
configured `ONE_TIME_SECRET_ENCRYPTION_KEY`. There is no implemented CLI command
or multi-key decryptor for staged one-time-secret key rotation.

Conservative rotation process:

1. Stop creating new pending key deliveries.
2. Send, consume, expire, or intentionally abandon current pending one-time
   secrets.
3. Rotate affected gateway keys if recipients still need a key.
4. Change `ONE_TIME_SECRET_ENCRYPTION_KEY` and increment
   `ONE_TIME_SECRET_KEY_VERSION`.
5. Restart API, worker, and scheduler.
6. Verify new create/rotate pending delivery creates decryptable rows.

## Ambiguous Or Pending Delivery Handling

- `pending` and `failed` deliveries can be sent or enqueued only while backed by
  a valid, unexpired, unconsumed one-time secret.
- `sending` and `ambiguous` deliveries are not retried automatically.
- If receipt cannot be confirmed, rotate the gateway key and create a new
  delivery.

## Verification Checklist

```bash
docker compose run --rm api slaif-gateway email send-pending-key --help
curl -fsS http://localhost:8000/readyz
```

Then create a safe test key in a non-production or controlled environment and
use `pending` or Mailpit-backed delivery to verify the path. Do not send real
external email during local verification.

## Do Not Store Or Log

Do not store or log plaintext gateway keys, encrypted payloads, nonces, provider
keys, SMTP passwords, or the encryption key itself. Celery task payloads should
carry IDs only.
