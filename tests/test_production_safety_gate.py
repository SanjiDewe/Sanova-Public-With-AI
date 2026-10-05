import pytest

from app.safety.gate import ProductionSafetyGate, SafetyGateError


def test_sandbox_execution_is_allowed_by_gate():
    gate = ProductionSafetyGate(environment="sandbox", live_execution=False)
    assert gate.evaluate().allowed is True
    gate.assert_sandbox_execution()


def test_non_sandbox_environment_is_blocked():
    gate = ProductionSafetyGate(environment="production", live_execution=False)
    with pytest.raises(SafetyGateError, match="environment is not sandbox"):
        gate.assert_sandbox_execution()


def test_live_execution_flag_is_blocked():
    gate = ProductionSafetyGate(environment="sandbox", live_execution=True)
    with pytest.raises(SafetyGateError, match="live execution"):
        gate.assert_sandbox_execution()


def test_physical_execution_is_blocked_until_phase_8():
    gate = ProductionSafetyGate(environment="sandbox", live_execution=False)
    with pytest.raises(SafetyGateError, match="Phase 7 production safety gate"):
        gate.assert_physical_execution()


def test_gate_is_defense_in_depth_for_execution_engine():
    from app.orchestration.executor import ExecutionEngine
    from app.orchestration.router import ProviderRouter
    from app.models.task import PhysicalTask
    from app.providers.mock import MockProvider

    class CountingProvider(MockProvider):
        name = "counting"

        def __init__(self):
            self.calls = 0

        def submit_sandbox(self, task):
            self.calls += 1
            return super().submit_sandbox(task)

    provider = CountingProvider()
    engine = ExecutionEngine(ProviderRouter({"counting": provider, "mock": MockProvider()}))
    engine.safety_gate = ProductionSafetyGate(environment="production", live_execution=False)

    with pytest.raises(SafetyGateError):
        engine.execute(PhysicalTask("blocked", provider="counting"))

    assert provider.calls == 0
