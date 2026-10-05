import pytest

from app.models.task import PhysicalTask, TaskState
from app.safety.controlled_test import ControlledPhysicalTest, ControlledTestError


def task(task_id="phase8-local"):
    return PhysicalTask(task_id, provider="mock")


def test_phase8_requires_explicit_approval():
    harness = ControlledPhysicalTest(approved=False)
    with pytest.raises(ControlledTestError, match="explicit approval"):
        harness.run(task())


def test_phase8_allows_only_one_synthetic_local_task():
    harness = ControlledPhysicalTest(approved=True)
    result = harness.run(task())
    assert result.accepted is True
    assert result.status.value == "submitted"
    assert harness.audit[-1].event == "executed-local-only"

    with pytest.raises(ControlledTestError, match="only one"):
        harness.run(task("phase8-second"))


def test_phase8_kill_switch_blocks_execution():
    harness = ControlledPhysicalTest(approved=True)
    harness.stop()
    with pytest.raises(ControlledTestError, match="kill switch"):
        harness.run(task())


def test_phase8_rejects_non_mock_provider():
    harness = ControlledPhysicalTest(approved=True)
    with pytest.raises(ControlledTestError, match="provider must be mock"):
        harness.run(PhysicalTask("phase8-provider", provider="prodigi-sandbox"))


def test_phase8_audit_is_synthetic_and_local_only():
    harness = ControlledPhysicalTest(approved=True)
    harness.run(task("phase8-audit"))
    assert [event.event for event in harness.audit] == ["approved", "executed-local-only"]
    assert all(event.target == "synthetic-local-target" for event in harness.audit)


def test_phase8_does_not_enable_production_physical_execution():
    from app.safety.gate import ProductionSafetyGate, SafetyGateError

    gate = ProductionSafetyGate(environment="sandbox", live_execution=False)
    with pytest.raises(SafetyGateError, match="Phase 7 production safety gate"):
        gate.assert_physical_execution()
