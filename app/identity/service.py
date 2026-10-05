from __future__ import annotations
import secrets
from datetime import datetime, timedelta, timezone
import hashlib
from .authorization import AuthorizationService, RoleRegistry
from .models import User
from .passwords import PasswordHasher, PasswordPolicyError
from .store import IdentityStore

class IdentityService:
    def __init__(self, store: IdentityStore, passwords: PasswordHasher | None = None, roles: RoleRegistry | None = None):
        self.store = store
        self.passwords = passwords or PasswordHasher()
        self.authorization = AuthorizationService(store, roles=roles)

    def register(self, email: str, password: str) -> User:
        return self.store.create_user(email, self.passwords.hash(password))

    def authenticate(self, email: str, password: str) -> str:
        user = self.store.get_user_by_email(email)
        if user is None or not user.active or not self.passwords.verify(password, user.password_hash):
            raise PermissionError("invalid credentials")
        token = secrets.token_urlsafe(32)
        self.store.create_session(user.id, token)
        return token

    def current_user(self, token: str):
        if not token:
            return None
        user = self.store.get_user_by_token(token)
        return user if user and user.active else None

    def register_pending(self, email: str, password: str) -> tuple[User, str]:
        code = f"{secrets.randbelow(1_000_000):06d}"
        user = self.store.create_pending_user(email, self.passwords.hash(password))
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        self.store.save_email_verification(
            user.id,
            hashlib.sha256(code.encode()).hexdigest(),
            expires.isoformat(),
        )
        return user, code

    def verify_email_code(self, email: str, code: str) -> bool:
        user = self.store.get_user_by_email(email)
        if user is None or user.active:
            return False
        record = self.store.get_email_verification(user.id)
        if record is None:
            return False
        try:
            expires = datetime.fromisoformat(record["expires_at"])
        except (TypeError, ValueError):
            return False
        if datetime.now(timezone.utc) >= expires:
            return False
        digest = hashlib.sha256(code.strip().encode()).hexdigest()
        if not secrets.compare_digest(digest, record["code_hash"]):
            return False
        self.store.set_active(user.id, True)
        self.store.delete_email_verification(user.id)
        return True

    def authenticate_oauth(self, email: str) -> str:
        user = self.store.get_user_by_email(email)
        if user is None or not user.active:
            raise PermissionError("account is inactive or missing")
        token = secrets.token_urlsafe(32)
        self.store.create_session(user.id, token)
        return token

    def logout(self, token: str) -> None:
        self.store.revoke_session(token)

    def require_execution(self, token: str) -> User:
        user = self.current_user(token)
        if user is None:
            raise PermissionError("authentication required")
        from .authorization import Permission
        if not self.authorization.has_permission(user, Permission.EXECUTE):
            raise PermissionError("execution permission required")
        return user
