from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True)
class OAuthAuthorization:
    url: str
    state: str


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    token_type: str = "Bearer"
    refresh_token: str | None = None
    expires_in: int | None = None
    scope: str | None = None


@dataclass(frozen=True)
class OAuthIdentity:
    provider: str
    subject: str
    email: str | None = None
    name: str | None = None


class OAuthProvider(ABC):
    name: str

    @abstractmethod
    def authorization_url(self, state: str, redirect_uri: str | None = None, scopes: tuple[str, ...] = (), code_verifier: str | None = None) -> OAuthAuthorization:
        raise NotImplementedError

    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str | None = None, code_verifier: str | None = None) -> OAuthToken:
        raise NotImplementedError

    def refresh(self, refresh_token: str) -> OAuthToken:
        raise NotImplementedError(f"{self.name} does not support refresh")

    def revoke(self, token: str) -> bool:
        raise NotImplementedError(f"{self.name} does not support revoke")

    @staticmethod
    def encode(params: dict[str, str]) -> str:
        return urlencode(params)
