"""Password, token, authorization-context, and CSRF helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from typing import Any


PBKDF2_ROUNDS = 600_000


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Actor:
    user_id: str
    email: str
    name: str
    organisation_id: str
    organisation_name: str
    is_platform_admin: bool
    permissions: frozenset[str]

    def can(self, permission: str) -> bool:
        return self.is_platform_admin or permission in self.permissions

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise PermissionError(f"Permission required: {permission}")


def csrf_valid(session: dict[str, Any], supplied: str | None) -> bool:
    expected = str(session.get("csrf_token", ""))
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))
