from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.models.task import PhysicalTask, TaskState
from app.core.orchestration.executor import ExecutionEngine
from app.core.orchestration.router import ProviderRouter
from app.integrations.providers.mock import MockProvider
from app.integrations.providers.base import ProviderResult
from app.core.safety.gate import SafetyGateError


class ControlledTestError(RuntimeError):
    """Raised when a controlled Phase 8 test violates its safety envelope."""


@dataclass(frozen=True)
class AuditEvent:
    event: str
    task_id: str
    target: str
    timestamp: str


class ControlledPhysicalTest:
    """Local-only Phase 8 harness.

    Despite the historical name "physical test", this harness never performs
    physical or external execution. It permits only one synthetic task through
    the local MockProvider after explicit approval.
    """

    SYNTHETIC_TARGET = "synthetic-local-target"

    def __init__(self, approved: bool = False, kill_switch: bool = False):
        self.approved = approved
        self.kill_switch = kill_switch
        self._used = False
        self.audit: list[AuditEvent] = []

    def run(self, task: PhysicalTask) -> ProviderResult:
        if not self.approved:
            raise ControlledTestError("explicit approval is required")
        if self.kill_switch:
            raise ControlledTestError("kill switch is active")
        if self._used:
            raise ControlledTestError("only one controlled task is permitted")
        if task.provider != "mock":
            raise ControlledTestError("controlled test provider must be mock")
        if getattr(task, "target", self.SYNTHETIC_TARGET) != self.SYNTHETIC_TARGET:
            raise ControlledTestError("target must be synthetic-local-target")

        self._used = True
        self.audit.append(self._event("approved", task))
        router = ProviderRouter({"mock": MockProvider()})
        engine = ExecutionEngine(router)
        try:
            result = engine.execute(task)
        except SafetyGateError:
            self.audit.append(self._event("blocked", task))
            raise
        self.audit.append(self._event("executed-local-only", task))
        return result

    def stop(self) -> None:
        self.kill_switch = True

    @staticmethod
    def _event(name: str, task: PhysicalTask) -> AuditEvent:
        return AuditEvent(
            event=name,
            task_id=task.id,
            target=ControlledPhysicalTest.SYNTHETIC_TARGET,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
