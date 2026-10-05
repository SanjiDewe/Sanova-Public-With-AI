import pytest

from app.identity import IdentityService, IdentityStore
from app.identity.authorization import Permission, RoleDefinition, RoleRegistry
from app.integrations.registry import ProviderRegistry
from app.management import AdminManagement, ManagementRouter, ProviderManagement

PASSWORD = "correct horse battery staple"


def make_router():
    store = IdentityStore()
    identity = IdentityService(store)
    admin = store.create_user(
        "admin@example.com", identity.passwords.hash(PASSWORD), role="admin"
    )
    user = identity.register("user@example.com", PASSWORD)
    admin_token = identity.authenticate(admin.email, PASSWORD)
    user_token = identity.authenticate(user.email, PASSWORD)
    registry = ProviderRegistry()
    registry.register("alpha", lambda: object())
    router = ManagementRouter(
        identity,
        providers=ProviderManagement(identity, registry),
    )
    return identity, store, router, admin, user, admin_token, user_token


def test_router_authenticates_before_management_operations():
    _, store, router, *_ = make_router()
    with pytest.raises(PermissionError, match="authentication required"):
        router.list_users("not-a-token")
    store.close()


def test_router_returns_safe_user_views_without_password_hash():
    identity, store, router, admin, user, admin_token, _ = make_router()
    result = router.get_user(admin_token, user.id)
    assert result.email == user.email
    assert result.role == "user"
    assert result.active is True
    assert not hasattr(result, "password_hash")
    assert result.id == user.id
    store.close()


def test_router_delegates_user_and_admin_management():
    _, store, router, _, user, admin_token, _ = make_router()
    disabled = router.set_user_active(admin_token, user.id, False)
    assert disabled.active is False
    enabled = router.set_user_active(admin_token, user.id, True)
    assert enabled.active is True
    promoted = router.grant_admin(admin_token, user.id)
    assert promoted.role == "admin"
    demoted = router.revoke_admin(admin_token, user.id)
    assert demoted.role == "user"
    store.close()


def test_router_delegates_provider_management():
    _, store, router, _, _, admin_token, _ = make_router()
    assert router.list_providers(admin_token) == ("alpha",)
    assert router.disable_provider(admin_token, "alpha") == ("alpha",)
    assert router.list_providers(admin_token, enabled_only=True) == ()
    assert router.enable_provider(admin_token, "alpha") == ("alpha",)
    router.register_provider(admin_token, "beta", lambda: object())
    assert set(router.list_providers(admin_token)) == {"alpha", "beta"}
    router.remove_provider(admin_token, "beta")
    assert router.list_providers(admin_token) == ("alpha",)
    store.close()


def test_router_uses_injected_admin_fallback_role():
    store = IdentityStore()
    roles = RoleRegistry()
    roles.register(RoleDefinition("operator", frozenset({Permission.EXECUTE})))
    identity = IdentityService(store)
    identity.authorization.roles = roles
    admin = store.create_user(
        "admin@example.com", identity.passwords.hash(PASSWORD), role="admin"
    )
    user = identity.register("user@example.com", PASSWORD)
    admin_token = identity.authenticate(admin.email, PASSWORD)
    router = ManagementRouter(
        identity,
        admins=AdminManagement(identity, fallback_role="operator"),
    )
    router.grant_admin(admin_token, user.id)
    demoted = router.revoke_admin(admin_token, user.id)
    assert demoted.role == "operator"
    store.close()


def test_router_preserves_management_authorization():
    _, store, router, _, user, _, user_token = make_router()
    with pytest.raises(PermissionError):
        router.list_users(user_token)
    with pytest.raises(PermissionError):
        router.list_providers(user_token)
    assert user.active
    store.close()


def test_router_can_register_disabled_provider_and_replace_it():
    _, store, router, _, _, admin_token, _ = make_router()
    router.register_provider(admin_token, "beta", lambda: "first", enabled=False)
    assert router.list_providers(admin_token) == ("alpha", "beta")
    assert router.list_providers(admin_token, enabled_only=True) == ("alpha",)

    router.register_provider(admin_token, "beta", lambda: "second", replace=True)
    assert router.list_providers(admin_token, enabled_only=True) == ("alpha", "beta")
    store.close()


def test_router_rejects_non_callable_provider_factory():
    _, store, router, _, _, admin_token, _ = make_router()
    with pytest.raises(TypeError, match="provider factory must be callable"):
        router.register_provider(admin_token, "beta", object())
    assert router.list_providers(admin_token) == ("alpha",)
    store.close()


def test_management_router_audits_user_admin_and_provider_mutations():
    from app.audit.trail import AuditTrail
    from app.integrations.registry import ProviderRegistry
    from app.management.admins import AdminManagement
    from app.management.providers import ProviderManagement
    from app.management.router import ManagementRouter

    identity, store, _, admin, target, admin_token, _ = make_router()
    registry = ProviderRegistry()
    audit = AuditTrail()
    router = ManagementRouter(
        identity,
        admins=AdminManagement(identity),
        providers=ProviderManagement(identity, registry),
        audit=audit,
    )

    router.set_user_active(admin_token, target.id, False)
    router.set_user_active(admin_token, target.id, True)
    router.grant_admin(admin_token, target.id)
    router.revoke_admin(admin_token, target.id)
    router.register_provider(admin_token, "synthetic", lambda: object())
    router.enable_provider(admin_token, "synthetic")
    router.disable_provider(admin_token, "synthetic")
    router.remove_provider(admin_token, "synthetic")

    types = [event.event_type for event in audit.events()]
    assert types == [
        "user_activation_changed",
        "user_activation_changed",
        "admin_granted",
        "admin_revoked",
        "provider_registered",
        "provider_enabled",
        "provider_disabled",
        "provider_removed",
    ]
    assert all(event.metadata["actor_id"] == identity.current_user(admin_token).id for event in audit.events())
    assert audit.verify()
    store.close()


def test_management_router_audit_is_optional_and_does_not_change_results():
    identity, store, router, _, target, admin_token, _ = make_router()
    result = router.set_user_active(admin_token, target.id, False)
    assert result.id == target.id
    assert result.active is False
    store.close()
