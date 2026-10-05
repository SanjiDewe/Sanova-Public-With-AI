from __future__ import annotations

from app.integrations.contracts.email import EmailMessage, EmailProvider, EmailResult


class MockEmailProvider(EmailProvider):
    name = "mock"
    sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailResult:
        self.sent.append(message)
        return EmailResult(True, self.name, f"mock-{len(self.sent)}", "simulated only")
