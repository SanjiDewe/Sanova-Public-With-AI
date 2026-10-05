from dataclasses import dataclass
from app.config import RuntimeConfig, load_runtime_config


class SafetyGateError(RuntimeError):
    """Raised when an execution cannot cross the production safety boundary."""


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


class ProductionSafetyGate:
    """Defense-in-depth gate for execution.

    Phase 7 keeps Sanova sandbox-only. The gate is deliberately independent
    from provider implementations so a provider cannot bypass the safety
    boundary.
    """

    def __init__(
        self,
        environment: str | None = None,
        live_execution: bool | None = None,
        config: RuntimeConfig | None = None,
    ):
        if config is not None and (environment is not None or live_execution is not None):
            raise ValueError("Provide either config or environment/live_execution, not both.")
        runtime = config or (
            RuntimeConfig(
                environment=environment,
                live_execution=live_execution,
            )
            if environment is not None or live_execution is not None
            else load_runtime_config()
        )
        self.environment = runtime.environment
        self.live_execution = runtime.live_execution

    def evaluate(self) -> SafetyDecision:
        if self.environment != "sandbox":
            return SafetyDecision(False, "execution environment is not sandbox")
        if self.live_execution:
            return SafetyDecision(False, "live execution is explicitly enabled")
        return SafetyDecision(True, "sandbox execution allowed")

    def assert_sandbox_execution(self) -> None:
        decision = self.evaluate()
        if not decision.allowed:
            raise SafetyGateError(decision.reason)

    def assert_physical_execution(self) -> None:
        """Physical execution remains unavailable until Phase 8."""
        raise SafetyGateError(
            "physical execution is blocked by the Phase 7 production safety gate"
        )
