import pytest

from app.application import ApplicationService
from app.contracts.physical_task import PhysicalTaskSpec
from app.models.task import TaskState


def test_application_service_executes_intent_through_existing_pipeline():
    service = ApplicationService()

    response = service.execute_intent(
        "make 1 mug using design.png and ship to TEST-DESTINATION"
    )

    assert response.accepted is True
    assert response.state == TaskState.SUBMITTED.value
    assert response.provider == "mock"
    assert response.external_id
    assert response.error_code is None


def test_application_service_supports_structured_spec():
    service = ApplicationService()
    spec = PhysicalTaskSpec(
        intent="make one mug and ship it",
        action="manufacture_and_fulfill",
        product="mug",
        destination="TEST-DESTINATION",
    )

    response = service.execute_spec(spec)

    assert response.accepted is True
    assert response.state == TaskState.SUBMITTED.value
    assert response.provider == "mock"


def test_application_service_rejects_ambiguous_intent_before_execution():
    service = ApplicationService()

    with pytest.raises(ValueError, match="unsupported or ambiguous intent"):
        service.execute_intent("make something for me")


def test_application_service_preserves_unknown_provider_rejection():
    service = ApplicationService()
    spec = PhysicalTaskSpec(
        intent="make one mug and ship it",
        action="manufacture_and_fulfill",
        product="mug",
        destination="TEST-DESTINATION",
        provider="sandbox",
    )

    with pytest.raises(ValueError, match="unsupported provider: sandbox"):
        service.execute_spec(spec)


def test_application_response_is_read_only_data():
    response = ApplicationService().execute_intent(
        "make 1 mug and ship to TEST-DESTINATION"
    )

    assert response.task_id
    assert response.state == TaskState.SUBMITTED.value
    assert not hasattr(response, "execute")


def test_application_service_keeps_execution_inside_injected_engine():
    class RecordingEngine:
        def __init__(self):
            self.tasks = []

        def execute(self, task):
            self.tasks.append(task)

            class Result:
                accepted = True
                message = "recorded"
                external_id = "synthetic-external-id"
                error = None

            task.state = TaskState.SUBMITTED
            return Result()

    engine = RecordingEngine()
    service = ApplicationService(engine=engine)

    response = service.execute_intent(
        "make 1 mug and ship to TEST-DESTINATION"
    )

    assert len(engine.tasks) == 1
    assert engine.tasks[0].product == "mug"
    assert response.external_id == "synthetic-external-id"
