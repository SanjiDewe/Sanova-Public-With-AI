from __future__ import annotations

import os

from app.integrations.providers.base import PhysicalProvider
from app.integrations.providers.cloudprinter import CloudprinterSandboxAdapter
from app.integrations.providers.mock import MockProvider
from app.integrations.providers.prodigi import ProdigiSandboxAdapter
from app.integrations.registry import ProviderRegistry


def build_physical_registry() -> ProviderRegistry[PhysicalProvider]:
    registry: ProviderRegistry[PhysicalProvider] = ProviderRegistry()
    registry.register("mock", MockProvider)

    sandbox_http_enabled = os.getenv("SANOVA_SANDBOX_HTTP_ENABLED", "false").strip().lower() == "true"
    registry.register(
        "prodigi",
        lambda: ProdigiSandboxAdapter(simulation=not sandbox_http_enabled),
    )
    registry.register(
        "cloudprinter",
        lambda: CloudprinterSandboxAdapter(simulation=not sandbox_http_enabled),
    )
    return registry


def physical_provider_registry() -> ProviderRegistry[PhysicalProvider]:
    registry = build_physical_registry()
    disabled = {
        value.strip().lower()
        for value in os.getenv("SANOVA_DISABLED_PHYSICAL_PROVIDERS", "").split(",")
        if value.strip()
    }
    for name in disabled:
        if name in registry.names():
            registry.disable(name)
    return registry
