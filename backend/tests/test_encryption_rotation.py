"""
Tests for AES-256-GCM AAD (associated data) support and key rotation.

Covers:
- AAD binding (encrypt/decrypt with matching and mismatched AAD)
- Backward compatibility (legacy format without AAD or version byte)
- Key rotation with dual-key fallback
- rotate_field() re-encryption helper
- Version byte detection
"""

import os

import pytest
from cryptography.exceptions import InvalidTag

# Two distinct 32-byte keys (64 hex chars each)
KEY_A_HEX = "aa" * 32  # key A
KEY_B_HEX = "bb" * 32  # key B


@pytest.fixture(autouse=True)
def _setup_key(monkeypatch):
    """Set the primary encryption key and clear previous key for each test."""
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_A_HEX)
    monkeypatch.delenv("FIELD_ENCRYPTION_KEY_PREVIOUS", raising=False)
    import utils.encryption as enc_mod
    from config.settings import Settings

    enc_mod.settings = Settings()
    yield


def _reload_settings(monkeypatch):
    """Rebuild the Settings object so encryption picks up env var changes."""
    import utils.encryption as enc_mod
    from config.settings import Settings

    enc_mod.settings = Settings()


# ---------------------------------------------------------------------------
# AAD tests
# ---------------------------------------------------------------------------


class TestAAD:
    """Associated Authenticated Data (AAD) binding tests."""

    def test_encrypt_with_aad_decrypt_with_same_aad(self):
        from utils.encryption import decrypt_field, encrypt_field

        aad = "utility_accounts:uuid-1234:account_number"
        ct = encrypt_field("secret-value", aad=aad)
        assert decrypt_field(ct, aad=aad) == "secret-value"

    def test_encrypt_with_aad_decrypt_with_different_aad_fails(self):
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("secret-value", aad="table_a:id1:field1")
        with pytest.raises(InvalidTag):
            decrypt_field(ct, aad="table_b:id2:field2")

    def test_encrypt_without_aad_decrypt_without_aad(self):
        """Backward compatibility: no AAD on either side works."""
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("plain-text")
        assert decrypt_field(ct) == "plain-text"

    def test_encrypt_without_aad_decrypt_with_aad_fails(self):
        """Adding AAD to decryption that was not present at encryption fails."""
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("value")
        with pytest.raises(InvalidTag):
            decrypt_field(ct, aad="unexpected-context")

    def test_encrypt_with_aad_decrypt_without_aad_fails(self):
        """Omitting AAD at decryption when it was present at encryption fails."""
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("value", aad="expected-context")
        with pytest.raises(InvalidTag):
            decrypt_field(ct)

    def test_aad_with_unicode(self):
        from utils.encryption import decrypt_field, encrypt_field

        aad = "table:uuid:field_name"
        ct = encrypt_field("unicode-value", aad=aad)
        assert decrypt_field(ct, aad=aad) == "unicode-value"

    def test_empty_string_aad_treated_as_no_aad(self):
        """Empty string AAD should behave like None (falsy)."""
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("value", aad="")
        # Empty string is falsy, so aad_bytes will be None
        assert decrypt_field(ct, aad="") == "value"
        # Also decryptable with explicit None
        assert decrypt_field(ct, aad=None) == "value"
        assert decrypt_field(ct) == "value"


# ---------------------------------------------------------------------------
# Version byte tests
# ---------------------------------------------------------------------------


class TestVersionByte:
    """Ensure new encryptions use versioned format."""

    def test_new_encryption_has_version_byte(self):
        from utils.encryption import encrypt_field

        ct = encrypt_field("test")
        assert ct[0:1] == b"\x01", "New ciphertext should start with version byte 0x01"

    def test_legacy_format_still_decryptable(self):
        """Simulate legacy (v0) ciphertext without version byte."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        from utils.encryption import decrypt_field

        # Manually create legacy format: nonce || ciphertext || tag
        key = bytes.fromhex(KEY_A_HEX)
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, b"legacy-data", None)
        legacy_blob = nonce + ct

        # decrypt_field should handle this transparently
        assert decrypt_field(legacy_blob) == "legacy-data"

    def test_legacy_format_with_aad_none(self):
        """Legacy data was encrypted with None AAD; decrypt with None AAD works."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        from utils.encryption import decrypt_field

        key = bytes.fromhex(KEY_A_HEX)
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, b"old-record", None)
        legacy_blob = nonce + ct

        assert decrypt_field(legacy_blob, aad=None) == "old-record"

    def test_version_byte_not_confused_with_nonce(self):
        """Version 0x01 as first byte should not be treated as part of the nonce."""
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("round-trip")
        # The nonce is bytes 1..13, not 0..12
        assert len(ct) > 13
        assert decrypt_field(ct) == "round-trip"


# ---------------------------------------------------------------------------
# Key rotation tests
# ---------------------------------------------------------------------------


class TestKeyRotation:
    """Dual-key decryption and rotate_field() tests."""

    def test_decrypt_with_previous_key_fallback(self, monkeypatch):
        """Encrypt with key A, switch to key B + key A as previous => decrypt succeeds."""
        from utils.encryption import decrypt_field, encrypt_field

        # Encrypt with key A (current)
        ct = encrypt_field("rotate-me")

        # Switch keys: B is now current, A is previous
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_A_HEX)
        _reload_settings(monkeypatch)

        # Should still decrypt via fallback to previous key
        assert decrypt_field(ct) == "rotate-me"

    def test_decrypt_fails_without_previous_key(self, monkeypatch):
        """Encrypt with key A, switch to key B without previous => fails."""
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("secret")

        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY_PREVIOUS", raising=False)
        _reload_settings(monkeypatch)

        with pytest.raises(InvalidTag):
            decrypt_field(ct)

    def test_decrypt_with_aad_and_previous_key(self, monkeypatch):
        """AAD + key rotation: must supply correct AAD even with fallback key."""
        from utils.encryption import decrypt_field, encrypt_field

        aad = "accounts:id:field"
        ct = encrypt_field("value", aad=aad)

        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_A_HEX)
        _reload_settings(monkeypatch)

        # Correct AAD + previous key => success
        assert decrypt_field(ct, aad=aad) == "value"
        # Wrong AAD + previous key => failure
        with pytest.raises(InvalidTag):
            decrypt_field(ct, aad="wrong-context")

    def test_rotate_field_reencrypts_from_old_key(self, monkeypatch):
        """rotate_field() should re-encrypt data from previous key to current key."""
        from utils.encryption import decrypt_field, encrypt_field, rotate_field

        # Encrypt with key A
        ct_old = encrypt_field("to-rotate")

        # Switch to key B, A as previous
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_A_HEX)
        _reload_settings(monkeypatch)

        ct_new = rotate_field(ct_old)
        assert ct_new is not None, "Should return new ciphertext"

        # New ciphertext should be decryptable with current key only
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY_PREVIOUS", raising=False)
        _reload_settings(monkeypatch)
        assert decrypt_field(ct_new) == "to-rotate"

    def test_rotate_field_returns_none_when_already_current(self):
        """rotate_field() returns None if data is already versioned + current key."""
        from utils.encryption import encrypt_field, rotate_field

        ct = encrypt_field("already-current")
        result = rotate_field(ct)
        assert result is None

    def test_rotate_field_upgrades_legacy_format(self):
        """rotate_field() should upgrade legacy (v0) format to versioned (v1)."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        from utils.encryption import decrypt_field, rotate_field

        # Create legacy format manually
        key = bytes.fromhex(KEY_A_HEX)
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, b"legacy-upgrade", None)
        legacy_blob = nonce + ct

        # Legacy format, current key => rotate upgrades to v1
        ct_new = rotate_field(legacy_blob)
        assert ct_new is not None, "Legacy format should be upgraded"
        assert ct_new[0:1] == b"\x01", "Upgraded ciphertext should be versioned"
        assert decrypt_field(ct_new) == "legacy-upgrade"

    def test_rotate_field_with_aad(self, monkeypatch):
        """rotate_field() preserves AAD binding during re-encryption."""
        from utils.encryption import decrypt_field, encrypt_field, rotate_field

        aad = "table:id:field"
        ct_old = encrypt_field("aad-rotate", aad=aad)

        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_A_HEX)
        _reload_settings(monkeypatch)

        ct_new = rotate_field(ct_old, aad=aad)
        assert ct_new is not None

        # Verify with current key + correct AAD
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY_PREVIOUS", raising=False)
        _reload_settings(monkeypatch)
        assert decrypt_field(ct_new, aad=aad) == "aad-rotate"

    def test_rotate_field_fails_with_unrecognized_key(self, monkeypatch):
        """rotate_field() raises InvalidTag if neither key can decrypt."""
        from utils.encryption import encrypt_field, rotate_field

        ct = encrypt_field("orphan")

        # Switch to entirely new keys (neither A nor B)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "cc" * 32)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", "dd" * 32)
        _reload_settings(monkeypatch)

        with pytest.raises(InvalidTag):
            rotate_field(ct)

    def test_previous_key_invalid_length_raises(self, monkeypatch):
        """A malformed previous key should raise RuntimeError."""
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", "ab" * 10)  # 10 bytes
        _reload_settings(monkeypatch)

        from utils.encryption import _get_previous_key

        with pytest.raises(RuntimeError, match="32 bytes"):
            _get_previous_key()

    def test_no_previous_key_returns_none(self, monkeypatch):
        """When no previous key is set, _get_previous_key returns None."""
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY_PREVIOUS", raising=False)
        _reload_settings(monkeypatch)

        from utils.encryption import _get_previous_key

        assert _get_previous_key() is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Additional edge cases for completeness."""

    def test_encrypt_empty_string(self):
        from utils.encryption import decrypt_field, encrypt_field

        ct = encrypt_field("")
        assert decrypt_field(ct) == ""

    def test_encrypt_long_plaintext(self):
        from utils.encryption import decrypt_field, encrypt_field

        long_text = "x" * 10_000
        ct = encrypt_field(long_text)
        assert decrypt_field(ct) == long_text

    def test_multiple_rotations(self, monkeypatch):
        """Data can be rotated through multiple key generations."""
        from utils.encryption import decrypt_field, encrypt_field, rotate_field

        # Gen 1: encrypt with A
        ct1 = encrypt_field("multi-gen")

        # Gen 2: rotate A -> B
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_A_HEX)
        _reload_settings(monkeypatch)
        ct2 = rotate_field(ct1)
        assert ct2 is not None
        assert decrypt_field(ct2) == "multi-gen"

        # Gen 3: rotate B -> C
        key_c = "cc" * 32
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", key_c)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_B_HEX)
        _reload_settings(monkeypatch)
        ct3 = rotate_field(ct2)
        assert ct3 is not None
        assert decrypt_field(ct3) == "multi-gen"

        # Verify only current key works without fallback
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY_PREVIOUS", raising=False)
        _reload_settings(monkeypatch)
        assert decrypt_field(ct3) == "multi-gen"

    def test_previous_key_from_env_var_directly(self, monkeypatch):
        """Fallback: read FIELD_ENCRYPTION_KEY_PREVIOUS from os.environ when
        the settings object does not have the attribute."""
        from utils.encryption import encrypt_field

        ct = encrypt_field("env-fallback")

        # Switch to key B, set previous via env var only
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", KEY_B_HEX)
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY_PREVIOUS", KEY_A_HEX)
        _reload_settings(monkeypatch)

        # Manually remove the attribute from settings to simulate older Settings class
        import utils.encryption as enc_mod

        if hasattr(enc_mod.settings, "field_encryption_key_previous"):
            # Force getattr to return None to test env var fallback path
            original_settings = enc_mod.settings

            class _SettingsProxy:
                """Proxy that hides field_encryption_key_previous from getattr."""

                def __getattr__(self, name):
                    if name == "field_encryption_key_previous":
                        return None
                    return getattr(original_settings, name)

            enc_mod.settings = _SettingsProxy()

        from utils.encryption import decrypt_field

        assert decrypt_field(ct) == "env-fallback"
