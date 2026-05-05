# Provider Key Rotation

## Purpose

Rotate the upstream provider key used by the gateway to call OpenAI,
OpenRouter, or a provider config row that references an environment variable.
This does not rotate user gateway keys.

## When To Use

- An upstream provider key may have leaked.
- Scheduled upstream provider key rotation is due.
- A provider revoked or disabled the current key.

## Affected Secrets

- `OPENAI_UPSTREAM_API_KEY`
- `OPENROUTER_API_KEY`
- Any `provider_configs.api_key_env_var` value referenced by enabled provider
  config rows.

## Do Not

- Do not store provider key values in PostgreSQL.
- Do not paste provider keys into dashboard notes, audit reasons, tickets, logs,
  or chat.
- Do not use `OPENAI_API_KEY` as the server-side upstream OpenAI key.
  `OPENAI_API_KEY` is reserved for clients carrying gateway-issued keys.

## Pre-Checks

1. Identify enabled provider configs:

   ```bash
   docker compose run --rm api slaif-gateway providers list --json
   ```

2. Check production readiness without exposing values:

   ```bash
   curl -fsS http://localhost:8000/readyz
   ```

3. Record the provider names and env var names only, for example
   `openai -> OPENAI_UPSTREAM_API_KEY`.

## Rotation Steps

1. Create the new upstream key in the provider console.
2. Update the VM, container environment, Docker secret, or secret-manager value
   for the relevant env var name.
3. Restart the services that read provider settings:

   ```bash
   docker compose up -d api worker scheduler
   ```

   If the deployment uses a separate secret injection mechanism, restart the
   equivalent API, worker, and scheduler processes there.

4. Verify readiness:

   ```bash
   curl -fsS http://localhost:8000/readyz
   ```

5. Verify local provider configuration without a real provider call where
   possible:

   ```bash
   docker compose run --rm api slaif-gateway providers list --json
   docker compose run --rm api slaif-gateway routes list --json
   ```

## Rollback

If the new provider key is rejected and the old key is still valid, restore the
previous deployment secret value and restart the same services. If the old key
was leaked, prefer creating another fresh key instead of restoring it.

## Verification Checklist

- `/readyz` is healthy.
- Enabled provider config rows reference env var names, not secret values.
- API logs do not contain provider key material.
- A controlled smoke request is made only if the operator intentionally chooses
  to spend provider quota.
- Old provider key is revoked in the provider console after successful rotation,
  unless it is intentionally retained for a short rollback window.

## Audit And Logs

The current provider-key value is outside the database. Local provider metadata
changes through the dashboard or CLI create safe audit rows, but changing an
environment secret may be audited by the deployment platform rather than the
gateway. Incident notes should contain env var names, provider names, timestamps,
and redacted identifiers only.

## If The Old Key Leaked

Treat the old upstream key as compromised. Revoke it in the provider console,
review provider billing and request logs, check gateway usage around the
exposure window, and rotate any deployment secrets or logs that may have
captured the key.
