"""Symmetric encryption for API keys stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) from the ``cryptography`` package.
The encryption key is read from the ``HADRON_ENCRYPTION_KEY`` environment
variable and must be a URL-safe base64-encoded 32-byte key — generate one
with ``cryptography.fernet.Fernet.generate_key()``.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken

_ENV_VAR = "HADRON_ENCRYPTION_KEY"


def get_fernet() -> Fernet | None:
    """Return a :class:`Fernet` instance, or *None* if the env var is unset."""
    key = os.environ.get(_ENV_VAR)
    if not key:
        return None
    return Fernet(key.encode())


def encrypt_value(plaintext: str) -> str:
    """Encrypt *plaintext* and return the Fernet token as a UTF-8 string.

    Raises :class:`RuntimeError` when ``HADRON_ENCRYPTION_KEY`` is not set.
    """
    f = get_fernet()
    if f is None:
        raise RuntimeError(
            f"{_ENV_VAR} is not set — cannot encrypt. "
            "Generate a key with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet token back to plaintext.

    Raises :class:`RuntimeError` when the env var is missing and
    :class:`cryptography.fernet.InvalidToken` on key mismatch.
    """
    f = get_fernet()
    if f is None:
        raise RuntimeError(f"{_ENV_VAR} is not set — cannot decrypt.")
    return f.decrypt(ciphertext.encode()).decode()


def mask_key(value: str) -> str:
    """Mask an API key, showing only the last 4 characters.

    Returns ``"••••abcd"`` for keys of 8+ chars, or ``"••••"`` for shorter ones.
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]
