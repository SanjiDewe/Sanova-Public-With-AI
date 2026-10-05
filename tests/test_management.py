import pytest

from app.identity import IdentityService, IdentityStore
from app.identity.authorization import Permission, RoleDefinition, RoleRegistry
from app.integrations.registry import ProviderRegistry
from app.management import AdminManagement, ProviderManagement, UserManagement

PASSWORD = "correct horse battery staple"


def make_identity(roles=None):
    store = IdentityStore()
    return IdentityService(store, roles=roles), store


def test_user_management_requires_permission_and_can_toggle_account():
    identity, store = make_identity()
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    user = identity.register("user@example.com", PASSWORD)
    management = UserManagement(identity)
    assert [u.email for u in management.list(admin)] == ["admin@example.com", "user@example.com"]
    updated = management.set_active(admin, user.id, False)
    assert not updated.active
    with pytest.raises(PermissionError):
        management.list(user)


def test_user_management_prevents_self_deactivation():
    identity, store = make_identity()
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    with pytest.raises(ValueError, match="current administrator"):
        UserManagement(identity).set_active(admin, admin.id, False)


def test_admin_management_is_separate_and_injectable():
    identity, store = make_identity()
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    user = identity.register("user@example.com", PASSWORD)
    management = AdminManagement(identity)
    assert management.grant(admin, user.id).role == "admin"
    assert management.revoke(admin, user.id).role == "user"
    with pytest.raises(ValueError, match="current administrator"):
        management.revoke(admin, admin.id)


def test_role_registry_allows_custom_management_role_without_hardcoding_permissions():
    roles = RoleRegistry()
    roles.register(RoleDefinition("operator", frozenset({Permission.EXECUTE, Permission.MANAGE_USERS})))
    identity, store = make_identity(roles)
    operator = store.create_user("operator@example.com", identity.passwords.hash(PASSWORD), role="operator")
    user = identity.register("user@example.com", PASSWORD)
    assert UserManagement(identity).get(operator, user.id).id == user.id


def test_provider_management_delegates_to_injected_registry():
    identity, store = make_identity()
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    registry = ProviderRegistry()
    registry.register("alpha", lambda: object())
    management = ProviderManagement(identity, registry)
    assert management.list(admin) == ("alpha",)
    management.disable(admin, "alpha")
    assert management.list(admin, enabled_only=True) == ()
    management.enable(admin, "alpha")
    management.register(admin, "beta", lambda: object())
    assert set(management.list(admin)) == {"alpha", "beta"}
    management.remove(admin, "beta")
    assert management.list(admin) == ("alpha",)


def test_provider_management_does_not_accept_normal_user():
    identity, _ = make_identity()
    user = identity.register("user@example.com", PASSWORD)
    registry = ProviderRegistry()
    registry.register("alpha", lambda: object())
    with pytest.raises(PermissionError):
        ProviderManagement(identity, registry).list(user)


def test_provider_management_supports_registry_replace_without_provider_hardcoding():
    identity, store = make_identity()
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    registry = ProviderRegistry()
    first = lambda: "first"
    second = lambda: "second"
    registry.register("alpha", first)
    management = ProviderManagement(identity, registry)

    with pytest.raises(ValueError, match="provider already registered"):
        management.register(admin, "alpha", second)

    management.register(admin, "alpha", second, replace=True)
    assert registry.get("alpha") == "second"
    store.close()


def test_provider_management_validates_factory_at_management_boundary():
    identity, store = make_identity()
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    registry = ProviderRegistry()
    management = ProviderManagement(identity, registry)

    with pytest.raises(TypeError, match="provider factory must be callable"):
        management.register(admin, "alpha", object())

    assert registry.names() == ()
    store.close()
