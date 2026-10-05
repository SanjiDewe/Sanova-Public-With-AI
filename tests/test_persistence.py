
from pathlib import Path

from app.models.task import PhysicalTask, TaskState
from app.orchestration.executor import ExecutionEngine
from app.orchestration.router import ProviderRouter
from app.persistence.store import ExecutionStore
from app.providers.mock import MockProvider


class CountingProvider(MockProvider):
    name = "counting"

    def __init__(self):
        self.calls = 0

    def submit_sandbox(self, task):
        self.calls += 1
        return super().submit_sandbox(task)


def test_persisted_result_survives_new_engine(tmp_path: Path):
    store = ExecutionStore(tmp_path / "state")
    provider = CountingProvider()
    task = PhysicalTask("persist", provider="counting")

    first = ExecutionEngine(ProviderRouter({"counting": provider, "mock": MockProvider()}), store).execute(task)
    assert first.accepted
    assert task.state is TaskState.SUBMITTED

    restarted = ExecutionEngine(
        ProviderRouter({"counting": provider, "mock": MockProvider()}),
        ExecutionStore(tmp_path / "state"),
    )
    replay = restarted.execute(PhysicalTask("persist", provider="counting", id=task.id))

    assert replay == first
    assert provider.calls == 1


def test_recovery_fence_prevents_resubmission_after_interrupted_execution(tmp_path: Path):
    store = ExecutionStore(tmp_path / "state")
    task = PhysicalTask("interrupted", provider="mock")
    store.put(task, None, "in_flight")

    provider = CountingProvider()
    result = ExecutionEngine(
        ProviderRouter({"counting": provider, "mock": MockProvider()}),
        ExecutionStore(tmp_path / "state"),
    ).execute(PhysicalTask("interrupted", provider="counting", id=task.id))

    assert result.failed
    assert result.status.value == "failed"
    assert "manual recovery required" in result.message
    assert provider.calls == 0


def test_recovery_marks_task_failed_and_persists_terminal_result(tmp_path: Path):
    store = ExecutionStore(tmp_path / "state")
    task = PhysicalTask("recover", provider="mock")
    store.put(task, None, "in_flight")

    recovered = PhysicalTask("recover", provider="mock", id=task.id)
    result = ExecutionEngine(store=ExecutionStore(tmp_path / "state")).execute(recovered)

    assert result.failed
    assert recovered.state is TaskState.FAILED
    record = ExecutionStore(tmp_path / "state").get(task.id)
    assert record["phase"] == "recovered"
    assert record["result"]["status"] == "failed"


def test_atomic_store_writes_valid_json(tmp_path: Path):
    store = ExecutionStore(tmp_path / "state")
    task = PhysicalTask("atomic", provider="mock")
    store.put(task, None, "in_flight")

    files = list((tmp_path / "state").iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".json"
    assert store.get(task.id)["version"] == 1


def test_persisted_task_state_is_restored(tmp_path: Path):
    store = ExecutionStore(tmp_path / "state")
    task = PhysicalTask("restore", provider="mock")
    provider = CountingProvider()
    result = ExecutionEngine(ProviderRouter({"counting": provider, "mock": MockProvider()}), store).execute(
        PhysicalTask("restore", provider="counting", id=task.id)
    )
    assert result.accepted

    restored = PhysicalTask("restore", provider="counting", id=task.id)
    ExecutionEngine(
        ProviderRouter({"counting": provider, "mock": MockProvider()}),
        ExecutionStore(tmp_path / "state"),
    ).execute(restored)
    assert restored.state is TaskState.SUBMITTED


def test_external_id_is_persisted_when_provider_returns_one(tmp_path: Path):
    class ExternalIdProvider(CountingProvider):
        def submit_sandbox(self, task):
            self.calls += 1
            result = super(CountingProvider, self).submit_sandbox(task)
            return result.__class__(
                True, result.status, "external-123", result.message, result.error
            )

    store = ExecutionStore(tmp_path / "state")
    provider = ExternalIdProvider()
    task = PhysicalTask("external", provider="external")
    result = ExecutionEngine(
        ProviderRouter({"external": provider, "mock": MockProvider()}), store
    ).execute(task)

    assert result.external_id == "external-123"
    assert ExecutionStore(tmp_path / "state").get(task.id)["result"]["external_id"] == "external-123"


def test_in_memory_store_remains_available_for_existing_sandbox_behavior():
    store = ExecutionStore()
    provider = CountingProvider()
    task = PhysicalTask("memory", provider="counting")
    result = ExecutionEngine(
        ProviderRouter({"counting": provider, "mock": MockProvider()}), store
    ).execute(task)

    assert result.accepted
    assert provider.calls == 1


def test_recovery_result_is_idempotent_after_restart(tmp_path: Path):
    state = tmp_path / "state"
    task = PhysicalTask("recover-once", provider="mock")
    ExecutionStore(state).put(task, None, "in_flight")

    first = ExecutionEngine(store=ExecutionStore(state)).execute(
        PhysicalTask("recover-once", provider="mock", id=task.id)
    )
    second = ExecutionEngine(store=ExecutionStore(state)).execute(
        PhysicalTask("recover-once", provider="mock", id=task.id)
    )

    assert first == second
    assert first.failed
