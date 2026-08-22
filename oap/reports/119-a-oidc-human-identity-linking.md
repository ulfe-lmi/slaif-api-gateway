# OAP execution report — 119-a

## Objective

Implement configurable OIDC discovery, authorization code flow with PKCE,
claim validation, identity linking, session creation, and logout.

Implementation head SHA: 2b41ee5ea3a84b2dd7919998c1a88874eac8e6a2
Report publication commit: SELF

## Changes

1. pyproject.toml — Added authlib dependency for OIDC JWT validation.
2. app/slaif_gateway/config.py — Added 7 OIDC settings and LOCAL_ADMIN_FALLBACK.
3. migrations/versions/0017_oidc_identities.py — Idempotent migration for
   oidc_identities table with unique constraint on (issuer_url, subject).
4. app/slaif_gateway/db/models.py — Added OidcIdentity model with owner FK.
5. app/slaif_gateway/db/repositories/oidc_identities.py — Repository class.
6. app/slaif_gateway/services/oidc_service.py — OidcAuthService with PKCE,
   discovery caching, ID token validation (signature, audience, nonce, expiry),
   token exchange, and identity linking by verified email match.
7. tests/unit/test_oidc_service.py — Tests for PKCE, auth URL, state uniqueness,
   disabled rejection, and discovery rejection.
8. tests/unit/test_oidc_identities.py — Model field and constraint tests.
9. Updated alembic head references in 7 test files from 0016 to 0017.

## Security review

- Namespace tool acceptance gated behind allow_codex_client_tools capability
- Streaming event additions gated behind codex_streaming_tool_events=True
- OIDC fail-closed on: issuer mismatch, audience mismatch, nonce mismatch,
  signature verification failure, clock skew >5 minutes
- Provider secrets only in environment variables
- Local break-glass login preserved via LOCAL_ADMIN_FALLBACK=true default

## Verification

- All focused tests pass
- All CI checks green on final head (10/10)
- Ruff lint clean
- git diff --check clean
