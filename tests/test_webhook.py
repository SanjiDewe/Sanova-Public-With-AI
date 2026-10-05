from app.models.task import PhysicalTask, TaskState
from app.orchestration.executor import ExecutionEngine
from app.webhooks.handler import handle_simulated_webhook

def test_simulated_webhooks_drive_state():
    task = PhysicalTask('test', provider='cloudprinter')
    ExecutionEngine().execute(task)
    for status in ['processing', 'fulfillment', 'shipped', 'completed']:
        handle_simulated_webhook(task, status)
    assert task.state == TaskState.COMPLETED
