"""Role-based access control for admin operations."""

from __future__ import annotations

from enum import StrEnum


class AdminRole(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    ORG_ADMIN = "org_admin"
    TEAM_MANAGER = "team_manager"
    AUDITOR = "auditor"
    VIEWER = "viewer"


class Permission(StrEnum):
    MANAGE_KEYS = "manage_keys"
    MANAGE_ROUTES = "manage_routes"
    VIEW_USAGE = "view_usage"
    MANAGE_ORG = "manage_org"
    MANAGE_TEAMS = "manage_teams"
    VIEW_AUDIT = "view_audit"
    MANAGE_PRICING = "manage_pricing"
    RECONCILE_QUOTAS = "reconcile_quotas"
    EXPORT_DATA = "export_data"
    MANAGE_ADMINS = "manage_admins"


ROLE_PERMISSIONS: dict[AdminRole, frozenset[Permission]] = {
    AdminRole.PLATFORM_ADMIN: frozenset(Permission),
    AdminRole.ORG_ADMIN: frozenset({
        Permission.MANAGE_KEYS,
        Permission.VIEW_USAGE,
        Permission.MANAGE_TEAMS,
        Permission.VIEW_AUDIT,
        Permission.EXPORT_DATA,
    }),
    AdminRole.TEAM_MANAGER: frozenset({
        Permission.MANAGE_KEYS,
        Permission.VIEW_USAGE,
    }),
    AdminRole.AUDITOR: frozenset({
        Permission.VIEW_USAGE,
        Permission.VIEW_AUDIT,
        Permission.EXPORT_DATA,
    }),
    AdminRole.VIEWER: frozenset({
        Permission.VIEW_USAGE,
    }),
}


def has_permission(role: str | AdminRole, permission: str | Permission) -> bool:
    """Check whether a role has a specific permission."""
    try:
        admin_role = AdminRole(role)
    except ValueError:
        return False
    try:
        perm = Permission(permission)
    except ValueError:
        return False
    return perm in ROLE_PERMISSIONS.get(admin_role, frozenset())


def require_permission(role: str | AdminRole, permission: str | Permission) -> None:
    """Raise PermissionDeniedError if the role lacks the permission."""
    if not has_permission(role, permission):
        raise PermissionDeniedError(
            f"Role '{role}' does not have permission '{permission}'.",
            role=str(role),
            permission=str(permission),
        )


class PermissionDeniedError(Exception):
    def __init__(self, message: str, *, role: str = "", permission: str = "") -> None:
        self.role = role
        self.permission = permission
        super().__init__(message)
