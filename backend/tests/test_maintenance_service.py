"""
Tests for MaintenanceService

Covers all public methods:
- cleanup_activity_logs: deletion count, retention period, commit, zero-row case
- cleanup_expired_uploads: FK cascade delete, file removal, zero-row case,
  missing file handling, OSError suppression
"""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# =============================================================================
# HELPERS
# =============================================================================


def _make_result(rowcount=0, fetchall_value=None):
    """Build a mock SQLAlchemy result proxy."""
    result = MagicMock()
    result.rowcount = rowcount
    result.fetchall.return_value = fetchall_value if fetchall_value is not None else []
    return result


def _upload_row(upload_id, file_path):
    """Create a 2-element mock row simulating (id, file_path)."""
    row = MagicMock()
    row.__getitem__ = lambda self, i: (upload_id, file_path)[i]
    # Also support positional tuple-style access used in the service
    return (upload_id, file_path)


# =============================================================================
# TestCleanupActivityLogs
# =============================================================================


class TestCleanupActivityLogs:
    """Tests for MaintenanceService.cleanup_activity_logs"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.maintenance_service import MaintenanceService
        return MaintenanceService(db)

    @pytest.mark.asyncio
    async def test_returns_deleted_count_and_retention_days(self, service, db):
        """Should return the number of deleted rows and the retention period used."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=42))

        result = await service.cleanup_activity_logs(retention_days=365)

        assert result["deleted"] == 42
        assert result["retention_days"] == 365

    @pytest.mark.asyncio
    async def test_default_retention_is_365_days(self, service, db):
        """Default retention period should be 365 days."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=0))

        result = await service.cleanup_activity_logs()

        assert result["retention_days"] == 365

    @pytest.mark.asyncio
    async def test_commit_is_called(self, service, db):
        """Should call commit after the DELETE."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=5))

        await service.cleanup_activity_logs()

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_zero_rows_deleted(self, service, db):
        """Should return deleted=0 when no logs are older than the cutoff."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=0))

        result = await service.cleanup_activity_logs(retention_days=30)

        assert result["deleted"] == 0
        assert result["retention_days"] == 30

    @pytest.mark.asyncio
    async def test_execute_called_once(self, service, db):
        """Should issue exactly one DELETE query."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=10))

        await service.cleanup_activity_logs()

        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cutoff_passed_to_query(self, service, db):
        """The DELETE query must receive a :cutoff parameter."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=3))

        from datetime import timezone
        before = datetime.now(timezone.utc) - timedelta(days=365)
        await service.cleanup_activity_logs(retention_days=365)
        after = datetime.now(timezone.utc) - timedelta(days=365)

        call_args = db.execute.call_args
        params = call_args[0][1]
        assert "cutoff" in params
        # Cutoff should be within a few seconds of expected value
        assert before <= params["cutoff"] <= after + timedelta(seconds=2)

    @pytest.mark.asyncio
    async def test_custom_retention_period(self, service, db):
        """Should respect a custom retention_days argument."""
        db.execute = AsyncMock(return_value=_make_result(rowcount=100))

        result = await service.cleanup_activity_logs(retention_days=90)

        assert result["retention_days"] == 90
        assert result["deleted"] == 100


# =============================================================================
# TestCleanupExpiredUploads
# =============================================================================


class TestCleanupExpiredUploads:
    """Tests for MaintenanceService.cleanup_expired_uploads"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        from services.maintenance_service import MaintenanceService
        return MaintenanceService(db)

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_old_uploads(self, service, db):
        """Should return deleted=0 when no uploads are older than the cutoff."""
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=[]))

        result = await service.cleanup_expired_uploads(retention_days=730)

        assert result["deleted"] == 0
        assert result["retention_days"] == 730
        # No DELETE queries should be issued
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_retention_is_730_days(self, service, db):
        """Default retention period should be 730 days."""
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=[]))

        result = await service.cleanup_expired_uploads()

        assert result["retention_days"] == 730

    @pytest.mark.asyncio
    async def test_returns_correct_deleted_count(self, service, db):
        """Should return count equal to number of upload rows found."""
        rows = [
            ("id-1", "/uploads/bill1.pdf"),
            ("id-2", "/uploads/bill2.pdf"),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.cleanup_expired_uploads()

        assert result["deleted"] == 2

    @pytest.mark.asyncio
    async def test_deletes_extracted_rates_before_uploads(self, service, db):
        """Should DELETE from connection_extracted_rates before bill_uploads (FK order)."""
        rows = [("upload-uuid-1", None)]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        await service.cleanup_expired_uploads()

        calls = db.execute.call_args_list
        # 1st call: SELECT, 2nd call: DELETE extracted_rates, 3rd call: DELETE bill_uploads
        assert db.execute.await_count == 3
        second_sql = str(calls[1][0][0])
        assert "connection_extracted_rates" in second_sql
        third_sql = str(calls[2][0][0])
        assert "bill_uploads" in third_sql

    @pytest.mark.asyncio
    async def test_commit_called_after_deletes(self, service, db):
        """Should commit once after all DELETE operations."""
        rows = [("id-1", None)]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        await service.cleanup_expired_uploads()

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_removes_existing_files(self, service, db, tmp_path):
        """Should delete files on disk that exist at the stored path."""
        tmp_file = tmp_path / "bill.pdf"
        tmp_file.write_bytes(b"fake pdf content")

        rows = [("id-1", str(tmp_file))]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        await service.cleanup_expired_uploads()

        assert not tmp_file.exists()

    @pytest.mark.asyncio
    async def test_skips_nonexistent_files(self, service, db):
        """Should not raise when file_path does not exist on disk."""
        rows = [("id-1", "/nonexistent/path/bill.pdf")]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        # Should not raise
        result = await service.cleanup_expired_uploads()

        assert result["deleted"] == 1

    @pytest.mark.asyncio
    async def test_skips_none_file_paths(self, service, db):
        """Should not attempt to delete files when file_path is None."""
        rows = [("id-1", None), ("id-2", None)]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        result = await service.cleanup_expired_uploads()

        assert result["deleted"] == 2

    @pytest.mark.asyncio
    async def test_oserror_suppressed_on_file_removal(self, service, db, tmp_path):
        """OSError during file removal should be swallowed (best-effort cleanup)."""
        tmp_file = tmp_path / "bill.pdf"
        tmp_file.write_bytes(b"content")

        rows = [("id-1", str(tmp_file))]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        with patch("os.remove", side_effect=OSError("permission denied")):
            # Should not propagate the OSError
            result = await service.cleanup_expired_uploads()

        assert result["deleted"] == 1

    @pytest.mark.asyncio
    async def test_multiple_uploads_upload_ids_in_fk_delete(self, service, db):
        """All upload IDs must appear in the FK DELETE query params."""
        rows = [
            ("aaaa-1111", "/uploads/a.pdf"),
            ("bbbb-2222", "/uploads/b.pdf"),
            ("cccc-3333", None),
        ]
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=rows))

        await service.cleanup_expired_uploads()

        calls = db.execute.call_args_list
        fk_delete_sql = str(calls[1][0][0])
        assert "connection_extracted_rates" in fk_delete_sql
        assert "ANY(:ids)" in fk_delete_sql
        # IDs are now in the parameterized query params, not inlined in SQL
        fk_delete_params = calls[1][0][1]
        assert "aaaa-1111" in fk_delete_params["ids"]
        assert "bbbb-2222" in fk_delete_params["ids"]
        assert "cccc-3333" in fk_delete_params["ids"]

    @pytest.mark.asyncio
    async def test_cutoff_passed_to_select_query(self, service, db):
        """The SELECT query must receive a :cutoff parameter."""
        db.execute = AsyncMock(return_value=_make_result(fetchall_value=[]))

        from datetime import timezone
        before = datetime.now(timezone.utc) - timedelta(days=730)
        await service.cleanup_expired_uploads(retention_days=730)
        after = datetime.now(timezone.utc) - timedelta(days=730)

        select_call = db.execute.call_args_list[0]
        params = select_call[0][1]
        assert "cutoff" in params
        assert before <= params["cutoff"] <= after + timedelta(seconds=2)


# =============================================================================
# TestMaintenanceEndpoint (integration via TestClient)
# =============================================================================


class TestMaintenanceEndpoint:
    """Integration tests for POST /api/v1/internal/maintenance/cleanup."""

    @pytest.fixture
    def mock_db(self):
        return AsyncMock()

    @pytest.fixture
    def auth_client(self, mock_db):
        from main import app
        from api.dependencies import get_db_session, verify_api_key

        app.dependency_overrides[verify_api_key] = lambda: True
        app.dependency_overrides[get_db_session] = lambda: mock_db

        from fastapi.testclient import TestClient
        client = TestClient(app)
        yield client

        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides.pop(get_db_session, None)

    @pytest.fixture
    def unauth_client(self, mock_db):
        from main import app
        from api.dependencies import get_db_session, verify_api_key

        app.dependency_overrides.pop(verify_api_key, None)
        app.dependency_overrides[get_db_session] = lambda: mock_db

        from fastapi.testclient import TestClient
        client = TestClient(app)
        yield client

        app.dependency_overrides.pop(get_db_session, None)

    @patch("services.maintenance_service.MaintenanceService")
    def test_maintenance_happy_path(self, mock_svc_cls, auth_client):
        """Should call both cleanup methods and return their results."""
        mock_svc = MagicMock()
        mock_svc.cleanup_activity_logs = AsyncMock(
            return_value={"deleted": 10, "retention_days": 365}
        )
        mock_svc.cleanup_expired_uploads = AsyncMock(
            return_value={"deleted": 3, "retention_days": 730}
        )
        mock_svc_cls.return_value = mock_svc

        from fastapi.testclient import TestClient
        response = auth_client.post("/api/v1/internal/maintenance/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["activity_logs"]["deleted"] == 10
        assert data["activity_logs"]["retention_days"] == 365
        assert data["uploads"]["deleted"] == 3
        assert data["uploads"]["retention_days"] == 730

    @patch("services.maintenance_service.MaintenanceService")
    def test_maintenance_zero_deletions(self, mock_svc_cls, auth_client):
        """Should return zero counts when nothing is old enough to clean up."""
        mock_svc = MagicMock()
        mock_svc.cleanup_activity_logs = AsyncMock(
            return_value={"deleted": 0, "retention_days": 365}
        )
        mock_svc.cleanup_expired_uploads = AsyncMock(
            return_value={"deleted": 0, "retention_days": 730}
        )
        mock_svc_cls.return_value = mock_svc

        response = auth_client.post("/api/v1/internal/maintenance/cleanup")

        assert response.status_code == 200
        data = response.json()
        assert data["activity_logs"]["deleted"] == 0
        assert data["uploads"]["deleted"] == 0

    def test_maintenance_requires_api_key(self, unauth_client):
        """Request without X-API-Key header should be rejected with 401."""
        response = unauth_client.post("/api/v1/internal/maintenance/cleanup")

        assert response.status_code == 401
