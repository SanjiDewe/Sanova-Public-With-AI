from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet


def _key() -> bytes:
    raw = os.getenv("SANOVA_GOOGLE_TOKEN_ENCRYPTION_KEY", "").strip()
    if raw:
        try:
            Fernet(raw.encode())
            return raw.encode()
        except ValueError as exc:
            raise RuntimeError("SANOVA_GOOGLE_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc

    environment = os.getenv("SANOVA_ENVIRONMENT", "local").strip().lower()
    if environment not in {"local", "test", "development"}:
        raise RuntimeError("SANOVA_GOOGLE_TOKEN_ENCRYPTION_KEY is required outside local/test/development")

    seed = os.getenv("SANOVA_TOKEN_DEV_SEED", "sanova-local-token-storage")
    digest = hashlib.sha256(seed.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt(value: str) -> str:
    return Fernet(_key()).encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return Fernet(_key()).decrypt(value.encode()).decode()
