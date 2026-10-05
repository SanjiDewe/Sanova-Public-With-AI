from __future__ import annotations

from dataclasses import dataclass

from app.ai.config import get_provider_definition
from app.ai.credentials import AICredentialCipher
from app.ai.provider import AnthropicProvider, GoogleProvider, OpenAIProvider, AIProviderRegistry, AIProviderError
from app.identity.authorization import Permission


@dataclass(frozen=True)
class AIProviderView:
    name: str
    label: str
    status: str
    enabled: bool
    credential_configured: bool
    credential_hint: str | None
    models: tuple[str, ...]
    selected_model: str | None
    base_url: str


class AIProviderManagement:
    """Super Admin lifecycle for runtime AI provider installations."""

    def __init__(self, identity, store, registry: AIProviderRegistry, *, cipher: AICredentialCipher | None = None):
        self.identity = identity
        self.store = store
        self.registry = registry
        self.cipher = cipher or AICredentialCipher()

    def _require(self, actor) -> None:
        if not self.identity.authorization.has_permission(actor, Permission.MANAGE_PROVIDERS):
            raise PermissionError("AI provider management permission required")

    def list(self, actor) -> tuple[AIProviderView, ...]:
        self._require(actor)
        rows = self.store.list_ai_provider_configs()
        configured = {row["name"]: row for row in rows}
        result = []
        for name in ("openai", "anthropic", "google"):
            definition = get_provider_definition(name)
            row = configured.get(name)
            result.append(self._view(definition, row))
        return tuple(result)

    def connect(self, actor, name: str, credential: str, *, base_url: str | None = None) -> AIProviderView:
        self._require(actor)
        definition = get_provider_definition(name)
        credential = str(credential).strip()
        if not credential:
            raise ValueError("credential is required")
        url = (base_url or definition.base_url).strip().rstrip("/")
        models = self._discover(name, credential, url)
        if not models:
            raise AIProviderError(f"AI provider '{name}' returned no usable models")
        selected = models[0]
        encrypted = self.cipher.encrypt(credential)
        # Connect validates the credential and discovers models; activation remains explicit.
        self.store.upsert_ai_provider_config(
            name=name,
            label=definition.label,
            base_url=url,
            credential=encrypted,
            models=models,
            selected_model=selected,
            enabled=False,
            status="connected",
        )
        self._refresh(name)
        return self._view(definition, self.store.get_ai_provider_config(name))

    def test(self, actor, name: str) -> tuple[str, ...]:
        self._require(actor)
        row = self.store.get_ai_provider_config(name)
        if not row or not row.get("credential"):
            raise ValueError("AI provider is not configured")
        credential = self.cipher.decrypt(row["credential"])
        models = self._discover(name, credential, row["base_url"])
        self.store.update_ai_provider_models(
            name, models,
            selected_model=row.get("selected_model") if row.get("selected_model") in models else (models[0] if models else None),
            status="active" if row.get("enabled") else "connected",
        )
        self._refresh(name)
        return tuple(models)

    def enable(self, actor, name: str) -> AIProviderView:
        self._require(actor)
        row = self.store.get_ai_provider_config(name)
        if not row or not row.get("credential"):
            raise ValueError("AI provider is not configured")
        credential = self.cipher.decrypt(row["credential"])
        models = tuple(row.get("models") or ())
        if not models:
            models = self._discover(name, credential, row["base_url"])
        if not models:
            raise ValueError("AI provider has no usable models")
        selected = row.get("selected_model") if row.get("selected_model") in models else models[0]
        self.store.set_ai_provider_state(name, enabled=True, status="active", models=models, selected_model=selected)
        self._refresh(name)
        return self._view(get_provider_definition(name), self.store.get_ai_provider_config(name))

    def disable(self, actor, name: str) -> AIProviderView:
        self._require(actor)
        if not self.store.get_ai_provider_config(name):
            raise ValueError("AI provider is not configured")
        self.store.set_ai_provider_state(name, enabled=False, status="disabled")
        self._refresh(name)
        return self._view(get_provider_definition(name), self.store.get_ai_provider_config(name))

    def replace(self, actor, name: str, credential: str) -> AIProviderView:
        self._require(actor)
        row = self.store.get_ai_provider_config(name)
        if not row or row.get("status") == "revoked" or not row.get("credential"):
            raise ValueError("AI provider is not configured")
        credential = str(credential).strip()
        if not credential:
            raise ValueError("credential is required")
        url = (row.get("base_url") or get_provider_definition(name).base_url).strip().rstrip("/")
        models = self._discover(name, credential, url)
        if not models:
            raise AIProviderError(f"AI provider '{name}' returned no usable models")
        encrypted = self.cipher.encrypt(credential)
        enabled = bool(row.get("enabled"))
        status = "active" if enabled else "connected"
        selected = row.get("selected_model") if row.get("selected_model") in models else models[0]
        self.store.upsert_ai_provider_config(
            name=name, label=row.get("label") or get_provider_definition(name).label,
            base_url=url, credential=encrypted, models=models, selected_model=selected,
            enabled=enabled, status=status,
        )
        self._refresh(name)
        return self._view(get_provider_definition(name), self.store.get_ai_provider_config(name))

    def revoke(self, actor, name: str) -> AIProviderView:
        self._require(actor)
        if not self.store.get_ai_provider_config(name):
            raise ValueError("AI provider is not configured")
        self.store.revoke_ai_provider_config(name)
        self._refresh(name)
        return self._view(get_provider_definition(name), self.store.get_ai_provider_config(name))

    def set_model(self, actor, name: str, model: str) -> AIProviderView:
        self._require(actor)
        row = self.store.get_ai_provider_config(name)
        if not row or row.get("status") == "revoked":
            raise ValueError("AI provider is not configured")
        models = tuple(row.get("models") or ())
        if model not in models:
            raise ValueError("selected AI model is not available")
        self.store.set_ai_provider_state(name, enabled=bool(row.get("enabled")), status=row.get("status", "disabled"), selected_model=model)
        return self._view(get_provider_definition(name), self.store.get_ai_provider_config(name))

    def _refresh(self, name: str) -> None:
        row = self.store.get_ai_provider_config(name)
        self.registry.remove(name)
        if not row or not row.get("enabled") or row.get("status") != "active":
            return
        credential = self.cipher.decrypt(row["credential"])
        models = tuple(row.get("models") or ())
        factory = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "google": GoogleProvider}[name]
        self.registry.register(factory(name, credential, row["base_url"], models))

    def _discover(self, name: str, credential: str, base_url: str) -> tuple[str, ...]:
        factory = {"openai": OpenAIProvider, "anthropic": AnthropicProvider, "google": GoogleProvider}[name]
        provider = factory(name, credential, base_url, ())
        return provider.discover_models()

    @staticmethod
    def _view(definition, row) -> AIProviderView:
        if not row:
            return AIProviderView(definition.name, definition.label, "not_configured", False, False, None, (), None, definition.base_url)
        credential = row.get("credential")
        hint = None
        if credential:
            hint = "configured"
        return AIProviderView(
            definition.name, definition.label, row.get("status", "disabled"), bool(row.get("enabled")), bool(credential), hint,
            tuple(row.get("models") or ()), row.get("selected_model"), row.get("base_url") or definition.base_url,
        )
