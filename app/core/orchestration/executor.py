
from threading import RLock

from app.core.audit.trail import AuditTrail
from app.config import RuntimeConfig, load_runtime_config
from app.core.models.task import PhysicalTask, TaskState
from app.core.orchestration.router import ProviderRouter
from app.core.persistence.store import ExecutionStore
from app.integrations.providers.base import ProviderError, ProviderErrorCode, ProviderResult, ProviderStatus
from app.core.safety.gate import ProductionSafetyGate


class ExecutionEngine:
    def __init__(self, router=None, store=None, audit=None, config: RuntimeConfig | None = None):
        self.config = config or load_runtime_config()
        self.config.assert_sandbox_only()
        self.router = router or ProviderRouter()
        self._results: dict[str, ProviderResult] = {}
        self._lock = RLock()
        self.store = store or ExecutionStore()
        self.safety_gate = ProductionSafetyGate()
        self.audit = audit or AuditTrail()

    def execute(self, task: PhysicalTask) -> ProviderResult:
        with self._lock:
            self.audit.append(
                "execution_requested",
                task.id,
                state=task.state.value,
                provider=task.provider,
            )
            if task.id in self._results:
                self.audit.append("execution_deduplicated", task.id, state=task.state.value)
                return self._results[task.id]

            persisted = self.store.get(task.id)
            if persisted:
                phase = persisted.get("phase")
                result = self.store.result_from_dict(persisted.get("result"))

                if phase in ("completed", "recovered") and result is not None:
                    self.store.restore_task(task, persisted)
                    self._results[task.id] = result
                    self.audit.append("execution_recovered", task.id, state=task.state.value, outcome="recovered")
                    return result

                if phase == "in_flight":
                    # Never automatically retry after a crash. The provider
                    # may have accepted the task before the process died.
                    error = ProviderError(
                        ProviderErrorCode.UNKNOWN,
                        "execution interrupted before result persistence; manual recovery required",
                    )
                    result = ProviderResult(
                        False,
                        status=ProviderStatus.FAILED,
                        message=error.message,
                        error=error,
                    )
                    task.state = TaskState.FAILED
                    self.store.put(task, result, "recovered")
                    self._results[task.id] = result
                    self.audit.append(
                        "execution_recovered",
                        task.id,
                        state=task.state.value,
                        outcome="failed",
                        reason="recovery_required",
                    )
                    return result

            self.safety_gate.assert_sandbox_execution()
            self.audit.append("safety_check_passed", task.id, state=task.state.value)

            if task.state is not TaskState.CREATED:
                raise ValueError(
                    f"task is not executable from state {task.state.value}"
                )
            if not task.id or not task.intent or not task.intent.strip():
                raise ValueError("task id and intent are required")

            provider = self.router.choose(task.provider)
            self.audit.append("provider_selected", task.id, provider=provider.name, state=task.state.value)

            # Persist the recovery fence BEFORE the provider call.
            self.store.put(task, None, "in_flight")
            self.audit.append("execution_fenced", task.id, state="in_flight", provider=provider.name)

            try:
                result = provider.submit_sandbox(task)
            except Exception as exc:
                result = ProviderResult(
                    accepted=False,
                    status=ProviderStatus.FAILED,
                    message=str(exc),
                    error=provider.normalize_error(exc),
                )

            result = self._validate_result(result, provider)
            self.audit.append(
                "provider_result",
                task.id,
                provider=provider.name,
                outcome="accepted" if result.accepted else "rejected",
                state=result.status.value if result.status else None,
                reason=result.error.code.value if result.error else None,
            )
            self._results[task.id] = result

            if result.failed:
                task.state = TaskState.FAILED
            elif result.status is not None:
                task.state = TaskState(result.status.value)

            self.audit.append("state_changed", task.id, state=task.state.value, provider=provider.name)
            self.store.put(task, result, "completed")
            self.audit.append("execution_persisted", task.id, state=task.state.value, outcome="completed")
            return result

    @staticmethod
    def _validate_result(result: ProviderResult, provider) -> ProviderResult:
        if not isinstance(result, ProviderResult):
            error = ProviderError(
                ProviderErrorCode.VALIDATION,
                "provider returned an invalid result",
            )
            return ProviderResult(False, message=error.message, error=error)

        if result.accepted and result.status is None:
            error = ProviderError(
                ProviderErrorCode.VALIDATION,
                "provider returned an incomplete result: status is required",
            )
            return ProviderResult(False, message=error.message, error=error)

        if result.accepted and result.status is ProviderStatus.FAILED:
            error = ProviderError(
                ProviderErrorCode.VALIDATION,
                "provider returned an inconsistent result: accepted cannot have failed status",
            )
            return ProviderResult(False, ProviderStatus.FAILED, message=error.message, error=error)

        if not result.accepted and result.error is None:
            error = provider.normalize_error(
                result.message or "provider returned an incomplete failure result"
            )
            return ProviderResult(False, status=ProviderStatus.FAILED, message=error.message, error=error)

        if not result.accepted and result.status not in (None, ProviderStatus.FAILED):
            error = ProviderError(
                ProviderErrorCode.VALIDATION,
                "provider returned an inconsistent result: rejected result must be failed",
            )
            return ProviderResult(False, ProviderStatus.FAILED, message=error.message, error=error)

        return result
