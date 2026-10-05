from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class Permission(str, Enum):
    EXECUTE = "execute"
    MANAGE_USERS = "manage_users"
    MANAGE_ADMINS = "manage_admins"
    MANAGE_PROVIDERS = "manage_providers"
    VIEW_AUDIT = "view_audit"


@dataclass(frozen=True)
class RoleDefinition:
    name: str
    permissions: frozenset[Permission]


class RoleRegistry:
    """Runtime role registry. Applications may replace the defaults with their own roles."""

    def __init__(self, definitions: Iterable[RoleDefinition] | None = None):
        self._roles: dict[str, RoleDefinition] = {}
        for definition in definitions or default_role_definitions():
            self.register(definition)

    def register(self, definition: RoleDefinition, *, replace: bool = False) -> None:
        key = self._normalize(definition.name)
        if key in self._roles and not replace:
            raise ValueError(f"role already registered: {key}")
        self._roles[key] = RoleDefinition(key, frozenset(definition.permissions))

    def get(self, role: str) -> RoleDefinition | None:
        return self._roles.get(self._normalize(role))

    def names(self) -> tuple[str, ...]:
        return tuple(self._roles)

    @staticmethod
    def _normalize(name: str) -> str:
        value = str(name).strip().lower()
        if not value:
            raise ValueError("role name is required")
        return value


def default_role_definitions() -> tuple[RoleDefinition, ...]:
    return (
        RoleDefinition("user", frozenset({Permission.EXECUTE})),
        RoleDefinition(
            "admin",
            frozenset({
                Permission.EXECUTE,
                Permission.MANAGE_USERS,
                Permission.MANAGE_ADMINS,
                Permission.MANAGE_PROVIDERS,
                Permission.VIEW_AUDIT,
            }),
        ),
    )


class AuthorizationService:
    def __init__(self, store, roles: RoleRegistry | None = None):
        self.store = store
        self.roles = roles or RoleRegistry()

    def has_permission(self, user, permission: Permission) -> bool:
        role = self.roles.get(user.role)
        return role is not None and permission in role.permissions and user.active

    def has_consent(self, user, scope: str, version: str) -> bool:
        if not user.active:
            return False
        return self.store.has_consent(user.id, scope, version)

    def grant_consent(self, user, scope: str, version: str) -> None:
        self.store.grant_consent(user.id, scope, version)

    def revoke_consent(self, user, scope: str) -> None:
        self.store.revoke_consent(user.id, scope)

    def require_consent(self, user, scope: str, version: str) -> None:
        if not self.has_consent(user, scope, version):
            raise PermissionError(f"consent required for {scope} {version}")
