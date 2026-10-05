from __future__ import annotations

from app.integrations.accounts.store import ConnectedAccountStore
from app.integrations.google.client import GoogleClient
from app.integrations.oauth.google import GoogleOAuthProvider


class GoogleService:
    """Application boundary for user-authorized Google Workspace operations."""

    def __init__(self, account_store: ConnectedAccountStore, oauth: GoogleOAuthProvider):
        self.account_store = account_store
        self.client = GoogleClient(account_store, oauth)

    def connected(self, user_id: str) -> bool:
        return self.account_store.get(user_id, "google") is not None

    def disconnect(self, user_id: str) -> None:
        self.account_store.delete(user_id, "google")

    def gmail_list_messages(self, user_id: str, *, query: str = "", max_results: int = 20) -> dict:
        return self.client.gmail_list_messages(user_id, query=query, max_results=max_results)

    def gmail_get_message(self, user_id: str, message_id: str) -> dict:
        return self.client.gmail_get_message(user_id, message_id)

    def gmail_send(self, user_id: str, raw_message: str) -> dict:
        return self.client.gmail_send(user_id, raw_message)

    def calendar_list_events(self, user_id: str, *, calendar_id: str = "primary", time_min: str | None = None,
                             time_max: str | None = None, max_results: int = 20) -> dict:
        return self.client.calendar_list_events(
            user_id, calendar_id=calendar_id, time_min=time_min, time_max=time_max, max_results=max_results
        )

    def calendar_create_event(self, user_id: str, *, summary: str, start: dict, end: dict,
                              calendar_id: str = "primary", description: str | None = None) -> dict:
        return self.client.calendar_create_event(
            user_id, summary=summary, start=start, end=end, calendar_id=calendar_id, description=description
        )

    def sheets_get(self, user_id: str, spreadsheet_id: str, range_name: str) -> dict:
        return self.client.sheets_get(user_id, spreadsheet_id, range_name)

    def sheets_update(self, user_id: str, spreadsheet_id: str, range_name: str, values: list[list[object]]) -> dict:
        return self.client.sheets_update(user_id, spreadsheet_id, range_name, values)
