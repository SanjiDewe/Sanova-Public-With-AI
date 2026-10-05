import pytest

from app.config import provider_config
from app.providers.cloudprinter import CloudprinterSandboxAdapter
from app.providers.prodigi import ProdigiSandboxAdapter
from app.models.task import PhysicalTask, TaskState


def test_provider_configs_have_no_hardcoded_credentials(monkeypatch):
    for key in (
        "SANOVA_PRODIGI_SANDBOX_API_KEY",
        "SANOVA_PRODIGI_SANDBOX_BASE_URL",
        "SANOVA_CLOUDPRINTER_SANDBOX_API_KEY",
        "SANOVA_CLOUDPRINTER_SANDBOX_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    assert provider_config("prodigi").api_key is None
    assert provider_config("cloudprinter").api_key is None


def test_sandbox_http_is_off_by_default(monkeypatch):
    monkeypatch.delenv("SANOVA_SANDBOX_HTTP_ENABLED", raising=False)
    task = PhysicalTask("test")
    with pytest.raises(RuntimeError, match="Sandbox HTTP is disabled"):
        ProdigiSandboxAdapter(simulation=False).submit_sandbox(task)
    assert task.state == TaskState.CREATED


def test_prodigi_request_builder_uses_runtime_configuration(monkeypatch):
    monkeypatch.setenv("SANOVA_PRODIGI_SANDBOX_BASE_URL", "https://api.sandbox.prodigi.com")
    req = ProdigiSandboxAdapter().build_order_request(PhysicalTask("test"))
    assert req.method == "POST"
    assert req.url.startswith("https://api.sandbox.prodigi.com/v4.0/Orders")
    assert "<configured-at-runtime>" in req.headers["X-API-Key"]


def test_cloudprinter_request_builder_uses_runtime_configuration(monkeypatch):
    monkeypatch.setenv("SANOVA_CLOUDPRINTER_SANDBOX_BASE_URL", "https://api.cloudprinter.com")
    req = CloudprinterSandboxAdapter().build_order_request(PhysicalTask("test"))
    assert req.method == "POST"
    assert req.url.startswith("https://api.cloudprinter.com/cloudcore/1.0/orders/add")


def test_live_prodigi_host_is_rejected(monkeypatch):
    monkeypatch.setenv("SANOVA_PRODIGI_SANDBOX_BASE_URL", "https://api.prodigi.com")
    with pytest.raises(RuntimeError, match="live API host is forbidden"):
        ProdigiSandboxAdapter().build_order_request(PhysicalTask("test"))


def test_provider_registry_uses_simulation_by_default(monkeypatch):
    monkeypatch.delenv("SANOVA_SANDBOX_HTTP_ENABLED", raising=False)
    from app.integrations.providers.registry import physical_provider_registry

    registry = physical_provider_registry()
    assert registry.get("prodigi").simulation is True
    assert registry.get("cloudprinter").simulation is True


def test_provider_registry_can_use_sandbox_http_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SANOVA_SANDBOX_HTTP_ENABLED", "true")
    from app.integrations.providers.registry import physical_provider_registry

    registry = physical_provider_registry()
    assert registry.get("prodigi").simulation is False
    assert registry.get("cloudprinter").simulation is False
