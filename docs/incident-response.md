# Incident response runbooks

## Credential compromise

1. Revoke the affected user's admin sessions and rotate credentials.
2. Clear abuse-tracker state after credential rotation.
3. Review audit exports for policy changes and key lifecycle actions.
4. Rotate gateway keys owned by the affected identity.

## Suspected session hijack

1. Immediately revoke the session.
2. Inspect recent admin actions for that session ID.
3. Force re-authentication through OIDC or local fallback.

## DLP bypass suspicion

1. Place the relevant policy in block mode.
2. Preserve metadata-only audit evidence; never archive raw content.
3. Review provider governance and route constraints.

PostgreSQL remains accounting truth. No raw prompt/completion content is stored.
