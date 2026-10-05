from app.core.audit.trail import AuditTrail
from app.core.models.task import PhysicalTask, TaskState
from app.core.orchestration.state_machine import transition
from app.integrations.providers.base import PhysicalProvider
from app.integrations.providers.normalization import normalize_status


def handle_simulated_webhook(task: PhysicalTask, status: str, audit=None) -> PhysicalTask:
    trail = audit or AuditTrail()
    normalized = normalize_status(status)
    previous = task.state
    result = transition(task, TaskState(normalized.value))
    trail.append("webhook_processed", task.id, state=result.state.value,
                 outcome="duplicate" if previous is result.state else "transitioned",
                 metadata={"source": "simulated", "raw_status": status})
    return result


def handle_provider_webhook(task: PhysicalTask, provider: PhysicalProvider, raw_status: str, audit=None) -> PhysicalTask:
    trail = audit or AuditTrail()
    normalized = provider.normalize_status(raw_status)
    previous = task.state
    result = transition(task, TaskState(normalized.value))
    trail.append("webhook_processed", task.id, state=result.state.value,
                 provider=provider.name,
                 outcome="duplicate" if previous is result.state else "transitioned",
                 metadata={"source": "provider", "raw_status": raw_status})
    return result
