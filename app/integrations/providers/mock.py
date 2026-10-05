from app.core.models.task import PhysicalTask, TaskState
from app.integrations.providers.base import PhysicalProvider, ProviderResult, ProviderStatus, ProviderError
from app.integrations.providers.normalization import normalize_error, normalize_status


class MockProvider(PhysicalProvider):
    name = "mock"

    def submit_sandbox(self, task: PhysicalTask) -> ProviderResult:
        task.state = TaskState.SUBMITTED
        return ProviderResult(
            True,
            ProviderStatus.SUBMITTED,
            f"mock-{task.id}",
            "simulated only",
        )

    def normalize_status(self, raw_status: str) -> ProviderStatus:
        return normalize_status(raw_status)

    def normalize_error(self, error: Exception | str) -> ProviderError:
        return normalize_error(error)
