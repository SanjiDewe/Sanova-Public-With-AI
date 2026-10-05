from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None
    from_email: str | None = None
    from_name: str | None = None


@dataclass(frozen=True)
class EmailResult:
    accepted: bool
    provider: str
    message_id: str | None = None
    message: str = ""


class EmailProvider(ABC):
    name: str

    @abstractmethod
    def send(self, message: EmailMessage) -> EmailResult:
        raise NotImplementedError

    def health(self) -> bool:
        return True
