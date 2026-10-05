from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.core.intent.parser import RuleBasedIntentParser
from app.integrations.google import GoogleService


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    data: dict[str, Any]
    requires_approval: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    handler: Callable[[dict[str, Any]], ToolResult]


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def definitions(self) -> list[dict[str, str]]:
        return [{"name": tool.name, "description": tool.description} for tool in self._tools.values()]

    def call(self, name: str, arguments: dict[str, Any], *, context: dict[str, Any] | None = None, approved: bool = False) -> ToolResult:
        try:
            tool = self._tools[name]
        except KeyError as exc:
            raise ValueError(f"unknown AI tool: {name}") from exc
        payload = dict(arguments)
        if context and name.startswith("google_"):
            payload["__context"] = dict(context)
        if approved:
            payload["__approved"] = True
        return tool.handler(payload)


def build_tool_registry(provider_names: tuple[str, ...] | None = None, *, google: GoogleService | None = None) -> ToolRegistry:
    registry = ToolRegistry()

    def prepare_physical_task(arguments: dict[str, Any]) -> ToolResult:
        raw = str(arguments.get("intent", "")).strip()
        if not raw:
            raise ValueError("tool argument 'intent' is required")
        structured = RuleBasedIntentParser().parse(raw)
        if structured.provider and provider_names is not None and structured.provider not in provider_names:
            raise ValueError(f"unsupported physical provider: {structured.provider}")
        return ToolResult(
            name="prepare_physical_task",
            ok=True,
            requires_approval=True,
            data={
                "intent": structured.raw_text,
                "action": structured.action,
                "product": structured.product,
                "asset": structured.asset,
                "destination": structured.destination,
                "quantity": structured.quantity,
                "provider": structured.provider,
            },
        )

    registry.register(Tool(
        "prepare_physical_task",
        "Validate and prepare a physical sandbox task. This tool never executes it; user approval is required.",
        prepare_physical_task,
    ))

    if google is not None:
        def google_context(arguments: dict[str, Any]) -> str:
            user_id = str(arguments.get("__context", {}).get("user_id", "")).strip()
            if not user_id:
                raise ValueError("authenticated user context is required")
            return user_id

        def google_gmail_list(arguments: dict[str, Any]) -> ToolResult:
            data = google.gmail_list_messages(google_context(arguments), query=str(arguments.get("query", "")), max_results=int(arguments.get("max_results", 20)))
            return ToolResult("google_gmail_list", True, data)

        def google_gmail_get(arguments: dict[str, Any]) -> ToolResult:
            message_id = str(arguments.get("message_id", "")).strip()
            if not message_id:
                raise ValueError("message_id is required")
            data = google.gmail_get_message(google_context(arguments), message_id)
            return ToolResult("google_gmail_get", True, data)

        def google_gmail_send(arguments: dict[str, Any]) -> ToolResult:
            raw_message = str(arguments.get("raw_message", ""))
            if not raw_message:
                raise ValueError("raw_message is required")
            if not arguments.get("__approved"):
                return ToolResult("google_gmail_send", True, {"raw_message": raw_message}, requires_approval=True)
            return ToolResult("google_gmail_send", True, google.gmail_send(google_context(arguments), raw_message))

        def google_calendar_list(arguments: dict[str, Any]) -> ToolResult:
            data = google.calendar_list_events(
                google_context(arguments), calendar_id=str(arguments.get("calendar_id", "primary")),
                time_min=arguments.get("time_min"), time_max=arguments.get("time_max"),
                max_results=int(arguments.get("max_results", 20)),
            )
            return ToolResult("google_calendar_list", True, data)

        def google_calendar_create(arguments: dict[str, Any]) -> ToolResult:
            summary = str(arguments.get("summary", "")).strip()
            start = arguments.get("start")
            end = arguments.get("end")
            if not summary or not isinstance(start, dict) or not isinstance(end, dict):
                raise ValueError("summary, start, and end are required")
            payload = {
                "summary": summary, "start": start, "end": end,
                "calendar_id": str(arguments.get("calendar_id", "primary")),
                "description": arguments.get("description"),
            }
            if not arguments.get("__approved"):
                return ToolResult("google_calendar_create", True, payload, requires_approval=True)
            return ToolResult("google_calendar_create", True, google.calendar_create_event(google_context(arguments), **payload))

        def google_sheets_get(arguments: dict[str, Any]) -> ToolResult:
            spreadsheet_id = str(arguments.get("spreadsheet_id", "")).strip()
            range_name = str(arguments.get("range", "")).strip()
            if not spreadsheet_id or not range_name:
                raise ValueError("spreadsheet_id and range are required")
            return ToolResult("google_sheets_get", True, google.sheets_get(google_context(arguments), spreadsheet_id, range_name))

        def google_sheets_update(arguments: dict[str, Any]) -> ToolResult:
            spreadsheet_id = str(arguments.get("spreadsheet_id", "")).strip()
            range_name = str(arguments.get("range", "")).strip()
            values = arguments.get("values")
            if not spreadsheet_id or not range_name or not isinstance(values, list) or not all(isinstance(row, list) for row in values):
                raise ValueError("spreadsheet_id, range, and values are required")
            if not arguments.get("__approved"):
                return ToolResult(
                    "google_sheets_update", True,
                    {"spreadsheet_id": spreadsheet_id, "range": range_name, "values": values},
                    requires_approval=True,
                )
            return ToolResult("google_sheets_update", True, google.sheets_update(google_context(arguments), spreadsheet_id, range_name, values))

        registry.register(Tool("google_gmail_list", "Read the authenticated user's Gmail message list.", google_gmail_list))
        registry.register(Tool("google_gmail_get", "Read an authenticated user's Gmail message metadata.", google_gmail_get))
        registry.register(Tool("google_gmail_send", "Send a Gmail message for the authenticated user after explicit approval.", google_gmail_send))
        registry.register(Tool("google_calendar_list", "Read the authenticated user's Google Calendar events.", google_calendar_list))
        registry.register(Tool("google_calendar_create", "Create a Google Calendar event for the authenticated user after explicit approval.", google_calendar_create))
        registry.register(Tool("google_sheets_get", "Read values from an authenticated Google Sheet.", google_sheets_get))
        registry.register(Tool("google_sheets_update", "Update values in an authenticated Google Sheet after explicit approval.", google_sheets_update))

    return registry
