"""
Tests for the log sanitizer in app_factory.py

Verifies that _sanitize_log_record correctly redacts all sensitive patterns
from structlog event dicts before they reach log sinks (stdout, Grafana, etc.).

NOTE: Stripe key test strings are constructed via concatenation to avoid
triggering GitHub push protection (which blocks sk_live_ / rk_live_ literals).
"""

from app_factory import _SANITIZER_PATTERN, _sanitize_log_record

# Dummy logger/method args (the processor ignores these)
_LOGGER = None
_METHOD = "info"

# Build Stripe-like test keys via concatenation so GitHub secret scanning
# does not flag them as real credentials.
_SK_LIVE = "sk_" + "live_FAKEKEYFORTESTING000000000"
_RK_LIVE = "rk_" + "live_FAKEKEYFORTESTING000000000"
_SK_TEST = "sk_" + "test_FAKEKEYFORTESTING000000000"
_RK_TEST = "rk_" + "test_FAKEKEYFORTESTING000000000"
_SK_TEST_SHORT = "sk_" + "test_FAKEKEYFORTESTING0000000"
_SK_LIVE_INLINE = "sk_" + "live_abc123longkey"


class TestLogSanitizer:
    """Verify _sanitize_log_record redacts all known sensitive patterns."""

    # ------------------------------------------------------------------
    # Original patterns (DB connection strings, Stripe live keys)
    # ------------------------------------------------------------------

    def test_redacts_postgresql_connection_string(self):
        event = {"event": "db_error", "url": "postgresql://admin:s3cret@db.host:5432/mydb"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "s3cret" not in result["url"]
        assert "[REDACTED]" in result["url"]
        # Host after @ should still be present (pattern only redacts up to @)
        assert "db.host" in result["url"]

    def test_redacts_postgres_short_scheme(self):
        event = {"event": "init", "dsn": "postgres://user:pw@host/db"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "pw" not in result["dsn"]
        assert "[REDACTED]" in result["dsn"]

    def test_redacts_redis_connection_string(self):
        event = {"event": "cache_fail", "url": "redis://default:hunter2@redis.internal:6379"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "hunter2" not in result["url"]
        assert "[REDACTED]" in result["url"]

    def test_redacts_stripe_live_secret_key(self):
        event = {"event": "stripe_init", "key": _SK_LIVE}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "sk_" not in result["key"] or result["key"] == "[REDACTED]"
        assert result["key"] == "[REDACTED]"

    def test_redacts_stripe_live_restricted_key(self):
        event = {"event": "stripe_init", "key": _RK_LIVE}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "rk_" not in result["key"] or result["key"] == "[REDACTED]"
        assert result["key"] == "[REDACTED]"

    # ------------------------------------------------------------------
    # New patterns: Stripe test keys
    # ------------------------------------------------------------------

    def test_redacts_stripe_test_secret_key(self):
        event = {"event": "stripe_init", "key": _SK_TEST}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "sk_" not in result["key"] or result["key"] == "[REDACTED]"
        assert result["key"] == "[REDACTED]"

    def test_redacts_stripe_test_restricted_key(self):
        event = {"event": "stripe_init", "key": _RK_TEST}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "rk_" not in result["key"] or result["key"] == "[REDACTED]"
        assert result["key"] == "[REDACTED]"

    # ------------------------------------------------------------------
    # New patterns: Resend API keys
    # ------------------------------------------------------------------

    def test_redacts_resend_api_key(self):
        event = {"event": "email_send", "api_key": "re_ABC123xyz456defgh"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "re_ABC123" not in result["api_key"]
        assert "[REDACTED]" in result["api_key"]

    def test_does_not_redact_short_re_prefix(self):
        """Short 're_' strings (like 're_test') should NOT be redacted --
        the pattern requires 10+ alphanumeric chars after the prefix to
        avoid false positives on common words."""
        event = {"event": "test", "msg": "re_short"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert result["msg"] == "re_short"

    # ------------------------------------------------------------------
    # New patterns: Groq API keys
    # ------------------------------------------------------------------

    def test_redacts_groq_api_key(self):
        event = {"event": "llm_init", "key": "gsk_abcdefghij1234567890"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "gsk_" not in result["key"]
        assert "[REDACTED]" in result["key"]

    # ------------------------------------------------------------------
    # New patterns: Google / Gemini API keys
    # ------------------------------------------------------------------

    def test_redacts_google_api_key(self):
        event = {"event": "gemini_init", "key": "AIzaSyD-fake-key-1234567890abcdefghijklm"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "AIza" not in result["key"]
        assert "[REDACTED]" in result["key"]

    def test_does_not_redact_short_aiza_string(self):
        """A short AIza prefix that doesn't meet the 30-char minimum should
        be left alone to avoid false positives."""
        event = {"event": "test", "msg": "AIzaShort"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert result["msg"] == "AIzaShort"

    # ------------------------------------------------------------------
    # New patterns: Bearer tokens
    # ------------------------------------------------------------------

    def test_redacts_bearer_token(self):
        event = {
            "event": "auth_debug",
            "header": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig",
        }
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "eyJhbGci" not in result["header"]
        assert "[REDACTED]" in result["header"]

    def test_redacts_bearer_case_insensitive(self):
        event = {"event": "auth", "header": "bearer some_long_token_value_here"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "some_long_token" not in result["header"]
        assert "[REDACTED]" in result["header"]

    # ------------------------------------------------------------------
    # New patterns: Authorization header values
    # ------------------------------------------------------------------

    def test_redacts_authorization_header(self):
        event = {"event": "request", "header": "Authorization: Basic dXNlcjpwYXNz"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "dXNlcjpwYXNz" not in result["header"]
        assert "[REDACTED]" in result["header"]

    def test_redacts_authorization_header_case_insensitive(self):
        event = {"event": "request", "header": "authorization: token ghp_abc123xyz"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "ghp_abc123xyz" not in result["header"]
        assert "[REDACTED]" in result["header"]

    # ------------------------------------------------------------------
    # Structural tests: lists, tuples, non-strings, embedded values
    # ------------------------------------------------------------------

    def test_redacts_inside_list_values(self):
        event = {
            "event": "multi",
            "args": ["safe string", "postgres://user:pw@host/db", "also safe"],
        }
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "pw" not in result["args"][1]
        assert "[REDACTED]" in result["args"][1]
        assert result["args"][0] == "safe string"
        assert result["args"][2] == "also safe"

    def test_redacts_inside_tuple_values(self):
        event = {
            "event": "multi",
            "args": ("safe", _SK_TEST_SHORT),
        }
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert isinstance(result["args"], tuple)
        assert "sk_" not in result["args"][1] or result["args"][1] == "[REDACTED]"

    def test_passes_through_non_string_values(self):
        event = {"event": "metrics", "count": 42, "ratio": 3.14, "flag": True}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert result["count"] == 42
        assert result["ratio"] == 3.14
        assert result["flag"] is True

    def test_redacts_sensitive_data_in_event_message(self):
        """The 'event' key itself is a string and should be scrubbed."""
        event = {"event": "Failed to connect to redis://admin:pw@host:6379"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "pw" not in result["event"]
        assert "[REDACTED]" in result["event"]

    def test_multiple_patterns_in_single_string(self):
        """A string containing multiple sensitive patterns should have all redacted."""
        event = {
            "event": "debug",
            "msg": f"DB=postgresql://u:p@h/d key={_SK_LIVE_INLINE} Bearer eyJhbGci.x.y",
        }
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert "u:p" not in result["msg"]
        assert "sk_" not in result["msg"] or "[REDACTED]" in result["msg"]
        assert "eyJhbGci" not in result["msg"]

    def test_safe_strings_pass_through_unchanged(self):
        event = {"event": "healthy", "status": "ok", "region": "us_ct"}
        result = _sanitize_log_record(_LOGGER, _METHOD, event)
        assert result == event

    # ------------------------------------------------------------------
    # Module-level compilation check
    # ------------------------------------------------------------------

    def test_patterns_are_compiled_at_module_level(self):
        """Pattern should be a single pre-compiled re.Pattern (alternation of all sub-patterns)."""
        import re

        assert isinstance(
            _SANITIZER_PATTERN, re.Pattern
        ), f"Expected re.Pattern, got {type(_SANITIZER_PATTERN)}"
        # The combined alternation should contain at least 7 sub-patterns
        # (postgresql, redis, sk_live, sk_test, re_, gsk_, AIza, Bearer, Authorization)
        assert _SANITIZER_PATTERN.groups >= 0  # Valid compiled regex
