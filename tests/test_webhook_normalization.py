from app.models.task import PhysicalTask, TaskState
from app.providers.prodigi import ProdigiSandboxAdapter
from app.providers.cloudprinter import CloudprinterSandboxAdapter
from app.webhooks.handler import handle_provider_webhook


def test_prodigi_webhook_uses_normalized_status():
    task = PhysicalTask(intent="x")
    task.state = TaskState.SUBMITTED
    result = handle_provider_webhook(task, ProdigiSandboxAdapter(), "in_production")
    assert result.state is TaskState.PROCESSING


def test_cloudprinter_webhook_uses_normalized_status():
    task = PhysicalTask(intent="x")
    task.state = TaskState.SUBMITTED
    result = handle_provider_webhook(task, CloudprinterSandboxAdapter(), "production")
    assert result.state is TaskState.PROCESSING
