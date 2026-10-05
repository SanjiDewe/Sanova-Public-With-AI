from __future__ import annotations

import os

from app.integrations.contracts.oauth import OAuthProvider
from app.integrations.oauth.google import GoogleOAuthProvider
from app.integrations.oauth.mock import MockOAuthProvider
from app.integrations.registry import ProviderRegistry


def build_oauth_registry() -> ProviderRegistry[OAuthProvider]:
    registry: ProviderRegistry[OAuthProvider] = ProviderRegistry()
    registry.register("mock", MockOAuthProvider)
    registry.register("google", GoogleOAuthProvider)
    return registry


def oauth_provider(registry: ProviderRegistry[OAuthProvider] | None = None) -> OAuthProvider:
    registry = registry or build_oauth_registry()
    return registry.get(os.getenv("SANOVA_OAUTH_PROVIDER", "mock"))
