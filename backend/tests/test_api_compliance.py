"""
Tests for the GDPR Compliance API Router (backend/api/v1/compliance.py)

Tests cover:
- POST /consent - record consent decision
- GET /gdpr/consents - get consent history
- GET /gdpr/consents/status - get current consent status
- GET /gdpr/export - export all user data
- DELETE /gdpr/delete-my-data - delete user data
- POST /gdpr/withdraw-all-consents - withdraw all consents
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, TokenData
from models.consent import ConsentRecord, DeletionLog


TEST_USER = TokenData(user_id="gdpr-user-1", email="gdpr@example.com")


@pytest.fixture
def mock_gdpr_service():
    """Create a mock GDPR compliance service."""
    service = AsyncMock()
    return service


@pytest.fixture
def compliance_client(mock_gdpr_service):
    """Create a TestClient with mocked dependencies."""
    from main import app
    from api.v1.compliance import get_gdpr_service

    app.dependency_overrides[get_current_user] = lambda: TEST_USER
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_gdpr_service] = lambda: mock_gdpr_service

    client = TestClient(app)
    yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_gdpr_service, None)


@pytest.fixture
def unauth_client():
    """Create a TestClient without authentication."""
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    client = TestClient(app)
    yield client


def _make_consent_record(**overrides):
    """Helper to create a ConsentRecord with sensible defaults."""
    defaults = {
        "id": "consent-1",
        "user_id": TEST_USER.user_id,
        "purpose": "analytics",
        "consent_given": True,
        "timestamp": datetime.now(timezone.utc),
        "ip_address": "127.0.0.1",
        "user_agent": "TestAgent",
    }
    defaults.update(overrides)
    return ConsentRecord(**defaults)


# =============================================================================
# POST /consent
# =============================================================================


class TestRecordConsent:
    """Tests for the POST /api/v1/compliance/consent endpoint."""

    def test_record_consent_success(self, compliance_client, mock_gdpr_service):
        """Recording consent should succeed and return 201."""
        mock_gdpr_service.record_consent.return_value = _make_consent_record()

        response = compliance_client.post(
            "/api/v1/compliance/consent",
            json={"purpose": "analytics", "consent_given": True},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert data["purpose"] == "analytics"
        assert data["consent_given"] is True
        assert "Consent given" in data["message"]

    def test_record_consent_withdrawal(self, compliance_client, mock_gdpr_service):
        """Recording consent withdrawal should return appropriate message."""
        mock_gdpr_service.record_consent.return_value = _make_consent_record(
            consent_given=False
        )

        response = compliance_client.post(
            "/api/v1/compliance/consent",
            json={"purpose": "marketing", "consent_given": False},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["consent_given"] is False
        assert "withdrawn" in data["message"].lower()

    def test_record_consent_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.post(
            "/api/v1/compliance/consent",
            json={"purpose": "analytics", "consent_given": True},
        )
        assert response.status_code == 401

    def test_record_consent_service_error(self, compliance_client, mock_gdpr_service):
        """Service error should return 500."""
        mock_gdpr_service.record_consent.side_effect = Exception("DB failure")

        response = compliance_client.post(
            "/api/v1/compliance/consent",
            json={"purpose": "analytics", "consent_given": True},
        )
        assert response.status_code == 500


# =============================================================================
# GET /gdpr/consents
# =============================================================================


class TestConsentHistory:
    """Tests for the GET /api/v1/compliance/gdpr/consents endpoint."""

    def test_consent_history_success(self, compliance_client, mock_gdpr_service):
        """Should return list of consent records."""
        records = [
            _make_consent_record(id="c1", purpose="analytics"),
            _make_consent_record(id="c2", purpose="marketing"),
        ]
        mock_gdpr_service.get_consent_history.return_value = records

        response = compliance_client.get("/api/v1/compliance/gdpr/consents")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert data["total_count"] == 2
        assert len(data["consents"]) == 2

    def test_consent_history_empty(self, compliance_client, mock_gdpr_service):
        """Empty history should return empty list with count 0."""
        mock_gdpr_service.get_consent_history.return_value = []

        response = compliance_client.get("/api/v1/compliance/gdpr/consents")
        assert response.status_code == 200
        data = response.json()
        assert data["total_count"] == 0
        assert data["consents"] == []

    def test_consent_history_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/compliance/gdpr/consents")
        assert response.status_code == 401


# =============================================================================
# GET /gdpr/consents/status
# =============================================================================


class TestConsentStatus:
    """Tests for the GET /api/v1/compliance/gdpr/consents/status endpoint."""

    def test_consent_status_success(self, compliance_client, mock_gdpr_service):
        """Should return current consent status per purpose."""
        mock_gdpr_service.get_current_consent_status.return_value = {
            "analytics": True,
            "marketing": False,
        }

        response = compliance_client.get("/api/v1/compliance/gdpr/consents/status")
        assert response.status_code == 200
        data = response.json()
        assert data["consents"]["analytics"] is True
        assert data["consents"]["marketing"] is False


# =============================================================================
# GET /gdpr/export
# =============================================================================


class TestDataExport:
    """Tests for the GET /api/v1/compliance/gdpr/export endpoint."""

    def test_export_success(self, compliance_client, mock_gdpr_service):
        """Should return full user data export."""
        mock_gdpr_service.export_user_data.return_value = {
            "user_id": TEST_USER.user_id,
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "export_format_version": "1.0",
            "profile_data": {"email": "gdpr@example.com"},
            "preferences_data": {},
            "consent_history": [],
            "price_alerts": [],
            "recommendations": [],
            "activity_logs": [],
        }

        response = compliance_client.get("/api/v1/compliance/gdpr/export")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert data["export_format_version"] == "1.0"
        assert "profile_data" in data

    def test_export_user_not_found(self, compliance_client, mock_gdpr_service):
        """Should return 404 when user not found."""
        from compliance.gdpr import UserNotFoundError

        mock_gdpr_service.export_user_data.side_effect = UserNotFoundError(
            TEST_USER.user_id
        )

        response = compliance_client.get("/api/v1/compliance/gdpr/export")
        assert response.status_code == 404

    def test_export_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.get("/api/v1/compliance/gdpr/export")
        assert response.status_code == 401


# =============================================================================
# DELETE /gdpr/delete-my-data
# =============================================================================


class TestDataDeletion:
    """Tests for the DELETE /api/v1/compliance/gdpr/delete-my-data endpoint."""

    def test_deletion_success(self, compliance_client, mock_gdpr_service):
        """Confirmed deletion should succeed."""
        mock_gdpr_service.delete_user_data.return_value = DeletionLog(
            id="del-1",
            user_id=TEST_USER.user_id,
            deleted_at=datetime.now(timezone.utc),
            deleted_by=TEST_USER.user_id,
            deletion_type="full",
            ip_address="127.0.0.1",
            user_agent="TestAgent",
            data_categories_deleted=["consents", "profile"],
        )

        response = compliance_client.request(
            "DELETE",
            "/api/v1/compliance/gdpr/delete-my-data",
            json={"confirmation": True, "retain_anonymized": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "consents" in data["deleted_categories"]

    def test_deletion_requires_confirmation(self, compliance_client, mock_gdpr_service):
        """Deletion without confirmation should return 400."""
        response = compliance_client.request(
            "DELETE",
            "/api/v1/compliance/gdpr/delete-my-data",
            json={"confirmation": False},
        )
        assert response.status_code == 400
        assert "confirmation" in response.json()["detail"].lower()

    def test_deletion_user_not_found(self, compliance_client, mock_gdpr_service):
        """Should return 404 when user not found."""
        from compliance.gdpr import UserNotFoundError

        mock_gdpr_service.delete_user_data.side_effect = UserNotFoundError(
            TEST_USER.user_id
        )

        response = compliance_client.request(
            "DELETE",
            "/api/v1/compliance/gdpr/delete-my-data",
            json={"confirmation": True},
        )
        assert response.status_code == 404


# =============================================================================
# POST /gdpr/withdraw-all-consents
# =============================================================================


class TestWithdrawAllConsents:
    """Tests for the POST /api/v1/compliance/gdpr/withdraw-all-consents endpoint."""

    def test_withdraw_all_success(self, compliance_client, mock_gdpr_service):
        """Should create withdrawal records for all purposes."""
        withdrawals = [
            _make_consent_record(id=f"w{i}", purpose=p, consent_given=False)
            for i, p in enumerate(["analytics", "marketing", "optimization"])
        ]
        mock_gdpr_service.withdraw_all_consents.return_value = withdrawals

        response = compliance_client.post(
            "/api/v1/compliance/gdpr/withdraw-all-consents"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == TEST_USER.user_id
        assert data["total_count"] == 3
        for record in data["consents"]:
            assert record["consent_given"] is False

    def test_withdraw_all_requires_auth(self, unauth_client):
        """Request without auth should return 401."""
        response = unauth_client.post(
            "/api/v1/compliance/gdpr/withdraw-all-consents"
        )
        assert response.status_code == 401
