# OAP Work Order — 119-a

PR mode: `CREATE_NEW_PR`
Branch: `oap/119-oidc-human-identity-linking`
Base: main @ 143d75f

## Objective and reason

Implement configurable OIDC discovery, authorization code flow with PKCE,
claim validation, identity linking, session creation, and logout for SME
human sign-in. This gives SMEs centralized human identity while preserving
a bounded local bootstrap/break-glass path.

## Verified current state

- main = 143d75f; no 119 branch or PR exists.
- 118-a merged (organization/team/project data model).
- No OIDC dependencies or code exist yet in the codebase.
- Existing admin auth uses email/password with argon2-cffi and itsdangerous
  session tokens (`AdminSessionService`).
- Existing `AdminSession` DB model provides session lifecycle pattern.

## Requirements

1. Add `authlib` to project dependencies for OIDC client support.

2. Add OIDC configuration to `Settings`:
   - `OIDC_ENABLED` (default false)
   - `OIDC_ISSUER_URL` (e.g., https://idp.example.com/realms/slaif)
   - `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` (env-sourced, never stored in DB)
   - `OIDC_REDIRECT_URI` (computed from base URL)
   - `OIDC_SCOPES` (default: openid profile email)

3. Add `oidc_identities` DB table:
   - id, owner_id FK, issuer_url, subject (unique per issuer), email, created_at
   - Migration 0017 (idempotent, follows 0016 pattern)

4. Implement `OidcAuthService`:
   - Discovery document fetch and caching
   - Authorization URL generation with PKCE (code_verifier/challenge)
   - State parameter generation and validation
   - Token exchange and ID token validation (signature, audience, nonce, expiry)
   - Identity linking: map OIDC subject to existing owner by verified email match
   - No automatic privilege escalation: mapped permissions only

5. Add API routes:
   - `GET /admin/auth/oidc/login` — redirect to IdP
   - `GET /admin/auth/oidc/callback` — handle authorization response
   - `POST /admin/auth/oidc/logout` — revoke session

6. Local bootstrap/break-glass:
   - Keep existing email/password admin login as documented fallback
   - Add `LOCAL_ADMIN_FALLBACK=true` setting (default true)
   - Document that local access is rate-limited and distinguishable in audit logs

7. Security requirements:
   - Fail closed on: issuer mismatch, audience mismatch, nonce mismatch,
     state mismatch, signature verification failure, clock skew beyond 5 minutes
   - All auth failures logged safely (no tokens or PII in error messages)
   - Session tokens use existing itsdangerous pattern with rotation on login

8. Documentation:
   - `docs/oidc-setup.md`: provider setup guide, secret rotation, outage behavior
   - Update `docs/database-schema.md` with oidc_identities table
   - Update admin docs to describe both OIDC and local login paths

## Non-goals

- No SAML, SCIM, arbitrary social login
- No provider-admin secret display
- No automatic role claims without explicit mapping policy
- No removal of local bootstrap/recovery access

## Allowed paths

pyproject.toml
docs/oidc-setup.md (new)
docs/database-schema.md
docs/administration.md (if exists, otherwise skip)
migrations/versions/0017_oidc_identities.py (new)
app/slaif_gateway/db/models.py
app/slaif_gateway/db/repositories/oidc_identities.py (new)
app/slaif_gateway/services/oidc_service.py (new)
app/slaif_gateway/api/admin.py
app/slaif_gateway/config.py
tests/unit/test_oidc_service.py (new)
tests/unit/test_oidc_identities.py (new)
oap/active
oap/orders/119-a-oidc-human-identity-linking.md
oap/reports/119-a-oidc-human-identity-linking.md

## Verification commands

PYTHONPATH=.:app .venv/bin/pytest -q \
  tests/unit/test_oidc_service.py \
  tests/unit/test_oidc_identities.py

git diff --check
Ruff on changed paths

## Acceptance criteria

1. OIDC login flow generates authorization URL with PKCE.
2. Token exchange validates signature, audience, nonce, and expiry.
3. Identity linking maps OIDC subject to existing owner by verified email.
4. Fail-closed on all security mismatches with safe audit logging.
5. Local break-glass login documented and distinguishable.
6. All CI checks green on final head.

## Security

- Provider secrets only in environment variables, never in DB or code
- PostgreSQL remains accounting truth
- Fail-closed unknowns
- No production credentials or real provider calls in CI

## OAP contract

- Objective 119-a creates exactly one new PR for numeric objective 119.
- Remediations use 119-b through 119-z on the same PR.
- The coding agent never merges or enables auto-merge.

## Boundaries

Non-production only. No production data or credentials.
PostgreSQL remains accounting truth.
