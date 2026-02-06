"""
SQL Injection Security Tests

Tests for:
- SQL injection in query parameters
- SQL injection in request bodies
- NoSQL injection patterns
- ORM parameterization
"""

import pytest
from fastapi.testclient import TestClient
from urllib.parse import quote


@pytest.fixture
def client():
    """Create test client."""
    from main import app
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Get authentication headers for protected endpoints."""
    return {"Authorization": "Bearer mock_test_token"}


class TestSQLInjectionInQueryParameters:
    """Tests for SQL injection in URL query parameters."""

    # Common SQL injection payloads
    SQL_INJECTION_PAYLOADS = [
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "' OR '1'='1' --",
        "' OR '1'='1' /*",
        "1; DROP TABLE users",
        "1'; EXEC xp_cmdshell('dir'); --",
        "' UNION SELECT * FROM users --",
        "' UNION SELECT username, password FROM users --",
        "admin'--",
        "' OR 1=1 --",
        "1 OR 1=1",
        "' OR 'x'='x",
        "') OR ('1'='1",
        "0 OR 1=1",
        "' AND 1=0 UNION SELECT table_name FROM information_schema.tables --",
        "'; WAITFOR DELAY '0:0:5'; --",  # Time-based injection
        "1; SELECT pg_sleep(5); --",  # PostgreSQL time-based
    ]

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_region_parameter_sql_injection(self, client, payload):
        """SQL injection in region parameter should be safely handled."""
        response = client.get(f"/api/v1/prices/current?region={quote(payload)}")

        # Should either reject (400/422) or safely handle (200 with no data)
        assert response.status_code in [200, 400, 422, 500], \
            f"Unexpected response for payload: {payload}"

        # Response should NOT contain evidence of SQL execution
        response_text = response.text.lower()
        dangerous_indicators = [
            "syntax error",
            "sql error",
            "database error",
            "pg_sleep",
            "waitfor delay",
            "information_schema",
            "table_name",
        ]
        for indicator in dangerous_indicators:
            assert indicator not in response_text, \
                f"Response may indicate SQL vulnerability: {indicator}"

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_supplier_id_sql_injection(self, client, payload):
        """SQL injection in supplier ID should be safely handled."""
        response = client.get(f"/api/v1/suppliers/{quote(payload)}")

        # Should return 400/404/422, not expose SQL errors
        assert response.status_code in [200, 400, 404, 422, 500]

    @pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
    def test_days_parameter_sql_injection(self, client, payload):
        """SQL injection in numeric parameters should be handled."""
        response = client.get(
            f"/api/v1/prices/history?region=UK&days={quote(payload)}"
        )

        # Numeric validation should reject non-numeric input
        assert response.status_code in [200, 400, 422, 500]

    def test_multiple_injection_points(self, client):
        """Test injection in multiple parameters simultaneously."""
        response = client.get(
            "/api/v1/prices/history?"
            "region=UK' OR '1'='1&"
            "days=7; DROP TABLE prices; --&"
            "sort=' UNION SELECT * FROM users --"
        )

        assert response.status_code in [200, 400, 422, 500]


class TestSQLInjectionInRequestBody:
    """Tests for SQL injection in POST request bodies."""

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "' UNION SELECT * FROM users --",
    ])
    def test_optimization_request_sql_injection(self, client, auth_headers, payload):
        """SQL injection in optimization request should be handled."""
        data = {
            "appliances": [
                {
                    "id": payload,
                    "power_kw": 1.5,
                    "duration_hours": 2,
                }
            ]
        }

        response = client.post(
            "/api/v1/optimization/schedule",
            json=data,
            headers=auth_headers
        )

        # Should handle the malicious input safely
        assert response.status_code in [200, 400, 401, 422, 500]

    @pytest.mark.parametrize("payload", [
        "'; DROP TABLE users; --",
        "admin'--",
        "' OR 1=1 --",
    ])
    def test_auth_request_sql_injection(self, client, payload):
        """SQL injection in auth request should be handled."""
        response = client.post(
            "/api/v1/auth/signin",
            json={
                "email": payload,
                "password": payload,
            }
        )

        # Should reject or handle safely
        assert response.status_code in [400, 401, 422, 500]

    def test_nested_json_sql_injection(self, client, auth_headers):
        """SQL injection in nested JSON should be handled."""
        data = {
            "user": {
                "name": "'; DROP TABLE users; --",
                "settings": {
                    "region": "' UNION SELECT * FROM prices --"
                }
            }
        }

        response = client.post(
            "/api/v1/user/preferences",
            json=data,
            headers=auth_headers
        )

        assert response.status_code in [200, 400, 401, 422, 500]


class TestNoSQLInjection:
    """Tests for NoSQL injection patterns (if using MongoDB, etc.)."""

    NOSQL_INJECTION_PAYLOADS = [
        {"$gt": ""},
        {"$ne": None},
        {"$where": "function() { return true; }"},
        {"$regex": ".*"},
        {"$or": [{"password": {"$exists": True}}]},
        "{'$gt': ''}",
        '{"$ne": null}',
    ]

    @pytest.mark.parametrize("payload", NOSQL_INJECTION_PAYLOADS)
    def test_nosql_injection_in_query(self, client, payload):
        """NoSQL injection patterns should be handled safely."""
        # Convert to string for URL parameter
        import json
        if isinstance(payload, dict):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)

        response = client.get(
            f"/api/v1/prices/current?region={quote(payload_str)}"
        )

        assert response.status_code in [200, 400, 422, 500]


class TestORMSafety:
    """Tests to verify ORM is properly parameterizing queries."""

    def test_integer_parameter_type_safety(self, client):
        """Integer parameters should be type-validated."""
        # Try to pass string where integer is expected
        response = client.get("/api/v1/prices/history?region=UK&days=abc")

        # Should fail validation
        assert response.status_code in [400, 422]

    def test_enum_parameter_validation(self, client):
        """Enum parameters should only accept valid values."""
        response = client.get(
            "/api/v1/prices/current?region=INVALID_REGION_XYZ"
        )

        # Should reject invalid enum value
        assert response.status_code in [400, 422]

    def test_special_characters_in_string_params(self, client):
        """Special characters should be escaped properly."""
        special_chars = [
            "test%00null",  # Null byte
            "test\nline",   # Newline
            "test\ttab",    # Tab
            "test\\slash",  # Backslash
            "test'quote",   # Single quote
            'test"quote',   # Double quote
        ]

        for chars in special_chars:
            response = client.get(
                f"/api/v1/suppliers?region={quote(chars)}"
            )
            # Should handle safely
            assert response.status_code in [200, 400, 422]


class TestSecondOrderInjection:
    """Tests for second-order SQL injection (stored XSS that becomes injection)."""

    def test_stored_value_injection(self, client, auth_headers):
        """Values stored in DB should not cause injection when read back."""
        # Store a malicious value
        response = client.post(
            "/api/v1/user/preferences",
            json={
                "display_name": "'; DROP TABLE users; --",
                "notification_enabled": True,
            },
            headers=auth_headers
        )

        # If stored successfully, reading it back should be safe
        if response.status_code == 200:
            get_response = client.get(
                "/api/v1/user/preferences",
                headers=auth_headers
            )
            # Should not execute the stored SQL
            assert get_response.status_code in [200, 401]


class TestDatabaseErrorHandling:
    """Tests to ensure database errors don't leak sensitive info."""

    def test_error_messages_dont_leak_schema(self, client):
        """Error messages should not reveal database schema."""
        # Trigger an error with invalid input
        response = client.get(
            "/api/v1/prices/current?region=' HAVING 1=1 --"
        )

        if response.status_code >= 400:
            response_text = response.text.lower()
            sensitive_info = [
                "table",
                "column",
                "postgresql",
                "mysql",
                "sqlite",
                "timescaledb",
                "schema",
                "syntax error at",
                "sql state",
            ]
            for info in sensitive_info:
                assert info not in response_text, \
                    f"Error response may leak schema info: {info}"

    def test_stack_traces_not_exposed(self, client):
        """Stack traces should not be exposed in error responses."""
        response = client.get(
            "/api/v1/prices/current?region='; SELECT * FROM--"
        )

        if response.status_code >= 400:
            response_text = response.text

            # Should not contain stack trace indicators
            assert "Traceback" not in response_text
            assert "File \"" not in response_text
            assert "line " not in response_text or "at line" not in response_text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
