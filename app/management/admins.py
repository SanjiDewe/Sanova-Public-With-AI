from __future__ import annotations

from app.identity.authorization import Permission


class AdminManagement:
    """Admin-role lifecycle separated from ordinary user lifecycle."""

    def __init__(self, identity, *, admin_role: str = "admin", fallback_role: str = "user"):
        self.identity = identity
        self.admin_role = self._require_role(admin_role)
        self.fallback_role = self._require_role(fallback_role)

    def _require_role(self, role: str) -> str:
        value = str(role).strip().lower()
        if not value or self.identity.authorization.roles.get(value) is None:
            raise ValueError(f"unknown role: {value or role}")
        return value

    def _require_admin_manager(self, actor):
        if not self.identity.authorization.has_permission(actor, Permission.MANAGE_ADMINS):
            raise PermissionError("admin management permission required")

    def grant(self, actor, user_id):
        self._require_admin_manager(actor)
        user = self.identity.store.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        self.identity.store.set_role(user_id, self.admin_role)
        return self.identity.store.get_user(user_id)

    def revoke(self, actor, user_id, fallback_role: str | None = None):
        self._require_admin_manager(actor)
        if actor.id == user_id:
            raise ValueError("cannot revoke the current administrator")
        target_role = self._require_role(fallback_role or self.fallback_role)
        user = self.identity.store.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        self.identity.store.set_role(user_id, target_role)
        return self.identity.store.get_user(user_id)
