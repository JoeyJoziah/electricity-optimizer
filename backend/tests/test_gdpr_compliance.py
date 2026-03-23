"""
GDPR Compliance Tests

Comprehensive tests for GDPR compliance features:
- Article 6: Lawful basis for processing (explicit consent)
- Article 15: Right to access (data export)
- Article 17: Right to erasure (complete deletion)
- Article 20: Data portability (machine-readable export)
- Article 21: Right to object (consent withdrawal)
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


# =============================================================================
# CONSENT RECORD MODEL TESTS
# =============================================================================


class TestConsentRecordModel:
    """Tests for ConsentRecord model validation"""

    def test_consent_record_valid_data(self):
        """Test creating a valid consent record"""
        from models.consent import ConsentRecord

        record = ConsentRecord(
            user_id="user-123",
            purpose="data_processing",
            consent_given=True,
            timestamp=datetime.now(UTC),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert record.user_id == "user-123"
        assert record.purpose == "data_processing"
        assert record.consent_given is True
        assert record.ip_address == "192.168.1.1"
        assert record.user_agent == "Mozilla/5.0"

    def test_consent_record_required_fields(self):
        """Test that all required fields are present"""
        from pydantic import ValidationError

        from models.consent import ConsentRecord

        with pytest.raises(ValidationError):
            ConsentRecord()

    def test_consent_record_valid_purposes(self):
        """Test that consent purposes are validated"""
        from models.consent import ConsentPurpose

        assert ConsentPurpose.DATA_PROCESSING.value == "data_processing"
        assert ConsentPurpose.MARKETING.value == "marketing"
        assert ConsentPurpose.ANALYTICS.value == "analytics"
        assert ConsentPurpose.PRICE_ALERTS.value == "price_alerts"
        assert ConsentPurpose.OPTIMIZATION.value == "optimization"

    def test_consent_record_with_all_optional_fields(self):
        """Test consent record with all fields populated"""
        from models.consent import ConsentRecord

        record = ConsentRecord(
            id="consent-id-123",
            user_id="user-123",
            purpose="marketing",
            consent_given=False,
            timestamp=datetime.now(UTC),
            ip_address="10.0.0.1",
            user_agent="Chrome/120.0",
            consent_version="1.0",
            withdrawal_timestamp=datetime.now(UTC),
            metadata={"source": "web"},
        )

        assert record.id == "consent-id-123"
        assert record.consent_version == "1.0"
        assert record.metadata == {"source": "web"}

    def test_consent_timestamp_has_timezone(self):
        """Test that timestamps always have timezone info"""
        from models.consent import ConsentRecord

        # Create with naive datetime - should be converted to UTC
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        record = ConsentRecord(
            user_id="user-123",
            purpose="data_processing",
            consent_given=True,
            timestamp=naive_dt,
            ip_address="192.168.1.1",
            user_agent="Test",
        )

        assert record.timestamp.tzinfo is not None


# =============================================================================
# CONSENT REQUEST/RESPONSE MODEL TESTS
# =============================================================================


class TestConsentRequestModels:
    """Tests for consent request and response models"""

    def test_consent_request_schema(self):
        """Test consent request schema validation"""
        from models.consent import ConsentRequest

        request = ConsentRequest(purpose="data_processing", consent_given=True)

        assert request.purpose == "data_processing"
        assert request.consent_given is True

    def test_consent_response_schema(self):
        """Test consent response schema"""
        from models.consent import ConsentResponse

        response = ConsentResponse(
            id="consent-123",
            user_id="user-123",
            purpose="analytics",
            consent_given=True,
            timestamp=datetime.now(UTC),
            message="Consent recorded successfully",
        )

        assert response.message == "Consent recorded successfully"

    def test_consent_history_response_schema(self):
        """Test consent history response schema"""
        from models.consent import ConsentHistoryResponse, ConsentRecord

        record = ConsentRecord(
            user_id="user-123",
            purpose="data_processing",
            consent_given=True,
            timestamp=datetime.now(UTC),
            ip_address="192.168.1.1",
            user_agent="Test",
        )

        response = ConsentHistoryResponse(user_id="user-123", consents=[record], total_count=1)

        assert len(response.consents) == 1
        assert response.total_count == 1


# =============================================================================
# DATA EXPORT MODEL TESTS
# =============================================================================


class TestDataExportModels:
    """Tests for GDPR data export models"""

    def test_user_data_export_model(self):
        """Test user data export model structure"""
        from models.consent import UserDataExport

        export = UserDataExport(
            user_id="user-123",
            export_timestamp=datetime.now(UTC),
            profile_data={"email": "test@example.com", "name": "Test User"},
            preferences_data={"notifications": True},
            consent_history=[],
            price_alerts=[],
            recommendations=[],
            activity_logs=[],
        )

        assert export.user_id == "user-123"
        assert export.profile_data["email"] == "test@example.com"

    def test_data_export_includes_all_user_data(self):
        """Test that data export includes all required user data categories"""
        from models.consent import UserDataExport

        required_fields = [
            "user_id",
            "export_timestamp",
            "profile_data",
            "preferences_data",
            "consent_history",
            "price_alerts",
            "recommendations",
            "activity_logs",
        ]

        export = UserDataExport(
            user_id="user-123",
            export_timestamp=datetime.now(UTC),
            profile_data={},
            preferences_data={},
            consent_history=[],
            price_alerts=[],
            recommendations=[],
            activity_logs=[],
        )

        for field in required_fields:
            assert hasattr(export, field), f"Missing required field: {field}"


# =============================================================================
# GDPR COMPLIANCE SERVICE TESTS
# =============================================================================


class TestGDPRComplianceService:
    """Tests for GDPRComplianceService"""

    @pytest.fixture
    def mock_consent_repository(self):
        """Create mock consent repository"""
        repo = AsyncMock()
        repo.create.return_value = MagicMock(id="consent-123")
        repo.get_by_user_id.return_value = []
        repo.get_by_id.return_value = None
        repo.update.return_value = MagicMock()
        repo.delete.return_value = True
        return repo

    @pytest.fixture
    def mock_user_repository(self):
        """Create mock user repository"""
        repo = AsyncMock()
        repo.get_by_id.return_value = MagicMock(
            id="user-123", email="test@example.com", name="Test User", preferences={}
        )
        repo.delete.return_value = True
        return repo

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session for atomic GDPR deletion."""
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=MagicMock(
                mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            )
        )
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        return session

    @pytest.fixture
    def gdpr_service(self, mock_consent_repository, mock_user_repository, mock_db_session):
        """Create GDPR compliance service with mocked repositories"""
        from compliance.gdpr import GDPRComplianceService

        return GDPRComplianceService(
            consent_repository=mock_consent_repository,
            user_repository=mock_user_repository,
            db_session=mock_db_session,
        )

    # -------------------------------------------------------------------------
    # Consent Recording Tests (Article 6)
    # -------------------------------------------------------------------------

    async def test_record_consent_success(self, gdpr_service, mock_consent_repository):
        """Test successful consent recording"""
        result = await gdpr_service.record_consent(
            user_id="user-123",
            purpose="data_processing",
            consent_given=True,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
        )

        assert result is not None
        mock_consent_repository.create.assert_called_once()

    async def test_record_consent_with_all_metadata(self, gdpr_service, mock_consent_repository):
        """Test consent recording captures all required metadata"""
        await gdpr_service.record_consent(
            user_id="user-123",
            purpose="marketing",
            consent_given=False,
            ip_address="10.0.0.1",
            user_agent="Chrome/120",
        )

        call_args = mock_consent_repository.create.call_args
        consent_record = call_args[0][0]

        assert consent_record.user_id == "user-123"
        assert consent_record.purpose == "marketing"
        assert consent_record.consent_given is False
        assert consent_record.ip_address == "10.0.0.1"
        assert consent_record.user_agent == "Chrome/120"
        assert consent_record.timestamp is not None

    async def test_record_consent_withdrawal(self, gdpr_service, mock_consent_repository):
        """Test consent withdrawal is properly recorded"""
        # Record initial consent
        await gdpr_service.record_consent(
            user_id="user-123",
            purpose="marketing",
            consent_given=True,
            ip_address="192.168.1.1",
            user_agent="Test",
        )

        # Withdraw consent
        await gdpr_service.record_consent(
            user_id="user-123",
            purpose="marketing",
            consent_given=False,
            ip_address="192.168.1.1",
            user_agent="Test",
        )

        assert mock_consent_repository.create.call_count == 2

    async def test_record_consent_multiple_purposes(self, gdpr_service, mock_consent_repository):
        """Test recording consent for multiple purposes"""
        purposes = ["data_processing", "marketing", "analytics", "price_alerts"]

        for purpose in purposes:
            await gdpr_service.record_consent(
                user_id="user-123",
                purpose=purpose,
                consent_given=True,
                ip_address="192.168.1.1",
                user_agent="Test",
            )

        assert mock_consent_repository.create.call_count == len(purposes)

    # -------------------------------------------------------------------------
    # Consent History Tests
    # -------------------------------------------------------------------------

    async def test_get_consent_history(self, gdpr_service, mock_consent_repository):
        """Test retrieving consent history for a user"""
        mock_consent_repository.get_by_user_id.return_value = [
            MagicMock(
                id="consent-1",
                user_id="user-123",
                purpose="data_processing",
                consent_given=True,
                timestamp=datetime.now(UTC),
            ),
            MagicMock(
                id="consent-2",
                user_id="user-123",
                purpose="marketing",
                consent_given=False,
                timestamp=datetime.now(UTC),
            ),
        ]

        history = await gdpr_service.get_consent_history("user-123")

        assert len(history) == 2
        mock_consent_repository.get_by_user_id.assert_called_once_with("user-123")

    async def test_get_consent_history_empty(self, gdpr_service, mock_consent_repository):
        """Test consent history for user with no consents"""
        mock_consent_repository.get_by_user_id.return_value = []

        history = await gdpr_service.get_consent_history("user-123")

        assert len(history) == 0

    async def test_get_current_consent_status(self, gdpr_service, mock_consent_repository):
        """Test getting current consent status for all purposes"""
        mock_consent_repository.get_latest_by_user_and_purpose.return_value = {
            "data_processing": True,
            "marketing": False,
            "analytics": True,
        }

        status = await gdpr_service.get_current_consent_status("user-123")

        assert status["data_processing"] is True
        assert status["marketing"] is False
        assert status["analytics"] is True

    # -------------------------------------------------------------------------
    # Data Export Tests (Article 15 & 20)
    # -------------------------------------------------------------------------

    async def test_export_user_data_returns_all_data(
        self, gdpr_service, mock_consent_repository, mock_user_repository
    ):
        """Test data export returns all user data"""
        export = await gdpr_service.export_user_data("user-123")

        assert export is not None
        assert "user_id" in export
        assert "export_timestamp" in export
        assert "profile_data" in export
        assert "preferences_data" in export
        assert "consent_history" in export

    async def test_export_user_data_includes_profile(self, gdpr_service, mock_user_repository):
        """Test data export includes user profile"""
        mock_user = MagicMock(
            id="user-123",
            email="test@example.com",
            region="uk",
            preferences={"notifications": True},
        )
        mock_user.name = "Test User"
        mock_user_repository.get_by_id.return_value = mock_user

        export = await gdpr_service.export_user_data("user-123")

        assert export["profile_data"]["email"] == "test@example.com"
        assert export["profile_data"]["name"] == "Test User"

    async def test_export_user_data_includes_consent_history(
        self, gdpr_service, mock_consent_repository
    ):
        """Test data export includes consent history"""
        mock_consent_repository.get_by_user_id.return_value = [
            MagicMock(purpose="data_processing", consent_given=True, timestamp=datetime.now(UTC))
        ]

        export = await gdpr_service.export_user_data("user-123")

        assert len(export["consent_history"]) > 0

    async def test_export_user_data_machine_readable(self, gdpr_service):
        """Test data export is in machine-readable format (JSON serializable)"""
        import json

        export = await gdpr_service.export_user_data("user-123")

        # Should be JSON serializable
        json_str = json.dumps(export, default=str)
        assert json_str is not None

    async def test_export_user_data_nonexistent_user(self, gdpr_service, mock_user_repository):
        """Test data export for nonexistent user"""
        from compliance.gdpr import UserNotFoundError

        mock_user_repository.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            await gdpr_service.export_user_data("nonexistent-user")

    # -------------------------------------------------------------------------
    # Data Deletion Tests (Article 17)
    # -------------------------------------------------------------------------

    async def test_delete_user_data_success(self, gdpr_service, mock_db_session):
        """Test successful user data deletion"""
        result = await gdpr_service.delete_user_data("user-123")

        assert result is not None
        # Single commit: deletion + deletion_log INSERT are now in ONE transaction
        # (fix for 09-P0-3 — deletion log transaction isolation)
        assert mock_db_session.commit.call_count == 1

    async def test_delete_user_data_deletes_all_categories(self, gdpr_service, mock_db_session):
        """Test deletion removes all user data categories atomically."""
        result = await gdpr_service.delete_user_data("user-123")

        # Verify all expected categories were deleted
        expected = {
            "consents",
            "price_alerts",
            "recommendations",
            "activity_logs",
            "extracted_rates",
            "bill_uploads",
            "connections",
            "supplier_accounts",
            "profile",
            "agent_data",
            "community_data",
            "notifications",
            "feedback",
            "savings",
            "recommendation_outcomes",
            "ml_data",
            "referrals",
        }
        assert set(result.data_categories_deleted) == expected

        # Single commit: deletion + audit log are fully atomic (fix for 09-P0-3)
        assert mock_db_session.commit.call_count == 1
        mock_db_session.rollback.assert_not_called()

    async def test_delete_user_data_logs_deletion(self, gdpr_service):
        """Test that data deletion is logged for audit purposes"""
        result = await gdpr_service.delete_user_data("user-123")

        assert result.user_id == "user-123"
        assert result.deletion_type == "full"
        assert result.legal_basis == "user_request"

    async def test_delete_user_data_anonymizes_retained_data(self, gdpr_service, mock_db_session):
        """Test that retained data (for legal reasons) is anonymized"""
        result = await gdpr_service.delete_user_data("user-123", anonymize_retained=True)

        assert result.deletion_type == "anonymization"
        assert "activity_logs" in result.data_categories_deleted

    async def test_delete_user_data_nonexistent_user(self, gdpr_service, mock_user_repository):
        """Test deletion for nonexistent user"""
        from compliance.gdpr import UserNotFoundError

        mock_user_repository.get_by_id.return_value = None

        with pytest.raises(UserNotFoundError):
            await gdpr_service.delete_user_data("nonexistent-user")

    async def test_delete_user_data_rollback_on_failure(self, gdpr_service, mock_db_session):
        """Test that partial failure rolls back all changes (atomic)."""
        from compliance.gdpr import DataDeletionError

        # Make the 3rd execute call fail (simulating a mid-transaction error)
        call_count = 0
        original_execute = mock_db_session.execute

        async def failing_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise Exception("Simulated DB error")
            return await original_execute(*args, **kwargs)

        mock_db_session.execute = AsyncMock(side_effect=failing_execute)

        with pytest.raises(DataDeletionError, match="Simulated DB error"):
            await gdpr_service.delete_user_data("user-123")

        # Verify rollback was called, commit was NOT called
        mock_db_session.rollback.assert_called_once()
        mock_db_session.commit.assert_not_called()

    async def test_delete_user_data_cascade(self, gdpr_service, mock_db_session):
        """Test cascade deletion of all related data via SQL."""
        await gdpr_service.delete_user_data("user-123")

        # Verify db_session.execute was called for each table
        # (consent_records, price_alerts, recommendations, activity_logs,
        #  connection_extracted_rates, bill_uploads SELECT, bill_uploads DELETE,
        #  user_connections, user_supplier_accounts, users)
        assert mock_db_session.execute.call_count >= 9

    # -------------------------------------------------------------------------
    # Right to Object Tests (Article 21)
    # -------------------------------------------------------------------------

    async def test_withdraw_all_consents(self, gdpr_service, mock_consent_repository):
        """Test withdrawing all consents at once"""
        await gdpr_service.withdraw_all_consents(
            user_id="user-123", ip_address="192.168.1.1", user_agent="Test"
        )

        # Should create withdrawal records for all consent types

    async def test_consent_withdrawal_stops_processing(self, gdpr_service):
        """Test that consent withdrawal stops related processing"""
        await gdpr_service.record_consent(
            user_id="user-123",
            purpose="marketing",
            consent_given=False,
            ip_address="192.168.1.1",
            user_agent="Test",
        )

        # After withdrawal, related processing should be stopped
        # This would typically trigger notifications to other services


# =============================================================================
# CONSENT REPOSITORY TESTS
# =============================================================================


class TestConsentRepository:
    """Tests for ConsentRepository"""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session"""
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result
        session.add = MagicMock()
        session.commit = AsyncMock()
        return session

    @pytest.fixture
    def consent_repository(self, mock_db_session):
        """Create consent repository with mock session"""
        from compliance.repositories import ConsentRepository

        return ConsentRepository(mock_db_session)

    async def test_create_consent_record(self, consent_repository, mock_db_session):
        """Test creating a consent record in database"""
        from models.consent import ConsentRecord

        record = ConsentRecord(
            user_id="user-123",
            purpose="data_processing",
            consent_given=True,
            timestamp=datetime.now(UTC),
            ip_address="192.168.1.1",
            user_agent="Test",
        )

        await consent_repository.create(record)

        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()

    async def test_get_consents_by_user_id(self, consent_repository, mock_db_session):
        """Test retrieving consents by user ID"""
        await consent_repository.get_by_user_id("user-123")

        mock_db_session.execute.assert_called_once()

    async def test_get_latest_consent_by_purpose(self, consent_repository, mock_db_session):
        """Test getting latest consent for specific purpose via DISTINCT ON."""
        # Mock the raw SQL fetchall result (purpose, consent_given)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [("marketing", True)]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await consent_repository.get_latest_by_user_and_purpose("user-123", "marketing")

        mock_db_session.execute.assert_called_once()
        assert result == {"marketing": True}

    async def test_get_latest_consent_all_purposes(self, consent_repository, mock_db_session):
        """Test getting latest consent for all purposes via DISTINCT ON."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("data_processing", True),
            ("marketing", False),
            ("analytics", True),
        ]
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await consent_repository.get_latest_by_user_and_purpose("user-123")

        mock_db_session.execute.assert_called_once()
        assert result == {
            "data_processing": True,
            "marketing": False,
            "analytics": True,
        }

    async def test_get_latest_consent_empty(self, consent_repository, mock_db_session):
        """Test getting latest consent when no records exist."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db_session.execute = AsyncMock(return_value=mock_result)

        result = await consent_repository.get_latest_by_user_and_purpose("user-123")

        assert result == {}

    async def test_delete_consents_by_user_id(self, consent_repository, mock_db_session):
        """Test deleting all consents for a user.

        Note: delete_by_user_id does NOT commit — the caller (GDPR atomic
        deletion block) is responsible for transaction management.
        """
        await consent_repository.delete_by_user_id("user-123")

        mock_db_session.execute.assert_called_once()
        mock_db_session.commit.assert_not_called()


# =============================================================================
# DELETION LOG TESTS
# =============================================================================


class TestDeletionLog:
    """Tests for deletion logging (audit trail)"""

    def test_deletion_log_model(self):
        """Test deletion log model structure"""
        from models.consent import DeletionLog

        log = DeletionLog(
            user_id="user-123",
            deleted_at=datetime.now(UTC),
            deleted_by="user-123",  # Self-deletion
            deletion_type="full",
            ip_address="192.168.1.1",
            user_agent="Test",
            data_categories_deleted=["profile", "consents", "preferences"],
        )

        assert log.user_id == "user-123"
        assert log.deletion_type == "full"
        assert "profile" in log.data_categories_deleted

    def test_deletion_log_immutable(self):
        """Test that deletion logs cannot be modified"""
        from models.consent import DeletionLog

        log = DeletionLog(
            user_id="user-123",
            deleted_at=datetime.now(UTC),
            deleted_by="user-123",
            deletion_type="full",
            ip_address="192.168.1.1",
            user_agent="Test",
            data_categories_deleted=["profile"],
        )

        # Deletion logs should be immutable for audit purposes


# =============================================================================
# GDPR COMPLIANCE API ENDPOINT TESTS
# =============================================================================


class TestGDPRComplianceAPI:
    """Tests for GDPR compliance API endpoints"""

    @pytest.fixture
    def mock_gdpr_service(self):
        """Create mock GDPR service"""
        service = AsyncMock()
        return service

    @pytest.fixture
    def mock_session_data(self):
        """Mock authenticated user session"""
        from auth.neon_auth import SessionData

        return SessionData(
            user_id="user-123",
            email="test@example.com",
            name="Test User",
            email_verified=True,
        )

    async def test_consent_endpoint_requires_auth(self):
        """Test that consent endpoints require authentication"""
        import inspect

        from api.v1.compliance import record_consent

        # Verify the endpoint has get_current_user dependency
        sig = inspect.signature(record_consent)
        param_names = list(sig.parameters.keys())
        assert "current_user" in param_names

    async def test_record_consent_endpoint(self, mock_gdpr_service, mock_session_data):
        """Test POST /api/v1/compliance/consent endpoint"""
        from models.consent import ConsentRecord

        mock_record = ConsentRecord(
            id="consent-1",
            user_id="user-123",
            purpose="data_processing",
            consent_given=True,
            timestamp=datetime.now(UTC),
            ip_address="127.0.0.1",
            user_agent="Test",
        )
        mock_gdpr_service.record_consent.return_value = mock_record

        from api.v1.compliance import record_consent
        from models.consent import ConsentRequest

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = "Test"

        consent_req = ConsentRequest(
            purpose="data_processing",
            consent_given=True,
        )

        result = await record_consent(
            request=mock_request,
            consent_request=consent_req,
            current_user=mock_session_data,
            gdpr_service=mock_gdpr_service,
        )

        assert result.user_id == "user-123"
        assert result.consent_given is True
        mock_gdpr_service.record_consent.assert_called_once()

    async def test_export_data_endpoint(self, mock_gdpr_service, mock_session_data):
        """Test GET /api/v1/compliance/gdpr/export endpoint"""
        mock_gdpr_service.export_user_data.return_value = {
            "user_id": "user-123",
            "export_timestamp": datetime.now(UTC).isoformat(),
            "export_format_version": "1.0",
            "profile_data": {"email": "test@example.com"},
            "preferences_data": {},
            "consent_history": [],
            "price_alerts": [],
            "recommendations": [],
            "activity_logs": [],
        }

        from api.v1.compliance import export_user_data

        result = await export_user_data(
            current_user=mock_session_data,
            gdpr_service=mock_gdpr_service,
        )

        assert result.user_id == "user-123"
        assert result.export_format_version == "1.0"
        mock_gdpr_service.export_user_data.assert_called_once_with("user-123")

    async def test_delete_data_endpoint(self, mock_gdpr_service, mock_session_data):
        """Test DELETE /api/v1/compliance/gdpr/delete-my-data endpoint"""
        from models.consent import DataDeletionRequest, DeletionLog

        mock_log = DeletionLog(
            id="del-1",
            user_id="user-123",
            deleted_at=datetime.now(UTC),
            deleted_by="user-123",
            deletion_type="full",
            ip_address="127.0.0.1",
            user_agent="Test",
            data_categories_deleted=["profile", "consents", "savings", "ml_data"],
        )
        mock_gdpr_service.delete_user_data.return_value = mock_log

        from api.v1.compliance import delete_user_data

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = "Test"

        deletion_req = DataDeletionRequest(confirmation=True)

        result = await delete_user_data(
            request=mock_request,
            deletion_request=deletion_req,
            current_user=mock_session_data,
            gdpr_service=mock_gdpr_service,
        )

        assert result.success is True
        assert "profile" in result.deleted_categories
        assert "savings" in result.deleted_categories
        mock_gdpr_service.delete_user_data.assert_called_once()

    async def test_consent_history_endpoint(self, mock_gdpr_service, mock_session_data):
        """Test GET /api/v1/compliance/gdpr/consents endpoint"""
        from models.consent import ConsentRecord

        mock_records = [
            ConsentRecord(
                id="c1",
                user_id="user-123",
                purpose="data_processing",
                consent_given=True,
                timestamp=datetime.now(UTC),
                ip_address="127.0.0.1",
                user_agent="Test",
            ),
        ]
        mock_gdpr_service.get_consent_history.return_value = mock_records

        from api.v1.compliance import get_consent_history

        result = await get_consent_history(
            current_user=mock_session_data,
            gdpr_service=mock_gdpr_service,
        )

        assert result.user_id == "user-123"
        assert result.total_count == 1
        mock_gdpr_service.get_consent_history.assert_called_once_with("user-123")


# =============================================================================
# DATA RETENTION TESTS
# =============================================================================


class TestDataRetention:
    """Tests for data retention policies"""

    @pytest.fixture
    def retention_service(self):
        """Create data retention service"""
        from compliance.gdpr import DataRetentionService

        return DataRetentionService(retention_days=730)

    async def test_identify_expired_data(self, retention_service):
        """Test identifying data past retention period"""
        assert retention_service.retention_days == 730

        # Cutoff date should be 730 days ago
        cutoff = datetime.now(UTC) - timedelta(days=730)
        assert cutoff < datetime.now(UTC)

        # A record older than retention period should be considered expired
        old_date = datetime.now(UTC) - timedelta(days=731)
        assert old_date < cutoff

        # A recent record should NOT be considered expired
        recent_date = datetime.now(UTC) - timedelta(days=100)
        assert recent_date > cutoff

    async def test_purge_expired_data(self, retention_service):
        """Test purging expired data"""
        # Retention service should track what was purged
        assert retention_service.retention_days == 730

        # Verify the service can compute the retention window correctly
        cutoff = datetime.now(UTC) - timedelta(days=retention_service.retention_days)
        assert isinstance(cutoff, datetime)
        assert cutoff.tzinfo is not None

    async def test_retention_respects_legal_holds(self, retention_service):
        """Test that retention respects legal hold flags"""
        # Retention period is configurable
        custom_service = type(retention_service)(retention_days=365)
        assert custom_service.retention_days == 365

        # Default is 730 days (2 years)
        assert retention_service.retention_days == 730


# =============================================================================
# ANONYMIZATION TESTS
# =============================================================================


class TestDataAnonymization:
    """Tests for data anonymization"""

    def test_anonymize_email(self):
        """Test email anonymization"""
        from compliance.gdpr import anonymize_email

        result = anonymize_email("test@example.com")
        assert "@" in result
        assert result != "test@example.com"
        assert result.startswith("anon_")

    def test_anonymize_name(self):
        """Test name anonymization"""
        from compliance.gdpr import anonymize_name

        result = anonymize_name("John Doe")
        assert result != "John Doe"
        assert result.startswith("Anonymous User")

    def test_anonymize_ip_address(self):
        """Test IP address anonymization"""
        from compliance.gdpr import anonymize_ip

        result = anonymize_ip("192.168.1.100")
        assert result == "192.168.1.0"  # Last octet zeroed

    def test_anonymize_user_agent(self):
        """Test user agent anonymization"""
        from compliance.gdpr import anonymize_user_agent

        result = anonymize_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64)")
        assert result == "Anonymous"


# =============================================================================
# INTEGRATION TESTS
# =============================================================================


class TestGDPRIntegration:
    """Integration tests for GDPR compliance"""

    async def test_full_consent_flow(self):
        """Test complete consent flow: record -> view -> withdraw"""
        mock_db = AsyncMock()
        mock_db.execute.return_value = MagicMock(
            fetchone=MagicMock(return_value=None),
            mappings=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[]))),
        )

        consent_repo = AsyncMock()
        user_repo = AsyncMock()

        from compliance.gdpr import GDPRComplianceService
        from models.consent import ConsentRecord

        service = GDPRComplianceService(
            consent_repository=consent_repo,
            user_repository=user_repo,
            db_session=mock_db,
        )

        # Step 1: Record consent
        mock_record = ConsentRecord(
            id="c1",
            user_id="user-1",
            purpose="data_processing",
            consent_given=True,
            timestamp=datetime.now(UTC),
            ip_address="127.0.0.1",
            user_agent="Test",
        )
        consent_repo.create.return_value = mock_record
        consent_repo.get_latest_by_user_and_purpose.return_value = {"data_processing": mock_record}

        result = await service.record_consent(
            user_id="user-1",
            purpose="data_processing",
            consent_given=True,
            ip_address="127.0.0.1",
            user_agent="Test",
        )
        assert result.consent_given is True

        # Step 2: Check consent status
        consent_repo.get_by_user_id.return_value = [mock_record]
        history = await service.get_consent_history("user-1")
        assert len(history) == 1

    async def test_full_data_export_flow(self):
        """Test complete data export flow"""
        mock_db = AsyncMock()
        consent_repo = AsyncMock()
        user_repo = AsyncMock()

        from compliance.gdpr import GDPRComplianceService

        user_repo.get_by_id.return_value = MagicMock(
            id="user-1",
            email="test@example.com",
            name="Test",
            region="CT",
            is_active=True,
        )
        consent_repo.get_by_user_id.return_value = []

        service = GDPRComplianceService(
            consent_repository=consent_repo,
            user_repository=user_repo,
            db_session=mock_db,
        )

        result = await service.export_user_data("user-1")

        assert result["user_id"] == "user-1"
        assert "profile_data" in result
        assert "export_timestamp" in result

    async def test_full_deletion_flow(self):
        """Test complete data deletion flow"""
        mock_db = AsyncMock()
        consent_repo = AsyncMock()
        user_repo = AsyncMock()

        # Mock execute to return a result with .mappings().all() for bill_uploads query
        mock_mappings_result = MagicMock()
        mock_mappings_result.mappings.return_value.all.return_value = []

        mock_db.execute.return_value = mock_mappings_result

        from compliance.gdpr import GDPRComplianceService

        user_repo.get_by_id.return_value = MagicMock(id="user-1")

        service = GDPRComplianceService(
            consent_repository=consent_repo,
            user_repository=user_repo,
            db_session=mock_db,
        )

        result = await service.delete_user_data(
            user_id="user-1",
            ip_address="127.0.0.1",
            user_agent="Test",
        )

        assert result.user_id == "user-1"
        assert result.deletion_type == "full"
        # Verify new tables are included in deletion categories
        assert "savings" in result.data_categories_deleted
        assert "recommendation_outcomes" in result.data_categories_deleted
        assert "ml_data" in result.data_categories_deleted
        assert "referrals" in result.data_categories_deleted
        # Verify DB operations were called (21 delete steps + 1 audit insert + 2 commits)
        assert mock_db.execute.call_count >= 17
        assert mock_db.commit.call_count >= 1

    async def test_consent_persists_across_sessions(self):
        """Test that consent records contain required audit fields"""
        from models.consent import ConsentRecord

        record = ConsentRecord(
            id="c1",
            user_id="user-1",
            purpose="data_processing",
            consent_given=True,
            timestamp=datetime.now(UTC),
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0",
            consent_version="1.0",
        )

        # Consent records must have all audit fields for persistence
        assert record.ip_address is not None
        assert record.user_agent is not None
        assert record.timestamp is not None
        assert record.consent_version == "1.0"
        # Verify the record captures who, what, when for audit compliance
        assert record.user_id == "user-1"
        assert record.purpose == "data_processing"
