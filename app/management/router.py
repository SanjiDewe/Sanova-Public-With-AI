from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.management.admins import AdminManagement
from app.management.providers import ProviderManagement
from app.ai.management import AIProviderManagement, AIProviderView
from app.management.users import UserManagement
from app.core.audit.trail import AuditTrail


@dataclass(frozen=True)
class UserView:
    """Safe application-facing representation of a managed user.

    Password hashes and other identity internals never cross this boundary.
    """

    id: str
    email: str
    role: str
    active: bool

    @classmethod
    def from_user(cls, user) -> "UserView":
        return cls(user.id, user.email, user.role, user.active)


class ManagementRouter:
    """Framework-agnostic application boundary for management operations.

    Authentication is resolved from the existing IdentityService token API.
    The management services remain the source of authorization and business
    rules; this class only adapts authenticated calls into safe views/results.
    """

    def __init__(
        self,
        identity,
        *,
        users: UserManagement | None = None,
        admins: AdminManagement | None = None,
        providers: ProviderManagement | None = None,
        ai_providers: AIProviderManagement | None = None,
        audit: AuditTrail | None = None,
    ) -> None:
        self.identity = identity
        self.users = users or UserManagement(identity)
        self.admins = admins or AdminManagement(identity)
        self.providers = providers
        self.ai_providers = ai_providers
        self.audit = audit

    def _audit(self, event_type: str, actor, target: str, *, outcome: str = "success", metadata: dict | None = None) -> None:
        if self.audit is None:
            return
        details = {"actor_id": actor.id, "actor_role": actor.role}
        if metadata:
            details.update(metadata)
        self.audit.append(
            event_type,
            str(target),
            outcome=outcome,
            metadata=details,
        )

    def _actor(self, token):
        actor = self.identity.current_user(token)
        if actor is None:
            raise PermissionError("authentication required")
        return actor

    # User management -------------------------------------------------
    def list_users(self, token, *, active: bool | None = None) -> tuple[UserView, ...]:
        actor = self._actor(token)
        return tuple(UserView.from_user(user) for user in self.users.list(actor, active=active))

    def get_user(self, token, user_id: str) -> UserView | None:
        actor = self._actor(token)
        user = self.users.get(actor, user_id)
        return UserView.from_user(user) if user is not None else None

    def set_user_active(self, token, user_id: str, active: bool) -> UserView:
        actor = self._actor(token)
        result = self.users.set_active(actor, user_id, active)
        self._audit("user_activation_changed", actor, user_id, metadata={"active": bool(active)})
        return UserView.from_user(result)

    # Admin management ------------------------------------------------
    def grant_admin(self, token, user_id: str) -> UserView:
        actor = self._actor(token)
        result = self.admins.grant(actor, user_id)
        self._audit("admin_granted", actor, user_id)
        return UserView.from_user(result)

    def revoke_admin(self, token, user_id: str, *, fallback_role: str | None = None) -> UserView:
        actor = self._actor(token)
        if fallback_role is None:
            result = self.admins.revoke(actor, user_id)
        else:
            result = self.admins.revoke(actor, user_id, fallback_role=fallback_role)
        self._audit("admin_revoked", actor, user_id, metadata={"fallback_role": result.role})
        return UserView.from_user(result)

    # Provider management ---------------------------------------------
    def _providers(self) -> ProviderManagement:
        if self.providers is None:
            raise RuntimeError("provider management is not configured")
        return self.providers

    def list_providers(self, token, *, enabled_only: bool = False) -> tuple[str, ...]:
        actor = self._actor(token)
        return self._providers().list(actor, enabled_only=enabled_only)

    def enable_provider(self, token, name: str) -> tuple[str, ...]:
        actor = self._actor(token)
        result = self._providers().enable(actor, name)
        self._audit("provider_enabled", actor, name)
        return result

    def disable_provider(self, token, name: str) -> tuple[str, ...]:
        actor = self._actor(token)
        result = self._providers().disable(actor, name)
        self._audit("provider_disabled", actor, name)
        return result

    def register_provider(
        self,
        token,
        name: str,
        factory: Callable,
        *,
        enabled: bool = True,
        replace: bool = False,
    ) -> tuple[str, ...]:
        actor = self._actor(token)
        result = self._providers().register(
            actor, name, factory, enabled=enabled, replace=replace
        )
        self._audit(
            "provider_registered",
            actor,
            name,
            metadata={"enabled": bool(enabled), "replace": bool(replace)},
        )
        return result

    def remove_provider(self, token, name: str) -> tuple[str, ...]:
        actor = self._actor(token)
        result = self._providers().remove(actor, name)
        self._audit("provider_removed", actor, name)
        return result

    # AI provider management ------------------------------------------
    def _ai(self) -> AIProviderManagement:
        if self.ai_providers is None:
            raise RuntimeError("AI provider management is not configured")
        return self.ai_providers

    def list_ai_providers(self, token) -> tuple[AIProviderView, ...]:
        actor = self._actor(token)
        return self._ai().list(actor)

    def connect_ai_provider(self, token, name: str, credential: str, *, base_url: str | None = None) -> AIProviderView:
        actor = self._actor(token)
        result = self._ai().connect(actor, name, credential, base_url=base_url)
        self._audit("ai_provider_connected", actor, name, metadata={"enabled": result.enabled, "models": list(result.models)})
        return result

    def test_ai_provider(self, token, name: str) -> tuple[str, ...]:
        actor = self._actor(token)
        result = self._ai().test(actor, name)
        self._audit("ai_provider_tested", actor, name, metadata={"models": list(result)})
        return result

    def enable_ai_provider(self, token, name: str) -> AIProviderView:
        actor = self._actor(token)
        result = self._ai().enable(actor, name)
        self._audit("ai_provider_enabled", actor, name)
        return result

    def disable_ai_provider(self, token, name: str) -> AIProviderView:
        actor = self._actor(token)
        result = self._ai().disable(actor, name)
        self._audit("ai_provider_disabled", actor, name)
        return result

    def replace_ai_credential(self, token, name: str, credential: str) -> AIProviderView:
        actor = self._actor(token)
        result = self._ai().replace(actor, name, credential)
        self._audit("ai_credential_replaced", actor, name)
        return result

    def revoke_ai_provider(self, token, name: str) -> AIProviderView:
        actor = self._actor(token)
        result = self._ai().revoke(actor, name)
        self._audit("ai_provider_revoked", actor, name)
        return result

    def set_ai_provider_model(self, token, name: str, model: str) -> AIProviderView:
        actor = self._actor(token)
        result = self._ai().set_model(actor, name, model)
        self._audit("ai_provider_model_selected", actor, name, metadata={"model": model})
        return result
