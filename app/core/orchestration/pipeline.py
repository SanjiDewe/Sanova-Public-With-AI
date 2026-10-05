from dataclasses import dataclass

from app.core.contracts.physical_task import PhysicalTaskSpec
from app.core.models.task import PhysicalTask, TaskState
from app.core.orchestration.executor import ExecutionEngine
from app.core.planner.planner import ExecutionPlanner
from app.integrations.webhooks.handler import handle_provider_webhook


@dataclass(frozen=True)
class VerificationResult:
    verified: bool
    state: TaskState
    message: str


class EndToEndSimulation:
    """Run one complete physical execution lifecycle without real-world I/O."""

    def __init__(self, engine: ExecutionEngine | None = None, planner: ExecutionPlanner | None = None):
        self.planner = planner or ExecutionPlanner()
        self.engine = engine or ExecutionEngine()

    def run(self, spec: PhysicalTaskSpec, statuses=None) -> tuple[PhysicalTask, VerificationResult]:
        task = self.planner.build(spec)
        result = self.engine.execute(task)
        if result.failed:
            return task, self.verify(task)

        provider = self.engine.router.choose(task.provider)
        for raw_status in statuses or ("processing", "fulfillment", "shipped", "completed"):
            handle_provider_webhook(task, provider, raw_status)

        return task, self.verify(task)

    @staticmethod
    def verify(task: PhysicalTask) -> VerificationResult:
        verified = task.state is TaskState.COMPLETED
        return VerificationResult(
            verified=verified,
            state=task.state,
            message="simulation completed and verified" if verified else "simulation did not complete",
        )
