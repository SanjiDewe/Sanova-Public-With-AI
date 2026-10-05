from app.core.models.task import PhysicalTask, TaskState

_ALLOWED = {
    TaskState.CREATED: {TaskState.SUBMITTED, TaskState.FAILED},
    TaskState.SUBMITTED: {TaskState.PROCESSING, TaskState.FAILED},
    TaskState.PROCESSING: {TaskState.FULFILLMENT, TaskState.FAILED},
    TaskState.FULFILLMENT: {TaskState.SHIPPED, TaskState.FAILED},
    TaskState.SHIPPED: {TaskState.COMPLETED, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
}


def transition(task: PhysicalTask, target: TaskState) -> PhysicalTask:
    # Webhook delivery is at-least-once in practice, so the same event can be
    # delivered more than once. Re-applying the current state is harmless.
    if target is task.state:
        return task
    if target not in _ALLOWED[task.state]:
        raise ValueError(f"invalid transition: {task.state} -> {target}")
    task.state = target
    return task
