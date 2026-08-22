# OAP Work Order — 120-a

PR mode: `CREATE_NEW_PR`
Branch: oap/120-rbac-mfa-permission-ceilings
Base: main @ d451610

## Objective and reason

Implement enforceable SME RBAC, permission ceilings, and MFA direction.
Replace all-admin operation with least-privilege organizational roles suitable
for SME pilots.

## Verified current state

- main = d451610; no 120 branch or PR exists.
- Dependencies (118, 119) are both merged.
- Existing admin_users table has no role column (all admins are equal).
- AdminSessionService provides session lifecycle pattern.
- OIDC service from 119-a provides identity linking.

## Requirements

1. Add `role` column to `admin_users` table:
   - Migration 0018 (idempotent)
   - Values: platform_admin, org_admin, team_manager, auditor, viewer
   - Default: viewer (fail-closed for existing users)

2. Define permission matrix in a new module `app/slaif_gateway/services/rbac.py`:
   - Permission enum: manage_keys, manage_routes, view_usage, manage_org,
     manage_teams, view_audit, manage_pricing, reconcile_quotas,
     export_data, manage_admins
   - Role-to-permissions mapping (least privilege)
   - `has_permission(role, permission)` function

3. Apply permission checks in admin API routes.

4. MFA direction:
   - Add `mfa_secret` nullable column to admin_users
   - Document that MFA enforcement is deferred to OIDC provider assurance
   - Local admin accounts should set mfa_secret when available

5. Tests for the permission matrix with negative evidence.

## Non-goals

No custom role designer, two-person approval workflow, SCIM provisioning,
or hostile tenant boundary.

## Allowed paths

docs/database-schema.md
docs/administration.md (if exists)
migrations/versions/0018_admin_roles.py (new)
app/slaif_gateway/db/models.py
app/slaif_gateway/services/rbac.py (new)
app/slaif_gateway/api/admin.py
tests/unit/test_rbac.py (new)
oap/active
oap/orders/120-a-rbac-mfa-permission-ceilings.md
oap/reports/120-a-rbac-mfa-permission-ceilings.md

## Verification commands

PYTHONPATH=.:app .venv/bin/pytest -q tests/unit/test_rbac.py

## Acceptance criteria

1. Every sensitive operation has a named permission check.
2. Auditor role is read-only.
3. Team managers cannot access resources outside their assigned unit.
4. Permission matrix tested with positive and negative cases.
5. All CI checks green on final head.

## OAP contract

Objective 120-a creates exactly one new PR. Remediations use 120-b through 120-z.

## Boundaries

Non-production only. No production data or credentials.
PostgreSQL remains accounting truth.
