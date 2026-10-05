from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivationDecision:
    allowed: bool
    reason: str


class ProductionActivationGate:
    """Final authorization boundary before any future production activation.

    Phase 14A only defines the authorization contract. It does not enable
    production execution and never changes runtime configuration.

    The hard lock is intentionally permanent in this phase. A future,
    explicitly approved activation phase may replace this gate with a
    deployment-specific authorization mechanism.
    """

    def __init__(
        self,
        *,
        readiness_passed: bool,
        explicit_authorization: bool = False,
        kill_switch: bool = False,
        hard_locked: bool = True,
    ) -> None:
        self.readiness_passed = readiness_passed
        self.explicit_authorization = explicit_authorization
        self.kill_switch = kill_switch
        self.hard_locked = hard_locked

    def evaluate(self) -> ActivationDecision:
        if self.hard_locked:
            return ActivationDecision(
                False,
                "production activation is hard-locked in Phase 14A",
            )

        if self.kill_switch:
            return ActivationDecision(
                False,
                "production activation is blocked by the kill switch",
            )

        if not self.readiness_passed:
            return ActivationDecision(
                False,
                "production readiness checks have not passed",
            )

        if not self.explicit_authorization:
            return ActivationDecision(
                False,
                "explicit production activation authorization is required",
            )

        return ActivationDecision(True, "production activation authorized")

    def assert_authorized(self) -> None:
        decision = self.evaluate()
        if not decision.allowed:
            raise RuntimeError(decision.reason)
