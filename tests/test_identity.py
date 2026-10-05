from datetime import datetime, timedelta, timezone

import pytest

from app.identity import IdentityService, IdentityStore, OAuthStateStore, PasswordHasher, PasswordPolicyError
from app.identity.authorization import Permission


def make_service():
    store = IdentityStore()
    return IdentityService(store), store


def test_password_hash_is_salted_and_verifies():
    hasher = PasswordHasher()
    a = hasher.hash("correct horse battery staple")
    b = hasher.hash("correct horse battery staple")
    assert a != b
    assert hasher.verify("correct horse battery staple", a)
    assert not hasher.verify("wrong password", a)


def test_password_policy():
    with pytest.raises(PasswordPolicyError):
        PasswordHasher().hash("short")


def test_register_normalizes_email_and_authenticates():
    service, store = make_service()
    user = service.register(" User@Example.COM ", "correct horse battery staple")
    assert user.email == "user@example.com"
    token = service.authenticate("USER@example.com", "correct horse battery staple")
    assert service.current_user(token).id == user.id
    store.close()


def test_duplicate_email_rejected():
    service, _ = make_service()
    service.register("user@example.com", "correct horse battery staple")
    with pytest.raises(ValueError, match="already registered"):
        service.register("USER@example.com", "another correct password")


def test_invalid_credentials_do_not_create_session():
    service, _ = make_service()
    service.register("user@example.com", "correct horse battery staple")
    with pytest.raises(PermissionError, match="invalid credentials"):
        service.authenticate("user@example.com", "wrong password")


def test_logout_revokes_session():
    service, _ = make_service()
    service.register("user@example.com", "correct horse battery staple")
    token = service.authenticate("user@example.com", "correct horse battery staple")
    assert service.current_user(token) is not None
    service.logout(token)
    assert service.current_user(token) is None


def test_inactive_user_cannot_authenticate_or_resolve():
    service, store = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    store.set_active(user.id, False)
    with pytest.raises(PermissionError):
        service.authenticate("user@example.com", "correct horse battery staple")


def test_session_token_is_not_stored_in_plaintext():
    service, store = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    token = service.authenticate(user.email, "correct horse battery staple")
    row = store._conn.execute("SELECT token_hash FROM sessions").fetchone()
    assert row["token_hash"] != token
    assert len(row["token_hash"]) == 64


def test_user_has_execution_permission_but_not_admin_permissions():
    service, store = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    assert service.authorization.has_permission(user, Permission.EXECUTE)
    assert not service.authorization.has_permission(user, Permission.MANAGE_USERS)


def test_consent_can_be_granted_checked_and_revoked():
    service, _ = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    assert not service.authorization.has_consent(user, "physical-action", "v1")
    service.authorization.grant_consent(user, "physical-action", "v1")
    assert service.authorization.has_consent(user, "physical-action", "v1")
    assert not service.authorization.has_consent(user, "physical-action", "v2")
    service.authorization.revoke_consent(user, "physical-action")
    assert not service.authorization.has_consent(user, "physical-action", "v1")


def test_require_consent_rejects_missing_consent():
    service, _ = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    with pytest.raises(PermissionError, match="consent"):
        service.authorization.require_consent(user, "physical-action", "v1")


def test_admin_permissions_are_separate():
    service, store = make_service()
    admin = store.create_user("admin@example.com", service.passwords.hash("correct horse battery staple"), role="admin")
    assert service.authorization.has_permission(admin, Permission.MANAGE_USERS)
    assert service.authorization.has_permission(admin, Permission.VIEW_AUDIT)


def test_execution_requires_authenticated_session():
    service, _ = make_service()
    with pytest.raises(PermissionError, match="authentication"):
        service.require_execution("invalid-token")


def test_execution_requirement_accepts_normal_user():
    service, _ = make_service()
    user = service.register("user@example.com", "correct horse battery staple")
    token = service.authenticate(user.email, "correct horse battery staple")
    assert service.require_execution(token).id == user.id


def test_oauth_state_persists_across_store_instances():
    identity_store = IdentityStore()
    first = OAuthStateStore(identity_store)
    state, verifier = first.issue("user-1", "example")
    second = OAuthStateStore(identity_store)
    assert second.consume(state, "user-1", "example") == verifier
    assert second.consume(state, "user-1", "example") is None
    identity_store.close()


def test_oauth_state_is_one_time_and_bound_to_user():
    states = OAuthStateStore()
    state, verifier = states.issue("user-1", "example")
    assert states.consume(state, "user-2", "example") is None
    assert states.consume(state, "user-1", "example") == verifier
    assert states.consume(state, "user-1", "example") is None


def test_oauth_state_binds_provider_and_does_not_consume_on_mismatch():
    states = OAuthStateStore()
    state, verifier = states.issue("user-1", "example")
    assert states.consume(state, "user-1", "other") is None
    assert states.consume(state, "user-1", "example") == verifier


def test_oauth_state_rejects_empty_identity():
    with pytest.raises(ValueError):
        OAuthStateStore().issue("", "example")


def test_oauth_state_expiration():
    states = OAuthStateStore(ttl_seconds=1)
    state, _ = states.issue("user-1", "example")
    key = states._hash(state)
    user, provider, verifier, _ = states._states[key]
    states._states[key] = (user, provider, verifier, datetime.now(timezone.utc) - timedelta(seconds=1))
    assert states.consume(state, "user-1", "example") is None


def test_password_hash_parser_rejects_malformed_value():
    assert not PasswordHasher().verify("correct horse battery staple", "not-a-valid-hash")


def test_unknown_role_has_no_permissions():
    service, store = make_service()
    user = store.create_user("unknown@example.com", service.passwords.hash("correct horse battery staple"), role="user")
    object.__setattr__(user, "role", "unknown")
    assert not service.authorization.has_permission(user, Permission.EXECUTE)


def test_sqlite_is_refused_outside_local_test_and_development(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "sandbox")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SANOVA_IDENTITY_DB", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        IdentityStore()


def test_postgres_url_normalization_requires_postgresql_and_enables_tls():
    normalized = IdentityStore._normalize_postgres_url("postgresql://user:pass@example.test/db")
    assert "sslmode=require" in normalized

    explicit = IdentityStore._normalize_postgres_url(
        "postgresql://user:pass@example.test/db?sslmode=verify-full"
    )
    assert "sslmode=verify-full" in explicit

    with pytest.raises(ValueError, match="PostgreSQL connection URL"):
        IdentityStore._normalize_postgres_url("sqlite:///identity.sqlite3")


def test_postgres_store_reconnects_after_closed_connection(monkeypatch):
    psycopg = pytest.importorskip("psycopg")
    from app.identity.store import IdentityStore

    class FakeCursor:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, sql, params=()):
            if self.connection.fail_once:
                self.connection.fail_once = False
                raise psycopg.OperationalError("the connection is closed")
            return self

        def fetchone(self):
            return None

    class FakeConnection:
        def __init__(self, fail_once=False):
            self.fail_once = fail_once
            self.closed = False
            self.autocommit = False

        def cursor(self):
            return FakeCursor(self)

        def commit(self):
            pass

        def close(self):
            self.closed = True

    connections = [FakeConnection()]
    monkeypatch.setattr(psycopg, "connect", lambda *args, **kwargs: connections.pop(0))

    store = object.__new__(IdentityStore)
    store._backend = "postgres"
    store._database_url = "postgresql://user:pass@example.test/db"
    store._conn = FakeConnection(fail_once=True)

    monkeypatch.setattr(store, "_initialize_postgres", lambda: None)
    result = store._execute("SELECT 1", ())
    assert result is not None
