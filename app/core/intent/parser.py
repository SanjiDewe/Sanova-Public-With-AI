from abc import ABC, abstractmethod
import re

from app.core.contracts.intent import StructuredIntent


class IntentParser(ABC):
    """Boundary for converting user language into structured intent.

    Implementations must only interpret text. They must not call planners,
    routers, providers, webhooks, or execution engines.
    """

    @abstractmethod
    def parse(self, text: str) -> StructuredIntent:
        raise NotImplementedError


class RuleBasedIntentParser(IntentParser):
    """Deterministic sandbox interpreter used until an AI model is wired in."""

    _PATTERN = re.compile(
        r"^make\s+(?P<quantity>\d+)\s+(?P<product>.+?)"
        r"(?:\s+using\s+(?P<asset>\S+))?"
        r"\s+and\s+ship\s+to\s+(?P<destination>\S+)"
        r"(?:\s+via\s+(?P<provider>\S+))?\s*$",
        re.IGNORECASE,
    )

    def parse(self, text: str) -> StructuredIntent:
        raw_text = text.strip()
        if not raw_text:
            raise ValueError("intent text is required")

        match = self._PATTERN.match(raw_text)
        if not match:
            raise ValueError("unsupported or ambiguous intent")

        values = match.groupdict()
        structured = StructuredIntent(
            raw_text=raw_text,
            intent=raw_text,
            action="manufacture_and_fulfill",
            product=values["product"].strip(),
            asset=values["asset"],
            destination=values["destination"],
            quantity=int(values["quantity"]),
            provider=values["provider"],
        )
        structured.validate()
        return structured
