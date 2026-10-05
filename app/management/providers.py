from __future__ import annotations

from collections.abc import Callable

from app.identity.authorization import Permission


class ProviderManagement:
    """Administrative facade over an injected provider registry."""

    def __init__(self, identity, registry):
        self.identity = identity
        self.registry = registry

    def _require(self, actor):
        if not self.identity.authorization.has_permission(actor, Permission.MANAGE_PROVIDERS):
            raise PermissionError("provider management permission required")

    def list(self, actor, *, enabled_only: bool = False):
        self._require(actor)
        return self.registry.names(enabled_only=enabled_only)

    def enable(self, actor, name):
        self._require(actor)
        self.registry.enable(name)
        return self.registry.names()

    def disable(self, actor, name):
        self._require(actor)
        self.registry.disable(name)
        return self.registry.names()

    def register(self, actor, name, factory: Callable, *, enabled: bool = True, replace: bool = False):
        self._require(actor)
        if not callable(factory):
            raise TypeError("provider factory must be callable")
        self.registry.register(name, factory, enabled=enabled, replace=replace)
        return self.registry.names()

    def remove(self, actor, name):
        self._require(actor)
        self.registry.unregister(name)
        return self.registry.names()
