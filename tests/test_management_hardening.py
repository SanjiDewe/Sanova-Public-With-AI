import pytest

from app.audit.trail import AuditTrail
from app.identity import IdentityService, IdentityStore
from app.identity.authorization import Permission, RoleDefinition, RoleRegistry
from app.integrations.registry import ProviderRegistry
from app.management import AdminManagement, ProviderManagement, UserManagement, ManagementRouter

PASSWORD = "correct horse battery staple"


def make_context():
    store = IdentityStore()
    identity = IdentityService(store)
    admin = store.create_user("admin@example.com", identity.passwords.hash(PASSWORD), role="admin")
    user = identity.register("user@example.com", PASSWORD)
    admin_token = identity.authenticate(admin.email, PASSWORD)
    user_token = identity.authenticate(user.email, PASSWORD)
    registry = ProviderRegistry()
    registry.register("alpha", lambda: object())
    return store, identity, admin, user, admin_token, user_token, registry


def test_revoked_management_session_cannot_mutate():
    store, identity, admin, user, admin_token, _, registry = make_context()
    identity.logout(admin_token)
    router = ManagementRouter(identity, providers=ProviderManagement(identity, registry))
    with pytest.raises(PermissionError, match="authentication required"):
        router.set_user_active(admin_token, user.id, False)
    assert store.get_user(user.id).active is True
    store.close()


def test_deactivated_management_actor_cannot_mutate():
    store, identity, admin, user, admin_token, _, registry = make_context()
    store.set_active(admin.id, False)
    router = ManagementRouter(identity, providers=ProviderManagement(identity, registry))
    with pytest.raises(PermissionError, match="authentication required"):
        router.list_providers(admin_token)
    store.close()


def test_execute_only_role_cannot_manage_anything():
    roles = RoleRegistry()
    roles.register(RoleDefinition("operator", frozenset({Permission.EXECUTE})))
    store = IdentityStore()
    identity = IdentityService(store, roles=roles)
    operator = store.create_user("operator@example.com", identity.passwords.hash(PASSWORD), role="operator")
    user = identity.register("user@example.com", PASSWORD)
    registry = ProviderRegistry()
    registry.register("alpha", lambda: object())
    router = ManagementRouter(identity, providers=ProviderManagement(identity, registry))

    with pytest.raises(PermissionError):
        router.list_users(identity.authenticate(operator.email, PASSWORD))
    with pytest.raises(PermissionError):
        router.grant_admin(identity.authenticate(operator.email, PASSWORD), user.id)
    with pytest.raises(PermissionError):
        router.list_providers(identity.authenticate(operator.email, PASSWORD))
    store.close()


def test_management_views_never_expose_password_hash():
    store, identity, admin, user, admin_token, _, registry = make_context()
    router = ManagementRouter(identity, providers=ProviderManagement(identity, registry))
    views = router.list_users(admin_token)
    assert views
    for view in views:
        assert not hasattr(view, "password_hash")
    store.close()


def test_provider_registration_does_not_execute_factory():
    store, identity, admin, _, admin_token, _, registry = make_context()
    calls = []

    def factory():
        calls.append("executed")
        return object()

    router = ManagementRouter(identity, providers=ProviderManagement(identity, registry))
    router.register_provider(admin_token, "lazy", factory)
    assert calls == []
    store.close()


def test_failed_management_mutation_is_not_audited():
    store, identity, admin, user, admin_token, _, registry = make_context()
    audit = AuditTrail()
    router = ManagementRouter(
        identity,
        providers=ProviderManagement(identity, registry),
        audit=audit,
    )
    with pytest.raises(ValueError):
        router.set_user_active(admin_token, admin.id, False)
    assert audit.events() == []
    store.close()


def test_audit_cannot_be_spoofed_by_management_input():
    store, identity, admin, user, admin_token, _, registry = make_context()
    audit = AuditTrail()
    router = ManagementRouter(
        identity,
        providers=ProviderManagement(identity, registry),
        audit=audit,
    )
    router.set_user_active(admin_token, user.id, False)
    event = audit.events()[0]
    assert event.metadata["actor_id"] == admin.id
    assert event.task_id == user.id
    store.close()
