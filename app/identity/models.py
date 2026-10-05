from __future__ import annotations
from dataclasses import dataclass

@dataclass
class User:
    id: str
    email: str
    password_hash: str
    role: str = "user"
    active: bool = True
