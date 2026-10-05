from app.contracts.physical_task import PhysicalTaskSpec
from app.models.task import TaskState
from app.orchestration.executor import ExecutionEngine
from app.planner.planner import ExecutionPlanner


def test_planned_task_can_only_simulate_execution():
    spec = PhysicalTaskSpec(
        intent="make one mug",
        action="manufacture_and_fulfill",
        product="mug",
        asset="design.png",
        destination="TEST-DESTINATION",
        provider="prodigi",
    )
    task = ExecutionPlanner().build(spec)
    result = ExecutionEngine().execute(task)

    assert result.accepted is True
    assert result.message == "simulated only"
    assert task.state == TaskState.SUBMITTED
    assert task.external_id is None
