"""
Tests for ABTestService (TASK-MLDATA-003).

Covers:
- assign_user: returns existing assignment; creates new one via hashing.
- get_assignment: returns persisted version or None.
- record_prediction: inserts prediction row; updates last_prediction_at.
- update_actual: backfills actual_value and error_pct; returns False for unknown ID.
- get_split_metrics: aggregates MAPE/MAE/count per version.
- auto_promote: promotes challenger when threshold met; returns None otherwise.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

# =============================================================================
# Helpers / fixtures
# =============================================================================


def _make_assignment_row(model_version="v1.0"):
    """Mock DB row for model_ab_assignments."""
    row = MagicMock()
    row.model_version = model_version
    return row


def _make_prediction_row(predicted_value=0.15):
    """Mock DB row for model_predictions (fetch for update_actual)."""
    row = MagicMock()
    row.predicted_value = predicted_value
    return row


def _make_metrics_row(model_version, mape, mae, total_count, observed_count):
    """Mock DB row for get_split_metrics aggregate query."""
    row = MagicMock()
    row.model_version = model_version
    row.mape = mape
    row.mae = mae
    row.total_count = total_count
    row.observed_count = observed_count
    return row


@pytest.fixture
def mock_db():
    """Async SQLAlchemy session stub."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    from services.ab_test_service import ABTestService

    return ABTestService(mock_db)


def _mock_fetchone(mock_db, row):
    result = MagicMock()
    result.fetchone.return_value = row
    mock_db.execute.return_value = result


def _mock_fetchall(mock_db, rows):
    result = MagicMock()
    result.fetchall.return_value = rows
    mock_db.execute.return_value = result


def _side_effect_fetchones(mock_db, rows_sequence):
    """Configure consecutive execute calls to return different fetchone rows."""
    results = []
    for row in rows_sequence:
        r = MagicMock()
        r.fetchone.return_value = row
        results.append(r)
    mock_db.execute.side_effect = results


# =============================================================================
# assign_user
# =============================================================================


class TestAssignUser:
    """Tests for ABTestService.assign_user"""

    async def test_returns_existing_assignment_without_new_insert(
        self, service, mock_db
    ):
        """If a persistent assignment exists it should be returned immediately."""
        _mock_fetchone(mock_db, _make_assignment_row("v2.0"))

        result = await service.assign_user("user-1", "v1.0", "v2.0")

        assert result == "v2.0"
        # Only one execute call: the SELECT in get_assignment
        assert mock_db.execute.call_count == 1
        mock_db.commit.assert_not_awaited()

    async def test_creates_new_assignment_when_none_exists(self, service, mock_db):
        """If no assignment exists, one should be created via hashing and persisted."""
        _side_effect_fetchones(mock_db, [None, None])

        result = await service.assign_user("user-new", "v1.0", "v2.0")

        assert result in ("v1.0", "v2.0")
        mock_db.commit.assert_awaited_once()

    async def test_same_user_always_gets_same_version(self, mock_db):
        """
        Multiple calls for the same user_id should return the same version
        deterministically — hash is stable so same inputs produce same output.
        """
        from services.ab_test_service import (ABTestService,
                                              _hash_user_to_bucket)

        user_id = "stable-user"
        version_a, version_b = "v1.0", "v2.0"
        salt = "ab_split"

        # Compute expected version via the same hash algorithm
        bucket = _hash_user_to_bucket(user_id, salt)
        split_pct = int(0.5 * 100)
        expected = version_a if bucket < split_pct else version_b

        # Call assign_user twice, each time returning no existing assignment
        # so the hash-based allocation runs both times
        for _ in range(3):
            svc = ABTestService(mock_db)
            _side_effect_fetchones(mock_db, [None, None])
            mock_db.commit.reset_mock()
            result = await svc.assign_user(user_id, version_a, version_b, salt=salt)
            assert result == expected

    async def test_raises_for_invalid_split_ratio_zero(self, service, mock_db):
        """split_ratio=0.0 should raise ValueError before any DB call."""
        with pytest.raises(ValueError, match="split_ratio"):
            await service.assign_user("u1", "v1.0", "v2.0", split_ratio=0.0)

        mock_db.execute.assert_not_awaited()

    async def test_raises_for_invalid_split_ratio_one(self, service, mock_db):
        """split_ratio=1.0 should raise ValueError before any DB call."""
        with pytest.raises(ValueError, match="split_ratio"):
            await service.assign_user("u1", "v1.0", "v2.0", split_ratio=1.0)

    async def test_rollback_on_insert_failure(self, service, mock_db):
        """Should rollback and re-raise if the INSERT fails."""
        no_existing = MagicMock()
        no_existing.fetchone.return_value = None
        mock_db.execute.side_effect = [no_existing, Exception("constraint")]

        with pytest.raises(Exception, match="constraint"):
            await service.assign_user("u-fail", "v1.0", "v2.0")

        mock_db.rollback.assert_awaited_once()

    async def test_insert_uses_on_conflict_do_nothing(self, service, mock_db):
        """INSERT must include ON CONFLICT (user_id) DO NOTHING for idempotency."""
        _side_effect_fetchones(mock_db, [None, None])

        await service.assign_user("user-idem", "v1.0", "v2.0")

        # The second execute call is the INSERT
        insert_sql = str(mock_db.execute.call_args_list[1][0][0])
        assert "ON CONFLICT" in insert_sql.upper()
        assert "DO NOTHING" in insert_sql.upper()

    async def test_split_ratio_90_routes_most_to_version_a(self, service, mock_db):
        """With split_ratio=0.9, approximately 90% of users should be assigned v1.0."""
        from services.ab_test_service import _hash_user_to_bucket

        version_a_count = 0
        total = 200
        salt = "ab_split"

        for i in range(total):
            uid = f"user-{i:04d}"
            bucket = _hash_user_to_bucket(uid, salt)
            if bucket < 90:
                version_a_count += 1

        ratio = version_a_count / total
        assert (
            ratio >= 0.70
        ), f"Expected >= 70% assigned to v1.0 with 0.9 split, got {ratio:.2%}"


# =============================================================================
# get_assignment
# =============================================================================


class TestGetAssignment:
    """Tests for ABTestService.get_assignment"""

    async def test_returns_none_when_no_assignment(self, service, mock_db):
        """Should return None when no record exists."""
        _mock_fetchone(mock_db, None)

        result = await service.get_assignment("unknown-user")

        assert result is None

    async def test_returns_model_version_string(self, service, mock_db):
        """Should return the model_version string from the DB row."""
        _mock_fetchone(mock_db, _make_assignment_row("v3.0"))

        result = await service.get_assignment("user-xyz")

        assert result == "v3.0"

    async def test_query_filters_by_user_id(self, service, mock_db):
        """Query params must include the correct user_id."""
        _mock_fetchone(mock_db, None)

        await service.get_assignment("target-user")

        params = mock_db.execute.call_args[0][1]
        assert params["user_id"] == "target-user"


# =============================================================================
# record_prediction
# =============================================================================


class TestRecordPrediction:
    """Tests for ABTestService.record_prediction"""

    async def test_returns_uuid_string(self, service, mock_db):
        """Should return a valid UUID string for the new prediction record."""
        import re

        result = await service.record_prediction("u1", "v1.0", "NY", 0.15)
        uuid_re = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_re.match(result), f"Expected UUID, got: {result!r}"

    async def test_commits_after_insert(self, service, mock_db):
        """Should commit once after both the INSERT and the UPDATE."""
        await service.record_prediction("u1", "v1.0", "CA", 0.12)
        mock_db.commit.assert_awaited_once()

    async def test_insert_params_include_required_fields(self, service, mock_db):
        """INSERT params must include user_id, model_version, region, predicted_value."""
        await service.record_prediction("user-abc", "v2.0", "TX", 0.20)

        # First execute call is the prediction INSERT
        insert_params = mock_db.execute.call_args_list[0][0][1]
        assert insert_params["user_id"] == "user-abc"
        assert insert_params["model_version"] == "v2.0"
        assert insert_params["region"] == "TX"
        assert insert_params["predicted_value"] == pytest.approx(0.20)

    async def test_error_pct_computed_when_actual_provided(self, service, mock_db):
        """When actual_value is provided, error_pct should be populated."""
        await service.record_prediction("u1", "v1.0", "NY", 0.10, actual_value=0.08)

        insert_params = mock_db.execute.call_args_list[0][0][1]
        # error_pct = |0.10 - 0.08| / 0.08 * 100 = 25.0
        assert insert_params["error_pct"] == pytest.approx(25.0)
        assert insert_params["actual_value"] == pytest.approx(0.08)

    async def test_error_pct_is_none_when_actual_not_provided(self, service, mock_db):
        """error_pct should be None when no actual_value is given."""
        await service.record_prediction("u1", "v1.0", "NY", 0.10)

        insert_params = mock_db.execute.call_args_list[0][0][1]
        assert insert_params["error_pct"] is None
        assert insert_params["actual_value"] is None

    async def test_updates_last_prediction_at(self, service, mock_db):
        """Should issue a second execute to UPDATE last_prediction_at."""
        await service.record_prediction("u-active", "v1.0", "MA", 0.11)

        # Two execute calls: INSERT prediction + UPDATE assignment
        assert mock_db.execute.call_count == 2
        update_params = mock_db.execute.call_args_list[1][0][1]
        assert update_params["user_id"] == "u-active"
        assert "ts" in update_params

    async def test_rollback_on_failure(self, service, mock_db):
        """Should rollback and re-raise on DB error."""
        mock_db.execute.side_effect = Exception("db error")

        with pytest.raises(Exception, match="db error"):
            await service.record_prediction("u1", "v1.0", "NY", 0.10)

        mock_db.rollback.assert_awaited_once()


# =============================================================================
# update_actual
# =============================================================================


class TestUpdateActual:
    """Tests for ABTestService.update_actual"""

    async def test_returns_false_when_prediction_not_found(self, service, mock_db):
        """Should return False when the prediction_id does not exist."""
        _mock_fetchone(mock_db, None)

        result = await service.update_actual("non-existent-id", 0.10)

        assert result is False
        mock_db.commit.assert_not_awaited()

    async def test_returns_true_on_success(self, service, mock_db):
        """Should return True when the row is found and updated."""
        _side_effect_fetchones(mock_db, [_make_prediction_row(0.15), None])

        result = await service.update_actual("pred-1", 0.12)

        assert result is True

    async def test_computes_error_pct_correctly(self, service, mock_db):
        """error_pct = |predicted - actual| / |actual| * 100."""
        _side_effect_fetchones(mock_db, [_make_prediction_row(0.20), None])

        await service.update_actual("pred-1", 0.16)

        update_params = mock_db.execute.call_args[0][1]
        # |0.20 - 0.16| / 0.16 * 100 = 25.0
        assert update_params["error_pct"] == pytest.approx(25.0)
        assert update_params["actual_value"] == pytest.approx(0.16)

    async def test_commits_after_update(self, service, mock_db):
        """Should commit once after the UPDATE."""
        _side_effect_fetchones(mock_db, [_make_prediction_row(0.10), None])

        await service.update_actual("pred-2", 0.09)

        mock_db.commit.assert_awaited_once()

    async def test_rollback_on_update_failure(self, service, mock_db):
        """Should rollback and re-raise if the UPDATE fails."""
        found_row = _make_prediction_row(0.10)
        result_with_row = MagicMock()
        result_with_row.fetchone.return_value = found_row
        mock_db.execute.side_effect = [result_with_row, Exception("update failed")]

        with pytest.raises(Exception, match="update failed"):
            await service.update_actual("pred-3", 0.09)

        mock_db.rollback.assert_awaited_once()

    async def test_error_pct_none_when_actual_is_zero(self, service, mock_db):
        """Should not divide by zero — error_pct must be None when actual=0."""
        _side_effect_fetchones(mock_db, [_make_prediction_row(0.10), None])

        await service.update_actual("pred-zero", 0.0)

        update_params = mock_db.execute.call_args[0][1]
        assert update_params["error_pct"] is None


# =============================================================================
# get_split_metrics
# =============================================================================


class TestGetSplitMetrics:
    """Tests for ABTestService.get_split_metrics"""

    async def test_returns_empty_list_when_no_data(self, service, mock_db):
        """Should return [] when there are no predictions."""
        _mock_fetchall(mock_db, [])

        result = await service.get_split_metrics()

        assert result == []

    async def test_returns_metrics_per_version(self, service, mock_db):
        """Should return a list with one entry per model_version."""
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
            _make_metrics_row(
                "v2.0", mape=4.2, mae=0.008, total_count=190, observed_count=175
            ),
        ]
        _mock_fetchall(mock_db, rows)

        result = await service.get_split_metrics()

        assert len(result) == 2
        v1 = next(m for m in result if m["model_version"] == "v1.0")
        v2 = next(m for m in result if m["model_version"] == "v2.0")
        assert v1["mape"] == pytest.approx(5.0)
        assert v2["mape"] == pytest.approx(4.2)
        assert v1["count"] == 200
        assert v2["observed"] == 175

    async def test_mape_is_none_when_no_observed(self, service, mock_db):
        """If mape is NULL in DB (no observed rows), it should be None in result."""
        row = _make_metrics_row(
            "v1.0", mape=None, mae=None, total_count=50, observed_count=0
        )
        _mock_fetchall(mock_db, [row])

        result = await service.get_split_metrics()

        assert result[0]["mape"] is None
        assert result[0]["mae"] is None

    async def test_metrics_dict_has_required_keys(self, service, mock_db):
        """Each metrics entry must include model_version, mape, mae, count, observed."""
        row = _make_metrics_row(
            "v1.0", mape=4.5, mae=0.009, total_count=100, observed_count=90
        )
        _mock_fetchall(mock_db, [row])

        result = await service.get_split_metrics()

        entry = result[0]
        assert "model_version" in entry
        assert "mape" in entry
        assert "mae" in entry
        assert "count" in entry
        assert "observed" in entry


# =============================================================================
# auto_promote
# =============================================================================


class TestAutoPromote:
    """Tests for ABTestService.auto_promote"""

    def _setup_metrics(self, mock_db, metrics_rows):
        """Configure mock_db.execute to return the given rows from fetchall."""
        _mock_fetchall(mock_db, metrics_rows)

    async def test_returns_none_when_version_a_missing(self, service, mock_db):
        """Should return None when version_a has no metrics."""
        rows = [
            _make_metrics_row(
                "v2.0", mape=3.0, mae=0.005, total_count=200, observed_count=150
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=100
        )

        assert result is None

    async def test_returns_none_when_version_b_missing(self, service, mock_db):
        """Should return None when version_b has no metrics."""
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=100
        )

        assert result is None

    async def test_returns_none_when_challenger_insufficient_observations(
        self, service, mock_db
    ):
        """Should return None when version_b has fewer than min_predictions observations."""
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
            _make_metrics_row(
                "v2.0", mape=4.0, mae=0.008, total_count=50, observed_count=50
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=100
        )

        assert result is None

    async def test_returns_challenger_when_improvement_exceeds_threshold(
        self, service, mock_db
    ):
        """Should return version_b when it beats version_a by > threshold."""
        # version_b MAPE is 4.0 vs version_a MAPE 5.0 → improvement = 0.20 > 0.05
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
            _make_metrics_row(
                "v2.0", mape=4.0, mae=0.008, total_count=150, observed_count=150
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=100
        )

        assert result == "v2.0"

    async def test_returns_none_when_improvement_below_threshold(
        self, service, mock_db
    ):
        """Should return None when challenger improvement is below threshold."""
        # version_b MAPE is 4.96 vs version_a 5.0 → improvement = 0.008 < 0.05
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
            _make_metrics_row(
                "v2.0", mape=4.96, mae=0.0098, total_count=150, observed_count=150
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=100
        )

        assert result is None

    async def test_returns_none_when_mape_is_none_for_either(self, service, mock_db):
        """Should return None when either version's MAPE is None (no observed data)."""
        rows = [
            _make_metrics_row(
                "v1.0", mape=None, mae=None, total_count=100, observed_count=0
            ),
            _make_metrics_row(
                "v2.0", mape=4.0, mae=0.008, total_count=150, observed_count=150
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=100
        )

        assert result is None

    async def test_custom_threshold_respected(self, service, mock_db):
        """A custom threshold=0.25 should require a larger improvement to promote."""
        # improvement = (5.0 - 4.0) / 5.0 = 0.20, which is < 0.25
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
            _make_metrics_row(
                "v2.0", mape=4.0, mae=0.008, total_count=150, observed_count=150
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.25, min_predictions=100
        )

        assert result is None

    async def test_custom_min_predictions_respected(self, service, mock_db):
        """Custom min_predictions=200 should block promotion when observed=150."""
        rows = [
            _make_metrics_row(
                "v1.0", mape=5.0, mae=0.01, total_count=200, observed_count=180
            ),
            _make_metrics_row(
                "v2.0", mape=4.0, mae=0.008, total_count=150, observed_count=150
            ),
        ]
        self._setup_metrics(mock_db, rows)

        result = await service.auto_promote(
            "v1.0", "v2.0", threshold=0.05, min_predictions=200
        )

        assert result is None


# =============================================================================
# Hash determinism  (white-box)
# =============================================================================


class TestHashDeterminism:
    """White-box tests for the consistent hashing helper."""

    def test_same_inputs_produce_same_bucket(self):
        from services.ab_test_service import _hash_user_to_bucket

        uid = "test-user-id-abc123"
        salt = "ab_split"

        results = [_hash_user_to_bucket(uid, salt) for _ in range(10)]
        assert len(set(results)) == 1

    def test_bucket_in_valid_range(self):
        from services.ab_test_service import _hash_user_to_bucket

        for i in range(50):
            bucket = _hash_user_to_bucket(f"user-{i}", "ab_split")
            assert 0 <= bucket <= 99

    def test_different_salts_produce_different_buckets(self):
        from services.ab_test_service import _hash_user_to_bucket

        uid = "collision-test-user"
        buckets = {_hash_user_to_bucket(uid, f"salt-{i}") for i in range(10)}
        # With 10 different salts, we expect at least 2 distinct bucket values
        # (probabilistically extremely likely)
        assert len(buckets) > 1

    def test_different_users_produce_different_buckets(self):
        from services.ab_test_service import _hash_user_to_bucket

        buckets = {_hash_user_to_bucket(f"user-{i}", "test") for i in range(20)}
        # 20 users with a uniform hash should produce multiple distinct buckets
        assert len(buckets) > 1
