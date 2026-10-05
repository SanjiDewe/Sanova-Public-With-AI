import pytest

from app.activation.gate import ProductionActivationGate


def test_phase14a_is_hard_locked_by_default():
    decision = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=True,
    ).evaluate()

    assert decision.allowed is False
    assert "hard-locked" in decision.reason


def test_readiness_failure_blocks_activation():
    decision = ProductionActivationGate(
        readiness_passed=False,
        explicit_authorization=True,
        hard_locked=False,
    ).evaluate()

    assert decision.allowed is False
    assert "readiness" in decision.reason


def test_missing_explicit_authorization_blocks_activation():
    decision = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=False,
        hard_locked=False,
    ).evaluate()

    assert decision.allowed is False
    assert "explicit" in decision.reason


def test_kill_switch_overrides_activation():
    decision = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=True,
        kill_switch=True,
        hard_locked=False,
    ).evaluate()

    assert decision.allowed is False
    assert "kill switch" in decision.reason


def test_authorization_requires_all_conditions():
    decision = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=True,
        hard_locked=False,
    ).evaluate()

    assert decision.allowed is True
    assert decision.reason == "production activation authorized"


def test_assert_authorized_fails_closed():
    gate = ProductionActivationGate(
        readiness_passed=True,
        explicit_authorization=True,
    )

    with pytest.raises(RuntimeError, match="hard-locked"):
        gate.assert_authorized()
