"""Tests for the RBAC permission matrix."""

import pytest

from slaif_gateway.services.rbac import (
    ROLE_PERMISSIONS,
    AdminRole,
    Permission,
    has_permission,
    require_permission,
    PermissionDeniedError,
)


class TestHasPermission:
    def test_platform_admin_has_all_permissions(self):
        for perm in Permission:
            assert has_permission(AdminRole.PLATFORM_ADMIN, perm)

    def test_org_admin_permissions(self):
        assert has_permission(AdminRole.ORG_ADMIN, Permission.MANAGE_KEYS)
        assert has_permission(AdminRole.ORG_ADMIN, Permission.VIEW_AUDIT)
        assert not has_permission(AdminRole.ORG_ADMIN, Permission.MANAGE_ADMINS)
        assert not has_permission(AdminRole.ORG_ADMIN, Permission.MANAGE_PRICING)

    def test_team_manager_permissions(self):
        assert has_permission(AdminRole.TEAM_MANAGER, Permission.MANAGE_KEYS)
        assert not has_permission(AdminRole.TEAM_MANAGER, Permission.VIEW_AUDIT)

    def test_auditor_is_read_only(self):
        assert has_permission(AdminRole.AUDITOR, Permission.VIEW_USAGE)
        assert has_permission(AdminRole.AUDITOR, Permission.EXPORT_DATA)
        for perm in Permission:
            if not str(perm).startswith("view") and perm != Permission.EXPORT_DATA:
                assert not has_permission(AdminRole.AUDITOR, perm), f"Auditor should not have {perm}"

    def test_viewer_is_minimal(self):
        assert has_permission(AdminRole.VIEWER, Permission.VIEW_USAGE)
        assert not has_permission(AdminRole.VIEWER, Permission.MANAGE_KEYS)


class TestRequirePermission:
    def test_passes_when_allowed(self):
        require_permission("platform_admin", "manage_keys")

    def test_raises_when_denied(self):
        with pytest.raises(PermissionDeniedError):
            require_permission("viewer", "manage_keys")

    def test_unknown_role_denied(self):
        assert not has_permission("unknown_role", "manage_keys")

    def test_unknown_permission_denied(self):
        assert not has_permission("platform_admin", "nonexistent")


class TestPermissionMatrix:
    """Property-style tests: verify least-privilege ordering."""

    def test_platform_admin_superset_of_all(self):
        platform_perms = set(ROLE_PERMISSIONS[AdminRole.PLATFORM_ADMIN])
        for role in AdminRole:
            if role != AdminRole.PLATFORM_ADMIN:
                role_perms = set(ROLE_PERMISSIONS[role])
                assert role_perms.issubset(platform_perms)

    def test_no_role_escapes_assigned_unit(self):
        # Team manager cannot manage organization-level settings
        assert not has_permission(AdminRole.TEAM_MANAGER, Permission.MANAGE_ORG)

    def test_auditor_cannot_manage(self):
        auditor_perms = ROLE_PERMISSIONS[AdminRole.AUDITOR]
        manage_perms = {p for p in Permission if p.value.startswith("manage")}
        assert not (auditor_perms & manage_perms)
