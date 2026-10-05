from importlib import import_module


def test_core_has_canonical_execution_domains():
    modules = (
        "app.core.activation.gate",
        "app.core.application.service",
        "app.core.audit.trail",
        "app.core.contracts.physical_task",
        "app.core.models.task",
        "app.core.orchestration.executor",
        "app.core.persistence.store",
        "app.core.planner.planner",
        "app.core.safety.gate",
    )
    for name in modules:
        assert import_module(name) is not None


def test_integrations_have_canonical_provider_boundary():
    modules = (
        "app.integrations.providers.base",
        "app.integrations.providers.prodigi",
        "app.integrations.providers.cloudprinter",
        "app.integrations.providers.mock",
        "app.integrations.webhooks.handler",
    )
    for name in modules:
        assert import_module(name) is not None


def test_legacy_paths_are_compatibility_shims():
    from app.orchestration.executor import ExecutionEngine as LegacyExecutionEngine
    from app.core.orchestration.executor import ExecutionEngine
    from app.providers.prodigi import ProdigiSandboxAdapter as LegacyProdigi
    from app.integrations.providers.prodigi import ProdigiSandboxAdapter

    assert LegacyExecutionEngine is ExecutionEngine
    assert LegacyProdigi is ProdigiSandboxAdapter
