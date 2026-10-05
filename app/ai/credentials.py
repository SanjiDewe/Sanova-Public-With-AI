from __future__ import annotations

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AICredentialError(RuntimeError):
    pass


class AICredentialCipher:
    """Encrypt AI credentials at rest with an application-level secret.

    The provider API key itself is never used as configuration or returned to
    the UI. SANOVA_AI_CREDENTIAL_KEY is the encryption key, not a provider key.
    """

    def __init__(self, key: str | bytes | None = None, *, key_path: str | os.PathLike[str] | None = None):
        raw = key if key is not None else os.getenv("SANOVA_AI_CREDENTIAL_KEY", "")
        if not raw and key_path is not None:
            environment = os.getenv("SANOVA_ENVIRONMENT", "local").strip().lower()
            if environment not in {"local", "test", "development"}:
                raise AICredentialError("SANOVA_AI_CREDENTIAL_KEY is required outside local/test/development")
            from pathlib import Path
            path = Path(key_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raw = path.read_bytes()
            else:
                raw = secrets.token_bytes(32)
                with path.open("wb") as handle:
                    handle.write(raw)
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not raw:
            raise AICredentialError("SANOVA_AI_CREDENTIAL_KEY is required for AI credential storage")
        try:
            decoded = base64.urlsafe_b64decode(raw + b"=" * (-len(raw) % 4))
        except Exception:
            decoded = b""
        if len(decoded) == 32:
            self._key = decoded
        elif len(raw) == 32:
            self._key = raw
        else:
            import hashlib
            self._key = hashlib.sha256(raw).digest()
        self._aead = AESGCM(self._key)

    def encrypt(self, plaintext: str) -> str:
        value = str(plaintext).strip()
        if not value:
            raise AICredentialError("credential is required")
        nonce = secrets.token_bytes(12)
        ciphertext = self._aead.encrypt(nonce, value.encode("utf-8"), b"sanova-ai")
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, token: str) -> str:
        try:
            blob = base64.urlsafe_b64decode(str(token).encode("ascii"))
            plaintext = self._aead.decrypt(blob[:12], blob[12:], b"sanova-ai")
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise AICredentialError("stored AI credential could not be decrypted") from exc
