# HMAC Secret Rotation

## Purpose

Gateway keys are stored as HMAC-SHA-256 digests of the full plaintext key using
server-side secret material. `ACTIVE_HMAC_KEY_VERSION` selects the version used
for newly generated keys. Existing key rows store `hmac_key_version` and require
the matching `TOKEN_HMAC_SECRET_V<version>` to validate.

## Current Supported Behavior

The configuration supports an active HMAC version and lookup of
`TOKEN_HMAC_SECRET_V<version>` from the environment. `TOKEN_HMAC_SECRET_V1` is
the normal first version. The legacy `TOKEN_HMAC_SECRET` fallback is
non-production only and version-1 only.

There is no CLI command that re-HMACs existing keys, because plaintext gateway
keys are not stored. Existing keys must keep their old HMAC secret available
until they are rotated, revoked, or expired.

## What Is Safe To Rotate

- New key generation can move to a new HMAC version by adding the new
  `TOKEN_HMAC_SECRET_V<version>` and setting `ACTIVE_HMAC_KEY_VERSION`.
- Existing keys remain valid only if their recorded HMAC version's secret is
  still configured.

If old HMAC key material is removed, keys created with that version become
invalid and cannot be repaired without rotating those keys.

## Staged Rotation Process

1. Generate a new high-entropy HMAC secret in the deployment secret manager.
2. Add it as a new env var, for example `TOKEN_HMAC_SECRET_V2`.
3. Set:

   ```env
   ACTIVE_HMAC_KEY_VERSION=2
   ```

4. Keep all old `TOKEN_HMAC_SECRET_V*` values required by unexpired active keys.
5. Restart API, worker, and scheduler:

   ```bash
   docker compose up -d api worker scheduler
   ```

6. Verify new key creation uses the active version. Do not expose the plaintext
   except through the normal one-time path.
7. Rotate issued keys that still depend on the old version:

   ```bash
   docker compose run --rm api slaif-gateway keys rotate <gateway-key-uuid> \
     --reason "HMAC secret rotation"
   ```

8. Retire the old HMAC version only after all keys using it are revoked,
   expired, or rotated.

## Verification Checklist

- `/readyz` is healthy after restart.
- New key rows record the new HMAC key version.
- Existing keys from old versions still validate while old secrets remain
  configured.
- No plaintext gateway keys are stored or logged.
- No HMAC secret values appear in audit rows, tickets, or logs.

## Rollback

If new key creation or validation fails, restore the previous
`ACTIVE_HMAC_KEY_VERSION` and secret set, then restart services. Keys created
with the new version need the new version's secret to remain available until
they are rotated or revoked.
