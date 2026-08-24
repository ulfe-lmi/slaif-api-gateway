# Incident response overview

> **Status:** Current operator index
> **Boundary:** Preserve safe metadata and exact identifiers; never collect content or secrets

## First actions

1. Identify the exact deployment, time window, affected key/provider/admin, and
   safe `gw-...` diagnostic IDs.
2. Preserve PostgreSQL, relevant redacted logs, configuration revision, and
   provider/operator timestamps before mutation.
3. Contain the smallest affected boundary: revoke/rotate a key, suspend a key,
   disable a provider/route, or restrict network ingress.
4. Never copy plaintext keys, provider credentials, cookies, session/CSRF
   tokens, database URLs, prompts, completions, media, or raw provider bodies
   into tickets or chat.
5. Verify containment through the Gateway boundary and PostgreSQL truth, then
   document recovery and follow-up.

## Runbooks by incident

| Incident | Procedure |
|---|---|
| Gateway key leak | [Gateway key leak response](runbooks/gateway-key-leak.md) |
| Provider credential compromise | [Provider key rotation](runbooks/provider-key-rotation.md) |
| HMAC material compromise | [HMAC rotation](runbooks/hmac-secret-rotation.md) |
| One-time-secret encryption issue | [Encryption-key handling](runbooks/one-time-secret-encryption-key.md) |
| Admin lockout or suspected session issue | [Admin access and lockout](runbooks/admin-access.md) |
| Redis outage | [Redis outage](runbooks/redis-outage.md) |
| PostgreSQL readiness/pool exhaustion | [PostgreSQL readiness](runbooks/postgresql-pool-readiness.md) |
| Stale reservation | [Reservation reconciliation](runbooks/stale-reservation-reconciliation.md) |
| Provider completed but finalization failed | [Provider-completed recovery](runbooks/provider-completed-reconciliation.md) |
| Unknown external-tool cost/outcome | [External-tool hold reconciliation](runbooks/external-tool-hold-reconciliation.md) |
| Ambiguous key email delivery | [Ambiguous delivery](runbooks/ambiguous-email-delivery.md) |
| NGINX/Compose failure | [Docker and NGINX troubleshooting](runbooks/docker-nginx-troubleshooting.md) |

## Foundation-only cautions

OIDC login, DLP egress enforcement, provider-governance routing, and automated
SIEM delivery are not wired current incident controls. Their standalone modules
must not be used as evidence that an incident was contained.

PostgreSQL remains accounting truth. No current incident workflow creates a
right to persist raw prompt/completion/provider content.
