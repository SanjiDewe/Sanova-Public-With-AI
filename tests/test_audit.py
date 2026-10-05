from app.audit.trail import AuditTrail
from app.models.task import PhysicalTask, TaskState
from app.orchestration.executor import ExecutionEngine
from app.webhooks.handler import handle_simulated_webhook


def test_audit_is_append_only_and_hash_chain_verifies():
    audit = AuditTrail()
    audit.append("task_created", "t1", state="created")
    audit.append("state_changed", "t1", state="submitted")
    assert [e.event_type for e in audit.events("t1")] == ["task_created", "state_changed"]
    assert audit.verify() is True


def test_audit_detects_tampering():
    audit = AuditTrail()
    audit.append("task_created", "t1")
    audit._events[0]["outcome"] = "tampered"
    assert audit.verify() is False


def test_execution_emits_ordered_audit_events():
    audit = AuditTrail()
    task = PhysicalTask("make test item")
    result = ExecutionEngine(audit=audit).execute(task)
    events = audit.events(task.id)
    types = [e.event_type for e in events]
    assert result.accepted
    assert types[:3] == ["execution_requested", "safety_check_passed", "provider_selected"]
    assert "execution_fenced" in types
    assert "provider_result" in types
    assert types[-2:] == ["state_changed", "execution_persisted"]
    assert audit.verify()


def test_duplicate_execution_is_audited():
    audit = AuditTrail()
    task = PhysicalTask("make test item")
    engine = ExecutionEngine(audit=audit)
    engine.execute(task)
    engine.execute(task)
    assert any(e.event_type == "execution_deduplicated" for e in audit.events(task.id))


def test_webhook_transition_is_audited():
    audit = AuditTrail()
    task = PhysicalTask("make test item")
    task.state = TaskState.SUBMITTED
    handle_simulated_webhook(task, "processing", audit=audit)
    event = audit.events(task.id)[0]
    assert event.event_type == "webhook_processed"
    assert event.outcome == "transitioned"
    assert event.state == "processing"


def test_duplicate_webhook_is_audited():
    audit = AuditTrail()
    task = PhysicalTask("make test item")
    task.state = TaskState.SUBMITTED
    handle_simulated_webhook(task, "processing", audit=audit)
    handle_simulated_webhook(task, "processing", audit=audit)
    events = audit.events(task.id)
    assert events[-1].outcome == "duplicate"
    assert audit.verify()


def test_audit_can_persist_across_instances(tmp_path):
    first = AuditTrail(tmp_path)
    first.append("task_created", "t1", state="created")
    second = AuditTrail(tmp_path)
    assert [e.event_type for e in second.events("t1")] == ["task_created"]
    assert second.verify()


def test_audit_does_not_control_execution_state():
    audit = AuditTrail()
    task = PhysicalTask("make test item")
    engine = ExecutionEngine(audit=audit)
    engine.execute(task)
    task.state = TaskState.COMPLETED
    assert audit.events(task.id)
    assert audit.verify()
