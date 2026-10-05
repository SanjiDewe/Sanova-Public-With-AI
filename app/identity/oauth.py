from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets


class OAuthStateStore:
    def __init__(self, identity_store=None, ttl_seconds: int = 300):
        self.identity_store = identity_store
        self.ttl_seconds = ttl_seconds
        # Compatibility mode for direct callers/tests that do not provide persistence.
        self._states = {}
        self._metadata = {}

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def issue(self, user_id: str | None, provider: str, purpose: str = "connect", next_path: str = "/app"):
        if user_id == "" or not provider or purpose not in {"connect", "login", "signup"} or not next_path.startswith("/") or next_path.startswith("//"):
            raise ValueError("provider, purpose, and safe next path are required")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.ttl_seconds)
        key = self._hash(state)
        if self.identity_store is not None:
            self.identity_store.save_oauth_state(
                state_hash=key, user_id=user_id, provider=provider, verifier=verifier,
                purpose=purpose, next_path=next_path, expires_at=expires.timestamp(),
            )
        else:
            self._states[key] = (user_id, provider, verifier, expires)
            self._metadata[key] = (purpose, next_path)
        return state, verifier

    def consume_record(self, state: str, user_id: str | None, provider: str):
        if not state or not provider:
            return None
        key = self._hash(state)
        if self.identity_store is not None:
            row = self.identity_store.consume_oauth_state(
                state_hash=key, user_id=user_id, provider=provider,
                now=datetime.now(timezone.utc).timestamp(),
            )
            if row is None:
                return None
            return {"verifier": row["verifier"], "purpose": row["purpose"], "next_path": row["next_path"]}

        entry = self._states.get(key)
        if entry is None:
            return None
        stored_user, stored_provider, verifier, expires = entry
        purpose, next_path = self._metadata.get(key, ("connect", "/app"))
        if datetime.now(timezone.utc) >= expires:
            self._states.pop(key, None)
            self._metadata.pop(key, None)
            return None
        if stored_provider != provider:
            return None
        if purpose == "connect" and (not user_id or stored_user != user_id):
            return None
        if purpose in {"login", "signup"} and stored_user is not None:
            return None
        self._states.pop(key, None)
        self._metadata.pop(key, None)
        return {"verifier": verifier, "purpose": purpose, "next_path": next_path}

    def consume(self, state: str, user_id: str, provider: str):
        record = self.consume_record(state, user_id, provider)
        return record["verifier"] if record else None
