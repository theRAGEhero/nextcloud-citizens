"""Recorder invite tokens: long random secrets, only their hash stored (brief §13–§14)."""

import hashlib
import secrets

TOKEN_BYTES = 32  # 256 bits


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
