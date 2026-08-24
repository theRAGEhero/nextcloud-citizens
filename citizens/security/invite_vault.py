"""Reversible at-rest encryption for invite tokens.

Join verification still runs against the SHA-256 hash; this vault only exists
so organizers can re-view and re-print QR sheets. The Fernet key is derived
from the AppAPI shared secret, so a database dump alone reveals nothing.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from citizens.config import get_settings


def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().app_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(token_encrypted: str) -> str | None:
    """None when undecryptable (e.g. the app secret changed since issuing)."""
    try:
        return _fernet().decrypt(token_encrypted.encode()).decode()
    except (InvalidToken, ValueError):
        return None
