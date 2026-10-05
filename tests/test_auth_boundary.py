import pytest

from app.application.service import ExecutionResponse
from app.auth import AuthenticatedApplicationService
from app.auth.service import AuthenticationRequired, ConsentRequired
from app.identity import IdentityService, IdentityStore


class StubApplication:
    def __init__(self):
        self.calls = []

    def execute_intent(self, text):
        self.calls.append(("intent", text))
        return ExecutionResponse("task-1", "completed", True, "ok")

    def execute_spec(self, spec):
        self.calls.append(("spec", spec))
        return ExecutionResponse("task-2", "completed", True, "ok")


def make_service():
    store = IdentityStore()
    identity = IdentityService(store)
    app = StubApplication()
    service = AuthenticatedApplicationService(identity, app)
    return service, store, app


def test_login_and_current_user_are_exposed_at_auth_boundary():
    service, store, _ = make_service()
    user = service.register("User@Example.com", "correct horse battery staple")
    token = service.login("user@example.com", "correct horse battery staple")
    assert service.current_user(token).id == user.id
    service.logout(token)
    assert service.current_user(token) is None
    store.close()


def test_execution_requires_authentication_before_delegation():
    service, _, app = make_service()
    with pytest.raises(AuthenticationRequired, match="authentication"):
        service.execute_intent("invalid", "print a photo")
    assert app.calls == []


def test_execution_requires_consent_before_delegation():
    service, _, app = make_service()
    token = service.login(service.register("user@example.com", "correct horse battery staple").email,
                          "correct horse battery staple")
    with pytest.raises(ConsentRequired, match="consent"):
        service.execute_intent(token, "print a photo")
    assert app.calls == []


def test_execution_delegates_only_after_auth_and_consent():
    service, _, app = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    token = service.login(user.email, "correct horse battery staple")
    service.grant_execution_consent(token)
    result = service.execute_intent(token, "print a photo")
    assert result.accepted is True
    assert app.calls == [("intent", "print a photo")]


def test_revoked_consent_blocks_future_execution():
    service, _, app = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    token = service.login(user.email, "correct horse battery staple")
    service.grant_execution_consent(token)
    service.revoke_execution_consent(token)
    with pytest.raises(ConsentRequired):
        service.execute_intent(token, "print a photo")
    assert app.calls == []


def test_invalid_login_does_not_create_authenticated_boundary():
    service, _, app = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    with pytest.raises(PermissionError, match="invalid credentials"):
        service.login(user.email, "wrong password")
    assert app.calls == []


def test_admin_role_does_not_bypass_execution_consent():
    service, store, app = make_service()
    user = store.create_user(
        "admin@example.com",
        service.identity.passwords.hash("correct horse battery staple"),
        role="admin",
    )
    token = service.login(user.email, "correct horse battery staple")
    with pytest.raises(ConsentRequired):
        service.execute_intent(token, "print a photo")
    assert app.calls == []


def test_logout_invalidates_execution_session():
    service, _, app = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    token = service.login(user.email, "correct horse battery staple")
    service.grant_execution_consent(token)
    service.logout(token)
    with pytest.raises(AuthenticationRequired):
        service.execute_intent(token, "print a photo")
    assert app.calls == []
