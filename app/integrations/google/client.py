from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from app.integrations.accounts.store import ConnectedAccountStore
from app.integrations.oauth.google import GoogleOAuthProvider


class GoogleAPIError(RuntimeError):
    pass


class GoogleClient:
    """Authenticated REST client for Google Workspace APIs."""

    def __init__(self, account_store: ConnectedAccountStore, oauth: GoogleOAuthProvider):
        self.account_store = account_store
        self.oauth = oauth

    def _account(self, user_id: str):
        account = self.account_store.get(user_id, "google")
        if account is None:
            raise GoogleAPIError("Google account is not connected")
        if account.expires_at and datetime.fromisoformat(account.expires_at) <= datetime.now(timezone.utc):
            if not account.refresh_token:
                raise GoogleAPIError("Google access token expired and no refresh token is available")
            token = self.oauth.refresh(account.refresh_token)
            refreshed_scopes = tuple(filter(None, (token.scope or " ").replace(",", " ").split()))
            account = self.account_store.save(
                user_id=user_id,
                provider="google",
                external_subject=account.external_subject,
                email=account.email,
                access_token=token.access_token,
                refresh_token=token.refresh_token or account.refresh_token,
                token_type=token.token_type,
                expires_in=token.expires_in,
                scopes=refreshed_scopes or account.scopes,
            )
        return account

    def request(self, user_id: str, method: str, url: str, *, query: dict[str, str] | None = None,
                body: dict | None = None) -> dict:
        account = self._account(user_id)
        if query:
            url += ("&" if "?" in url else "?") + urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        request = Request(
            url, data=data,
            headers={
                "authorization": f"{account.token_type} {account.access_token}",
                "accept": "application/json",
                **({"content-type": "application/json"} if body is not None else {}),
            },
            method=method.upper(),
        )
        try:
            with urlopen(request, timeout=self.oauth.config.timeout_seconds) as response:
                payload = response.read().decode()
                return json.loads(payload) if payload else {}
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise GoogleAPIError(f"Google API request failed ({exc.code}): {detail[:500]}") from exc

    @staticmethod
    def _path_segment(value: str) -> str:
        return quote(value, safe="")

    def gmail_list_messages(self, user_id: str, *, query: str = "", max_results: int = 20) -> dict:
        params = {"maxResults": str(max(1, min(max_results, 100)))}
        if query:
            params["q"] = query
        return self.request(user_id, "GET", "https://gmail.googleapis.com/gmail/v1/users/me/messages", query=params)

    def gmail_get_message(self, user_id: str, message_id: str) -> dict:
        return self.request(user_id, "GET", f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{self._path_segment(message_id)}", query={"format": "metadata"})

    def gmail_send(self, user_id: str, raw_message: str) -> dict:
        import base64
        encoded = base64.urlsafe_b64encode(raw_message.encode()).decode().rstrip("=")
        return self.request(user_id, "POST", "https://gmail.googleapis.com/gmail/v1/users/me/messages/send", body={"raw": encoded})

    def calendar_list_events(self, user_id: str, *, calendar_id: str = "primary", time_min: str | None = None,
                             time_max: str | None = None, max_results: int = 20) -> dict:
        params = {"maxResults": str(max(1, min(max_results, 250))), "singleEvents": "true", "orderBy": "startTime"}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max
        return self.request(user_id, "GET", f"https://www.googleapis.com/calendar/v3/calendars/{self._path_segment(calendar_id)}/events", query=params)

    def calendar_create_event(self, user_id: str, *, summary: str, start: dict, end: dict,
                              calendar_id: str = "primary", description: str | None = None) -> dict:
        body = {"summary": summary, "start": start, "end": end}
        if description:
            body["description"] = description
        return self.request(user_id, "POST", f"https://www.googleapis.com/calendar/v3/calendars/{self._path_segment(calendar_id)}/events", body=body)

    def sheets_get(self, user_id: str, spreadsheet_id: str, range_name: str) -> dict:
        return self.request(user_id, "GET", f"https://sheets.googleapis.com/v4/spreadsheets/{self._path_segment(spreadsheet_id)}/values/{self._path_segment(range_name)}")

    def sheets_update(self, user_id: str, spreadsheet_id: str, range_name: str, values: list[list[object]]) -> dict:
        return self.request(
            user_id, "PUT",
            f"https://sheets.googleapis.com/v4/spreadsheets/{self._path_segment(spreadsheet_id)}/values/{self._path_segment(range_name)}",
            query={"valueInputOption": "USER_ENTERED"},
            body={"range": range_name, "majorDimension": "ROWS", "values": values},
        )
