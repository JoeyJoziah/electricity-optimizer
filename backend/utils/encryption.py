"""
Field-level encryption for sensitive data (account numbers, meter numbers).

Uses AES-256-GCM with a per-ciphertext random nonce. The FIELD_ENCRYPTION_KEY
environment variable must contain a 32-byte hex-encoded key (64 hex chars).

Ciphertext formats:
  - Legacy (v0): nonce (12 bytes) || ciphertext || tag (16 bytes)
  - Versioned (v1): version (1 byte, 0x01) || nonce (12 bytes) || ciphertext || tag (16 bytes)

Key rotation:
  Set FIELD_ENCRYPTION_KEY to the new key and FIELD_ENCRYPTION_KEY_PREVIOUS to
  the old key. decrypt_field() will try the current key first, then fall back to
  the previous key. Use rotate_field() to re-encrypt data with the current key.
"""

import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config.settings import settings

_NONCE_SIZE = 12  # 96-bit nonce for GCM
_VERSION_V1 = b"\x01"  # Version byte for the new format


def _get_key() -> bytes:
    """Get the AES-256 key from settings, decoded from hex."""
    key_hex = getattr(settings, "field_encryption_key", None)
    if not key_hex:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY is not configured. "
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be exactly 32 bytes (64 hex characters)")
    return key_bytes


def _get_previous_key() -> bytes | None:
    """Get the previous encryption key for rotation (decryption only).

    Checks settings first, falls back to the environment variable directly.
    Returns None if no previous key is configured.
    """
    key_hex = getattr(settings, "field_encryption_key_previous", None)
    if not key_hex:
        key_hex = os.environ.get("FIELD_ENCRYPTION_KEY_PREVIOUS")
    if not key_hex:
        return None
    key_bytes = bytes.fromhex(key_hex)
    if len(key_bytes) != 32:
        raise RuntimeError(
            "FIELD_ENCRYPTION_KEY_PREVIOUS must be exactly 32 bytes (64 hex characters)"
        )
    return key_bytes


def encrypt_field(plaintext: str, aad: str | None = None) -> bytes:
    """
    Encrypt a plaintext string with AES-256-GCM.

    Args:
        plaintext: The string to encrypt.
        aad: Optional associated data for authentication (e.g.
             ``f"{table}:{record_id}:{field}"``). When provided, the same AAD
             must be supplied to decrypt_field() for decryption to succeed.

    Returns:
        bytes: version (1) || nonce (12) || ciphertext || tag (16)
    """
    key = _get_key()
    nonce = os.urandom(_NONCE_SIZE)
    aesgcm = AESGCM(key)
    aad_bytes = aad.encode("utf-8") if aad else None
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad_bytes)
    return _VERSION_V1 + nonce + ct


def _try_decrypt(key: bytes, data: bytes, aad: str | None = None) -> str:
    """Attempt decryption with a given key, handling both legacy and versioned formats.

    Args:
        key: The AES-256 key bytes.
        data: The raw ciphertext bytes (may or may not have a version prefix).
        aad: Optional associated data string.

    Returns:
        Decrypted plaintext string.

    Raises:
        InvalidTag: If decryption fails (wrong key, tampered data, or wrong AAD).
    """
    aesgcm = AESGCM(key)
    aad_bytes = aad.encode("utf-8") if aad else None

    if len(data) > 0 and data[0:1] == _VERSION_V1:
        # Versioned format: skip version byte
        nonce = data[1 : 1 + _NONCE_SIZE]
        ct = data[1 + _NONCE_SIZE :]
    else:
        # Legacy format (v0): no version byte
        nonce = data[:_NONCE_SIZE]
        ct = data[_NONCE_SIZE:]

    return aesgcm.decrypt(nonce, ct, aad_bytes).decode("utf-8")


def decrypt_field(data: bytes, aad: str | None = None) -> str:
    """
    Decrypt AES-256-GCM ciphertext.

    Tries the current key first. If decryption fails with ``InvalidTag`` and a
    previous key is configured (``FIELD_ENCRYPTION_KEY_PREVIOUS``), retries with
    the previous key to support seamless key rotation.

    Args:
        data: version? || nonce || ciphertext || tag
        aad: Optional associated data that was used during encryption.

    Returns:
        Decrypted plaintext string.

    Raises:
        cryptography.exceptions.InvalidTag: If ciphertext was tampered with or
            no configured key can decrypt it.
    """
    key = _get_key()
    try:
        return _try_decrypt(key, data, aad)
    except InvalidTag:
        previous_key = _get_previous_key()
        if previous_key is None:
            raise
        return _try_decrypt(previous_key, data, aad)


def rotate_field(data: bytes, aad: str | None = None) -> bytes | None:
    """Re-encrypt ciphertext with the current key.

    Attempts to decrypt ``data`` (trying current key, then previous key) and
    re-encrypts with the current key. If the data is already encrypted with the
    current key **and** uses the versioned format, returns ``None`` to signal
    that no rotation is needed.

    Args:
        data: Existing ciphertext bytes.
        aad: Optional associated data for authentication context.

    Returns:
        New ciphertext encrypted with the current key, or ``None`` if already
        up-to-date.

    Raises:
        cryptography.exceptions.InvalidTag: If no configured key can decrypt
            the data.
    """
    key = _get_key()

    # First, check if decryption succeeds with the current key
    try:
        plaintext = _try_decrypt(key, data, aad)
        # If the data is already in versioned format with the current key,
        # no rotation is needed
        if len(data) > 0 and data[0:1] == _VERSION_V1:
            return None
        # Legacy format but current key works — upgrade to versioned format
        return encrypt_field(plaintext, aad)
    except InvalidTag:
        pass

    # Current key failed — try previous key
    previous_key = _get_previous_key()
    if previous_key is None:
        raise InvalidTag()

    plaintext = _try_decrypt(previous_key, data, aad)
    return encrypt_field(plaintext, aad)


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
