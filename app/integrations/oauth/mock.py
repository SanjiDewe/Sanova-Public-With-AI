from __future__ import annotations

from app.integrations.contracts.oauth import OAuthAuthorization, OAuthProvider, OAuthToken


class MockOAuthProvider(OAuthProvider):
    name = "mock"

    def authorization_url(self, state: str, redirect_uri: str | None = None, scopes: tuple[str, ...] = (), code_verifier: str | None = None) -> OAuthAuthorization:
        return OAuthAuthorization(f"mock://authorize?state={state}", state)

    def exchange_code(self, code: str, redirect_uri: str | None = None, code_verifier: str | None = None) -> OAuthToken:
        if not code:
            raise ValueError("authorization code is required")
        return OAuthToken(access_token=f"mock-access-{code}", refresh_token="mock-refresh")
