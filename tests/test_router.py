from app.orchestration.router import ProviderRouter


def test_router_resolves_known_sandbox_providers():
    router = ProviderRouter()
    assert router.provider_name("prodigi") == "prodigi-sandbox"
    assert router.provider_name("cloudprinter") == "cloudprinter-sandbox"


def test_router_defaults_to_mock():
    assert ProviderRouter().provider_name(None) == "mock"
