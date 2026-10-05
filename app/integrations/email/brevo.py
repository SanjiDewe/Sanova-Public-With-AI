from __future__ import annotations

import json
from urllib.request import Request, urlopen

from app.config import email_provider_config
from app.integrations.contracts.email import EmailMessage, EmailProvider, EmailResult


class BrevoEmailProvider(EmailProvider):
    name = "brevo"

    def __init__(self) -> None:
        self.config = email_provider_config("brevo")

    def send(self, message: EmailMessage) -> EmailResult:
        if not self.config.api_key:
            raise RuntimeError("Brevo API key is not configured")
        sender_email = message.from_email or self.config.from_email
        if not sender_email:
            raise RuntimeError("Brevo sender email is not configured")
        payload = {
            "sender": {"email": sender_email, **({"name": message.from_name} if message.from_name else {})},
            "to": [{"email": message.to}],
            "subject": message.subject,
            "textContent": message.text,
        }
        if message.html:
            payload["htmlContent"] = message.html
        request = Request(
            f"{self.config.base_url.rstrip('/')}/smtp/email",
            data=json.dumps(payload).encode(),
            headers={"accept": "application/json", "api-key": self.config.api_key, "content-type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=self.config.timeout_seconds) as response:
            body = json.loads(response.read().decode() or "{}")
        return EmailResult(True, self.name, body.get("messageId"), "accepted by Brevo")
