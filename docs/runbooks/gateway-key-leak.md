# Gateway Key Leak Response

## What A Leaked Gateway Key Means

A gateway key is the bearer token a user supplies as `OPENAI_API_KEY` or in the
`Authorization` header. A leaked key can spend that key's allowed quota and use
its allowed endpoint/model/provider policy until it is suspended, revoked,
expired, or exhausted. It does not reveal upstream provider keys.

## Immediate Containment

1. Identify the key by safe metadata: public key ID, hint, owner, gateway key
   UUID, request ID, or usage timestamps. Do not paste the full leaked key into
   tools or notes.
2. Suspend the key while investigating:

   ```bash
   docker compose run --rm api slaif-gateway keys suspend <gateway-key-uuid> \
     --reason "suspected leaked gateway key"
   ```

3. Revoke the key permanently if compromise is confirmed:

   ```bash
   docker compose run --rm api slaif-gateway keys revoke <gateway-key-uuid> \
     --reason "confirmed leaked gateway key"
   ```

4. Rotate if the owner needs a replacement:

   ```bash
   docker compose run --rm api slaif-gateway keys rotate <gateway-key-uuid> \
     --email-delivery pending \
     --reason "replacement after key leak"
   ```

5. Reset limits only when intentionally approved. Usage reset preserves ledger
   rows and should not be used to hide incident activity.

## Dashboard References

Use `/admin/keys` to filter and inspect safe key metadata. Use
`/admin/keys/<gateway-key-uuid>` for suspend, activate, revoke, limits,
usage-counter reset, and rotation actions. Use `/admin/usage` and `/admin/audit`
for investigation and export controls.

## CLI Investigation

```bash
docker compose run --rm api slaif-gateway keys list --json
docker compose run --rm api slaif-gateway keys show <gateway-key-uuid> --json
docker compose run --rm api slaif-gateway usage summarize --json
docker compose run --rm api slaif-gateway usage export --help
```

## Usage And Audit Investigation

- Review usage by key, owner, provider, model, endpoint, and time window in
  `/admin/usage`.
- Export safe usage metadata when needed through the audited CSV export.
- Review `/admin/audit` for key lifecycle actions, usage exports, and metadata
  changes.
- Preserve request IDs and usage ledger IDs for follow-up; do not preserve
  plaintext keys in incident records.

## Owner Notification

Notify the owner or organizer with the approximate exposure window, containment
action, quota impact, and whether a replacement key was issued. Send only the
new replacement key through the documented one-time delivery path or the
operator's approved secure channel.

## Do Not

- Do not try to recover or resend the old plaintext key.
- Do not expose `token_hash`.
- Do not delete usage ledger rows.
- Do not paste the leaked key into audit reasons, dashboard notes, logs, or
  issue trackers.

## Post-Incident Checklist

- Key suspended or revoked.
- Replacement key issued only if needed.
- Usage and audit reviewed for the exposure window.
- Owner notified.
- Provider keys confirmed unaffected.
- Any screenshots, tickets, and chat messages checked for accidental key
  disclosure.
