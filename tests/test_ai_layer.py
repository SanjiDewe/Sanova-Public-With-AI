import pytest

from app.ai.agent import AIAgent
from app.ai.provider import AIMessage, AIProvider, AIProviderRegistry, AIResponse, MockAIProvider
from app.ai.store import AIConversationStore
from app.ai.tools import ToolRegistry
from app.identity import IdentityService, IdentityStore


class ToolCallingProvider(AIProvider):
    name = "test"

    def models(self):
        from app.ai.provider import AIModel
        return (AIModel("test", "test-model", "Test Model"),)

    def generate(self, *, model, messages, system):
        return AIResponse(
            "test",
            model,
            '{"action":"tool","tool":"prepare","arguments":{"value":"ok"}}',
        )


def test_ai_preferences_persist_per_user():
    store = IdentityStore()
    service = IdentityService(store)
    user = service.register("ai@example.com", "correct horse battery staple")
    assert store.get_ai_preferences(user.id) is None
    store.save_ai_preferences(user.id, "OpenAI", "model-a")
    assert store.get_ai_preferences(user.id) == {"provider": "openai", "model": "model-a"}
    store.save_ai_preferences(user.id, "google", "model-b")
    assert store.get_ai_preferences(user.id) == {"provider": "google", "model": "model-b"}
    store.close()


def test_agent_requires_selected_provider_and_model():
    registry = AIProviderRegistry({"mock": MockAIProvider(("m1",))})
    agent = AIAgent(registry, ToolRegistry(), AIConversationStore())
    with pytest.raises(ValueError, match="not available"):
        agent.start_or_load("u1", None, "mock", "missing")


def test_ai_approval_is_not_execution_and_can_be_restored():
    tools = ToolRegistry()
    from app.ai.tools import Tool, ToolResult
    tools.register(Tool("prepare", "test", lambda args: ToolResult("prepare", True, args, True)))
    registry = AIProviderRegistry({"test": ToolCallingProvider()})
    agent = AIAgent(registry, tools, AIConversationStore())

    turn = agent.chat(user_id="u1", conversation_id=None, provider="test", model="test-model", message="do it")
    assert turn.proposal == {"tool": "prepare", "data": {"value": "ok"}}

    proposal = agent.approve(user_id="u1", conversation_id=turn.conversation_id)
    assert proposal["data"] == {"value": "ok"}
    assert agent.pending("u1", turn.conversation_id) == proposal

    agent.restore_approval(user_id="u1", conversation_id=turn.conversation_id)
    assert agent.pending("u1", turn.conversation_id) == proposal

    agent.approve(user_id="u1", conversation_id=turn.conversation_id)
    agent.complete_approval(user_id="u1", conversation_id=turn.conversation_id)
    assert agent.pending("u1", turn.conversation_id) is None


def test_google_tool_registry_matches_workspace_capabilities_and_gates_writes():
    from app.ai.tools import build_tool_registry

    class FakeGoogle:
        def gmail_list_messages(self, user_id, **kwargs): return {"ok": "gmail-list"}
        def gmail_get_message(self, user_id, message_id): return {"ok": "gmail-get"}
        def gmail_send(self, user_id, raw_message): return {"ok": "gmail-send"}
        def calendar_list_events(self, user_id, **kwargs): return {"ok": "calendar-list"}
        def calendar_create_event(self, user_id, **kwargs): return {"ok": "calendar-create"}
        def sheets_get(self, user_id, spreadsheet_id, range_name): return {"ok": "sheets-get"}
        def sheets_update(self, user_id, spreadsheet_id, range_name, values): return {"ok": "sheets-update"}

    registry = build_tool_registry(google=FakeGoogle())
    assert {
        "google_gmail_list", "google_gmail_get", "google_gmail_send",
        "google_calendar_list", "google_calendar_create",
        "google_sheets_get", "google_sheets_update",
    }.issubset(set(registry.names()))
    context = {"user_id": "u1"}
    proposal = registry.call("google_gmail_send", {"raw_message": "To: user@example.com\n\nhello"}, context=context)
    assert proposal.requires_approval is True
    executed = registry.call("google_gmail_send", proposal.data, context=context, approved=True)
    assert executed.requires_approval is False
    assert executed.data == {"ok": "gmail-send"}
