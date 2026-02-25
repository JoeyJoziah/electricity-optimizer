"""
Field-level encryption for sensitive data (account numbers, meter numbers).

Uses AES-256-GCM with a per-ciphertext random nonce. The FIELD_ENCRYPTION_KEY
environment variable must contain a 32-byte hex-encoded key (64 hex chars).

Ciphertext format: nonce (12 bytes) || ciphertext || tag (16 bytes)
"""

import os
import re
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config.settings import settings


_NONCE_SIZE = 12  # 96-bit nonce for GCM


def _get_key() -> bytes:
    """Get the AES-256 key from settings, decoded from hex."""
    key_hex = getattr(settings, "field_encryption_key", None)
    if not key_hex:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is not configured. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be exactly 32 bytes (64 hex characters)")
    return key_bytes


def encrypt_field(plaintext: str) -> bytes:
    """
    Encrypt a plaintext string with AES-256-GCM.

    Returns:
        bytes: nonce || ciphertext || tag
    """
    key = _get_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ct


def decrypt_field(data: bytes) -> str:
    """
    Decrypt AES-256-GCM ciphertext.

    Args:
        data: nonce || ciphertext || tag

    Returns:
        Decrypted plaintext string

    Raises:
        cryptography.exceptions.InvalidTag: If ciphertext was tampered with
    """
    key = _get_key()
    nonce = data[:_NONCE_SIZE]
    ct = data[_NONCE_SIZE:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")


# Account number validation pattern
ACCOUNT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9\-\s]{4,30}$")


def validate_account_number(value: str) -> bool:
    """Validate account number format: 4-30 alphanumeric chars, hyphens, spaces."""
    return bool(ACCOUNT_NUMBER_PATTERN.match(value))


def mask_account_number(account_number: str) -> str:
    """
    Mask an account number, showing only the last 4 characters.

    Examples:
        "1234567890" -> "******7890"
        "AB12" -> "AB12"  (too short to mask)
    """
    if len(account_number) <= 4:
        return account_number
    return "*" * (len(account_number) - 4) + account_number[-4:]
