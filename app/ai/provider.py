from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class AIProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class AIModel:
    provider: str
    model: str
    label: str


@dataclass(frozen=True)
class AIMessage:
    role: str
    content: str


@dataclass(frozen=True)
class AIResponse:
    provider: str
    model: str
    text: str
    raw: dict[str, Any] | None = None


class AIProvider:
    name: str

    def models(self) -> tuple[AIModel, ...]:
        raise NotImplementedError

    def generate(self, *, model: str, messages: list[AIMessage], system: str) -> AIResponse:
        raise NotImplementedError


class HTTPJSONProvider(AIProvider):
    def __init__(self, name: str, api_key: str | None, base_url: str, models: tuple[str, ...], timeout: float = 45.0):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._models = tuple(models)
        self.timeout = timeout

    def models(self) -> tuple[AIModel, ...]:
        return tuple(AIModel(self.name, model, model) for model in self._models)

    def _request(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
        return self._request_json(url, payload, headers, method="POST")

    def _request_json(
        self, url: str, payload: dict[str, Any] | None, headers: dict[str, str], *, method: str = "GET"
    ) -> dict[str, Any]:
        if not self.api_key:
            raise AIProviderError(f"AI provider '{self.name}' is not configured with an API key")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", **headers},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise AIProviderError(f"AI provider '{self.name}' returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AIProviderError(f"AI provider '{self.name}' is unavailable: {exc}") from exc
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise AIProviderError(f"AI provider '{self.name}' returned invalid JSON") from exc

    def discover_models(self) -> tuple[str, ...]:
        raise NotImplementedError


class OpenAIProvider(HTTPJSONProvider):
    def discover_models(self) -> tuple[str, ...]:
        data = self._request_json(
            f"{self.base_url}/models",
            None,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        return tuple(item["id"] for item in data.get("data", []) if isinstance(item, dict) and item.get("id"))

    def generate(self, *, model: str, messages: list[AIMessage], system: str) -> AIResponse:
        payload = {
            "model": model,
            "input": [
                {"role": "developer", "content": system},
                *[{"role": item.role, "content": item.content} for item in messages],
            ],
        }
        data = self._request(
            f"{self.base_url}/responses",
            payload,
            {"Authorization": f"Bearer {self.api_key}"},
        )
        text = data.get("output_text")
        if not text:
            parts: list[str] = []
            for item in data.get("output", []):
                for content in item.get("content", []) if isinstance(item, dict) else []:
                    if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                        if content.get("text"):
                            parts.append(str(content["text"]))
            text = "".join(parts)
        if not text:
            raise AIProviderError("OpenAI response contained no text output")
        return AIResponse(self.name, model, str(text), data)


class AnthropicProvider(HTTPJSONProvider):
    def discover_models(self) -> tuple[str, ...]:
        data = self._request_json(
            f"{self.base_url}/v1/models",
            None,
            {"x-api-key": str(self.api_key), "anthropic-version": "2023-06-01"},
        )
        return tuple(item["id"] for item in data.get("data", []) if isinstance(item, dict) and item.get("id"))

    def generate(self, *, model: str, messages: list[AIMessage], system: str) -> AIResponse:
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "messages": [{"role": item.role, "content": item.content} for item in messages],
        }
        data = self._request(
            f"{self.base_url}/v1/messages",
            payload,
            {"x-api-key": str(self.api_key), "anthropic-version": "2023-06-01"},
        )
        parts = [item.get("text", "") for item in data.get("content", []) if item.get("type") == "text"]
        text = "".join(parts).strip()
        if not text:
            raise AIProviderError("Anthropic response contained no text output")
        return AIResponse(self.name, model, text, data)


class GoogleProvider(HTTPJSONProvider):
    def discover_models(self) -> tuple[str, ...]:
        data = self._request_json(
            f"{self.base_url}/v1beta/models",
            None,
            {"x-goog-api-key": str(self.api_key)},
        )
        models = []
        for item in data.get("models", []):
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = str(item["name"]).split("/", 1)[-1]
            methods = item.get("supportedGenerationMethods") or []
            if not methods or "generateContent" in methods:
                models.append(name)
        return tuple(dict.fromkeys(models))

    def generate(self, *, model: str, messages: list[AIMessage], system: str) -> AIResponse:
        contents = []
        for item in messages:
            contents.append({"role": "model" if item.role == "assistant" else "user", "parts": [{"text": item.content}]})
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": contents,
        }
        data = self._request(
            f"{self.base_url}/v1beta/models/{model}:generateContent",
            payload,
            {"x-goog-api-key": str(self.api_key)},
        )
        parts = []
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("text"):
                    parts.append(str(part["text"]))
        text = "".join(parts).strip()
        if not text:
            raise AIProviderError("Google response contained no text output")
        return AIResponse(self.name, model, text, data)


class MockAIProvider(AIProvider):
    name = "mock"

    def __init__(self, models: tuple[str, ...] = ("mock-agent",)):
        self._models = models

    def models(self) -> tuple[AIModel, ...]:
        return tuple(AIModel(self.name, model, model) for model in self._models)

    def generate(self, *, model: str, messages: list[AIMessage], system: str) -> AIResponse:
        latest = messages[-1].content.strip() if messages else ""
        return AIResponse(
            self.name,
            model,
            json.dumps({"action": "respond", "message": f"Mock AI received: {latest}"}),
            None,
        )


class AIProviderRegistry:
    """Runtime registry for AI providers and models.

    Providers are discovered from configuration; the agent only sees this
    registry. No provider or model is selected by the agent itself.
    """

    def __init__(self, providers: dict[str, AIProvider] | None = None):
        self._providers = dict(providers or {})

    def register(self, provider: AIProvider) -> None:
        key = provider.name.strip().lower()
        if not key:
            raise ValueError("AI provider name is required")
        self._providers[key] = provider

    def remove(self, name: str) -> None:
        self._providers.pop(name.strip().lower(), None)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))

    def get(self, name: str) -> AIProvider:
        key = name.strip().lower()
        try:
            return self._providers[key]
        except KeyError as exc:
            raise ValueError(f"unsupported AI provider: {name}") from exc

    def models(self, provider: str) -> tuple[AIModel, ...]:
        return self.get(provider).models()

    def has_model(self, provider: str, model: str) -> bool:
        return any(item.model == model for item in self.models(provider))


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _models(name: str, default: str) -> tuple[str, ...]:
    raw = _env(name, default)
    return tuple(dict.fromkeys(value.strip() for value in raw.split(",") if value.strip()))


def build_ai_provider_registry() -> AIProviderRegistry:
    """Build the base registry. External AI providers are runtime-managed.

    Provider credentials and model discovery are intentionally not sourced from
    provider-specific environment variables; Super Admin installs them through
    AIProviderManagement and refreshes this registry at runtime.
    """
    registry = AIProviderRegistry()
    registry.register(MockAIProvider(_models("SANOVA_AI_MOCK_MODELS", "mock-agent")))
    return registry
