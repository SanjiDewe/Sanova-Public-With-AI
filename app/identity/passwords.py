from __future__ import annotations
import hashlib
import secrets

class PasswordPolicyError(ValueError):
    pass

class PasswordHasher:
    algorithm = "pbkdf2_sha256"
    iterations = 310_000
    min_length = 12

    def hash(self, password: str) -> str:
        if not isinstance(password, str) or len(password) < self.min_length:
            raise PasswordPolicyError("password must be at least 12 characters")
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, self.iterations)
        return f"{self.algorithm}${self.iterations}${salt.hex()}${digest.hex()}"

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt_hex, digest_hex = encoded.split("$")
            if algorithm != self.algorithm:
                return False
            iterations = int(iterations)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
            return secrets.compare_digest(actual, expected)
        except (ValueError, TypeError, AttributeError):
            return False
