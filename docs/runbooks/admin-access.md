# Admin Access And Lockout

> **Status:** Current operator runbook
> **Safety:** Treat every active admin as highly privileged

## Current Admin Model

Legacy admin authority is broad: apart from the enforced
existing-`superadmin` boundaries described below, every active admin
retains full operator authority over the existing admin surfaces. MFA and
full RBAC are not implemented in the current RC-beta system.

There are three enforced role boundaries today:

1. The ENTIRE admin accounts area (G17/218) - every account view and
   action (list, create, password reset) - requires the authenticated
   user's EXISTING `superadmin` role. This is a per-request server-side
   gate, not a hidden link: an ordinary `admin` receives a fixed safe
   403 refusal on every account surface.
2. Applying reviewed accounting recovery operations (the confirm-and-apply
   step of the admin console's accounting operations area, G14/216)
   requires the same EXISTING `superadmin` role.
3. The admin catalog workspace's reviewed catalog-refresh apply and its
   custody cleanup actions (G15/217) require the same EXISTING
   `superadmin` role.

All other admin authority — every read-only view, preview, review,
collection, proposal, export, and inspection step, including every catalog
workspace surface other than apply/cleanup — is unchanged for ordinary
`admin` accounts; a non-superadmin receives a fixed safe refusal at those
mutating steps only. No automatic elevation exists: an account becomes a
superadmin only by being created with the explicit flag (CLI) or through
the console's create-account form with its explicit privileged-role
acknowledgement (both below); there is no promote command, and the first
created admin is not elevated automatically.

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

A superadmin can also be created from the console's accounts area (see
[Console Account Administration](#console-account-administration)), where
choosing the privileged role requires an explicit additional
acknowledgement. An upgraded deployment whose only existing account is an
ordinary `admin` cannot manage accounts from the console until a
superadmin exists; use the CLI `admin create --superadmin` path above for
that setup. This is intentional: there is never a silent auto-elevation or
a browser bootstrap of the first superadmin.

## Console Account Administration

The admin console's accounts area (visible to superadmins) lists existing
admin identities - name, email, exact stored role, active state, and safe
timestamps - and supports creating an account and resetting an account's
password. It exposes no hashes, session tokens, or secrets.

- **Create** an ordinary `admin` by default. Choosing the `superadmin`
  role requires an explicit additional privileged-role acknowledgement,
  and every create requires an explicit confirmation plus a bounded
  nonblank reason (audited with the acting admin).
- **Reset password** is entered from a list row link bound to its
  server-derived target. Before confirmation the form shows the target's
  server-derived identity and explains the consequence: the account's
  previous sessions are all signed out immediately. The new password must
  match its confirmation exactly; exact entered bytes are used (nonempty,
  at most 128 characters; no trimming or normalization), and the password
  is never shown again or stored in plain text.
- **Session consequences**: the password change, the revocation of ALL of
  the target's existing console sessions, and the actor/target/reason
  audit entry are committed together as one transaction, so a fault before
  commit changes nothing. If a reset request fails at the commit or
  connection stage, the console cannot confirm the outcome: verify the
  account's current state (a sign-in attempt with the new password, or the
  audit log) before retrying. Sessions that are already running a request
  are not recalled; new requests with the old sessions are refused from
  the moment the reset is committed.
- **Self-reset** (resetting your own account) deliberately signs YOU out:
  your own session is revoked together with the password change and your
  cookie is cleared. You then sign in again with the new password.
- The CLI `admin create`, `admin reset-password`, and `admin list`
  commands remain available and preserve their behavior; `reset-password`
  shares the same transactional session-revocation behavior as the console
  (one shared service, not a second weaker reset).

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

Reset the password through the console's accounts area (a superadmin
action; see [Console Account Administration](#console-account-administration))
or through the CLI:

```bash
printf '%s\n' '<new-strong-password>' \
  | docker compose run --rm api slaif-gateway admin reset-password \
      <admin-email-or-uuid> \
      --password-stdin
```

Both paths share the same transactional behavior: the new hash, the
revocation of ALL of the account's existing console sessions, and the
audit entry commit together. Use a real secure secret channel for the new
password. Do not put personal emails or real passwords in documentation,
tickets, or command history examples.

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
