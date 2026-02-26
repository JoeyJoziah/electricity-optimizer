"""
Tests for the Alerts API (backend/api/v1/alerts.py) and the new DB-backed
methods in AlertService.

Coverage
--------
- GET    /api/v1/alerts              — list, empty, auth guard
- POST   /api/v1/alerts              — create, validation errors
- GET    /api/v1/alerts/history      — list, pagination, auth guard
- DELETE /api/v1/alerts/{id}         — delete owned, 404 for missing
- PUT    /api/v1/alerts/{id}         — update fields, 404 for missing

- AlertService.get_user_alerts       — unit test with mock DB
- AlertService.get_alert_history     — unit test with mock DB
- AlertService.create_alert          — unit test with mock DB
- AlertService.update_alert          — unit test with mock DB
- AlertService.delete_alert          — unit test with mock DB
- AlertService.record_triggered_alert — unit test with mock DB

All tests use function-scoped TestClient to prevent rate-limiter state
accumulation across tests.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from api.dependencies import get_current_user, get_db_session, TokenData
from services.alert_service import AlertService, PriceAlert

# ---------------------------------------------------------------------------
# Stable IDs
# ---------------------------------------------------------------------------

TEST_USER_ID = "aaaaaaaa-0000-0000-0000-000000000001"
OTHER_USER_ID = "bbbbbbbb-0000-0000-0000-000000000002"


# ---------------------------------------------------------------------------
# In-memory mock DB — routes SQL text to alert-specific operations
# ---------------------------------------------------------------------------


class _MockAlertDB:
    """
    In-memory DB session that routes text() SQL to alert table operations.

    Tables simulated:
      - price_alert_configs
      - alert_history
    """

    def __init__(self):
        self._configs: list[dict] = []
        self._history: list[dict] = []
        self.commit = AsyncMock()

    # -----------------------------------------------------------------------
    # execute dispatcher
    # -----------------------------------------------------------------------

    async def execute(self, stmt, params=None):
        sql = self._sql(stmt)
        params = params or {}
        return self._dispatch(sql, params)

    def _dispatch(self, sql: str, params: dict) -> MagicMock:
        # --- price_alert_configs operations ---
        if "INSERT INTO PRICE_ALERT_CONFIGS" in sql:
            return self._insert_config(params)
        if "DELETE FROM PRICE_ALERT_CONFIGS" in sql:
            return self._delete_config(params)
        if "UPDATE PRICE_ALERT_CONFIGS" in sql:
            return self._update_config(sql, params)
        if "FROM PRICE_ALERT_CONFIGS" in sql and "COUNT(*)" in sql:
            return self._count_configs(params)
        if "FROM PRICE_ALERT_CONFIGS" in sql and "LIMIT" in sql and "OFFSET" in sql:
            return self._paginated_configs(params)
        if "FROM PRICE_ALERT_CONFIGS" in sql and "WHERE ID" in sql:
            return self._select_config_by_id(params)
        if "FROM PRICE_ALERT_CONFIGS" in sql:
            return self._list_configs(params)

        # --- alert_history operations ---
        if "INSERT INTO ALERT_HISTORY" in sql:
            return self._insert_history(params)
        if "FROM ALERT_HISTORY" in sql and "COUNT(*)" in sql:
            return self._count_history(params)
        if "FROM ALERT_HISTORY" in sql and "LIMIT" in sql and "OFFSET" in sql:
            return self._paginated_history(params)

        # Fallback
        return self._empty_result()

    # -----------------------------------------------------------------------
    # Config handlers
    # -----------------------------------------------------------------------

    def _insert_config(self, params: dict) -> MagicMock:
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": params.get("id", str(uuid4())),
            "user_id": params["user_id"],
            "region": params.get("region", "us_ct"),
            "currency": params.get("currency", "USD"),
            "price_below": (
                Decimal(str(params["price_below"])) if params.get("price_below") else None
            ),
            "price_above": (
                Decimal(str(params["price_above"])) if params.get("price_above") else None
            ),
            "notify_optimal_windows": params.get("notify_optimal_windows", True),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self._configs.append(row)
        return self._mapping_first(row)

    def _list_configs(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        rows = [r for r in self._configs if str(r["user_id"]) == str(uid)]
        return self._mapping_all(rows)

    def _select_config_by_id(self, params: dict) -> MagicMock:
        cid = params.get("id")
        uid = params.get("user_id")
        row = next(
            (
                r
                for r in self._configs
                if str(r["id"]) == str(cid) and str(r["user_id"]) == str(uid)
            ),
            None,
        )
        return self._mapping_first(row)

    def _update_config(self, sql: str, params: dict) -> MagicMock:
        cid = params.get("id")
        uid = params.get("user_id")
        row = next(
            (
                r
                for r in self._configs
                if str(r["id"]) == str(cid) and str(r["user_id"]) == str(uid)
            ),
            None,
        )
        if row is None:
            return self._mapping_first(None)
        # Apply permitted fields
        for key in ("region", "currency", "price_below", "price_above",
                    "notify_optimal_windows", "is_active"):
            if key in params:
                val = params[key]
                if key in ("price_below", "price_above") and val is not None:
                    val = Decimal(str(val))
                row[key] = val
        row["updated_at"] = datetime.now(tz=timezone.utc)
        return self._mapping_first(row)

    def _delete_config(self, params: dict) -> MagicMock:
        cid = params.get("id")
        uid = params.get("user_id")
        before = len(self._configs)
        self._configs = [
            r
            for r in self._configs
            if not (str(r["id"]) == str(cid) and str(r["user_id"]) == str(uid))
        ]
        deleted = before - len(self._configs)
        result = MagicMock()
        result.rowcount = deleted
        return result

    def _count_configs(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        count = sum(1 for r in self._configs if str(r["user_id"]) == str(uid))
        result = MagicMock()
        result.scalar.return_value = count
        return result

    def _paginated_configs(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        rows = [r for r in self._configs if str(r["user_id"]) == str(uid)]
        return self._mapping_all(rows[offset: offset + limit])

    # -----------------------------------------------------------------------
    # History handlers
    # -----------------------------------------------------------------------

    def _insert_history(self, params: dict) -> MagicMock:
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": params.get("id", str(uuid4())),
            "user_id": params["user_id"],
            "alert_config_id": params.get("alert_config_id"),
            "alert_type": params["alert_type"],
            "current_price": Decimal(str(params["current_price"])),
            "threshold": (
                Decimal(str(params["threshold"])) if params.get("threshold") else None
            ),
            "region": params["region"],
            "supplier": params.get("supplier"),
            "currency": params.get("currency", "USD"),
            "optimal_window_start": params.get("optimal_window_start"),
            "optimal_window_end": params.get("optimal_window_end"),
            "estimated_savings": (
                Decimal(str(params["estimated_savings"]))
                if params.get("estimated_savings")
                else None
            ),
            "triggered_at": params.get("triggered_at", now),
            "email_sent": params.get("email_sent", False),
        }
        self._history.append(row)
        return self._mapping_first(row)

    def _count_history(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        count = sum(1 for r in self._history if str(r["user_id"]) == str(uid))
        result = MagicMock()
        result.scalar.return_value = count
        return result

    def _paginated_history(self, params: dict) -> MagicMock:
        uid = params.get("user_id")
        limit = params.get("limit", 20)
        offset = params.get("offset", 0)
        rows = [r for r in self._history if str(r["user_id"]) == str(uid)]
        return self._mapping_all(rows[offset: offset + limit])

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _sql(stmt) -> str:
        raw = str(stmt.text if hasattr(stmt, "text") else stmt)
        return " ".join(raw.split()).upper()

    @staticmethod
    def _mapping_first(row) -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.first.return_value = row
        result.mappings.return_value = mapping
        return result

    @staticmethod
    def _mapping_all(rows: list) -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.all.return_value = rows
        result.mappings.return_value = mapping
        return result

    @staticmethod
    def _empty_result() -> MagicMock:
        result = MagicMock()
        mapping = MagicMock()
        mapping.first.return_value = None
        mapping.all.return_value = []
        result.mappings.return_value = mapping
        result.rowcount = 0
        result.scalar.return_value = 0
        return result

    # -----------------------------------------------------------------------
    # Seed helper
    # -----------------------------------------------------------------------

    def seed_config(
        self,
        user_id: str = TEST_USER_ID,
        region: str = "us_ct",
        price_below: float = 0.20,
        price_above: float | None = None,
        notify_optimal_windows: bool = True,
        is_active: bool = True,
    ) -> dict:
        """Insert a config row directly."""
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "region": region,
            "currency": "USD",
            "price_below": Decimal(str(price_below)) if price_below is not None else None,
            "price_above": Decimal(str(price_above)) if price_above is not None else None,
            "notify_optimal_windows": notify_optimal_windows,
            "is_active": is_active,
            "created_at": now,
            "updated_at": now,
        }
        self._configs.append(row)
        return row

    def seed_history(
        self,
        user_id: str = TEST_USER_ID,
        alert_type: str = "price_drop",
        current_price: float = 0.18,
        threshold: float | None = 0.20,
        region: str = "us_ct",
        supplier: str = "Eversource Energy",
    ) -> dict:
        """Insert a history row directly."""
        now = datetime.now(tz=timezone.utc)
        row = {
            "id": str(uuid4()),
            "user_id": user_id,
            "alert_config_id": None,
            "alert_type": alert_type,
            "current_price": Decimal(str(current_price)),
            "threshold": Decimal(str(threshold)) if threshold is not None else None,
            "region": region,
            "supplier": supplier,
            "currency": "USD",
            "optimal_window_start": None,
            "optimal_window_end": None,
            "estimated_savings": None,
            "triggered_at": now,
            "email_sent": True,
        }
        self._history.append(row)
        return row


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db():
    return _MockAlertDB()


@pytest.fixture()
def auth_client(mock_db):
    from main import app

    test_user = TokenData(user_id=TEST_USER_ID, email="test@example.com")
    app.dependency_overrides[get_current_user] = lambda: test_user
    app.dependency_overrides[get_db_session] = lambda: mock_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture()
def unauth_client():
    from main import app

    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_db_session, None)

    with TestClient(app) as client:
        yield client


# =============================================================================
# Unit tests — AlertService DB methods
# =============================================================================


class TestAlertServiceDBMethods:
    """Unit-test the new DB-backed methods in AlertService."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.service = AlertService()
        self.db = _MockAlertDB()

    @pytest.mark.asyncio
    async def test_create_alert_stores_row(self):
        config = await self.service.create_alert(
            user_id=TEST_USER_ID,
            db=self.db,
            price_below=Decimal("0.20"),
        )
        assert config["user_id"] == TEST_USER_ID
        assert config["price_below"] == pytest.approx(0.20)
        assert config["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_alert_raises_if_no_conditions(self):
        with pytest.raises(ValueError, match="At least one"):
            await self.service.create_alert(
                user_id=TEST_USER_ID,
                db=self.db,
                price_below=None,
                price_above=None,
                notify_optimal_windows=False,
            )

    @pytest.mark.asyncio
    async def test_get_user_alerts_empty(self):
        alerts = await self.service.get_user_alerts(TEST_USER_ID, self.db)
        assert alerts == []

    @pytest.mark.asyncio
    async def test_get_user_alerts_returns_owned(self):
        self.db.seed_config(user_id=TEST_USER_ID)
        self.db.seed_config(user_id=TEST_USER_ID, price_below=0.15)
        self.db.seed_config(user_id=OTHER_USER_ID)  # should not appear

        alerts = await self.service.get_user_alerts(TEST_USER_ID, self.db)
        assert len(alerts) == 2
        for a in alerts:
            assert a["user_id"] == TEST_USER_ID

    @pytest.mark.asyncio
    async def test_delete_alert_returns_true_when_found(self):
        row = self.db.seed_config(user_id=TEST_USER_ID)
        deleted = await self.service.delete_alert(TEST_USER_ID, row["id"], self.db)
        assert deleted is True
        assert len(self.db._configs) == 0

    @pytest.mark.asyncio
    async def test_delete_alert_returns_false_when_missing(self):
        deleted = await self.service.delete_alert(TEST_USER_ID, str(uuid4()), self.db)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_alert_enforces_ownership(self):
        row = self.db.seed_config(user_id=OTHER_USER_ID)
        deleted = await self.service.delete_alert(TEST_USER_ID, row["id"], self.db)
        assert deleted is False
        # Row still present for the other user
        assert len(self.db._configs) == 1

    @pytest.mark.asyncio
    async def test_update_alert_modifies_fields(self):
        row = self.db.seed_config(user_id=TEST_USER_ID, price_below=0.20)
        updated = await self.service.update_alert(
            user_id=TEST_USER_ID,
            alert_id=row["id"],
            db=self.db,
            updates={"price_below": 0.15, "region": "us_ny"},
        )
        assert updated is not None
        assert updated["price_below"] == pytest.approx(0.15)
        assert updated["region"] == "us_ny"

    @pytest.mark.asyncio
    async def test_update_alert_returns_none_when_missing(self):
        updated = await self.service.update_alert(
            user_id=TEST_USER_ID,
            alert_id=str(uuid4()),
            db=self.db,
            updates={"price_below": 0.10},
        )
        assert updated is None

    @pytest.mark.asyncio
    async def test_get_alert_history_empty(self):
        result = await self.service.get_alert_history(TEST_USER_ID, self.db)
        assert result["total"] == 0
        assert result["items"] == []
        assert result["pages"] == 1

    @pytest.mark.asyncio
    async def test_get_alert_history_pagination(self):
        for _ in range(5):
            self.db.seed_history(user_id=TEST_USER_ID)
        self.db.seed_history(user_id=OTHER_USER_ID)  # should not appear

        result = await self.service.get_alert_history(
            TEST_USER_ID, self.db, page=1, page_size=2
        )
        assert result["total"] == 5
        assert len(result["items"]) == 2
        assert result["pages"] == 3

    @pytest.mark.asyncio
    async def test_record_triggered_alert(self):
        alert = PriceAlert(
            alert_type="price_drop",
            current_price=Decimal("0.18"),
            threshold=Decimal("0.20"),
            region="us_ct",
            supplier="Eversource Energy",
            timestamp=datetime.now(timezone.utc),
        )
        record = await self.service.record_triggered_alert(
            user_id=TEST_USER_ID,
            alert=alert,
            db=self.db,
            email_sent=True,
        )
        assert record["alert_type"] == "price_drop"
        assert record["current_price"] == pytest.approx(0.18)
        assert record["email_sent"] is True
        assert record["user_id"] == TEST_USER_ID


# =============================================================================
# API endpoint tests — GET /api/v1/alerts
# =============================================================================


class TestGetAlerts:
    def test_get_alerts_empty(self, auth_client):
        response = auth_client.get("/api/v1/alerts")
        assert response.status_code == 200
        data = response.json()
        assert data["alerts"] == []
        assert data["total"] == 0

    def test_get_alerts_returns_owned_configs(self, auth_client, mock_db):
        mock_db.seed_config(user_id=TEST_USER_ID)
        mock_db.seed_config(user_id=TEST_USER_ID, price_below=0.15)

        response = auth_client.get("/api/v1/alerts")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["alerts"]) == 2

    def test_get_alerts_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/v1/alerts")
        assert response.status_code in (401, 503)

    def test_get_alerts_shape(self, auth_client, mock_db):
        mock_db.seed_config(user_id=TEST_USER_ID, price_below=0.20)
        response = auth_client.get("/api/v1/alerts")
        assert response.status_code == 200
        item = response.json()["alerts"][0]
        for key in ("id", "user_id", "region", "currency", "price_below",
                    "notify_optimal_windows", "is_active", "created_at"):
            assert key in item, f"Missing key: {key}"


# =============================================================================
# API endpoint tests — POST /api/v1/alerts
# =============================================================================


class TestCreateAlert:
    def test_create_alert_price_below(self, auth_client):
        response = auth_client.post(
            "/api/v1/alerts",
            json={"price_below": 0.18, "region": "us_ct"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["price_below"] == pytest.approx(0.18)
        assert data["region"] == "us_ct"

    def test_create_alert_price_above(self, auth_client):
        response = auth_client.post(
            "/api/v1/alerts",
            json={"price_above": 0.35},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["price_above"] == pytest.approx(0.35)

    def test_create_alert_optimal_windows_only(self, auth_client):
        response = auth_client.post(
            "/api/v1/alerts",
            json={"notify_optimal_windows": True},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["notify_optimal_windows"] is True

    def test_create_alert_all_fields(self, auth_client):
        response = auth_client.post(
            "/api/v1/alerts",
            json={
                "price_below": 0.15,
                "price_above": 0.40,
                "notify_optimal_windows": False,
                "region": "us_ny",
                "currency": "USD",
            },
        )
        assert response.status_code == 201

    def test_create_alert_fails_no_conditions(self, auth_client):
        """price_below=None, price_above=None, notify_optimal_windows=False -> 422."""
        response = auth_client.post(
            "/api/v1/alerts",
            json={"notify_optimal_windows": False},
        )
        assert response.status_code == 422

    def test_create_alert_requires_auth(self, unauth_client):
        response = unauth_client.post(
            "/api/v1/alerts",
            json={"price_below": 0.20},
        )
        assert response.status_code in (401, 503)

    def test_create_alert_negative_price_rejected(self, auth_client):
        response = auth_client.post(
            "/api/v1/alerts",
            json={"price_below": -0.10},
        )
        assert response.status_code == 422

    def test_create_alert_user_id_set_from_token(self, auth_client):
        response = auth_client.post(
            "/api/v1/alerts",
            json={"price_below": 0.20},
        )
        assert response.status_code == 201
        assert response.json()["user_id"] == TEST_USER_ID


# =============================================================================
# API endpoint tests — GET /api/v1/alerts/history
# =============================================================================


class TestAlertHistory:
    def test_history_empty(self, auth_client):
        response = auth_client.get("/api/v1/alerts/history")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["pages"] == 1

    def test_history_returns_records(self, auth_client, mock_db):
        mock_db.seed_history(user_id=TEST_USER_ID)
        mock_db.seed_history(user_id=TEST_USER_ID, alert_type="price_spike")

        response = auth_client.get("/api/v1/alerts/history")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_history_pagination_params(self, auth_client, mock_db):
        for _ in range(5):
            mock_db.seed_history(user_id=TEST_USER_ID)

        response = auth_client.get("/api/v1/alerts/history?page=1&page_size=2")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert data["pages"] == 3
        assert len(data["items"]) == 2

    def test_history_page_size_max(self, auth_client):
        response = auth_client.get("/api/v1/alerts/history?page_size=101")
        assert response.status_code == 422

    def test_history_item_shape(self, auth_client, mock_db):
        mock_db.seed_history(user_id=TEST_USER_ID)
        response = auth_client.get("/api/v1/alerts/history")
        assert response.status_code == 200
        item = response.json()["items"][0]
        for key in ("id", "user_id", "alert_type", "current_price", "region",
                    "triggered_at", "email_sent"):
            assert key in item, f"Missing key: {key}"

    def test_history_requires_auth(self, unauth_client):
        response = unauth_client.get("/api/v1/alerts/history")
        assert response.status_code in (401, 503)

    def test_history_user_isolation(self, mock_db):
        mock_db.seed_history(user_id=OTHER_USER_ID)

        from main import app

        my_user = TokenData(user_id=TEST_USER_ID, email="me@example.com")
        app.dependency_overrides[get_current_user] = lambda: my_user
        app.dependency_overrides[get_db_session] = lambda: mock_db

        try:
            with TestClient(app) as client:
                response = client.get("/api/v1/alerts/history")
                assert response.status_code == 200
                data = response.json()
                assert data["total"] == 0
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db_session, None)


# =============================================================================
# API endpoint tests — DELETE /api/v1/alerts/{alert_id}
# =============================================================================


class TestDeleteAlert:
    def test_delete_owned_alert(self, auth_client, mock_db):
        row = mock_db.seed_config(user_id=TEST_USER_ID)
        response = auth_client.delete(f"/api/v1/alerts/{row['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["alert_id"] == row["id"]

    def test_delete_nonexistent_alert_returns_404(self, auth_client):
        response = auth_client.delete(f"/api/v1/alerts/{uuid4()}")
        assert response.status_code == 404

    def test_delete_other_users_alert_returns_404(self, auth_client, mock_db):
        row = mock_db.seed_config(user_id=OTHER_USER_ID)
        response = auth_client.delete(f"/api/v1/alerts/{row['id']}")
        assert response.status_code == 404
        # Row should still exist
        assert len(mock_db._configs) == 1

    def test_delete_requires_auth(self, unauth_client):
        response = unauth_client.delete(f"/api/v1/alerts/{uuid4()}")
        assert response.status_code in (401, 503)


# =============================================================================
# API endpoint tests — PUT /api/v1/alerts/{alert_id}
# =============================================================================


class TestUpdateAlert:
    def test_update_price_below(self, auth_client, mock_db):
        row = mock_db.seed_config(user_id=TEST_USER_ID, price_below=0.20)
        response = auth_client.put(
            f"/api/v1/alerts/{row['id']}",
            json={"price_below": 0.15},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["price_below"] == pytest.approx(0.15)

    def test_update_is_active_false(self, auth_client, mock_db):
        row = mock_db.seed_config(user_id=TEST_USER_ID)
        response = auth_client.put(
            f"/api/v1/alerts/{row['id']}",
            json={"is_active": False},
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    def test_update_region_and_currency(self, auth_client, mock_db):
        row = mock_db.seed_config(user_id=TEST_USER_ID)
        response = auth_client.put(
            f"/api/v1/alerts/{row['id']}",
            json={"region": "us_ny", "currency": "USD"},
        )
        assert response.status_code == 200
        assert response.json()["region"] == "us_ny"

    def test_update_nonexistent_returns_404(self, auth_client):
        response = auth_client.put(
            f"/api/v1/alerts/{uuid4()}",
            json={"price_below": 0.10},
        )
        assert response.status_code == 404

    def test_update_other_users_alert_returns_404(self, auth_client, mock_db):
        row = mock_db.seed_config(user_id=OTHER_USER_ID)
        response = auth_client.put(
            f"/api/v1/alerts/{row['id']}",
            json={"price_below": 0.10},
        )
        assert response.status_code == 404

    def test_update_requires_auth(self, unauth_client, mock_db):
        row = mock_db.seed_config(user_id=TEST_USER_ID)
        response = unauth_client.put(
            f"/api/v1/alerts/{row['id']}",
            json={"price_below": 0.10},
        )
        assert response.status_code in (401, 503)

    def test_update_empty_body_returns_existing(self, auth_client, mock_db):
        """An empty update body should return the existing record unchanged (not 404)."""
        row = mock_db.seed_config(user_id=TEST_USER_ID, price_below=0.22)
        response = auth_client.put(
            f"/api/v1/alerts/{row['id']}",
            json={},
        )
        # With no valid fields to update the service fetches and returns the existing row
        assert response.status_code == 200
        assert response.json()["price_below"] == pytest.approx(0.22)
