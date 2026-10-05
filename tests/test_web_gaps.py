import pytest
from fastapi.testclient import TestClient

from app.integrations.email.mock import MockEmailProvider
from app.integrations.contracts.oauth import OAuthIdentity, OAuthToken
from app.integrations.contracts.oauth import OAuthAuthorization
from app.web.app import create_app

PASSWORD = "correct horse battery staple"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SANOVA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("SANOVA_IDENTITY_DB", str(tmp_path / "identity.sqlite3"))
    monkeypatch.setenv("SANOVA_STATE_DIR", str(tmp_path / "tasks"))
    monkeypatch.setenv("SANOVA_AUDIT_DIR", str(tmp_path / "audit"))
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def login(client, email="admin@example.com"):
    client.post("/signup", data={"email": email, "password": PASSWORD})
    import re
    code = re.search(r"\b(\d{6})\b", MockEmailProvider.sent[-1].text).group(1)
    client.post("/verify-email", data={"email": email, "code": code})
    client.post("/login", data={"email": email, "password": PASSWORD})


def make_admin(client, monkeypatch):
    login(client)
    monkeypatch.setenv("SANOVA_SUPER_ADMIN_ACCESS_CODE", "test-super-code")
    client.app.state.sanova.identity.authorization.has_permission = lambda actor, permission: True
    response = client.post("/super-admin/access", data={"access_code": "test-super-code"}, follow_redirects=False)
    assert response.status_code == 303
    response = client.post(
        "/super-admin/login",
        data={"email": "admin@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_email_test_and_oauth_ui(client, monkeypatch):
    login(client, "user@example.com")
    response = client.post("/app/integrations/email/test", data={"recipient": "user@example.com"}, follow_redirects=False)
    assert response.status_code == 303
    assert MockEmailProvider.sent
    assert client.get("/app/integrations").status_code == 200
    assert "/oauth/google/start" in client.get("/app/integrations").text


def test_e2e_simulation_and_webhook_ui(client):
    login(client, "runner@example.com")
    response = client.post("/app/simulate", data={"intent": "make 1 mug using design.png and ship to TEST-DESTINATION", "provider": "mock"})
    assert response.status_code == 200
    assert "simulation completed and verified" in response.text


def test_admin_user_detail_and_provider_lifecycle_ui(client, monkeypatch):
    make_admin(client, monkeypatch)
    response = client.get("/super-admin")
    assert response.status_code == 200
    assert "/super-admin/users/" in response.text
    import re
    user_id = re.search(r"/super-admin/users/([0-9a-f-]+)", response.text).group(1)
    assert client.get(f"/super-admin/users/{user_id}").status_code == 200
    client.post("/super-admin/providers/mock", data={"action": "remove"}, follow_redirects=False)
    client.post("/super-admin/providers/register", data={"name": "mock"}, follow_redirects=False)
    assert "mock" in client.app.state.sanova.physical_registry.names()


class FakeGoogleProvider:
    name = "google"

    class _Config:
        client_id = "test-client"
        redirect_uri = "http://testserver/oauth/callback"

    config = _Config()

    def authorization_url(self, state, redirect_uri=None, scopes=(), code_verifier=None):
        suffix = f"&code_challenge={code_verifier}&code_challenge_method=S256" if code_verifier else ""
        return OAuthAuthorization(f"https://accounts.google.com/o/oauth2/v2/auth?state={state}{suffix}", state)

    def exchange_code(self, code, redirect_uri=None, code_verifier=None):
        assert code_verifier
        return OAuthToken(access_token="access-token", refresh_token="refresh-token")

    def identity_from_userinfo(self, access_token):
        return OAuthIdentity("google", "google-sub", "google@example.com", "Google User")


def test_google_oauth_is_visible_on_public_auth_pages_when_configured(client, monkeypatch):
    monkeypatch.setenv("SANOVA_OAUTH_PROVIDER", "google")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "http://testserver/oauth/callback")
    client.app.state.sanova.oauth_registry.register("google", FakeGoogleProvider, replace=True)
    assert "Continue with Google" in client.get("/login").text
    assert "Continue with Google" in client.get("/signup").text


def test_google_oauth_login_creates_session_from_callback(client, monkeypatch):
    monkeypatch.setenv("SANOVA_OAUTH_PROVIDER", "google")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "http://testserver/oauth/callback")
    client.app.state.sanova.oauth_registry.register("google", FakeGoogleProvider, replace=True)
    start = client.get("/oauth/google/start?mode=login", follow_redirects=False)
    assert start.status_code == 303
    from urllib.parse import parse_qs, urlsplit
    state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
    callback = client.get(f"/oauth/callback?code=test-code&state={state}", follow_redirects=False)
    assert callback.status_code == 303
    assert callback.headers["location"] == "/app"
    assert "sanova_session=" in callback.headers["set-cookie"]
    assert client.get("/app").status_code == 200



def test_email_signup_requires_verification_code(client):
    response = client.post("/signup", data={"email": "pending@example.com", "password": PASSWORD}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/verify-email?email=")
    blocked = client.post("/login", data={"email": "pending@example.com", "password": PASSWORD}, follow_redirects=False)
    assert blocked.status_code == 200
    code = __import__("re").search(r"\b(\d{6})\b", MockEmailProvider.sent[-1].text).group(1)
    verified = client.post("/verify-email", data={"email": "pending@example.com", "code": code}, follow_redirects=False)
    assert verified.status_code == 303
    login_response = client.post("/login", data={"email": "pending@example.com", "password": PASSWORD}, follow_redirects=False)
    assert login_response.status_code == 303


def test_google_oauth_uses_pkce_challenge(client, monkeypatch):
    monkeypatch.setenv("SANOVA_OAUTH_PROVIDER", "google")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "http://testserver/oauth/callback")
    client.app.state.sanova.oauth_registry.register("google", FakeGoogleProvider, replace=True)
    start = client.get("/oauth/google/start?mode=login", follow_redirects=False)
    assert start.status_code == 303
    assert "code_challenge=" in start.headers["location"]
    assert "code_challenge_method=S256" in start.headers["location"]

def test_google_oauth_connect_requires_authenticated_user(client, monkeypatch):
    monkeypatch.setenv("SANOVA_OAUTH_PROVIDER", "google")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "test-client")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "http://testserver/oauth/callback")
    response = client.get("/oauth/google/start", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/login")
