import json
from dataclasses import dataclass
from urllib import request

from app.config import assert_sandbox_url


@dataclass(frozen=True)
class SandboxHttpRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: dict | None = None


class SandboxHttpClient:
    """Small injectable HTTP client. Network is opt-in and sandbox-only."""

    def __init__(self, api_key: str, base_url: str, provider: str):
        if not api_key:
            raise RuntimeError("Sandbox API key is required when HTTP is enabled.")
        assert_sandbox_url(base_url, provider)
        self.api_key = api_key
        self.provider = provider
        self.base_url = base_url.rstrip("/")

    def request_json(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        assert_sandbox_url(url, self.provider)
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json", "X-API-Key": self.api_key}
        req = request.Request(url, data=payload, headers=headers, method=method.upper())
        with request.urlopen(req, timeout=15) as response:  # nosec B310 - URL is sandbox-validated
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
