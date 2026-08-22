# OAP execution report — 120-a

## Objective

Implement enforceable SME RBAC, permission ceilings, and MFA direction.

Implementation head SHA: 88360e11cb1f4e9c1a6046121d03468bd9314941
Report publication commit: SELF

## Changes

1. app/slaif_gateway/services/rbac.py — RBAC module with AdminRole enum
   (platform_admin, org_admin, team_manager, auditor, viewer), Permission enum
   (10 permissions), ROLE_PERMISSIONS mapping (least privilege),
   has_permission() and require_permission() functions.
2. migrations/versions/0018_admin_roles.py — Idempotent migration adding
   role column (default: viewer, fail-closed) and mfa_secret nullable column.
3. app/slaif_gateway/db/models.py — Updated AdminUser model with viewer default
   and mfa_secret field.
4. tests/unit/test_rbac.py — Comprehensive permission matrix tests including:
   platform admin superset property, auditor read-only enforcement,
   team manager unit boundary, unknown role/permission rejection.

## Security review

- Default role is "viewer" (least privilege, fail-closed for existing users)
- Auditor role has no manage permissions (read-only enforced)
- Team manager cannot access organization-level settings
- MFA enforcement deferred to OIDC provider assurance (documented)
- Local break-glass access preserved and distinguishable

## Verification

- All focused tests pass (12 RBAC tests + all existing)
- All CI checks green on final head (10/10)
- Ruff lint clean
