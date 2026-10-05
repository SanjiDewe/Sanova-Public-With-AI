import pytest

from app.contracts.intent import StructuredIntent
from app.intent.parser import IntentParser, RuleBasedIntentParser
from app.models.task import TaskState
from app.planner.planner import ExecutionPlanner


def test_intent_parser_is_an_execution_free_boundary():
    parser = RuleBasedIntentParser()
    assert isinstance(parser, IntentParser)
    intent = parser.parse("make 2 mug using design.png and ship to TEST-DESTINATION via prodigi")

    assert intent.product == "mug"
    assert intent.quantity == 2
    assert intent.asset == "design.png"
    assert intent.destination == "TEST-DESTINATION"
    assert intent.provider == "prodigi"


def test_structured_intent_can_only_feed_the_existing_planner():
    intent = RuleBasedIntentParser().parse(
        "make 1 mug using design.png and ship to TEST-DESTINATION via prodigi"
    )

    task = ExecutionPlanner().build_from_intent(intent)

    assert task.state == TaskState.CREATED
    assert task.provider == "prodigi"
    assert task.product == "mug"
    assert task.external_id is None


def test_parser_rejects_ambiguous_intent():
    with pytest.raises(ValueError, match="unsupported or ambiguous intent"):
        RuleBasedIntentParser().parse("make something for me")


def test_structured_intent_rejects_missing_fulfillment_destination():
    intent = StructuredIntent(
        raw_text="make one mug",
        intent="make one mug",
        action="manufacture_and_fulfill",
        product="mug",
    )
    with pytest.raises(ValueError, match="destination is required"):
        intent.validate()
