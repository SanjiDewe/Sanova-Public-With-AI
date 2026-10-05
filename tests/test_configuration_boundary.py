from app.config import RuntimeConfig, load_runtime_config
from app.core.orchestration.executor import ExecutionEngine
from app.core.safety.gate import ProductionSafetyGate


def test_config_resolution_is_explicit_and_does_not_depend_on_import_order():
    config = load_runtime_config({
        "SANOVA_ENVIRONMENT": "sandbox",
        "SANOVA_LIVE_EXECUTION": "false",
    })
    assert config == RuntimeConfig("sandbox", False)


def test_executor_uses_injected_runtime_config():
    config = RuntimeConfig("sandbox", False)
    engine = ExecutionEngine(config=config)
    assert engine.config is config


def test_safety_gate_accepts_injected_runtime_config():
    config = RuntimeConfig("sandbox", False)
    gate = ProductionSafetyGate(config=config)
    assert gate.evaluate().allowed is True


def test_unsafe_injected_runtime_config_is_blocked():
    config = RuntimeConfig("production", False)
    try:
        ExecutionEngine(config=config)
    except RuntimeError:
        return
    raise AssertionError("unsafe runtime configuration must be blocked")
