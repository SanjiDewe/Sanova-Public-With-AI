from app.models.task import PhysicalTask, TaskState
from app.orchestration.executor import ExecutionEngine

def test_execution_is_simulated():
    task = PhysicalTask('make a mug', provider='prodigi')
    result = ExecutionEngine().execute(task)
    assert result.accepted
    assert result.message == 'simulated only'
    assert task.state == TaskState.SUBMITTED
    assert task.external_id is None
