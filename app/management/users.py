from __future__ import annotations

from app.identity.authorization import Permission, RoleRegistry


class UserManagement:
    """Management operations for user accounts; auth remains owned by identity."""

    def __init__(self, identity):
        self.identity = identity

    def _require_admin(self, actor):
        if not self.identity.authorization.has_permission(actor, Permission.MANAGE_USERS):
            raise PermissionError("user management permission required")

    def list(self, actor, *, active: bool | None = None):
        self._require_admin(actor)
        return self.identity.store.list_users(active=active)

    def get(self, actor, user_id):
        self._require_admin(actor)
        return self.identity.store.get_user(user_id)

    def set_active(self, actor, user_id, active: bool):
        self._require_admin(actor)
        if actor.id == user_id and not active:
            raise ValueError("cannot deactivate the current administrator")
        user = self.identity.store.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        self.identity.store.set_active(user_id, bool(active))
        return self.identity.store.get_user(user_id)
