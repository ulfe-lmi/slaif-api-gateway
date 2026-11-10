# Admin Access And Lockout

> **Status:** Current operator runbook
> **Safety:** Treat every active admin as highly privileged

## Current Admin Model

Legacy admin authority is broad: apart from the enforced
existing-`superadmin` boundaries described below, every active admin
retains full operator authority over the existing admin surfaces. MFA and
full RBAC are not implemented in the current RC-beta system.

There are two enforced role boundaries today, both at the mutating
confirm-and-apply / custody-cleanup step only:

1. Applying reviewed accounting recovery operations (the confirm-and-apply
   step of the admin console's accounting operations area, G14/216)
   requires the authenticated user's EXISTING `superadmin` role.
2. The admin catalog workspace's reviewed catalog-refresh apply and its
   custody cleanup actions (G15/217) require the same EXISTING
   `superadmin` role.

All other admin authority — every read-only view, preview, review,
collection, proposal, export, and inspection step, including every catalog
workspace surface other than apply/cleanup — is unchanged for ordinary
`admin` accounts; a non-superadmin receives a fixed safe refusal at those
mutating steps only. No automatic elevation exists: an account becomes a
superadmin only by being created with the explicit flag (below); there is
no promote command, and the first created admin is not elevated
automatically.

Protect `/admin` with HTTPS, strong passwords, login rate limiting, and
preferably VPN, IP allowlisting, or equivalent ingress control.

## Offline Superadmin Setup

To create (or replace) a superadmin without a running console session,
use the CLI from the server environment, for example:

```bash
printf '%s\n' '<new-strong-password>' \
  | docker compose run --rm api slaif-gateway admin create \
      --email superadmin@example.org \
      --display-name "Gateway Superadmin" \
      --superadmin \
      --password-stdin
```

Without `--superadmin` the account is a full ordinary `admin`. Verify the
result with `slaif-gateway admin list` (it reports `is_superadmin`) and
rotate or disable any account whose password was shared through an unsafe
channel.

## Login Rate Limits

Admin login attempts are rate-limited through PostgreSQL/audit state by
normalized email and client IP. Relevant settings:

- `ADMIN_LOGIN_RATE_LIMIT_ENABLED`
- `ADMIN_LOGIN_MAX_FAILED_ATTEMPTS`
- `ADMIN_LOGIN_WINDOW_SECONDS`
- `ADMIN_LOGIN_LOCKOUT_SECONDS`

Messages remain generic and do not reveal whether an account exists.

## Inactive Admins And Sessions

Inactive admins cannot log in. Revoked or expired server-side sessions cannot
access admin routes. Session settings include `ADMIN_SESSION_TTL_SECONDS` and
admin session cookie settings documented in configuration.

## Lost Password

Reset the password through the CLI:

```bash
printf '%s\n' '<new-strong-password>' \
  | docker compose run --rm api slaif-gateway admin reset-password \
      <admin-email-or-uuid> \
      --password-stdin
```

Use a real secure secret channel for the new password. Do not put personal
emails or real passwords in documentation, tickets, or command history examples.

## Lost All Admin Access

Create a new admin from the server environment:

```bash
printf '%s\n' '<new-strong-password>' \
  | docker compose run --rm api slaif-gateway admin create \
      --email admin@example.org \
      --display-name "Admin User" \
      --password-stdin
```

Then log in, review existing active admins, and disable or rotate credentials
for accounts involved in the incident.

## Checklist

- Confirm `/admin/login` is reachable only through approved ingress.
- Reset or create admin access through CLI.
- Review `/admin/audit` for failed login and lockout events.
- Review active admin accounts.
- Rotate any password shared through an unsafe channel.
