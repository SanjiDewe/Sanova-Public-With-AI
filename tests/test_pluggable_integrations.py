from app.config import email_provider_config, oauth_provider_config
from app.integrations.contracts.email import EmailMessage
from app.integrations.email import BrevoEmailProvider, email_provider
from app.integrations.oauth import GoogleOAuthProvider, oauth_provider
from app.integrations.registry import ProviderRegistry


def test_registry_supports_add_replace_disable_and_remove():
    registry = ProviderRegistry()
    registry.register("first", lambda: "one")
    assert registry.get("first") == "one"
    registry.register("first", lambda: "two", replace=True)
    assert registry.get("first") == "two"
    registry.disable("first")
    try:
        registry.get("first")
        assert False, "disabled provider should not be selectable"
    except RuntimeError:
        pass
    registry.enable("first")
    assert registry.get("first") == "two"
    registry.unregister("first")
    assert "first" not in registry.names()


def test_email_provider_selection_is_configuration_driven(monkeypatch):
    monkeypatch.setenv("SANOVA_EMAIL_PROVIDER", "mock")
    provider = email_provider()
    result = provider.send(EmailMessage("user@example.com", "hello", "world"))
    assert result.accepted is True
    assert result.provider == "mock"


def test_brevo_never_needs_credentials_until_used(monkeypatch):
    monkeypatch.delenv("SANOVA_BREVO_API_KEY", raising=False)
    monkeypatch.delenv("SANOVA_EMAIL_FROM", raising=False)
    provider = BrevoEmailProvider()
    assert provider.config.api_key is None


def test_oauth_provider_selection_is_configuration_driven(monkeypatch):
    monkeypatch.setenv("SANOVA_OAUTH_PROVIDER", "mock")
    provider = oauth_provider()
    auth = provider.authorization_url("state-123")
    assert auth.state == "state-123"
    assert auth.url.startswith("mock://authorize")


def test_google_oauth_url_uses_runtime_configuration(monkeypatch):
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "client-from-env")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "https://example.test/oauth/callback")
    monkeypatch.setenv("SANOVA_GOOGLE_OAUTH_SCOPES", "openid,email")
    provider = GoogleOAuthProvider()
    auth = provider.authorization_url("state-xyz")
    assert "client_id=client-from-env" in auth.url
    assert "state=state-xyz" in auth.url
    assert "scope=openid+email" in auth.url


def test_physical_provider_can_be_disabled_by_configuration(monkeypatch):
    monkeypatch.setenv("SANOVA_DISABLED_PHYSICAL_PROVIDERS", "prodigi")
    from app.integrations.providers.registry import physical_provider_registry

    registry = physical_provider_registry()
    assert "prodigi" in registry.names()
    assert "prodigi" not in registry.names(enabled_only=True)


def test_connected_google_account_is_persisted_encrypted(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "test")
    from app.identity import IdentityStore
    from app.integrations.accounts import ConnectedAccountStore

    store = IdentityStore()
    user = store.create_user("google@example.com", "hash")
    accounts = ConnectedAccountStore(store)
    account = accounts.save(
        user_id=user.id,
        provider="google",
        external_subject="google-subject",
        email="google@example.com",
        access_token="access-secret",
        refresh_token="refresh-secret",
        expires_in=3600,
        scopes=("openid", "https://www.googleapis.com/auth/calendar"),
    )
    assert account.access_token == "access-secret"
    assert account.refresh_token == "refresh-secret"
    raw = store.get_connected_account(user.id, "google")
    assert raw["access_token"] != "access-secret"
    assert raw["refresh_token"] != "refresh-secret"
    accounts.delete(user.id, "google")
    assert accounts.get(user.id, "google") is None
    store.close()
