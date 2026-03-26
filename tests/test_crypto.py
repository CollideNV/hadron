"""Tests for hadron.security.crypto — encryption, decryption, masking."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet, InvalidToken

from hadron.security.crypto import decrypt_value, encrypt_value, get_fernet, mask_key


@pytest.fixture()
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("HADRON_ENCRYPTION_KEY", key)
    return key


# --- get_fernet ---


def test_get_fernet_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HADRON_ENCRYPTION_KEY", raising=False)
    assert get_fernet() is None


def test_get_fernet_returns_instance(encryption_key: str) -> None:
    f = get_fernet()
    assert isinstance(f, Fernet)


# --- encrypt / decrypt round-trip ---


def test_round_trip(encryption_key: str) -> None:
    plaintext = "sk-ant-api03-secret-key-here"
    ciphertext = encrypt_value(plaintext)
    assert ciphertext != plaintext
    assert decrypt_value(ciphertext) == plaintext


def test_encrypt_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HADRON_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="HADRON_ENCRYPTION_KEY is not set"):
        encrypt_value("secret")


def test_decrypt_raises_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HADRON_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="HADRON_ENCRYPTION_KEY is not set"):
        decrypt_value("token")


def test_decrypt_with_wrong_key(encryption_key: str) -> None:
    ciphertext = encrypt_value("secret")
    # Switch to a different key
    os.environ["HADRON_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    with pytest.raises(InvalidToken):
        decrypt_value(ciphertext)


# --- mask_key ---


def test_mask_key_normal() -> None:
    assert mask_key("sk-ant-api03-abcd") == "••••abcd"


def test_mask_key_short() -> None:
    assert mask_key("abc") == "••••"


def test_mask_key_exactly_four() -> None:
    assert mask_key("abcd") == "••••"


def test_mask_key_five_chars() -> None:
    assert mask_key("abcde") == "••••bcde"


def test_mask_key_empty() -> None:
    assert mask_key("") == ""
