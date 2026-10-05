from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ProviderDescriptor(Generic[T]):
    name: str
    factory: Callable[[], T]
    enabled: bool = True


class ProviderRegistry(Generic[T]):
    """Small runtime registry: providers can be registered, replaced, disabled, or removed."""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderDescriptor[T]] = {}

    def register(self, name: str, factory: Callable[[], T], *, enabled: bool = True, replace: bool = False) -> None:
        key = self._normalize(name)
        if key in self._providers and not replace:
            raise ValueError(f"provider already registered: {key}")
        self._providers[key] = ProviderDescriptor(key, factory, enabled)

    def unregister(self, name: str) -> None:
        self._providers.pop(self._normalize(name), None)

    def enable(self, name: str) -> None:
        key = self._normalize(name)
        descriptor = self._providers.get(key)
        if descriptor is None:
            raise KeyError(key)
        self._providers[key] = ProviderDescriptor(descriptor.name, descriptor.factory, True)

    def disable(self, name: str) -> None:
        key = self._normalize(name)
        descriptor = self._providers.get(key)
        if descriptor is None:
            raise KeyError(key)
        self._providers[key] = ProviderDescriptor(descriptor.name, descriptor.factory, False)

    def get(self, name: str) -> T:
        key = self._normalize(name)
        descriptor = self._providers.get(key)
        if descriptor is None:
            raise ValueError(f"unsupported provider: {key}")
        if not descriptor.enabled:
            raise RuntimeError(f"provider is disabled: {key}")
        return descriptor.factory()

    def names(self, *, enabled_only: bool = False) -> tuple[str, ...]:
        return tuple(
            name for name, descriptor in self._providers.items() if descriptor.enabled or not enabled_only
        )

    @staticmethod
    def _normalize(name: str) -> str:
        value = str(name).strip().lower()
        if not value:
            raise ValueError("provider name is required")
        return value
