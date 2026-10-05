from __future__ import annotations

import os

from app.integrations.contracts.email import EmailProvider
from app.integrations.email.brevo import BrevoEmailProvider
from app.integrations.email.mock import MockEmailProvider
from app.integrations.registry import ProviderRegistry


def build_email_registry() -> ProviderRegistry[EmailProvider]:
    registry: ProviderRegistry[EmailProvider] = ProviderRegistry()
    registry.register("mock", MockEmailProvider)
    registry.register("brevo", BrevoEmailProvider)
    return registry


def email_provider(registry: ProviderRegistry[EmailProvider] | None = None) -> EmailProvider:
    registry = registry or build_email_registry()
    return registry.get(os.getenv("SANOVA_EMAIL_PROVIDER", "mock"))
