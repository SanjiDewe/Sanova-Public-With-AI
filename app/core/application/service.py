from __future__ import annotations

from dataclasses import dataclass

from app.core.contracts.physical_task import PhysicalTaskSpec
from app.core.intent.parser import IntentParser, RuleBasedIntentParser
from app.core.models.task import PhysicalTask
from app.core.orchestration.executor import ExecutionEngine
from app.core.planner.planner import ExecutionPlanner
from app.integrations.providers.base import ProviderResult


@dataclass(frozen=True)
class ExecutionResponse:
    """Application-facing result with no provider execution capability."""

    task_id: str
    state: str
    accepted: bool
    message: str
    provider: str | None = None
    external_id: str | None = None
    error_code: str | None = None


class ApplicationService:
    """Application boundary for turning user intent into sandbox execution.

    The service coordinates parser -> planner -> execution engine. It never
    selects or calls providers directly, so the existing safety and execution
    boundaries remain authoritative.
    """

    def __init__(
        self,
        *,
        parser: IntentParser | None = None,
        planner: ExecutionPlanner | None = None,
        engine: ExecutionEngine | None = None,
    ) -> None:
        self.parser = parser or RuleBasedIntentParser()
        self.planner = planner or ExecutionPlanner()
        self.engine = engine or ExecutionEngine()

    def execute_intent(self, text: str, *, owner_id: str | None = None) -> ExecutionResponse:
        """Interpret and execute one user intent through the existing pipeline."""
        intent = self.parser.parse(text)
        task = self.planner.build_from_intent(intent)
        task.owner_id = owner_id
        return self._execute(task)

    def execute_spec(self, spec: PhysicalTaskSpec, *, owner_id: str | None = None) -> ExecutionResponse:
        """Execute a validated application task specification."""
        task = self.planner.build(spec)
        task.owner_id = owner_id
        return self._execute(task)

    def _execute(self, task: PhysicalTask) -> ExecutionResponse:
        result = self.engine.execute(task)
        return self._response(task, result)

    def _response(self, task: PhysicalTask, result: ProviderResult) -> ExecutionResponse:
        provider = task.provider
        router = getattr(self.engine, "router", None)
        if provider is None and router is not None:
            provider = router.provider_name(None)

        return ExecutionResponse(
            task_id=task.id,
            state=task.state.value,
            accepted=result.accepted,
            message=result.message,
            provider=provider,
            external_id=result.external_id,
            error_code=result.error.code.value if result.error else None,
        )
