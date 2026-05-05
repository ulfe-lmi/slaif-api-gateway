# Admin Access And Lockout

## Current Admin Model

Every active admin is a full operator. `superadmin` is metadata/future-proofing
and is not currently an enforced RBAC boundary. MFA and full RBAC are not
implemented in the current RC-beta system.

Protect `/admin` with HTTPS, strong passwords, login rate limiting, and
preferably VPN, IP allowlisting, or equivalent ingress control.

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
