from __future__ import annotations

from app.integrations.providers.base import PhysicalProvider
from app.integrations.providers.registry import physical_provider_registry


class ProviderRouter:
    """Select a registered physical provider with lazy factory execution."""

    def __init__(self, providers=None, registry=None):
        if providers is not None:
            self.providers = providers
            self.registry = None
        else:
            self.registry = registry or physical_provider_registry()
            self.providers = None

    def choose(self, requested: str | None) -> PhysicalProvider:
        if requested is None:
            requested = "mock"
        if self.registry is None:
            try:
                return self.providers[requested]
            except KeyError as exc:
                raise ValueError(f"unsupported provider: {requested}") from exc

        if requested not in self.registry.names():
            raise ValueError(f"unsupported provider: {requested}")
        if requested not in self.registry.names(enabled_only=True):
            raise RuntimeError(f"provider is disabled: {requested}")
        return self.registry.get(requested)

    def provider_name(self, requested: str | None) -> str:
        return self.choose(requested).name
