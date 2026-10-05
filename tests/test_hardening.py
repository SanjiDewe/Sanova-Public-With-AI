import threading
import time

import pytest

from app.models.task import PhysicalTask, TaskState
from app.orchestration.executor import ExecutionEngine
from app.orchestration.router import ProviderRouter
from app.providers.base import PhysicalProvider, ProviderResult, ProviderStatus
from app.providers.mock import MockProvider
from app.providers.prodigi import ProdigiSandboxAdapter
from app.config import assert_sandbox_url


class SlowCountingProvider(MockProvider):
    name = "slow-counting"

    def __init__(self):
        self.calls = 0

    def submit_sandbox(self, task):
        self.calls += 1
        time.sleep(0.03)
        return super().submit_sandbox(task)


class InconsistentProvider(MockProvider):
    name = "inconsistent"

    def submit_sandbox(self, task):
        return ProviderResult(True, ProviderStatus.FAILED, message="bad provider result")


def test_non_created_task_cannot_be_reexecuted_by_a_fresh_engine():
    task = PhysicalTask("task", provider="mock")
    first = ExecutionEngine().execute(task)
    assert first.accepted
    assert task.state is TaskState.SUBMITTED

    with pytest.raises(ValueError, match="not executable"):
        ExecutionEngine().execute(task)


def test_concurrent_duplicate_execution_submits_once():
    provider = SlowCountingProvider()
    engine = ExecutionEngine(ProviderRouter({"slow": provider, "mock": MockProvider()}))
    task = PhysicalTask("concurrent", provider="slow")
    results = []

    threads = [threading.Thread(target=lambda: results.append(engine.execute(task))) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert provider.calls == 1
    assert len(results) == 8
    assert all(result is results[0] for result in results)


def test_unknown_provider_fails_closed_instead_of_falling_back_to_mock():
    with pytest.raises(ValueError, match="unsupported provider"):
        ProviderRouter().choose("not-a-provider")


def test_rejected_provider_result_is_normalized_to_failed():
    class RejectingProvider(MockProvider):
        name = "rejecting"

        def submit_sandbox(self, task):
            return ProviderResult(False, ProviderStatus.PROCESSING, message="rejected")

    engine = ExecutionEngine(ProviderRouter({"rejecting": RejectingProvider(), "mock": MockProvider()}))
    task = PhysicalTask("reject", provider="rejecting")
    result = engine.execute(task)

    assert result.failed
    assert result.status is ProviderStatus.FAILED
    assert result.error is not None
    assert task.state is TaskState.FAILED


def test_accepted_failed_provider_result_is_rejected_as_invalid():
    engine = ExecutionEngine(ProviderRouter({"bad": InconsistentProvider(), "mock": MockProvider()}))
    task = PhysicalTask("inconsistent", provider="bad")
    result = engine.execute(task)

    assert result.failed
    assert result.error.code.value == "validation"
    assert task.state is TaskState.FAILED


def test_blank_task_intent_is_rejected_before_provider_call():
    task = PhysicalTask("   ", provider="mock")
    with pytest.raises(ValueError, match="intent"):
        ExecutionEngine().execute(task)


def test_blank_task_id_is_rejected_before_provider_call():
    task = PhysicalTask("valid", provider="mock", id="")
    with pytest.raises(ValueError, match="id and intent"):
        ExecutionEngine().execute(task)


@pytest.mark.parametrize(
    ("url", "provider"),
    [
        ("https://api.prodigi.com/v4.0/Orders", "prodigi"),
        ("https://prodigi.com/v4.0/Orders", "prodigi"),
        ("https://cloudprinter.com/cloudcore/1.0/orders/add", "cloudprinter"),
    ],
)
def test_known_live_provider_hosts_are_forbidden(url, provider):
    with pytest.raises(RuntimeError, match="live API host"):
        assert_sandbox_url(url, provider)


def test_unknown_sandbox_host_is_rejected():
    with pytest.raises(RuntimeError, match="not allowlisted"):
        assert_sandbox_url("https://sandbox.example/cloudcore/1.0/orders/add", "cloudprinter")


def test_provider_specific_sandbox_hosts_are_allowed():
    assert_sandbox_url("https://api.sandbox.prodigi.com/v4.0/Orders", "prodigi")
    assert_sandbox_url("https://api.cloudprinter.com/cloudcore/1.0/orders/add", "cloudprinter")


def test_provider_mismatch_is_rejected():
    with pytest.raises(RuntimeError, match="not allowlisted"):
        assert_sandbox_url("https://api.sandbox.prodigi.com/v4.0/Orders", "cloudprinter")
