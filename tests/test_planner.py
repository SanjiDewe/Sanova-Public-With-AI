from app.contracts.physical_task import PhysicalTaskSpec
from app.planner.planner import ExecutionPlanner
from app.models.task import TaskState


def test_planner_only_builds_task():
    spec = PhysicalTaskSpec(
        intent="make one mug",
        action="manufacture_and_fulfill",
        product="mug",
        asset="design.png",
        destination="TEST-DESTINATION",
        provider="prodigi",
    )
    task = ExecutionPlanner().build(spec)
    assert task.provider == "prodigi"
    assert task.product == "mug"
    assert task.state == TaskState.CREATED
    assert task.external_id is None
