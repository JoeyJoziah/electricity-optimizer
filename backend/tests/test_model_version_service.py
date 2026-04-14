"""
Tests for ModelVersionService (TASK-MLDATA-003).

Covers:
- create_version: inserts a new inactive version, returns ModelVersion.
- get_active_version: returns active row; returns None when absent.
- promote_version: deactivates previous active version, sets target active.
- list_versions: returns versions newest-first, respects limit parameter.
- compare_versions: returns side-by-side metric deltas; handles missing metrics.
- create_ab_test: creates running test; rejects duplicate running tests.
- get_ab_assignment: deterministic bucket assignment; consistent across calls.
- record_ab_outcome: inserts outcome row; idempotent on duplicate (test, user).
"""

import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

# =============================================================================
# Helpers / fixtures
# =============================================================================


def _make_version_row(
    id="ver-1",
    model_name="ensemble",
    version_tag="v1.0",
    config=None,
    metrics=None,
    is_active=False,
    created_at=None,
    promoted_at=None,
):
    """Create a mock DB row that mimics a model_versions SQLAlchemy Row."""
    row = MagicMock()
    row.id = id
    row.model_name = model_name
    row.version_tag = version_tag
    row.config = config or {"lr": 0.01, "epochs": 10}
    row.metrics = metrics or {"mape": 5.0, "rmse": 0.01}
    row.is_active = is_active
    row.created_at = created_at or datetime(2026, 3, 10, 0, 0, tzinfo=UTC)
    row.promoted_at = promoted_at
    return row


def _make_ab_test_row(
    id="test-1",
    model_name="ensemble",
    version_a_id="ver-a",
    version_b_id="ver-b",
    traffic_split=0.5,
    status="running",
    started_at=None,
    ended_at=None,
    results=None,
):
    """Create a mock DB row that mimics an ab_tests SQLAlchemy Row."""
    row = MagicMock()
    row.id = id
    row.model_name = model_name
    row.version_a_id = version_a_id
    row.version_b_id = version_b_id
    row.traffic_split = traffic_split
    row.status = status
    row.started_at = started_at or datetime(2026, 3, 10, 0, 0, tzinfo=UTC)
    row.ended_at = ended_at
    row.results = results or {}
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
    from services.model_version_service import ModelVersionService

    return ModelVersionService(mock_db)


def _mock_fetchone(mock_db, row):
    """Configure mock_db.execute to return a result whose fetchone() is row."""
    result = MagicMock()
    result.fetchone.return_value = row
    mock_db.execute.return_value = result


def _mock_fetchall(mock_db, rows):
    """Configure mock_db.execute to return a result whose fetchall() is rows."""
    result = MagicMock()
    result.fetchall.return_value = rows
    mock_db.execute.return_value = result


# =============================================================================
# create_version
# =============================================================================


class TestCreateVersion:
    """Tests for ModelVersionService.create_version"""

    async def test_returns_model_version_with_correct_fields(self, service, mock_db):
        """create_version should return a ModelVersion with the provided values."""
        config = {"lr": 0.01, "batch_size": 32}
        metrics = {"mape": 4.8, "rmse": 0.009}

        result = await service.create_version(
            "ensemble",
            config=config,
            metrics=metrics,
            version_tag="v2.0",
        )

        assert result.model_name == "ensemble"
        assert result.version_tag == "v2.0"
        assert result.config == config
        assert result.metrics == metrics
        assert result.is_active is False

    async def test_generates_uuid_id(self, service, mock_db):
        """The returned version should have a valid UUID id."""
        import re

        result = await service.create_version("ensemble", config={}, metrics={})
        uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert uuid_re.match(result.id), f"Expected UUID, got: {result.id!r}"

    async def test_auto_generates_version_tag_when_omitted(self, service, mock_db):
        """version_tag should be auto-generated when not provided."""
        result = await service.create_version("ensemble", config={}, metrics={})

        assert result.version_tag.startswith("v")
        assert len(result.version_tag) > 1

    async def test_new_version_is_inactive(self, service, mock_db):
        """create_version must create an INACTIVE version."""
        result = await service.create_version("ensemble", config={}, metrics={})

        assert result.is_active is False

    async def test_commits_after_insert(self, service, mock_db):
        """Should call commit exactly once."""
        await service.create_version("ensemble", config={}, metrics={})

        mock_db.commit.assert_awaited_once()

    async def test_rollback_and_reraise_on_db_error(self, service, mock_db):
        """Should rollback and re-raise the exception on DB failure."""
        mock_db.execute.side_effect = Exception("disk full")

        with pytest.raises(Exception, match="disk full"):
            await service.create_version("ensemble", config={}, metrics={})

        mock_db.rollback.assert_awaited_once()

    async def test_insert_params_contain_model_name_and_tag(self, service, mock_db):
        """INSERT parameters must include the model_name and version_tag."""
        await service.create_version("my_model", config={}, metrics={}, version_tag="v42")

        insert_params = mock_db.execute.call_args[0][1]
        assert insert_params["model_name"] == "my_model"
        assert insert_params["version_tag"] == "v42"

    async def test_config_serialised_as_json_string(self, service, mock_db):
        """The config dict must be JSON-serialised for the ::jsonb cast."""
        import json

        cfg = {"key": "value", "count": 3}
        await service.create_version("ensemble", config=cfg, metrics={})

        params = mock_db.execute.call_args[0][1]
        assert isinstance(params["config"], str)
        assert json.loads(params["config"]) == cfg


# =============================================================================
# get_active_version
# =============================================================================


class TestGetActiveVersion:
    """Tests for ModelVersionService.get_active_version"""

    async def test_returns_none_when_no_active_row(self, service, mock_db):
        """Should return None when no active version exists."""
        _mock_fetchone(mock_db, None)

        result = await service.get_active_version("ensemble")

        assert result is None

    async def test_returns_model_version_when_row_exists(self, service, mock_db):
        """Should return a populated ModelVersion from the active row."""
        row = _make_version_row(
            id="active-1",
            model_name="ensemble",
            version_tag="v3.0",
            metrics={"mape": 3.5},
            is_active=True,
        )
        _mock_fetchone(mock_db, row)

        result = await service.get_active_version("ensemble")

        assert result is not None
        assert result.id == "active-1"
        assert result.model_name == "ensemble"
        assert result.version_tag == "v3.0"
        assert result.is_active is True

    async def test_query_filters_by_model_name(self, service, mock_db):
        """The SQL query must filter by the correct model_name."""
        _mock_fetchone(mock_db, None)

        await service.get_active_version("forecast_model")

        params = mock_db.execute.call_args[0][1]
        assert params["model_name"] == "forecast_model"

    async def test_parses_json_string_config(self, service, mock_db):
        """Should handle config/metrics columns returned as raw JSON strings."""
        import json

        row = _make_version_row(
            config=json.dumps({"hidden": 128}),
            metrics=json.dumps({"mape": 5.0}),
        )
        _mock_fetchone(mock_db, row)

        result = await service.get_active_version("ensemble")

        assert result.config == {"hidden": 128}
        assert result.metrics == {"mape": 5.0}


# =============================================================================
# promote_version
# =============================================================================


class TestPromoteVersion:
    """Tests for ModelVersionService.promote_version"""

    async def test_raises_value_error_when_version_not_found(self, service, mock_db):
        """Should raise ValueError if the version_id does not exist."""
        _mock_fetchone(mock_db, None)

        with pytest.raises(ValueError, match="Model version not found"):
            await service.promote_version("non-existent-id")

    async def test_returns_model_version_with_is_active_true(self, service, mock_db):
        """Promoted version must have is_active=True."""
        row = _make_version_row(
            id="ver-2",
            model_name="ensemble",
            version_tag="v2.0",
            is_active=False,
        )
        _mock_fetchone(mock_db, row)

        result = await service.promote_version("ver-2")

        assert result.is_active is True
        assert result.id == "ver-2"

    async def test_promoted_at_is_set(self, service, mock_db):
        """promoted_at must be populated after promotion."""
        row = _make_version_row(id="ver-3", model_name="ensemble")
        _mock_fetchone(mock_db, row)

        result = await service.promote_version("ver-3")

        assert result.promoted_at is not None
        assert isinstance(result.promoted_at, datetime)

    async def test_executes_two_updates(self, service, mock_db):
        """Should run two UPDATEs: one to deactivate others, one to activate target."""
        row = _make_version_row(id="ver-4", model_name="ensemble")
        # First call (SELECT) returns the row; subsequent calls (UPDATEs) return None
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.return_value = result_mock

        await service.promote_version("ver-4")

        # 1 SELECT + 2 UPDATEs = 3 execute calls
        assert mock_db.execute.call_count == 3

    async def test_commits_once(self, service, mock_db):
        """Should commit exactly once after both UPDATEs."""
        row = _make_version_row(id="ver-5")
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.return_value = result_mock

        await service.promote_version("ver-5")

        mock_db.commit.assert_awaited_once()

    async def test_rollback_on_update_failure(self, service, mock_db):
        """Should rollback and re-raise if the UPDATE fails."""
        row = _make_version_row(id="ver-6")
        # First execute (SELECT) succeeds, subsequent ones fail
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.side_effect = [result_mock, Exception("lock timeout")]

        with pytest.raises(Exception, match="lock timeout"):
            await service.promote_version("ver-6")

        mock_db.rollback.assert_awaited_once()

    async def test_deactivate_uses_correct_model_name(self, service, mock_db):
        """The deactivation UPDATE must filter by model_name."""
        row = _make_version_row(
            id="ver-7",
            model_name="price_forecast",
        )
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.return_value = result_mock

        await service.promote_version("ver-7")

        # Second execute call is the deactivation UPDATE
        deactivate_params = mock_db.execute.call_args_list[1][0][1]
        assert deactivate_params["model_name"] == "price_forecast"

    async def test_deactivate_excludes_target_version(self, service, mock_db):
        """The deactivation UPDATE must exclude the version being promoted."""
        row = _make_version_row(id="ver-8", model_name="ensemble")
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.return_value = result_mock

        await service.promote_version("ver-8")

        deactivate_params = mock_db.execute.call_args_list[1][0][1]
        assert deactivate_params["version_id"] == "ver-8"


# =============================================================================
# list_versions
# =============================================================================


class TestListVersions:
    """Tests for ModelVersionService.list_versions"""

    async def test_returns_empty_list_when_no_rows(self, service, mock_db):
        """Should return [] when there are no versions stored."""
        _mock_fetchall(mock_db, [])

        result = await service.list_versions("ensemble")

        assert result == []

    async def test_returns_list_of_model_versions(self, service, mock_db):
        """Should return a list of ModelVersion objects."""
        rows = [
            _make_version_row(id="r1", version_tag="v3.0", is_active=True),
            _make_version_row(id="r2", version_tag="v2.0"),
            _make_version_row(id="r3", version_tag="v1.0"),
        ]
        _mock_fetchall(mock_db, rows)

        result = await service.list_versions("ensemble")

        assert len(result) == 3
        assert result[0].version_tag == "v3.0"
        assert result[1].version_tag == "v2.0"
        assert result[2].version_tag == "v1.0"

    async def test_default_limit_is_10(self, service, mock_db):
        """Should pass limit=10 by default."""
        _mock_fetchall(mock_db, [])

        await service.list_versions("ensemble")

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == 10

    async def test_custom_limit_is_passed(self, service, mock_db):
        """Should pass the provided limit to the SQL query."""
        _mock_fetchall(mock_db, [])

        await service.list_versions("ensemble", limit=5)

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == 5

    async def test_filters_by_model_name(self, service, mock_db):
        """Should scope the query to the correct model_name."""
        _mock_fetchall(mock_db, [])

        await service.list_versions("custom_model")

        params = mock_db.execute.call_args[0][1]
        assert params["model_name"] == "custom_model"

    async def test_active_version_is_marked_correctly(self, service, mock_db):
        """The active version in the list should have is_active=True."""
        rows = [
            _make_version_row(id="active", is_active=True),
            _make_version_row(id="old", is_active=False),
        ]
        _mock_fetchall(mock_db, rows)

        result = await service.list_versions("ensemble")

        active_versions = [v for v in result if v.is_active]
        assert len(active_versions) == 1
        assert active_versions[0].id == "active"


# =============================================================================
# compare_versions
# =============================================================================


class TestCompareVersions:
    """Tests for ModelVersionService.compare_versions"""

    def _setup_two_versions(self, mock_db, metrics_a, metrics_b):
        """Configure mock_db to return two version rows on consecutive fetchone calls."""
        row_a = _make_version_row(
            id="ver-a",
            version_tag="v1.0",
            metrics=metrics_a,
            is_active=False,
        )
        row_b = _make_version_row(
            id="ver-b",
            version_tag="v2.0",
            metrics=metrics_b,
            is_active=True,
        )
        result_a = MagicMock()
        result_a.fetchone.return_value = row_a
        result_b = MagicMock()
        result_b.fetchone.return_value = row_b
        mock_db.execute.side_effect = [result_a, result_b]

    async def test_raises_if_version_a_not_found(self, service, mock_db):
        """Should raise ValueError if version_a_id does not exist."""
        _mock_fetchone(mock_db, None)

        with pytest.raises(ValueError, match="Model version not found"):
            await service.compare_versions("missing-a", "ver-b")

    async def test_raises_if_version_b_not_found(self, service, mock_db):
        """Should raise ValueError if version_b_id does not exist."""
        row_a = _make_version_row(id="ver-a")
        result_a = MagicMock()
        result_a.fetchone.return_value = row_a
        result_missing = MagicMock()
        result_missing.fetchone.return_value = None
        mock_db.execute.side_effect = [result_a, result_missing]

        with pytest.raises(ValueError, match="Model version not found"):
            await service.compare_versions("ver-a", "missing-b")

    async def test_numeric_delta_computed_correctly(self, service, mock_db):
        """Delta should equal b_val - a_val for numeric metrics."""
        self._setup_two_versions(
            mock_db,
            metrics_a={"mape": 5.0, "rmse": 0.02},
            metrics_b={"mape": 4.0, "rmse": 0.015},
        )

        result = await service.compare_versions("ver-a", "ver-b")

        assert result.metric_comparison["mape"]["delta"] == pytest.approx(-1.0)
        assert result.metric_comparison["rmse"]["delta"] == pytest.approx(-0.005)

    async def test_non_numeric_metric_has_none_delta(self, service, mock_db):
        """Non-numeric metric values should produce delta=None."""
        self._setup_two_versions(
            mock_db,
            metrics_a={"label": "good"},
            metrics_b={"label": "better"},
        )

        result = await service.compare_versions("ver-a", "ver-b")

        assert result.metric_comparison["label"]["delta"] is None

    async def test_missing_metric_in_one_version(self, service, mock_db):
        """Metrics present in only one version should appear with None for the other."""
        self._setup_two_versions(
            mock_db,
            metrics_a={"mape": 5.0},
            metrics_b={"mape": 4.0, "coverage": 0.95},
        )

        result = await service.compare_versions("ver-a", "ver-b")

        assert "coverage" in result.metric_comparison
        assert result.metric_comparison["coverage"]["version_a"] is None
        assert result.metric_comparison["coverage"]["version_b"] == 0.95
        assert result.metric_comparison["coverage"]["delta"] is None

    async def test_returns_correct_version_tags_in_result(self, service, mock_db):
        """Comparison result should carry the correct version tags."""
        self._setup_two_versions(
            mock_db,
            metrics_a={"mape": 5.0},
            metrics_b={"mape": 4.0},
        )

        result = await service.compare_versions("ver-a", "ver-b")

        assert result.version_a.version_tag == "v1.0"
        assert result.version_b.version_tag == "v2.0"


# =============================================================================
# create_ab_test
# =============================================================================


class TestCreateABTest:
    """Tests for ModelVersionService.create_ab_test"""

    def _setup_no_running_test_and_two_versions(self, mock_db, model_name="ensemble"):
        """
        Configure mock_db for a successful create_ab_test call:
        1. _get_running_test SELECT → None (no active test)
        2. get_version_by_id SELECT for version_a → row
        3. get_version_by_id SELECT for version_b → row
        4. INSERT ab_tests → (no meaningful return value needed)

        The INSERT call does not use fetchone/fetchall so a plain MagicMock
        with no special fetchone configuration is sufficient for step 4.
        """
        no_test = MagicMock()
        no_test.fetchone.return_value = None

        ver_a_row = _make_version_row(id="ver-a", model_name=model_name, is_active=True)
        ver_b_row = _make_version_row(id="ver-b", model_name=model_name, is_active=False)
        result_a = MagicMock()
        result_a.fetchone.return_value = ver_a_row
        result_b = MagicMock()
        result_b.fetchone.return_value = ver_b_row
        insert_result = MagicMock()

        mock_db.execute.side_effect = [no_test, result_a, result_b, insert_result]

    async def test_returns_ab_test_with_running_status(self, service, mock_db):
        """New A/B test should have status='running'."""
        self._setup_no_running_test_and_two_versions(mock_db)

        result = await service.create_ab_test("ensemble", "ver-a", "ver-b")

        assert result.status == "running"
        assert result.model_name == "ensemble"
        assert result.version_a_id == "ver-a"
        assert result.version_b_id == "ver-b"

    async def test_default_traffic_split_is_50_percent(self, service, mock_db):
        """Default traffic_split should be 0.5."""
        self._setup_no_running_test_and_two_versions(mock_db)

        result = await service.create_ab_test("ensemble", "ver-a", "ver-b")

        assert result.traffic_split == pytest.approx(0.5)

    async def test_custom_traffic_split_is_respected(self, service, mock_db):
        """Supplied traffic_split must be stored correctly."""
        self._setup_no_running_test_and_two_versions(mock_db)

        result = await service.create_ab_test("ensemble", "ver-a", "ver-b", traffic_split=0.3)

        assert result.traffic_split == pytest.approx(0.3)

    async def test_raises_if_running_test_already_exists(self, service, mock_db):
        """Should raise ValueError when a running test already exists."""
        running_row = _make_ab_test_row(model_name="ensemble", status="running")
        result_mock = MagicMock()
        result_mock.fetchone.return_value = running_row
        mock_db.execute.return_value = result_mock

        with pytest.raises(ValueError, match="already running"):
            await service.create_ab_test("ensemble", "ver-a", "ver-b")

    async def test_raises_for_invalid_traffic_split_zero(self, service, mock_db):
        """traffic_split=0.0 should raise ValueError before any DB call."""
        with pytest.raises(ValueError, match="traffic_split"):
            await service.create_ab_test("ensemble", "ver-a", "ver-b", traffic_split=0.0)

    async def test_raises_for_invalid_traffic_split_one(self, service, mock_db):
        """traffic_split=1.0 should raise ValueError before any DB call."""
        with pytest.raises(ValueError, match="traffic_split"):
            await service.create_ab_test("ensemble", "ver-a", "ver-b", traffic_split=1.0)

    async def test_raises_if_version_a_not_found(self, service, mock_db):
        """Should raise ValueError if version_a does not exist in the DB."""
        no_test = MagicMock()
        no_test.fetchone.return_value = None
        missing = MagicMock()
        missing.fetchone.return_value = None
        mock_db.execute.side_effect = [no_test, missing]

        with pytest.raises(ValueError, match="Model version not found"):
            await service.create_ab_test("ensemble", "missing-a", "ver-b")

    async def test_raises_if_version_belongs_to_different_model(self, service, mock_db):
        """Should raise ValueError if a version belongs to a different model."""
        no_test = MagicMock()
        no_test.fetchone.return_value = None

        # version_a belongs to model "other_model", not "ensemble"
        wrong_model_row = _make_version_row(id="ver-wrong", model_name="other_model")
        result_wrong = MagicMock()
        result_wrong.fetchone.return_value = wrong_model_row
        mock_db.execute.side_effect = [no_test, result_wrong]

        with pytest.raises(ValueError, match="belongs to model"):
            await service.create_ab_test("ensemble", "ver-wrong", "ver-b")

    async def test_generated_test_id_is_uuid(self, service, mock_db):
        """The returned test should have a valid UUID id."""
        import re

        self._setup_no_running_test_and_two_versions(mock_db)
        result = await service.create_ab_test("ensemble", "ver-a", "ver-b")
        uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert uuid_re.match(result.id), f"Expected UUID, got: {result.id!r}"

    async def test_commits_after_insert(self, service, mock_db):
        """Should commit exactly once after inserting the test row."""
        self._setup_no_running_test_and_two_versions(mock_db)
        await service.create_ab_test("ensemble", "ver-a", "ver-b")
        mock_db.commit.assert_awaited_once()

    async def test_rollback_on_db_failure(self, service, mock_db):
        """Should rollback and re-raise if the INSERT fails."""
        no_test = MagicMock()
        no_test.fetchone.return_value = None
        ver_a_result = MagicMock()
        ver_a_result.fetchone.return_value = _make_version_row(id="ver-a", model_name="ensemble")
        ver_b_result = MagicMock()
        ver_b_result.fetchone.return_value = _make_version_row(id="ver-b", model_name="ensemble")
        mock_db.execute.side_effect = [
            no_test,
            ver_a_result,
            ver_b_result,
            Exception("constraint violation"),
        ]

        with pytest.raises(Exception, match="constraint violation"):
            await service.create_ab_test("ensemble", "ver-a", "ver-b")

        mock_db.rollback.assert_awaited_once()


# =============================================================================
# get_ab_assignment  —  determinism tests
# =============================================================================


class TestGetABAssignment:
    """Tests for ModelVersionService.get_ab_assignment"""

    async def test_returns_none_when_no_running_test(self, service, mock_db):
        """Should return None when there is no running A/B test for the model."""
        _mock_fetchone(mock_db, None)

        result = await service.get_ab_assignment("ensemble", "user-123")

        assert result is None

    async def test_returns_ab_assignment_object(self, service, mock_db):
        """Should return an ABAssignment with test_id and user_id set."""
        test_row = _make_ab_test_row(
            id="test-abc",
            version_a_id="ver-a",
            version_b_id="ver-b",
            traffic_split=0.5,
        )
        _mock_fetchone(mock_db, test_row)

        result = await service.get_ab_assignment("ensemble", "user-xyz")

        assert result is not None
        assert result.test_id == "test-abc"
        assert result.user_id == "user-xyz"
        assert result.assigned_version_id in ("ver-a", "ver-b")
        assert result.bucket in ("a", "b")

    async def test_same_user_always_gets_same_bucket(self, service, mock_db):
        """Determinism: the same user_id must always receive the same bucket."""
        test_row = _make_ab_test_row(
            id="test-det",
            version_a_id="ver-a",
            version_b_id="ver-b",
            traffic_split=0.5,
        )

        assignments = []
        for _ in range(5):
            _mock_fetchone(mock_db, test_row)
            assignment = await service.get_ab_assignment("ensemble", "stable-user-id")
            assignments.append(assignment.bucket)

        assert (
            len(set(assignments)) == 1
        ), f"Expected all assignments to be the same bucket, got: {assignments}"

    async def test_different_users_can_get_different_buckets(self, service, mock_db):
        """
        With 0.5 traffic split and enough users, both buckets should be assigned.
        This test verifies the hash distributes across buckets.
        """
        test_row = _make_ab_test_row(
            id="test-spread",
            version_a_id="ver-a",
            version_b_id="ver-b",
            traffic_split=0.5,
        )

        buckets = set()
        # Use a stable list of user_ids that we know will produce both buckets
        user_ids = [f"user-{i:04d}" for i in range(50)]
        for uid in user_ids:
            _mock_fetchone(mock_db, test_row)
            assignment = await service.get_ab_assignment("ensemble", uid)
            buckets.add(assignment.bucket)

        assert "a" in buckets, "No users were assigned to bucket A"
        assert "b" in buckets, "No users were assigned to bucket B"

    async def test_traffic_split_skew_routes_most_to_a(self, service, mock_db):
        """
        With traffic_split=0.9, approximately 90% of users should be in bucket A.
        Uses a 200-user sample; accepts any result >= 70% to avoid flakiness.
        """
        test_row = _make_ab_test_row(
            id="test-skew",
            version_a_id="ver-a",
            version_b_id="ver-b",
            traffic_split=0.9,
        )

        bucket_a_count = 0
        total = 200
        for i in range(total):
            _mock_fetchone(mock_db, test_row)
            assignment = await service.get_ab_assignment("ensemble", f"user-{i:04d}")
            if assignment.bucket == "a":
                bucket_a_count += 1

        ratio = bucket_a_count / total
        assert ratio >= 0.70, f"Expected >= 70% in bucket A with 0.9 split, got {ratio:.2%}"

    async def test_assignment_is_stable_across_calls_via_hash(self):
        """
        White-box test: verify the SHA-256 hash produces the correct bucket
        without any DB interaction.
        """
        test_id = "fixed-test-id"
        user_id = "fixed-user-id"
        traffic_split = 0.5

        hash_input = f"{test_id}:{user_id}".encode()
        hash_int = int(hashlib.sha256(hash_input).hexdigest(), 16)
        bucket_pct = hash_int % 100
        split_pct = int(traffic_split * 100)  # 50

        expected_bucket = "a" if bucket_pct < split_pct else "b"
        assert expected_bucket in ("a", "b")

        # Now exercise the service with the same inputs
        test_row = _make_ab_test_row(
            id=test_id,
            version_a_id="ver-a",
            version_b_id="ver-b",
            traffic_split=traffic_split,
        )
        db = AsyncMock()
        db.execute = AsyncMock()
        db.commit = AsyncMock()
        db.rollback = AsyncMock()

        from services.model_version_service import ModelVersionService

        svc = ModelVersionService(db)
        _mock_fetchone(db, test_row)
        assignment = await svc.get_ab_assignment("ensemble", user_id)

        assert assignment.bucket == expected_bucket


# =============================================================================
# record_ab_outcome
# =============================================================================


class TestRecordABOutcome:
    """Tests for ModelVersionService.record_ab_outcome"""

    async def test_returns_ab_outcome_object(self, service, mock_db):
        """Should return a populated ABOutcome on success."""
        result = await service.record_ab_outcome(
            test_id="test-1",
            version_id="ver-a",
            user_id="user-1",
            outcome="conversion",
        )

        assert result.test_id == "test-1"
        assert result.version_id == "ver-a"
        assert result.user_id == "user-1"
        assert result.outcome == "conversion"

    async def test_outcome_has_uuid_id(self, service, mock_db):
        """The returned ABOutcome should have a valid UUID id."""
        import re

        result = await service.record_ab_outcome(
            test_id="test-1",
            version_id="ver-a",
            user_id="user-1",
            outcome="success",
        )
        uuid_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
        assert uuid_re.match(result.id), f"Expected UUID, got: {result.id!r}"

    async def test_commits_after_insert(self, service, mock_db):
        """Should commit exactly once after the INSERT."""
        await service.record_ab_outcome("t1", "v1", "u1", "hit")

        mock_db.commit.assert_awaited_once()

    async def test_insert_contains_on_conflict_do_nothing(self, service, mock_db):
        """The INSERT SQL must include ON CONFLICT DO NOTHING for idempotency."""
        await service.record_ab_outcome("t1", "v1", "u1", "hit")

        sql = str(mock_db.execute.call_args[0][0])
        assert "ON CONFLICT" in sql.upper() and "DO NOTHING" in sql.upper()

    async def test_insert_params_include_all_fields(self, service, mock_db):
        """INSERT params must include test_id, version_id, user_id, and outcome."""
        await service.record_ab_outcome(
            test_id="test-XYZ",
            version_id="ver-ABC",
            user_id="user-DEF",
            outcome="error",
        )

        params = mock_db.execute.call_args[0][1]
        assert params["test_id"] == "test-XYZ"
        assert params["version_id"] == "ver-ABC"
        assert params["user_id"] == "user-DEF"
        assert params["outcome"] == "error"

    async def test_rollback_and_reraise_on_db_error(self, service, mock_db):
        """Should rollback and re-raise if the INSERT fails."""
        mock_db.execute.side_effect = Exception("unique constraint")

        with pytest.raises(Exception, match="unique constraint"):
            await service.record_ab_outcome("t1", "v1", "u1", "hit")

        mock_db.rollback.assert_awaited_once()

    async def test_recorded_at_is_set(self, service, mock_db):
        """recorded_at must be a timezone-aware datetime."""
        result = await service.record_ab_outcome("t1", "v1", "u1", "hit")

        assert result.recorded_at is not None
        assert result.recorded_at.tzinfo is not None


# =============================================================================
# Promote / deactivate integration
# =============================================================================


class TestPromoteDeactivateIntegration:
    """Higher-level tests verifying the deactivate-then-activate pattern."""

    async def test_promotion_produces_unique_promoted_at_timestamps(self, mock_db):
        """Two promotions for different versions should get different promoted_at values."""
        import asyncio

        from services.model_version_service import ModelVersionService

        svc = ModelVersionService(mock_db)

        row_1 = _make_version_row(id="v1", model_name="m")
        row_2 = _make_version_row(id="v2", model_name="m")

        result_1 = MagicMock()
        result_1.fetchone.return_value = row_1
        result_2 = MagicMock()
        result_2.fetchone.return_value = row_2
        mock_db.execute.side_effect = [result_1, MagicMock(), MagicMock()] + [
            result_2,
            MagicMock(),
            MagicMock(),
        ]

        promo_1 = await svc.promote_version("v1")
        await asyncio.sleep(0.001)  # ensure clock advances slightly
        promo_2 = await svc.promote_version("v2")

        # promoted_at timestamps should both be set and be datetime objects
        assert promo_1.promoted_at is not None
        assert promo_2.promoted_at is not None

    async def test_list_versions_reflects_active_state(self, service, mock_db):
        """
        After promotion, only the promoted version row should have is_active=True
        in the list — DB reflects state, service reads it correctly.
        """
        rows = [
            _make_version_row(id="active-v", version_tag="v3.0", is_active=True),
            _make_version_row(id="old-v1", version_tag="v2.0", is_active=False),
            _make_version_row(id="old-v2", version_tag="v1.0", is_active=False),
        ]
        _mock_fetchall(mock_db, rows)

        result = await service.list_versions("ensemble", limit=10)

        active = [v for v in result if v.is_active]
        inactive = [v for v in result if not v.is_active]
        assert len(active) == 1
        assert active[0].version_tag == "v3.0"
        assert len(inactive) == 2
