import pytest

from app.contracts.physical_task import PhysicalTaskSpec
from app.models.task import PhysicalTask, TaskState
from app.orchestration.executor import ExecutionEngine
from app.orchestration.pipeline import EndToEndSimulation
from app.orchestration.router import ProviderRouter
from app.providers.base import ProviderError, ProviderErrorCode, ProviderResult, ProviderStatus, PhysicalProvider
from app.providers.mock import MockProvider
from app.planner.planner import ExecutionPlanner
from app.webhooks.handler import handle_provider_webhook


class CountingProvider(PhysicalProvider):
    name = "counting"

    def __init__(self, result=None):
        self.calls = 0
        self.result = result

    def submit_sandbox(self, task):
        self.calls += 1
        if self.result is not None:
            return self.result
        return ProviderResult(True, ProviderStatus.SUBMITTED, f"external-{task.id}", "simulated")

    def normalize_status(self, raw_status):
        return MockProvider().normalize_status(raw_status)

    def normalize_error(self, error):
        from app.providers.normalization import normalize_error
        return normalize_error(error)


def spec(provider="mock"):
    return PhysicalTaskSpec(
        intent="make one mug and ship it",
        action="manufacture_and_fulfill",
        product="mug",
        asset="design.png",
        destination="TEST-DESTINATION",
        provider=provider,
    )


def test_full_pipeline_reaches_completed_and_verifies():
    pipeline = EndToEndSimulation()
    task, verification = pipeline.run(spec())

    assert task.state is TaskState.COMPLETED
    assert verification.verified is True
    assert verification.state is TaskState.COMPLETED


def test_provider_timeout_fails_task():
    provider = CountingProvider(
        ProviderResult(
            False,
            ProviderStatus.FAILED,
            message="request timed out",
            error=ProviderError(ProviderErrorCode.TIMEOUT, "request timed out", retryable=True),
        )
    )
    engine = ExecutionEngine(ProviderRouter({"timeout": provider, "mock": MockProvider()}))
    task = PhysicalTask("timeout", provider="timeout")

    result = engine.execute(task)

    assert result.failed
    assert result.error.code is ProviderErrorCode.TIMEOUT
    assert result.error.retryable is True
    assert task.state is TaskState.FAILED


def test_provider_failure_fails_task():
    provider = CountingProvider(
        ProviderResult(
            False,
            ProviderStatus.FAILED,
            message="provider rejected the order",
            error=ProviderError(ProviderErrorCode.UNKNOWN, "provider rejected the order"),
        )
    )
    engine = ExecutionEngine(ProviderRouter({"failure": provider, "mock": MockProvider()}))
    task = PhysicalTask("failure", provider="failure")

    result = engine.execute(task)

    assert result.failed
    assert result.error.code is ProviderErrorCode.UNKNOWN
    assert task.state is TaskState.FAILED


def test_provider_unavailable_fails_task():
    provider = CountingProvider(
        ProviderResult(
            False,
            ProviderStatus.FAILED,
            message="503 unavailable",
            error=ProviderError(ProviderErrorCode.UNAVAILABLE, "503 unavailable", retryable=True),
        )
    )
    engine = ExecutionEngine(ProviderRouter({"unavailable": provider, "mock": MockProvider()}))
    task = PhysicalTask("unavailable", provider="unavailable")

    result = engine.execute(task)

    assert result.failed
    assert result.error.code is ProviderErrorCode.UNAVAILABLE
    assert task.state is TaskState.FAILED


def test_invalid_task_is_rejected_before_execution():
    bad = PhysicalTaskSpec(
        intent="make it",
        action="manufacture_and_fulfill",
        product="mug",
        destination=None,
        provider="mock",
    )
    with pytest.raises(ValueError, match="destination is required"):
        ExecutionPlanner().build(bad)


def test_duplicate_execution_is_idempotent():
    provider = CountingProvider()
    engine = ExecutionEngine(ProviderRouter({"counting": provider, "mock": MockProvider()}))
    task = PhysicalTask("duplicate", provider="counting")

    first = engine.execute(task)
    second = engine.execute(task)

    assert first is second
    assert provider.calls == 1
    assert task.state is TaskState.SUBMITTED


def test_duplicate_webhook_is_idempotent():
    task = PhysicalTask("webhook")
    task.state = TaskState.SUBMITTED
    provider = MockProvider()

    handle_provider_webhook(task, provider, "processing")
    handle_provider_webhook(task, provider, "processing")

    assert task.state is TaskState.PROCESSING


def test_incomplete_provider_result_fails_safely():
    provider = CountingProvider(ProviderResult(True, None, message="accepted without status"))
    engine = ExecutionEngine(ProviderRouter({"incomplete": provider, "mock": MockProvider()}))
    task = PhysicalTask("incomplete", provider="incomplete")

    result = engine.execute(task)

    assert result.failed
    assert result.error.code is ProviderErrorCode.VALIDATION
    assert "status is required" in result.error.message
    assert task.state is TaskState.FAILED
