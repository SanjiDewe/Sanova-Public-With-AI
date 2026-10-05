from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.ai.provider import AIMessage, AIProviderRegistry
from app.ai.store import AIConversationStore
from app.ai.tools import ToolRegistry


SYSTEM_PROMPT = """You are Sanova's action-oriented assistant. You can converse naturally, but you must never execute physical actions yourself.
When a user asks for a physical task, return JSON only in this shape:
{"action":"tool","tool":"prepare_physical_task","arguments":{"intent":"make 1 mug using design.png and ship to TEST-DESTINATION via mock"}}
The intent must use Sanova's supported task syntax. If required information is missing or ambiguous, return JSON only:
{"action":"respond","message":"..."}
For ordinary conversation return the same respond shape. Never invent provider names. Use a provider explicitly supplied by the user or ask for one.
"""


@dataclass(frozen=True)
class AgentTurn:
    conversation_id: str
    provider: str
    model: str
    message: str
    proposal: dict[str, Any] | None = None
    error: str | None = None


class AIAgent:
    def __init__(self, providers: AIProviderRegistry, tools: ToolRegistry, store: AIConversationStore):
        self.providers = providers
        self.tools = tools
        self.store = store

    def start_or_load(self, user_id: str, conversation_id: str | None, provider: str, model: str) -> dict[str, Any]:
        cid = conversation_id or str(uuid.uuid4())
        record = self.store.get(cid)
        if record is None:
            record = {"id": cid, "user_id": user_id, "messages": [], "pending": None}
            self.store.put(cid, record)
        elif record.get("user_id") != user_id:
            raise PermissionError("conversation does not belong to the current user")
        if not self.providers.has_model(provider, model):
            raise ValueError("selected AI provider/model is not available")
        return record

    def chat(self, *, user_id: str, conversation_id: str | None, provider: str, model: str, message: str) -> AgentTurn:
        message = message.strip()
        if not message:
            raise ValueError("message is required")
        record = self.start_or_load(user_id, conversation_id, provider, model)
        record["messages"].append({"role": "user", "content": message})
        history = [AIMessage(item["role"], item["content"]) for item in record["messages"][-20:]]
        try:
            response = self.providers.get(provider).generate(model=model, messages=history, system=SYSTEM_PROMPT)
            payload = self._parse_payload(response.text)
            proposal = None
            if payload.get("action") == "tool":
                result = self.tools.call(payload.get("tool", ""), payload.get("arguments") or {}, context={"user_id": user_id})
                if result.requires_approval:
                    proposal = {"tool": result.name, "data": result.data}
                    record["pending"] = proposal
                    assistant_text = "I prepared the action. Please review it and approve it before execution."
                else:
                    assistant_text = json.dumps(result.data)
            else:
                assistant_text = str(payload.get("message") or response.text)
            record["messages"].append({"role": "assistant", "content": assistant_text})
            self.store.put(record["id"], record)
            return AgentTurn(record["id"], provider, model, assistant_text, proposal)
        except Exception as exc:
            record["messages"].append({"role": "assistant", "content": str(exc)})
            self.store.put(record["id"], record)
            return AgentTurn(record["id"], provider, model, "I could not complete that request.", error=str(exc))

    def pending(self, user_id: str, conversation_id: str) -> dict[str, Any] | None:
        record = self.start_or_load(user_id, conversation_id, self.providers.names()[0], self.providers.models(self.providers.names()[0])[0].model)
        return record.get("pending")

    def approve(self, *, user_id: str, conversation_id: str) -> dict[str, Any]:
        record = self.store.get(conversation_id)
        if not record or record.get("user_id") != user_id:
            raise PermissionError("conversation not found")
        proposal = record.get("pending")
        if not proposal:
            raise ValueError("there is no pending action to approve")
        if record.get("approval_in_progress"):
            raise ValueError("the pending action is already being approved")
        record["approval_in_progress"] = True
        self.store.put(conversation_id, record)
        return proposal

    def complete_approval(self, *, user_id: str, conversation_id: str) -> None:
        record = self.store.get(conversation_id)
        if not record or record.get("user_id") != user_id:
            raise PermissionError("conversation not found")
        record["pending"] = None
        record.pop("approval_in_progress", None)
        self.store.put(conversation_id, record)

    def restore_approval(self, *, user_id: str, conversation_id: str) -> None:
        record = self.store.get(conversation_id)
        if not record or record.get("user_id") != user_id:
            raise PermissionError("conversation not found")
        record.pop("approval_in_progress", None)
        self.store.put(conversation_id, record)

    def reject(self, *, user_id: str, conversation_id: str) -> None:
        record = self.store.get(conversation_id)
        if not record or record.get("user_id") != user_id:
            raise PermissionError("conversation not found")
        record["pending"] = None
        record["messages"].append({"role": "assistant", "content": "The pending action was cancelled."})
        self.store.put(conversation_id, record)

    @staticmethod
    def _parse_payload(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`").replace("json\n", "", 1).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            return {"action": "respond", "message": cleaned}
        if not isinstance(payload, dict):
            return {"action": "respond", "message": cleaned}
        return payload
