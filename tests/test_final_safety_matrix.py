
import os
import pytest

from app.activation.gate import ProductionActivationGate
from app.deployment.readiness import evaluate as deployment_evaluate
from app.readiness.check import evaluate as readiness_evaluate
from app.safety.gate import ProductionSafetyGate, SafetyGateError
from app.models.task import PhysicalTask
from app.orchestration.router import ProviderRouter
from app.orchestration.executor import ExecutionEngine
from app.audit.trail import AuditTrail
from app.models.task import TaskState
from app.providers.base import ProviderResult, ProviderStatus, ProviderError, ProviderErrorCode


def test_activation_gate_cannot_open_with_readiness_failure():
    decision = ProductionActivationGate(
        readiness_passed=False,
        explicit_authorization=True,
        hard_locked=False,
    ).evaluate()
    assert not decision.allowed
    assert "readiness" in decision.reason


def test_activation_gate_cannot_open_when_kill_switch_is_on():
    decision = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=True,
        kill_switch=True,
        hard_locked=False,
    ).evaluate()
    assert not decision.allowed
    assert "kill switch" in decision.reason


def test_activation_gate_hard_lock_overrides_everything():
    decision = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=True,
        kill_switch=False,
        hard_locked=True,
    ).evaluate()
    assert not decision.allowed
    assert "hard-locked" in decision.reason


def test_deployment_failure_and_readiness_failure_are_independent(monkeypatch):
    monkeypatch.setenv("SANOVA_ENVIRONMENT", "production")
    monkeypatch.setenv("SANOVA_LIVE_EXECUTION", "true")
    deployment = deployment_evaluate()
    readiness = readiness_evaluate()
    assert not deployment.safe
    assert not readiness.sandbox_safe
    assert deployment.production_locked is True
    assert readiness.production_locked is True


def test_safety_gate_rejects_non_sandbox_even_if_live_flag_is_false():
    gate = ProductionSafetyGate(environment="production", live_execution=False)
    decision = gate.evaluate()
    assert not decision.allowed
    assert "sandbox" in decision.reason


def test_safety_gate_rejects_explicit_live_execution():
    gate = ProductionSafetyGate(environment="sandbox", live_execution=True)
    decision = gate.evaluate()
    assert not decision.allowed
    assert "live execution" in decision.reason


def test_unknown_provider_cannot_cross_execution_router():
    router = ProviderRouter()
    with pytest.raises(ValueError, match="unsupported provider"):
        router.choose("unknown-provider")


def test_physical_execution_is_always_blocked():
    gate = ProductionSafetyGate(environment="sandbox", live_execution=False)
    with pytest.raises(SafetyGateError, match="production safety gate"):
        gate.assert_physical_execution()


def test_duplicate_execution_cannot_submit_provider_twice():
    engine = ExecutionEngine()
    task = PhysicalTask("matrix duplicate")
    first = engine.execute(task)
    second = engine.execute(task)
    assert first is second


def test_in_flight_recovery_does_not_retry_provider():
    from app.persistence.store import ExecutionStore

    store = ExecutionStore()
    task = PhysicalTask("matrix recovery")
    store.put(task, None, "in_flight")
    engine = ExecutionEngine(store=store)
    result = engine.execute(task)
    assert not result.accepted
    assert task.state is TaskState.FAILED


def test_live_provider_host_is_rejected_by_sandbox_url_check():
    from app.config import assert_sandbox_url

    with pytest.raises(RuntimeError):
        assert_sandbox_url("https://api.prodigi.com", "prodigi")


def test_audit_integrity_failure_is_detectable_without_becoming_execution_authority(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    trail = AuditTrail(root=tmp_path)
    trail.append("test_event", "matrix-task", state="created")
    assert trail.verify() is True

    raw = audit_path.read_text(encoding="utf-8")
    audit_path.write_text(raw.replace("test_event", "tampered_event", 1), encoding="utf-8")
    assert trail.verify() is False

    engine = ExecutionEngine()
    result = engine.execute(PhysicalTask("audit observer"))
    assert result.accepted is True
