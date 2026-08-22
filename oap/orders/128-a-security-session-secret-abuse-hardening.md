# OAP Work Order — 128-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/128-security-session-secret-abuse-hardening`
Base: main @ 7acd8d8f346b

## Objective and reason

Harden identities, sessions, secrets, abuse controls, and threat model to close
the expanded SME attack surface introduced by objectives 118–127 before
operational qualification. Covers OIDC, RBAC, service accounts, Codex, external
tools, DLP, catalogs, budgets, exports, and reconciliation boundaries.

## Verified state

- main = 7acd8d8f346b; no open non-Dependabot PR.
- Objectives 118–127 merged.
- Existing security controls: CSRF on admin actions, bearer auth, HMAC key hashing,
  provider-secret isolation via env vars.

## Scope

1. Session/token hardening:
   - Rotation on privilege change; short-lived admin sessions with refresh.
   - Credential compromise response runbook (revoke all sessions for user).
2. Abuse limits:
   - Login attempt throttling per IP/user.
   - API rate limiting already exists; add per-identity abuse tracking.
3. Security headers and CSRF:
   - Content-Security-Policy appropriate for server-rendered templates.
   - X-Content-Type-Options, X-Frame-Options, Referrer-Policy.
   - Verify all POST endpoints require CSRF token.
4. SSRF/redirect protection:
   - No open redirects in admin URLs.
   - Provider base_url validation (no redirects, no private IP ranges unless LAN-approved).
5. Secret startup validation:
   - Fail closed if required secrets missing or too short.
   - Warn on default/example values in non-development environments.
6. Dependency scanning:
   - Add pip-audit or safety to CI pipeline.
7. Incident evidence and operator runbooks:
   - Document credential compromise, session hijack, and DLP bypass response steps.

## Exact requirements

1. All existing tests continue to pass after hardening changes.
2. New security-focused unit/integration tests cover each hardened area.
3. No penetration-test or compliance claim without an external engagement.
4. Documentation updated for new headers, secret requirements, and runbooks.

## Allowed paths

```
app/slaif_gateway/api/admin.py
app/slaif_gateway/services/security.py
app/slaif_gateway/config.py
tests/unit/test_security_hardening*.py
tests/integration/test_security*_postgres.py
docs/security-hardening.md
docs/incident-response.md
oap/orders/128-a-security-session-secret-abuse-hardening.md
oap/reports/128-a-security-session-secret-abuse-hardening.md
oap/active
.github/workflows/*.yml  # for dependency scanning addition
```

## Non-goals

No penetration-test claim without external engagement. No compliance certification.

## Observable acceptance

- Security header tests pass.
- CSRF verification covers all POST endpoints.
- SSRF protection blocks redirects to unexpected hosts.
- Secret startup validation fails closed on missing/too-short secrets.
- Dependency scanning runs in CI without critical vulnerabilities.
- Incident response documentation is complete.
- All required final-head CI checks green.

## Verification commands

```bash
PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_security_hardening*.py
PYTHONPATH=.:app .venv/bin/pytest -q tests/integration/test_security*_postgres.py
git diff --check
```

## Boundaries

Non-production only. Provider credentials never exposed.

## OAP contract

Objective 128-a creates one PR; remediation uses 128-b–z same PR.
Coding agent never merges.
