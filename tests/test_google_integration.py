from datetime import datetime, timedelta, timezone

from app.identity import IdentityStore
from app.integrations.accounts import ConnectedAccountStore
from app.integrations.google import GoogleClient, GoogleService
from app.integrations.oauth.google import GoogleOAuthProvider


def test_google_client_encodes_path_segments_for_workspace_apis(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "test")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "https://example.test/oauth/callback")
    client = GoogleClient(None, GoogleOAuthProvider())
    calls = []

    def fake_request(user_id, method, url, *, query=None, body=None):
        calls.append((method, url, query, body))
        return {}

    client.request = fake_request
    client.gmail_get_message("user", "message/id")
    client.calendar_list_events("user", calendar_id="team@example.com")
    client.calendar_create_event("user", summary="Meeting", start={}, end={}, calendar_id="team@example.com")
    client.sheets_get("user", "sheet/id", "My Sheet!A1:B2")
    client.sheets_update("user", "sheet/id", "My Sheet!A1:B2", [["value"]])

    urls = [call[1] for call in calls]
    assert "/messages/message%2Fid" in urls[0]
    assert "/calendars/team%40example.com/events" in urls[1]
    assert "/calendars/team%40example.com/events" in urls[2]
    assert "/spreadsheets/sheet%2Fid/values/My%20Sheet%21A1%3AB2" in urls[3]
    assert "/spreadsheets/sheet%2Fid/values/My%20Sheet%21A1%3AB2" in urls[4]



def test_google_service_reports_connection(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "test")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "https://example.test/oauth/callback")
    store = IdentityStore()
    user = store.create_user("google@example.com", "hash")
    accounts = ConnectedAccountStore(store)
    service = GoogleService(accounts, GoogleOAuthProvider())
    assert service.connected(user.id) is False
    accounts.save(
        user_id=user.id, provider="google", external_subject="sub", email=user.email,
        access_token="access", refresh_token="refresh", expires_in=3600, scopes=("openid",),
    )
    assert service.connected(user.id) is True
    service.disconnect(user.id)
    assert service.connected(user.id) is False
    store.close()


def test_google_oauth_scopes_include_workspace_apis(monkeypatch):
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "https://example.test/oauth/callback")
    monkeypatch.delenv("SANOVA_GOOGLE_OAUTH_SCOPES", raising=False)
    provider = GoogleOAuthProvider()
    scopes = provider.config.scopes
    assert "https://www.googleapis.com/auth/gmail.readonly" in scopes
    assert "https://www.googleapis.com/auth/gmail.send" in scopes
    assert "https://www.googleapis.com/auth/calendar" in scopes
    assert "https://www.googleapis.com/auth/spreadsheets" in scopes


def test_connected_account_normalizes_postgres_datetime_and_preserves_refresh_scopes(monkeypatch):
    # The storage normalization is exercised with the same native datetime
    # type psycopg returns for TIMESTAMPTZ columns.
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "test")
    store = IdentityStore()
    user = store.create_user("google-types@example.com", "hash")
    accounts = ConnectedAccountStore(store)
    accounts.save(
        user_id=user.id, provider="google", external_subject="sub", email=user.email,
        access_token="access", refresh_token="refresh", expires_in=3600,
        scopes=("openid", "calendar"),
    )
    raw = store.get_connected_account(user.id, "google")
    # SQLite returns text; replace the row value with a datetime through a
    # tiny fake identity-store adapter to exercise the PostgreSQL normalization.
    class FakeIdentityStore:
        def get_connected_account(self, user_id, provider):
            return {**raw, "expires_at": datetime.now(timezone.utc)}
    normalized = ConnectedAccountStore(FakeIdentityStore()).get(user.id, "google")
    assert normalized is not None
    assert isinstance(normalized.expires_at, str)
    assert normalized.expires_at.endswith("+00:00")
    assert normalized.scopes == ("openid", "calendar")
    store.close()


def test_google_service_exposes_all_workspace_client_operations(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "test")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_ID", "client")
    monkeypatch.setenv("SANOVA_GOOGLE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("SANOVA_GOOGLE_REDIRECT_URI", "https://example.test/oauth/callback")
    store = IdentityStore()
    accounts = ConnectedAccountStore(store)
    service = GoogleService(accounts, GoogleOAuthProvider())
    expected = {
        "gmail_list_messages", "gmail_get_message", "gmail_send",
        "calendar_list_events", "calendar_create_event", "sheets_get", "sheets_update",
    }
    assert expected.issubset({name for name in dir(service) if not name.startswith("_")})
    store.close()
