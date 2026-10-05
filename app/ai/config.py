from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AIProviderDefinition:
    name: str
    label: str
    base_url: str
    default_models: tuple[str, ...] = ()


PROVIDERS: dict[str, AIProviderDefinition] = {
    "openai": AIProviderDefinition("openai", "OpenAI", "https://api.openai.com/v1"),
    "anthropic": AIProviderDefinition("anthropic", "Anthropic", "https://api.anthropic.com"),
    "google": AIProviderDefinition("google", "Google", "https://generativelanguage.googleapis.com"),
}


def get_provider_definition(name: str) -> AIProviderDefinition:
    key = str(name).strip().lower()
    try:
        return PROVIDERS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported AI provider: {name}") from exc
