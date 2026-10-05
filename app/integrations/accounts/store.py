from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.identity.store import IdentityStore
from app.integrations.accounts.crypto import decrypt, encrypt


@dataclass(frozen=True)
class ConnectedAccount:
    id: str
    user_id: str
    provider: str
    external_subject: str | None
    email: str | None
    access_token: str
    refresh_token: str | None
    token_type: str
    expires_at: str | None
    scopes: tuple[str, ...]


class ConnectedAccountStore:
    """Persistence boundary for user-authorized external accounts."""

    def __init__(self, identity_store: IdentityStore):
        self.identity_store = identity_store

    def save(self, *, user_id: str, provider: str, external_subject: str | None,
             email: str | None, access_token: str, refresh_token: str | None,
             token_type: str = "Bearer", expires_in: int | None = None,
             scopes: tuple[str, ...] = ()) -> ConnectedAccount:
        expires_at = None
        if expires_in is not None:
            expires_at = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + max(0, expires_in), timezone.utc
            ).isoformat()
        self.identity_store.save_connected_account(
            user_id=user_id,
            provider=provider,
            external_subject=external_subject,
            email=email,
            access_token=encrypt(access_token),
            refresh_token=encrypt(refresh_token) if refresh_token else None,
            token_type=token_type,
            expires_at=expires_at,
            scopes=" ".join(scopes),
        )
        return self.get(user_id, provider)

    def get(self, user_id: str, provider: str) -> ConnectedAccount | None:
        row = self.identity_store.get_connected_account(user_id, provider)
        if not row:
            return None
        expires_at = row["expires_at"]
        if isinstance(expires_at, datetime):
            expires_at = expires_at.astimezone(timezone.utc).isoformat()
        elif expires_at is not None:
            expires_at = str(expires_at)
        scopes = str(row["scopes"] or "").split()
        return ConnectedAccount(
            id=row["id"], user_id=row["user_id"], provider=row["provider"],
            external_subject=row["external_subject"], email=row["email"],
            access_token=decrypt(row["access_token"]),
            refresh_token=decrypt(row["refresh_token"]) if row["refresh_token"] else None,
            token_type=row["token_type"], expires_at=expires_at,
            scopes=tuple(filter(None, scopes)),
        )

    def delete(self, user_id: str, provider: str) -> None:
        self.identity_store.delete_connected_account(user_id, provider)
