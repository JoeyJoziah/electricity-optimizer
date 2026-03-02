"""
Unit tests for SavingsService (backend/services/savings_service.py).

Coverage:
  - get_savings_summary: no data (all zeros), with data, region filter,
    currency fallback, streak skipped on zero total
  - get_savings_history: empty user, with records, pagination clamping,
    page/offset math, pages ceiling calculation
  - record_savings: happy path, all optional params, commit called,
    UUID generation, _row_to_record serialisation
  - _row_to_record: datetime/None serialisation, float coercion
  - _compute_streak: no rows, today missing, consecutive run,
    broken streak, gap at start, date vs datetime objects

All DB calls are mocked via AsyncMock — no real Postgres connection required.
Run with:
    .venv/bin/python -m pytest backend/tests/test_savings_service.py
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.savings_service import SavingsService


# =============================================================================
# HELPERS
# =============================================================================


def _make_mapping_first(row: dict) -> MagicMock:
    """Return a mock execute() result whose .mappings().first() returns *row*."""
    result = MagicMock()
    mapping = MagicMock()
    mapping.first.return_value = row
    result.mappings.return_value = mapping
    return result


def _make_mapping_all(rows: list) -> MagicMock:
    """Return a mock execute() result whose .mappings().all() returns *rows*."""
    result = MagicMock()
    mapping = MagicMock()
    mapping.all.return_value = rows
    result.mappings.return_value = mapping
    return result


def _make_scalar(value) -> MagicMock:
    """Return a mock execute() result whose .scalar() returns *value*."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


def _make_fetchall(rows: list) -> MagicMock:
    """Return a mock execute() result whose .fetchall() returns *rows*."""
    result = MagicMock()
    result.fetchall.return_value = rows
    return result


def _make_agg_row(
    total=0,
    weekly=0,
    monthly=0,
    currency="USD",
) -> dict:
    """Build an aggregate row dict matching the SavingsService agg query."""
    return {
        "total": Decimal(str(total)),
        "weekly": Decimal(str(weekly)),
        "monthly": Decimal(str(monthly)),
        "currency": currency,
    }


def _now():
    return datetime.now(tz=timezone.utc)


def _make_savings_row(
    user_id: str = "user-123",
    amount: float = 10.0,
    savings_type: str = "switching",
    currency: str = "USD",
    region: str = "US_CT",
    description: str = "Test saving",
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    created_at: datetime | None = None,
    row_id: str | None = None,
) -> dict:
    """Build a full savings row dict matching the shape returned by Postgres RETURNING."""
    now = _now()
    return {
        "id": row_id or str(uuid.uuid4()),
        "user_id": user_id,
        "savings_type": savings_type,
        "amount": Decimal(str(amount)),
        "currency": currency,
        "description": description,
        "region": region,
        "period_start": period_start or (now - timedelta(days=30)),
        "period_end": period_end or now,
        "created_at": created_at or now,
    }


# =============================================================================
# TestGetSavingsSummary
# =============================================================================


class TestGetSavingsSummary:
    """Tests for SavingsService.get_savings_summary"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        return SavingsService(db)

    @pytest.mark.asyncio
    async def test_no_records_returns_all_zeros(self, service, db):
        """A user with no savings records should get all-zero totals and streak 0."""
        agg_row = _make_agg_row(total=0, weekly=0, monthly=0, currency="USD")
        db.execute = AsyncMock(return_value=_make_mapping_first(agg_row))

        result = await service.get_savings_summary(user_id="user-new")

        assert result["total"] == 0.0
        assert result["weekly"] == 0.0
        assert result["monthly"] == 0.0
        assert result["streak_days"] == 0
        assert result["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_no_records_skips_streak_query(self, service, db):
        """When total is 0 the streak SQL should never be executed."""
        agg_row = _make_agg_row(total=0)
        db.execute = AsyncMock(return_value=_make_mapping_first(agg_row))

        await service.get_savings_summary(user_id="user-new")

        # Only the aggregate query should be issued
        assert db.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_with_data_returns_correct_totals(self, service, db):
        """User with savings should receive correct aggregated float values."""
        agg_row = _make_agg_row(total=35.0, weekly=15.0, monthly=35.0, currency="USD")
        agg_result = _make_mapping_first(agg_row)

        # Streak: 2 consecutive days ending today
        today = _now().date()
        streak_result = _make_fetchall([(today,), (today - timedelta(days=1),)])

        db.execute = AsyncMock(side_effect=[agg_result, streak_result])

        result = await service.get_savings_summary(user_id="user-a")

        assert result["total"] == pytest.approx(35.0)
        assert result["weekly"] == pytest.approx(15.0)
        assert result["monthly"] == pytest.approx(35.0)
        assert result["streak_days"] == 2
        assert result["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_region_filter_passed_to_db(self, service, db):
        """When region is provided it should be forwarded to both SQL calls."""
        agg_row = _make_agg_row(total=10.0)
        agg_result = _make_mapping_first(agg_row)
        streak_result = _make_fetchall([])

        db.execute = AsyncMock(side_effect=[agg_result, streak_result])

        await service.get_savings_summary(user_id="user-b", region="US_CT")

        # Both calls should carry the region param
        for call in db.execute.call_args_list:
            params = call[0][1]
            assert params.get("region") == "US_CT"

    @pytest.mark.asyncio
    async def test_no_region_filter_omits_region_param(self, service, db):
        """Without region, the SQL params should NOT include a 'region' key."""
        agg_row = _make_agg_row(total=5.0)
        agg_result = _make_mapping_first(agg_row)
        streak_result = _make_fetchall([])

        db.execute = AsyncMock(side_effect=[agg_result, streak_result])

        await service.get_savings_summary(user_id="user-c")

        first_params = db.execute.call_args_list[0][0][1]
        assert "region" not in first_params

    @pytest.mark.asyncio
    async def test_currency_null_defaults_to_usd(self, service, db):
        """When the DB returns NULL for currency, it should default to 'USD'."""
        agg_row = _make_agg_row(total=0, currency=None)
        db.execute = AsyncMock(return_value=_make_mapping_first(agg_row))

        result = await service.get_savings_summary(user_id="user-d")

        assert result["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_currency_empty_string_defaults_to_usd(self, service, db):
        """When the DB returns an empty string for currency, it should be 'USD'."""
        agg_row = _make_agg_row(total=0, currency="")
        db.execute = AsyncMock(return_value=_make_mapping_first(agg_row))

        result = await service.get_savings_summary(user_id="user-e")

        assert result["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_currency_gbp_preserved(self, service, db):
        """Non-USD currency codes returned from the DB should be preserved."""
        agg_row = _make_agg_row(total=0, currency="GBP")
        db.execute = AsyncMock(return_value=_make_mapping_first(agg_row))

        result = await service.get_savings_summary(user_id="user-f")

        assert result["currency"] == "GBP"

    @pytest.mark.asyncio
    async def test_agg_row_none_returns_zeros(self, service, db):
        """When the aggregate query returns no row at all, everything is 0."""
        result_mock = _make_mapping_first(None)
        db.execute = AsyncMock(return_value=result_mock)

        result = await service.get_savings_summary(user_id="user-g")

        assert result["total"] == 0.0
        assert result["weekly"] == 0.0
        assert result["monthly"] == 0.0
        assert result["streak_days"] == 0

    @pytest.mark.asyncio
    async def test_two_queries_issued_when_data_exists(self, service, db):
        """When total > 0, exactly two queries should be issued (agg + streak)."""
        agg_row = _make_agg_row(total=1.0)
        agg_result = _make_mapping_first(agg_row)
        streak_result = _make_fetchall([])

        db.execute = AsyncMock(side_effect=[agg_result, streak_result])

        await service.get_savings_summary(user_id="user-h")

        assert db.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_streak_zero_when_today_missing(self, service, db):
        """If the most recent record is from yesterday (not today), streak = 0."""
        agg_row = _make_agg_row(total=50.0)
        agg_result = _make_mapping_first(agg_row)

        yesterday = _now().date() - timedelta(days=1)
        streak_result = _make_fetchall([(yesterday,)])

        db.execute = AsyncMock(side_effect=[agg_result, streak_result])

        result = await service.get_savings_summary(user_id="user-i")

        assert result["streak_days"] == 0

    @pytest.mark.asyncio
    async def test_streak_five_consecutive_days(self, service, db):
        """Five consecutive days ending today should produce streak_days = 5."""
        agg_row = _make_agg_row(total=100.0)
        agg_result = _make_mapping_first(agg_row)

        today = _now().date()
        days = [(today - timedelta(days=i),) for i in range(5)]
        streak_result = _make_fetchall(days)

        db.execute = AsyncMock(side_effect=[agg_result, streak_result])

        result = await service.get_savings_summary(user_id="user-j")

        assert result["streak_days"] == 5


# =============================================================================
# TestGetSavingsHistory
# =============================================================================


class TestGetSavingsHistory:
    """Tests for SavingsService.get_savings_history"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        return SavingsService(db)

    @pytest.mark.asyncio
    async def test_empty_user_returns_empty_items(self, service, db):
        """A user with no records should get an empty items list."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(0),         # COUNT
                _make_mapping_all([]),   # paginated rows
            ]
        )

        result = await service.get_savings_history(user_id="user-new")

        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["page_size"] == 20
        assert result["pages"] == 1  # at least 1 even when empty

    @pytest.mark.asyncio
    async def test_returns_items_with_correct_shape(self, service, db):
        """Items should be serialised dicts with all expected keys."""
        row = _make_savings_row(user_id="user-x", amount=12.50)
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(1),
                _make_mapping_all([row]),
            ]
        )

        result = await service.get_savings_history(user_id="user-x")

        assert len(result["items"]) == 1
        item = result["items"][0]
        assert "id" in item
        assert "user_id" in item
        assert "savings_type" in item
        assert "amount" in item
        assert "currency" in item
        assert "description" in item
        assert "region" in item
        assert "period_start" in item
        assert "period_end" in item
        assert "created_at" in item
        assert item["amount"] == pytest.approx(12.50)

    @pytest.mark.asyncio
    async def test_pagination_defaults_to_page_1_size_20(self, service, db):
        """Default call should use page=1, page_size=20 in the query params."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(0),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-1")

        assert result["page"] == 1
        assert result["page_size"] == 20

        # Verify offset=0 and limit=20 were passed to the paginated query
        paginated_call = db.execute.call_args_list[1]
        params = paginated_call[0][1]
        assert params["limit"] == 20
        assert params["offset"] == 0

    @pytest.mark.asyncio
    async def test_page_2_calculates_correct_offset(self, service, db):
        """Page 2 with page_size=10 should produce offset=10."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(25),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-2", page=2, page_size=10)

        assert result["page"] == 2
        assert result["page_size"] == 10

        paginated_call = db.execute.call_args_list[1]
        params = paginated_call[0][1]
        assert params["limit"] == 10
        assert params["offset"] == 10

    @pytest.mark.asyncio
    async def test_pages_ceiling_calculated_correctly(self, service, db):
        """ceil(25 / 10) = 3 total pages."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(25),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-3", page_size=10)

        assert result["total"] == 25
        assert result["pages"] == 3

    @pytest.mark.asyncio
    async def test_pages_exact_divisor(self, service, db):
        """20 records / 10 per page = exactly 2 pages."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(20),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-4", page_size=10)

        assert result["pages"] == 2

    @pytest.mark.asyncio
    async def test_page_below_1_clamped_to_1(self, service, db):
        """page=0 (or negative) should be clamped to page=1."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(0),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-5", page=0)

        assert result["page"] == 1

    @pytest.mark.asyncio
    async def test_page_size_below_1_clamped_to_1(self, service, db):
        """page_size=0 should be clamped to 1."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(0),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-6", page_size=0)

        assert result["page_size"] == 1

    @pytest.mark.asyncio
    async def test_page_size_above_100_clamped_to_100(self, service, db):
        """page_size=9999 should be clamped to 100."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(0),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-7", page_size=9999)

        assert result["page_size"] == 100

    @pytest.mark.asyncio
    async def test_scalar_none_treated_as_zero_total(self, service, db):
        """COUNT returning None should be treated as total=0."""
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(None),
                _make_mapping_all([]),
            ]
        )

        result = await service.get_savings_history(user_id="user-8")

        assert result["total"] == 0
        assert result["pages"] == 1

    @pytest.mark.asyncio
    async def test_multiple_items_serialised(self, service, db):
        """Multiple rows should all appear as serialised dicts."""
        rows = [_make_savings_row(user_id="u", amount=float(i)) for i in range(5)]
        db.execute = AsyncMock(
            side_effect=[
                _make_scalar(5),
                _make_mapping_all(rows),
            ]
        )

        result = await service.get_savings_history(user_id="u")

        assert len(result["items"]) == 5
        amounts = {item["amount"] for item in result["items"]}
        assert amounts == {0.0, 1.0, 2.0, 3.0, 4.0}


# =============================================================================
# TestRecordSavings
# =============================================================================


class TestRecordSavings:
    """Tests for SavingsService.record_savings"""

    @pytest.fixture
    def db(self):
        db = AsyncMock()
        db.commit = AsyncMock()
        return db

    @pytest.fixture
    def service(self, db):
        return SavingsService(db)

    @pytest.mark.asyncio
    async def test_happy_path_returns_record_dict(self, service, db):
        """Successful insert should return a complete record dict."""
        now = _now()
        returned_row = _make_savings_row(
            user_id="user-r1",
            amount=25.00,
            savings_type="switching",
            currency="USD",
            region="US_CT",
            created_at=now,
        )
        db.execute = AsyncMock(return_value=_make_mapping_first(returned_row))

        result = await service.record_savings(
            user_id="user-r1",
            savings_type="switching",
            amount=25.00,
            period_start=now - timedelta(days=30),
            period_end=now,
            region="US_CT",
        )

        assert result["user_id"] == "user-r1"
        assert result["savings_type"] == "switching"
        assert result["amount"] == pytest.approx(25.00)
        assert result["currency"] == "USD"
        assert result["region"] == "US_CT"

    @pytest.mark.asyncio
    async def test_commit_called_after_insert(self, service, db):
        """The DB session should be committed exactly once after the INSERT."""
        now = _now()
        db.execute = AsyncMock(return_value=_make_mapping_first(_make_savings_row()))

        await service.record_savings(
            user_id="user-r2",
            savings_type="usage",
            amount=5.0,
            period_start=now - timedelta(days=7),
            period_end=now,
        )

        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uuid_id_passed_to_insert(self, service, db):
        """A freshly generated UUID should be sent as the :id parameter."""
        now = _now()
        captured_params = {}

        async def capture_execute(stmt, params=None):
            captured_params.update(params or {})
            return _make_mapping_first(_make_savings_row())

        db.execute = capture_execute

        await service.record_savings(
            user_id="user-r3",
            savings_type="alert",
            amount=3.0,
            period_start=now - timedelta(days=1),
            period_end=now,
        )

        assert "id" in captured_params
        parsed = uuid.UUID(captured_params["id"])
        assert str(parsed) == captured_params["id"]

    @pytest.mark.asyncio
    async def test_optional_params_passed_correctly(self, service, db):
        """Optional region, description, and currency should be forwarded to the query."""
        now = _now()
        captured_params = {}

        async def capture_execute(stmt, params=None):
            captured_params.update(params or {})
            return _make_mapping_first(_make_savings_row())

        db.execute = capture_execute

        await service.record_savings(
            user_id="user-r4",
            savings_type="switching",
            amount=100.0,
            period_start=now - timedelta(days=30),
            period_end=now,
            region="US_MA",
            description="Switched to cheaper supplier",
            currency="GBP",
        )

        assert captured_params["region"] == "US_MA"
        assert captured_params["description"] == "Switched to cheaper supplier"
        assert captured_params["currency"] == "GBP"

    @pytest.mark.asyncio
    async def test_optional_params_default_to_none_and_usd(self, service, db):
        """Omitting optional params should use None for region/description and USD for currency."""
        now = _now()
        captured_params = {}

        async def capture_execute(stmt, params=None):
            captured_params.update(params or {})
            return _make_mapping_first(_make_savings_row())

        db.execute = capture_execute

        await service.record_savings(
            user_id="user-r5",
            savings_type="usage",
            amount=7.0,
            period_start=now - timedelta(days=7),
            period_end=now,
        )

        assert captured_params["region"] is None
        assert captured_params["description"] is None
        assert captured_params["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_period_datetimes_forwarded_to_insert(self, service, db):
        """period_start and period_end should be passed verbatim to the INSERT."""
        now = _now()
        start = now - timedelta(days=14)
        end = now
        captured_params = {}

        async def capture_execute(stmt, params=None):
            captured_params.update(params or {})
            return _make_mapping_first(_make_savings_row())

        db.execute = capture_execute

        await service.record_savings(
            user_id="user-r6",
            savings_type="switching",
            amount=8.0,
            period_start=start,
            period_end=end,
        )

        assert captured_params["period_start"] == start
        assert captured_params["period_end"] == end

    @pytest.mark.asyncio
    async def test_zero_amount_records_and_returns(self, service, db):
        """Zero-dollar savings should be accepted and returned as 0.0."""
        now = _now()
        row = _make_savings_row(amount=0.0)
        db.execute = AsyncMock(return_value=_make_mapping_first(row))

        result = await service.record_savings(
            user_id="user-r7",
            savings_type="usage",
            amount=0.0,
            period_start=now - timedelta(days=1),
            period_end=now,
        )

        assert result["amount"] == 0.0

    @pytest.mark.asyncio
    async def test_unique_ids_across_two_calls(self, service, db):
        """Two consecutive record_savings calls should generate distinct UUIDs."""
        now = _now()
        ids_seen = []

        async def capture_execute(stmt, params=None):
            ids_seen.append((params or {}).get("id"))
            return _make_mapping_first(_make_savings_row())

        db.execute = capture_execute

        for _ in range(2):
            await service.record_savings(
                user_id="user-r8",
                savings_type="switching",
                amount=5.0,
                period_start=now - timedelta(days=7),
                period_end=now,
            )

        assert len(ids_seen) == 2
        assert ids_seen[0] != ids_seen[1]

    @pytest.mark.asyncio
    async def test_savings_types_all_accepted(self, service, db):
        """All documented savings_type values should be forwarded without error."""
        now = _now()
        for savings_type in ("switching", "usage", "alert"):
            captured = {}

            async def capture_execute(stmt, params=None, _t=savings_type):
                captured.update(params or {})
                return _make_mapping_first(_make_savings_row(savings_type=_t))

            db.execute = capture_execute

            result = await service.record_savings(
                user_id="user-r9",
                savings_type=savings_type,
                amount=1.0,
                period_start=now - timedelta(days=1),
                period_end=now,
            )

            assert result["savings_type"] == savings_type


# =============================================================================
# TestRowToRecord
# =============================================================================


class TestRowToRecord:
    """Unit tests for SavingsService._row_to_record (static helper)."""

    def test_all_fields_serialised(self):
        """A fully-populated row should produce a dict with all expected keys."""
        now = _now()
        row = _make_savings_row(
            user_id="user-s1",
            amount=42.50,
            savings_type="switching",
            currency="USD",
            region="US_CT",
            description="Monthly saving",
            period_start=now - timedelta(days=30),
            period_end=now,
            created_at=now,
        )

        record = SavingsService._row_to_record(row)

        assert isinstance(record["id"], str)
        assert record["user_id"] == "user-s1"
        assert record["savings_type"] == "switching"
        assert record["amount"] == pytest.approx(42.50)
        assert record["currency"] == "USD"
        assert record["region"] == "US_CT"
        assert record["description"] == "Monthly saving"
        assert isinstance(record["period_start"], str)
        assert isinstance(record["period_end"], str)
        assert isinstance(record["created_at"], str)

    def test_amount_is_float(self):
        """amount should always be returned as float, not Decimal."""
        row = _make_savings_row(amount=10.0)
        record = SavingsService._row_to_record(row)
        assert isinstance(record["amount"], float)

    def test_none_period_start_serialised_as_none(self):
        """None period_start should become None in the output dict (not a string)."""
        row = _make_savings_row(period_start=None)
        row["period_start"] = None
        record = SavingsService._row_to_record(row)
        assert record["period_start"] is None

    def test_none_period_end_serialised_as_none(self):
        """None period_end should become None in the output dict."""
        row = _make_savings_row(period_end=None)
        row["period_end"] = None
        record = SavingsService._row_to_record(row)
        assert record["period_end"] is None

    def test_none_created_at_serialised_as_none(self):
        """None created_at should become None in the output dict."""
        row = _make_savings_row()
        row["created_at"] = None
        record = SavingsService._row_to_record(row)
        assert record["created_at"] is None

    def test_datetime_fields_isoformat(self):
        """Datetime fields should be serialised with .isoformat()."""
        dt = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        row = _make_savings_row(period_start=dt, period_end=dt, created_at=dt)
        record = SavingsService._row_to_record(row)

        assert record["period_start"] == dt.isoformat()
        assert record["period_end"] == dt.isoformat()
        assert record["created_at"] == dt.isoformat()

    def test_none_description_preserved(self):
        """None description should be passed through as None."""
        row = _make_savings_row()
        row["description"] = None
        record = SavingsService._row_to_record(row)
        assert record["description"] is None

    def test_none_region_preserved(self):
        """None region should be passed through as None."""
        row = _make_savings_row()
        row["region"] = None
        record = SavingsService._row_to_record(row)
        assert record["region"] is None

    def test_id_and_user_id_cast_to_str(self):
        """id and user_id should be cast to str even if stored as UUID objects."""
        row = _make_savings_row()
        uid = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        row["id"] = uid
        row["user_id"] = uid
        record = SavingsService._row_to_record(row)
        assert record["id"] == str(uid)
        assert record["user_id"] == str(uid)


# =============================================================================
# TestComputeStreak
# =============================================================================


class TestComputeStreak:
    """Unit tests for SavingsService._compute_streak (static helper)."""

    def _today(self) -> date:
        return datetime.now(tz=timezone.utc).date()

    def _day(self, days_ago: int) -> date:
        return self._today() - timedelta(days=days_ago)

    def _rows(self, *days_ago: int) -> list:
        """Build fetchall-style tuples (most-recent first) from days_ago offsets."""
        return [(self._day(d),) for d in sorted(days_ago)]

    def test_empty_rows_returns_zero(self):
        """No DB rows should produce a streak of 0."""
        assert SavingsService._compute_streak([]) == 0

    def test_today_only_returns_one(self):
        """A single record from today should produce a streak of 1."""
        rows = self._rows(0)
        assert SavingsService._compute_streak(rows) == 1

    def test_five_consecutive_days(self):
        """Five consecutive days ending today should produce streak = 5."""
        rows = self._rows(0, 1, 2, 3, 4)
        assert SavingsService._compute_streak(rows) == 5

    def test_gap_breaks_streak(self):
        """A missing day in the sequence should cap the streak at the run ending today."""
        # Days 0, 1 present; day 2 missing; days 3, 4 present
        rows = self._rows(0, 1, 3, 4)
        assert SavingsService._compute_streak(rows) == 2

    def test_today_missing_streak_is_zero(self):
        """If today has no record, the streak should be 0 regardless of other days."""
        rows = self._rows(1, 2, 3)
        assert SavingsService._compute_streak(rows) == 0

    def test_single_old_record_streak_is_zero(self):
        """A single record from 5 days ago (no record today) = streak 0."""
        rows = self._rows(5)
        assert SavingsService._compute_streak(rows) == 0

    def test_duplicate_day_does_not_inflate_streak(self):
        """Duplicate dates for the same day should not extend the streak count."""
        today = self._today()
        # Two rows for today and one for yesterday (most-recent first)
        rows = [(today,), (today,), (today - timedelta(days=1),)]
        # Streak: today matches i=0, second today matches i=1 (yesterday expected) → breaks
        result = SavingsService._compute_streak(rows)
        # The streak breaks at the second element (another 'today' != yesterday)
        assert result == 1

    def test_datetime_objects_coerced_to_date(self):
        """Row elements that are datetime objects (not date) should be handled correctly."""
        today_dt = datetime.now(tz=timezone.utc)
        yesterday_dt = today_dt - timedelta(days=1)
        rows = [(today_dt,), (yesterday_dt,)]
        assert SavingsService._compute_streak(rows) == 2

    def test_long_streak_at_boundary(self):
        """30-day consecutive streak should return 30."""
        rows = self._rows(*range(30))
        assert SavingsService._compute_streak(rows) == 30

    def test_streak_one_when_only_today(self):
        """Exactly one row for today should yield streak = 1."""
        rows = [(self._today(),)]
        assert SavingsService._compute_streak(rows) == 1

    def test_large_gap_before_consecutive_run(self):
        """A run ending today but preceded by a large gap should count only the run."""
        # Days 0, 1, 2 present; day 3 missing; days 10+ present
        rows = self._rows(0, 1, 2, 10, 11, 12)
        assert SavingsService._compute_streak(rows) == 3
