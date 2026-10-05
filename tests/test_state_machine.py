import pytest
from app.models.task import PhysicalTask, TaskState
from app.orchestration.state_machine import transition

def test_happy_path():
    task = PhysicalTask('test')
    for state in [TaskState.SUBMITTED, TaskState.PROCESSING, TaskState.FULFILLMENT, TaskState.SHIPPED, TaskState.COMPLETED]:
        transition(task, state)
    assert task.state == TaskState.COMPLETED

def test_invalid_transition_rejected():
    task = PhysicalTask('test')
    with pytest.raises(ValueError):
        transition(task, TaskState.COMPLETED)
