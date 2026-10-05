from app.core.orchestration.router import ProviderRouter
from app.integrations.registry import ProviderRegistry


def test_provider_router_does_not_instantiate_registered_factories_until_selected():
    calls = []

    class Provider:
        name = "lazy"

    def factory():
        calls.append("created")
        return Provider()

    registry = ProviderRegistry()
    registry.register("lazy", factory)

    router = ProviderRouter(registry=registry)

    assert calls == []
    assert router.choose("lazy").name == "lazy"
    assert calls == ["created"]


def test_provider_router_only_instantiates_the_selected_provider():
    calls = []

    class Provider:
        def __init__(self, name):
            self.name = name

    def first():
        calls.append("first")
        return Provider("first")

    def second():
        calls.append("second")
        return Provider("second")

    registry = ProviderRegistry()
    registry.register("first", first)
    registry.register("second", second)

    router = ProviderRouter(registry=registry)

    assert calls == []
    assert router.choose("second").name == "second"
    assert calls == ["second"]
