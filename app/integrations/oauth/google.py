from __future__ import annotations

import json
import base64
import hashlib
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import oauth_provider_config
from app.integrations.contracts.oauth import OAuthAuthorization, OAuthIdentity, OAuthProvider, OAuthToken


class GoogleOAuthProvider(OAuthProvider):
    name = "google"

    def __init__(self) -> None:
        self.config = oauth_provider_config("google")

    def authorization_url(self, state: str, redirect_uri: str | None = None, scopes: tuple[str, ...] = (), code_verifier: str | None = None) -> OAuthAuthorization:
        if not self.config.client_id:
            raise RuntimeError("Google OAuth client ID is not configured")
        uri = redirect_uri or self.config.redirect_uri
        if not uri:
            raise RuntimeError("Google OAuth redirect URI is not configured")
        requested_scopes = scopes or self.config.scopes
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": uri,
            "response_type": "code",
            "scope": " ".join(requested_scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        if code_verifier:
            challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
            params["code_challenge"] = challenge
            params["code_challenge_method"] = "S256"
        return OAuthAuthorization(f"{self.config.authorization_url}?{urlencode(params)}", state)

    def exchange_code(self, code: str, redirect_uri: str | None = None, code_verifier: str | None = None) -> OAuthToken:
        if not self.config.client_id or not self.config.client_secret:
            raise RuntimeError("Google OAuth client credentials are not configured")
        uri = redirect_uri or self.config.redirect_uri
        if not uri:
            raise RuntimeError("Google OAuth redirect URI is not configured")
        data = {
            "code": code,
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "redirect_uri": uri,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier
        request = Request(
            self.config.token_url,
            data=urlencode(data).encode(),
            headers={"content-type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            payload = json.loads(response.read().decode())
        return OAuthToken(
            access_token=payload["access_token"],
            token_type=payload.get("token_type", "Bearer"),
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
        )

    def refresh(self, refresh_token: str) -> OAuthToken:
        if not self.config.client_id or not self.config.client_secret:
            raise RuntimeError("Google OAuth client credentials are not configured")
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        request = Request(
            self.config.token_url,
            data=urlencode(data).encode(),
            headers={"content-type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            payload = json.loads(response.read().decode())
        return OAuthToken(
            access_token=payload["access_token"],
            token_type=payload.get("token_type", "Bearer"),
            refresh_token=payload.get("refresh_token", refresh_token),
            expires_in=payload.get("expires_in"),
            scope=payload.get("scope"),
        )

    def revoke(self, token: str) -> bool:
        if not token:
            return False
        request = Request(f"{self.config.revoke_url}?token={token}", method="POST")
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            return 200 <= response.status < 300

    def identity_from_userinfo(self, access_token: str) -> OAuthIdentity:
        request = Request(
            self.config.userinfo_url,
            headers={"authorization": f"Bearer {access_token}"},
            method="GET",
        )
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            payload = json.loads(response.read().decode())
        return OAuthIdentity(self.name, str(payload["sub"]), payload.get("email"), payload.get("name"))
