"""
Tests for field-level encryption utility.
"""

import os
import pytest


# Provide a test encryption key for all tests in this module
TEST_KEY_HEX = "a" * 64  # 32 bytes = 64 hex chars


@pytest.fixture(autouse=True)
def set_encryption_key(monkeypatch):
    """Set encryption key via env var — no mocking."""
    monkeypatch.setenv("FIELD_ENCRYPTION_KEY", TEST_KEY_HEX)
    from config.settings import Settings
    import utils.encryption as enc_mod
    enc_mod.settings = Settings()
    yield


class TestEncryptDecrypt:
    """AES-256-GCM encrypt/decrypt round-trip tests."""

    def test_round_trip_basic(self):
        from utils.encryption import encrypt_field, decrypt_field

        plaintext = "1234567890"
        ciphertext = encrypt_field(plaintext)
        assert decrypt_field(ciphertext) == plaintext

    def test_round_trip_alphanumeric(self):
        from utils.encryption import encrypt_field, decrypt_field

        plaintext = "ABC-123 456"
        ciphertext = encrypt_field(plaintext)
        assert decrypt_field(ciphertext) == plaintext

    def test_round_trip_unicode(self):
        from utils.encryption import encrypt_field, decrypt_field

        plaintext = "Test-Value-123"
        ciphertext = encrypt_field(plaintext)
        assert decrypt_field(ciphertext) == plaintext

    def test_ciphertext_is_bytes(self):
        from utils.encryption import encrypt_field

        ct = encrypt_field("hello")
        assert isinstance(ct, bytes)

    def test_ciphertext_longer_than_plaintext(self):
        from utils.encryption import encrypt_field

        ct = encrypt_field("hi")
        # nonce (12) + ciphertext + tag (16) should be longer than "hi" (2 bytes)
        assert len(ct) > 2

    def test_different_plaintext_different_ciphertext(self):
        from utils.encryption import encrypt_field

        ct1 = encrypt_field("value1")
        ct2 = encrypt_field("value2")
        assert ct1 != ct2

    def test_same_plaintext_different_ciphertext(self):
        """Due to random nonce, same plaintext should produce different ciphertext."""
        from utils.encryption import encrypt_field

        ct1 = encrypt_field("same")
        ct2 = encrypt_field("same")
        assert ct1 != ct2

    def test_tampered_ciphertext_raises(self):
        from utils.encryption import encrypt_field, decrypt_field

        ct = bytearray(encrypt_field("secret"))
        # Flip a byte in the ciphertext portion
        ct[15] ^= 0xFF
        with pytest.raises(Exception):
            decrypt_field(bytes(ct))

    def test_different_key_cannot_decrypt(self, monkeypatch):
        from utils.encryption import encrypt_field, decrypt_field

        ct = encrypt_field("secret")

        # Swap to a different key via env var
        different_key = "b" * 64
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", different_key)
        from config.settings import Settings
        import utils.encryption as enc_mod
        enc_mod.settings = Settings()
        with pytest.raises(Exception):
            decrypt_field(ct)


class TestMaskAccountNumber:
    """Tests for the masking utility."""

    def test_mask_long_number(self):
        from utils.encryption import mask_account_number

        assert mask_account_number("1234567890") == "******7890"

    def test_mask_exactly_5_chars(self):
        from utils.encryption import mask_account_number

        assert mask_account_number("12345") == "*2345"

    def test_mask_4_chars_no_mask(self):
        from utils.encryption import mask_account_number

        assert mask_account_number("1234") == "1234"

    def test_mask_3_chars_no_mask(self):
        from utils.encryption import mask_account_number

        assert mask_account_number("ABC") == "ABC"

    def test_mask_empty_string(self):
        from utils.encryption import mask_account_number

        assert mask_account_number("") == ""


class TestValidateAccountNumber:
    """Tests for account number validation."""

    def test_valid_numeric(self):
        from utils.encryption import validate_account_number

        assert validate_account_number("123456") is True

    def test_valid_alphanumeric(self):
        from utils.encryption import validate_account_number

        assert validate_account_number("ABC-123 456") is True

    def test_too_short(self):
        from utils.encryption import validate_account_number

        assert validate_account_number("AB") is False

    def test_too_long(self):
        from utils.encryption import validate_account_number

        assert validate_account_number("A" * 31) is False

    def test_special_chars_rejected(self):
        from utils.encryption import validate_account_number

        assert validate_account_number("abc@123") is False

    def test_valid_with_hyphens_and_spaces(self):
        from utils.encryption import validate_account_number

        assert validate_account_number("AA-BB CC-DD") is True


class TestMissingKey:
    """Tests for missing encryption key."""

    def test_encrypt_without_key_raises(self, monkeypatch):
        monkeypatch.delenv("FIELD_ENCRYPTION_KEY", raising=False)
        from config.settings import Settings
        import utils.encryption as enc_mod
        enc_mod.settings = Settings()

        from utils.encryption import encrypt_field
        with pytest.raises(RuntimeError, match="FIELD_ENCRYPTION_KEY"):
            encrypt_field("test")

    def test_invalid_key_length_raises(self, monkeypatch):
        monkeypatch.setenv("FIELD_ENCRYPTION_KEY", "aa" * 10)  # 10 bytes, not 32
        from config.settings import Settings
        import utils.encryption as enc_mod
        enc_mod.settings = Settings()

        from utils.encryption import encrypt_field
        with pytest.raises(RuntimeError, match="32 bytes"):
            encrypt_field("test")
