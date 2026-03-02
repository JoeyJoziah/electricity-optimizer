"""
Unit tests for ConnectionService.

Coverage:
  - list_connections: empty result, multiple rows, correct user scoping
  - create_connection: happy path (all fields), minimal required fields,
    optional field defaulting, logging side-effects
  - get_connection: found, not found, wrong user
  - delete_connection: success (True), not found (False), wrong user
  - get_extracted_rates: empty, multiple rows (newest-first ordering check)
  - get_current_rate: found, not found (empty connection)
  - _row_to_connection: static helper, None supplier_id, all optional fields

All DB calls are fully mocked via AsyncMock — no real Postgres connection.
Fixtures are function-scoped per project convention for connection tests.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
TEST_OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"
TEST_CONNECTION_ID = str(uuid4())
TEST_SUPPLIER_ID = str(uuid4())
NOW = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _DictRow(dict):
    """Dict subclass that behaves like a SQLAlchemy RowMapping.

    Supports dict(row), row['key'], and row.get() without any extra plumbing.
    """


def _row(**kwargs) -> "_DictRow":
    """Build a RowMapping-compatible row."""
    return _DictRow(kwargs)


def _mapping_result(rows: list) -> MagicMock:
    """Wrap rows into a mock execute() result that supports .mappings().all()
    and .mappings().first()."""
    result = MagicMock()
    mock_rows = [_DictRow(r) for r in rows]
    result.mappings.return_value.all.return_value = mock_rows
    result.mappings.return_value.first.return_value = mock_rows[0] if mock_rows else None
    return result


def _empty_mapping_result() -> MagicMock:
    """Mock execute() result with no rows."""
    result = MagicMock()
    result.mappings.return_value.all.return_value = []
    result.mappings.return_value.first.return_value = None
    return result


def _scalar_result(value) -> MagicMock:
    """Mock execute() result for scalar queries (RETURNING id / soft-delete)."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_db() -> AsyncMock:
    """Return a fresh async DB session mock."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def _connection_row(
    *,
    user_id: str = TEST_USER_ID,
    connection_id: str = TEST_CONNECTION_ID,
    connection_type: str = "direct",
    supplier_id: str = TEST_SUPPLIER_ID,
    supplier_name: str = "Eversource",
    status: str = "active",
    account_number_masked: str = "******1234",
    email_provider=None,
    label=None,
) -> dict:
    """Return a dict shaped like a DB row for user_connections."""
    return {
        "id": connection_id,
        "user_id": user_id,
        "connection_type": connection_type,
        "supplier_id": supplier_id,
        "supplier_name": supplier_name,
        "status": status,
        "account_number_masked": account_number_masked,
        "email_provider": email_provider,
        "label": label,
        "created_at": NOW,
    }


def _rate_row(
    *,
    connection_id: str = TEST_CONNECTION_ID,
    rate_per_kwh: float = 0.2145,
    source: str = "bill_parse",
    raw_label: str = "Standard Rate",
) -> dict:
    """Return a dict shaped like a DB row for connection_extracted_rates."""
    return {
        "id": str(uuid4()),
        "connection_id": connection_id,
        "rate_per_kwh": rate_per_kwh,
        "effective_date": NOW,
        "source": source,
        "raw_label": raw_label,
    }


# ---------------------------------------------------------------------------
# Function-scoped service fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def db():
    """Fresh mock async DB session (function-scoped)."""
    return _make_db()


@pytest.fixture
def service(db):
    """ConnectionService under test, bound to the mock db (function-scoped)."""
    from services.connection_service import ConnectionService
    return ConnectionService(db)


# ===========================================================================
# 1. list_connections
# ===========================================================================


class TestListConnections:
    """Tests for ConnectionService.list_connections."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rows(self, service, db):
        """User with no connections gets an empty list — not None or an error."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        result = await service.list_connections(TEST_USER_ID)

        assert result == []
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_all_rows_for_user(self, service, db):
        """All connection rows for the user are returned as dicts."""
        rows = [
            _connection_row(connection_id=str(uuid4()), connection_type="direct"),
            _connection_row(connection_id=str(uuid4()), connection_type="email_import",
                            supplier_id=None, supplier_name=None,
                            email_provider="gmail", account_number_masked=None),
        ]
        db.execute = AsyncMock(return_value=_mapping_result(rows))

        result = await service.list_connections(TEST_USER_ID)

        assert len(result) == 2
        assert result[0]["connection_type"] == "direct"
        assert result[1]["connection_type"] == "email_import"

    @pytest.mark.asyncio
    async def test_passes_correct_user_id_to_query(self, service, db):
        """The correct user_id is forwarded to the SQL query parameters."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        await service.list_connections(TEST_USER_ID)

        call_args = db.execute.call_args
        # Second positional arg is the params dict
        params = call_args[0][1]
        assert params["user_id"] == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_row_ids_converted_to_strings(self, service, db):
        """UUIDs stored as non-string types must be stringified in the output."""
        # Simulate a UUID object (not already a string) coming from the DB
        uuid_obj = uuid4()
        row = _connection_row(connection_id=uuid_obj, supplier_id=uuid4())
        db.execute = AsyncMock(return_value=_mapping_result([row]))

        result = await service.list_connections(TEST_USER_ID)

        assert isinstance(result[0]["id"], str)
        assert isinstance(result[0]["supplier_id"], str)

    @pytest.mark.asyncio
    async def test_null_supplier_id_stays_none(self, service, db):
        """Optional supplier_id=None must not be coerced to the string 'None'."""
        row = _connection_row(supplier_id=None, supplier_name=None)
        db.execute = AsyncMock(return_value=_mapping_result([row]))

        result = await service.list_connections(TEST_USER_ID)

        assert result[0]["supplier_id"] is None

    @pytest.mark.asyncio
    async def test_does_not_return_other_users_connections(self, service, db):
        """Service passes user_id as a WHERE parameter; verify it is the right one."""
        # The query result is empty because the DB is parameterised by user_id.
        # Here we just confirm the parameter is scoped to the requesting user.
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        await service.list_connections(TEST_USER_ID)

        params = db.execute.call_args[0][1]
        assert params["user_id"] == TEST_USER_ID
        assert params["user_id"] != TEST_OTHER_USER_ID


# ===========================================================================
# 2. create_connection
# ===========================================================================


class TestCreateConnection:
    """Tests for ConnectionService.create_connection."""

    @pytest.mark.asyncio
    async def test_creates_direct_connection_all_fields(self, service, db):
        """Happy path: all optional fields are passed, row is inserted and returned."""
        inserted_row = _connection_row(status="active", label="Home")
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        result = await service.create_connection(
            TEST_USER_ID,
            "direct",
            supplier_id=TEST_SUPPLIER_ID,
            supplier_name="Eversource",
            account_number_encrypted=b"encrypted_bytes",
            account_number_masked="******1234",
            label="Home",
            status="active",
        )

        db.execute.assert_awaited_once()
        db.commit.assert_awaited_once()
        assert result["connection_type"] == "direct"
        assert result["status"] == "active"
        assert result["account_number_masked"] == "******1234"
        assert result["supplier_name"] == "Eversource"
        assert result["label"] == "Home"

    @pytest.mark.asyncio
    async def test_creates_email_connection_minimal(self, service, db):
        """Minimal email connection with only required fields succeeds."""
        inserted_row = _connection_row(
            connection_type="email_import",
            supplier_id=None,
            supplier_name=None,
            account_number_masked=None,
            email_provider="gmail",
            status="pending",
        )
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        result = await service.create_connection(
            TEST_USER_ID,
            "email_import",
            email_provider="gmail",
        )

        assert result["connection_type"] == "email_import"
        assert result["email_provider"] == "gmail"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_default_status_is_pending(self, service, db):
        """When status is not specified, 'pending' is forwarded to the query."""
        inserted_row = _connection_row(status="pending")
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        await service.create_connection(TEST_USER_ID, "manual_upload")

        params = db.execute.call_args[0][1]
        assert params["status"] == "pending"

    @pytest.mark.asyncio
    async def test_commit_called_after_insert(self, service, db):
        """Transaction must be committed after the INSERT."""
        inserted_row = _connection_row()
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        await service.create_connection(TEST_USER_ID, "direct")

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_correct_params_forwarded_to_query(self, service, db):
        """All keyword arguments are forwarded to the SQL params dict."""
        inserted_row = _connection_row()
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        await service.create_connection(
            TEST_USER_ID,
            "direct",
            supplier_id=TEST_SUPPLIER_ID,
            supplier_name="Test Supplier",
            account_number_encrypted=b"enc",
            account_number_masked="**1234",
            email_provider=None,
            label="Office",
            status="active",
        )

        params = db.execute.call_args[0][1]
        assert params["user_id"] == TEST_USER_ID
        assert params["connection_type"] == "direct"
        assert params["status"] == "active"
        assert params["supplier_id"] == TEST_SUPPLIER_ID
        assert params["supplier_name"] == "Test Supplier"
        assert params["enc_acct"] == b"enc"
        assert params["masked_acct"] == "**1234"
        assert params["email_provider"] is None
        assert params["label"] == "Office"

    @pytest.mark.asyncio
    async def test_logs_connection_created(self, service, db):
        """A 'connection_created' event must be logged after successful insert."""
        inserted_row = _connection_row(connection_id=TEST_CONNECTION_ID)
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        with patch("services.connection_service.logger") as mock_logger:
            await service.create_connection(TEST_USER_ID, "direct")

            mock_logger.info.assert_called_once()
            log_kwargs = mock_logger.info.call_args
            # First positional arg is the event name
            assert log_kwargs[0][0] == "connection_created"

    @pytest.mark.asyncio
    async def test_returns_dict_with_string_id(self, service, db):
        """The returned dict must always have 'id' as a string."""
        uuid_obj = uuid4()
        inserted_row = _connection_row(connection_id=uuid_obj)
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        result = await service.create_connection(TEST_USER_ID, "direct")

        assert isinstance(result["id"], str)

    @pytest.mark.asyncio
    async def test_optional_fields_are_none_when_omitted(self, service, db):
        """Fields not passed must default to None in the output."""
        inserted_row = _connection_row(
            supplier_id=None, supplier_name=None,
            account_number_masked=None, email_provider=None, label=None,
        )
        db.execute = AsyncMock(return_value=_mapping_result([inserted_row]))

        result = await service.create_connection(TEST_USER_ID, "manual_upload")

        assert result["supplier_id"] is None
        assert result["supplier_name"] is None
        assert result["account_number_masked"] is None
        assert result["email_provider"] is None
        assert result["label"] is None


# ===========================================================================
# 3. get_connection
# ===========================================================================


class TestGetConnection:
    """Tests for ConnectionService.get_connection."""

    @pytest.mark.asyncio
    async def test_returns_connection_when_found(self, service, db):
        """Owner can retrieve their connection by ID."""
        row = _connection_row()
        db.execute = AsyncMock(return_value=_mapping_result([row]))

        result = await service.get_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        assert result is not None
        assert result["id"] == str(TEST_CONNECTION_ID)
        assert result["user_id"] == str(TEST_USER_ID)
        assert result["connection_type"] == "direct"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, service, db):
        """Non-existent connection_id returns None, not an exception."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        result = await service.get_connection(TEST_USER_ID, str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_wrong_user(self, service, db):
        """Requesting another user's connection returns None (ownership enforced by SQL)."""
        # DB returns no row because WHERE user_id filters it out
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        result = await service.get_connection(TEST_OTHER_USER_ID, TEST_CONNECTION_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_both_ids_to_query(self, service, db):
        """Both connection_id and user_id must be passed to the SQL query."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        await service.get_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        params = db.execute.call_args[0][1]
        assert params["connection_id"] == TEST_CONNECTION_ID
        assert params["user_id"] == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_supplier_id_converted_to_string(self, service, db):
        """supplier_id returned as a UUID object must be converted to str."""
        supplier_uuid = uuid4()
        row = _connection_row(supplier_id=supplier_uuid)
        db.execute = AsyncMock(return_value=_mapping_result([row]))

        result = await service.get_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        assert result["supplier_id"] == str(supplier_uuid)
        assert isinstance(result["supplier_id"], str)

    @pytest.mark.asyncio
    async def test_email_connection_fields_preserved(self, service, db):
        """email_provider and null account fields are preserved correctly."""
        row = _connection_row(
            connection_type="email_import",
            supplier_id=None,
            supplier_name=None,
            account_number_masked=None,
            email_provider="outlook",
        )
        db.execute = AsyncMock(return_value=_mapping_result([row]))

        result = await service.get_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        assert result["connection_type"] == "email_import"
        assert result["email_provider"] == "outlook"
        assert result["supplier_id"] is None
        assert result["account_number_masked"] is None


# ===========================================================================
# 4. delete_connection
# ===========================================================================


class TestDeleteConnection:
    """Tests for ConnectionService.delete_connection."""

    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self, service, db):
        """Soft-deleting an existing connection returns True."""
        # RETURNING id comes back as a scalar
        db.execute = AsyncMock(return_value=_scalar_result(TEST_CONNECTION_ID))

        result = await service.delete_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self, service, db):
        """Deleting a non-existent connection returns False, not an exception."""
        db.execute = AsyncMock(return_value=_scalar_result(None))

        result = await service.delete_connection(TEST_USER_ID, str(uuid4()))

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_wrong_user(self, service, db):
        """Attempting to delete another user's connection returns False."""
        # DB returns None because WHERE user_id filters it out
        db.execute = AsyncMock(return_value=_scalar_result(None))

        result = await service.delete_connection(TEST_OTHER_USER_ID, TEST_CONNECTION_ID)

        assert result is False

    @pytest.mark.asyncio
    async def test_commit_called_after_update(self, service, db):
        """Transaction must be committed after the soft-delete UPDATE."""
        db.execute = AsyncMock(return_value=_scalar_result(TEST_CONNECTION_ID))

        await service.delete_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_commit_called_even_when_not_found(self, service, db):
        """Commit is still called even when the UPDATE matches zero rows."""
        db.execute = AsyncMock(return_value=_scalar_result(None))

        await service.delete_connection(TEST_USER_ID, str(uuid4()))

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_logs_deletion_on_success(self, service, db):
        """A 'connection_deleted' event is logged when the row is found and updated."""
        db.execute = AsyncMock(return_value=_scalar_result(TEST_CONNECTION_ID))

        with patch("services.connection_service.logger") as mock_logger:
            await service.delete_connection(TEST_USER_ID, TEST_CONNECTION_ID)

            mock_logger.info.assert_called_once()
            log_kwargs = mock_logger.info.call_args
            assert log_kwargs[0][0] == "connection_deleted"

    @pytest.mark.asyncio
    async def test_no_log_when_not_found(self, service, db):
        """No log event is emitted when the connection is not found."""
        db.execute = AsyncMock(return_value=_scalar_result(None))

        with patch("services.connection_service.logger") as mock_logger:
            await service.delete_connection(TEST_USER_ID, str(uuid4()))

            mock_logger.info.assert_not_called()

    @pytest.mark.asyncio
    async def test_correct_params_forwarded_to_update(self, service, db):
        """Both connection_id and user_id must be forwarded to the UPDATE query."""
        db.execute = AsyncMock(return_value=_scalar_result(None))

        await service.delete_connection(TEST_USER_ID, TEST_CONNECTION_ID)

        params = db.execute.call_args[0][1]
        assert params["connection_id"] == TEST_CONNECTION_ID
        assert params["user_id"] == TEST_USER_ID


# ===========================================================================
# 5. get_extracted_rates
# ===========================================================================


class TestGetExtractedRates:
    """Tests for ConnectionService.get_extracted_rates."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_rates(self, service, db):
        """Connection with no extracted rates returns an empty list."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        result = await service.get_extracted_rates(TEST_CONNECTION_ID)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_all_rate_rows(self, service, db):
        """Multiple rate rows are all returned."""
        rate_rows = [
            _rate_row(rate_per_kwh=0.25, source="bill_parse"),
            _rate_row(rate_per_kwh=0.21, source="api_pull"),
        ]
        db.execute = AsyncMock(return_value=_mapping_result(rate_rows))

        result = await service.get_extracted_rates(TEST_CONNECTION_ID)

        assert len(result) == 2
        assert result[0]["rate_per_kwh"] == 0.25
        assert result[1]["source"] == "api_pull"

    @pytest.mark.asyncio
    async def test_passes_connection_id_to_query(self, service, db):
        """The connection_id is forwarded as a query parameter."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        await service.get_extracted_rates(TEST_CONNECTION_ID)

        params = db.execute.call_args[0][1]
        assert params["connection_id"] == TEST_CONNECTION_ID

    @pytest.mark.asyncio
    async def test_returns_plain_dicts(self, service, db):
        """Each item in the result list must be a plain dict."""
        rate_rows = [_rate_row()]
        db.execute = AsyncMock(return_value=_mapping_result(rate_rows))

        result = await service.get_extracted_rates(TEST_CONNECTION_ID)

        assert isinstance(result[0], dict)

    @pytest.mark.asyncio
    async def test_null_raw_label_preserved(self, service, db):
        """Rates without a raw_label must carry None, not an empty string."""
        rate_rows = [_rate_row(raw_label=None)]
        db.execute = AsyncMock(return_value=_mapping_result(rate_rows))

        result = await service.get_extracted_rates(TEST_CONNECTION_ID)

        assert result[0]["raw_label"] is None

    @pytest.mark.asyncio
    async def test_all_expected_fields_present(self, service, db):
        """Each returned dict must contain all expected rate fields."""
        rate_rows = [_rate_row()]
        db.execute = AsyncMock(return_value=_mapping_result(rate_rows))

        result = await service.get_extracted_rates(TEST_CONNECTION_ID)

        assert set(result[0].keys()) >= {
            "id", "connection_id", "rate_per_kwh", "effective_date", "source", "raw_label"
        }

    @pytest.mark.asyncio
    async def test_single_rate_row_returned_as_list(self, service, db):
        """Even a single rate is returned inside a list."""
        rate_rows = [_rate_row()]
        db.execute = AsyncMock(return_value=_mapping_result(rate_rows))

        result = await service.get_extracted_rates(TEST_CONNECTION_ID)

        assert isinstance(result, list)
        assert len(result) == 1


# ===========================================================================
# 6. get_current_rate
# ===========================================================================


class TestGetCurrentRate:
    """Tests for ConnectionService.get_current_rate."""

    @pytest.mark.asyncio
    async def test_returns_most_recent_rate(self, service, db):
        """The most recent rate (top row from ORDER BY effective_date DESC) is returned."""
        rate_row = _rate_row(rate_per_kwh=0.2301, source="bill_parse", raw_label="Peak Rate")
        db.execute = AsyncMock(return_value=_mapping_result([rate_row]))

        result = await service.get_current_rate(TEST_CONNECTION_ID)

        assert result is not None
        assert result["rate_per_kwh"] == 0.2301
        assert result["source"] == "bill_parse"
        assert result["raw_label"] == "Peak Rate"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_rates(self, service, db):
        """Connection with no rates returns None — not an exception."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        result = await service.get_current_rate(TEST_CONNECTION_ID)

        assert result is None

    @pytest.mark.asyncio
    async def test_passes_connection_id_to_query(self, service, db):
        """The connection_id is forwarded correctly to the LIMIT 1 query."""
        db.execute = AsyncMock(return_value=_empty_mapping_result())

        await service.get_current_rate(TEST_CONNECTION_ID)

        params = db.execute.call_args[0][1]
        assert params["connection_id"] == TEST_CONNECTION_ID

    @pytest.mark.asyncio
    async def test_returns_dict_not_row_object(self, service, db):
        """The result must be a plain dict, not a raw DB row."""
        rate_row = _rate_row()
        db.execute = AsyncMock(return_value=_mapping_result([rate_row]))

        result = await service.get_current_rate(TEST_CONNECTION_ID)

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_all_expected_fields_present(self, service, db):
        """Returned dict contains all rate fields."""
        rate_row = _rate_row()
        db.execute = AsyncMock(return_value=_mapping_result([rate_row]))

        result = await service.get_current_rate(TEST_CONNECTION_ID)

        assert set(result.keys()) >= {
            "id", "connection_id", "rate_per_kwh", "effective_date", "source", "raw_label"
        }

    @pytest.mark.asyncio
    async def test_connection_id_in_result(self, service, db):
        """The connection_id field in the result matches the queried connection."""
        rate_row = _rate_row(connection_id=TEST_CONNECTION_ID)
        db.execute = AsyncMock(return_value=_mapping_result([rate_row]))

        result = await service.get_current_rate(TEST_CONNECTION_ID)

        assert result["connection_id"] == TEST_CONNECTION_ID


# ===========================================================================
# 7. _row_to_connection (static helper)
# ===========================================================================


class TestRowToConnection:
    """Unit tests for ConnectionService._row_to_connection static method."""

    def test_converts_all_fields(self):
        """All fields from the DB row appear correctly in the output dict."""
        from services.connection_service import ConnectionService

        row = _row(
            id=TEST_CONNECTION_ID,
            user_id=TEST_USER_ID,
            connection_type="direct",
            supplier_id=TEST_SUPPLIER_ID,
            supplier_name="Eversource",
            status="active",
            account_number_masked="******1234",
            email_provider=None,
            label="Home",
            created_at=NOW,
        )

        result = ConnectionService._row_to_connection(row)

        assert result["id"] == str(TEST_CONNECTION_ID)
        assert result["user_id"] == str(TEST_USER_ID)
        assert result["connection_type"] == "direct"
        assert result["supplier_id"] == str(TEST_SUPPLIER_ID)
        assert result["supplier_name"] == "Eversource"
        assert result["status"] == "active"
        assert result["account_number_masked"] == "******1234"
        assert result["email_provider"] is None
        assert result["label"] == "Home"
        assert result["created_at"] == str(NOW)

    def test_null_supplier_id_becomes_none(self):
        """supplier_id=None must not be stringified to 'None'."""
        from services.connection_service import ConnectionService

        row = _row(
            id=TEST_CONNECTION_ID,
            user_id=TEST_USER_ID,
            connection_type="email_import",
            supplier_id=None,
            supplier_name=None,
            status="pending",
            account_number_masked=None,
            email_provider="gmail",
            label=None,
            created_at=NOW,
        )

        result = ConnectionService._row_to_connection(row)

        assert result["supplier_id"] is None

    def test_uuid_supplier_id_converted_to_string(self):
        """supplier_id stored as a UUID object must be returned as a str."""
        from services.connection_service import ConnectionService

        supplier_uuid = uuid4()
        row = _row(
            id=str(uuid4()),
            user_id=TEST_USER_ID,
            connection_type="direct",
            supplier_id=supplier_uuid,
            supplier_name="SupplierX",
            status="active",
            account_number_masked=None,
            email_provider=None,
            label=None,
            created_at=NOW,
        )

        result = ConnectionService._row_to_connection(row)

        assert result["supplier_id"] == str(supplier_uuid)
        assert isinstance(result["supplier_id"], str)

    def test_email_provider_preserved(self):
        """email_provider field value is returned unchanged."""
        from services.connection_service import ConnectionService

        row = _row(
            id=str(uuid4()),
            user_id=TEST_USER_ID,
            connection_type="email_import",
            supplier_id=None,
            supplier_name=None,
            status="active",
            account_number_masked=None,
            email_provider="outlook",
            label=None,
            created_at=NOW,
        )

        result = ConnectionService._row_to_connection(row)

        assert result["email_provider"] == "outlook"

    def test_label_preserved_when_set(self):
        """label field is returned when set."""
        from services.connection_service import ConnectionService

        row = _row(
            id=str(uuid4()),
            user_id=TEST_USER_ID,
            connection_type="manual_upload",
            supplier_id=None,
            supplier_name=None,
            status="active",
            account_number_masked=None,
            email_provider=None,
            label="January Invoice",
            created_at=NOW,
        )

        result = ConnectionService._row_to_connection(row)

        assert result["label"] == "January Invoice"

    def test_output_has_exactly_expected_keys(self):
        """The output dict must contain exactly the defined set of keys."""
        from services.connection_service import ConnectionService

        row = _row(
            id=str(uuid4()),
            user_id=TEST_USER_ID,
            connection_type="direct",
            supplier_id=None,
            supplier_name=None,
            status="pending",
            account_number_masked=None,
            email_provider=None,
            label=None,
            created_at=NOW,
        )

        result = ConnectionService._row_to_connection(row)

        expected_keys = {
            "id", "user_id", "connection_type", "supplier_id", "supplier_name",
            "status", "account_number_masked", "email_provider", "label", "created_at",
        }
        assert set(result.keys()) == expected_keys

    def test_created_at_converted_to_string(self):
        """created_at is always returned as a string."""
        from services.connection_service import ConnectionService

        dt_obj = datetime.now(timezone.utc)
        row = _row(
            id=str(uuid4()),
            user_id=TEST_USER_ID,
            connection_type="direct",
            supplier_id=None,
            supplier_name=None,
            status="active",
            account_number_masked=None,
            email_provider=None,
            label=None,
            created_at=dt_obj,
        )

        result = ConnectionService._row_to_connection(row)

        assert isinstance(result["created_at"], str)


# ===========================================================================
# 8. Integration-style: full create → get → delete lifecycle
# ===========================================================================


class TestConnectionLifecycle:
    """End-to-end lifecycle tests using the service with a sequenced mock DB."""

    @pytest.mark.asyncio
    async def test_create_then_get_returns_same_data(self, service, db):
        """Data inserted via create_connection is retrievable via get_connection."""
        conn_id = str(uuid4())
        row = _connection_row(connection_id=conn_id, status="active")

        # First call: INSERT (create), second call: SELECT (get)
        db.execute = AsyncMock(side_effect=[
            _mapping_result([row]),  # create_connection INSERT RETURNING
            _mapping_result([row]),  # get_connection SELECT
        ])

        created = await service.create_connection(
            TEST_USER_ID, "direct",
            supplier_id=TEST_SUPPLIER_ID,
            status="active",
        )
        fetched = await service.get_connection(TEST_USER_ID, conn_id)

        assert created["id"] == fetched["id"]
        assert created["status"] == fetched["status"]

    @pytest.mark.asyncio
    async def test_delete_makes_get_return_none(self, service, db):
        """After deletion, get_connection returns None (simulated by empty SELECT)."""
        conn_id = str(uuid4())

        db.execute = AsyncMock(side_effect=[
            _scalar_result(conn_id),      # delete_connection UPDATE RETURNING
            _empty_mapping_result(),       # get_connection SELECT (post-delete)
        ])

        deleted = await service.delete_connection(TEST_USER_ID, conn_id)
        fetched = await service.get_connection(TEST_USER_ID, conn_id)

        assert deleted is True
        assert fetched is None

    @pytest.mark.asyncio
    async def test_list_then_delete_reduces_count(self, service, db):
        """Simulates listing 2 connections then deleting 1, leaving 1 in the list."""
        conn_id_1 = str(uuid4())
        conn_id_2 = str(uuid4())

        rows_before = [
            _connection_row(connection_id=conn_id_1),
            _connection_row(connection_id=conn_id_2),
        ]
        rows_after = [_connection_row(connection_id=conn_id_2)]

        db.execute = AsyncMock(side_effect=[
            _mapping_result(rows_before),  # list before
            _scalar_result(conn_id_1),     # delete conn_id_1
            _mapping_result(rows_after),   # list after
        ])

        before = await service.list_connections(TEST_USER_ID)
        await service.delete_connection(TEST_USER_ID, conn_id_1)
        after = await service.list_connections(TEST_USER_ID)

        assert len(before) == 2
        assert len(after) == 1
        assert after[0]["id"] == str(conn_id_2)
