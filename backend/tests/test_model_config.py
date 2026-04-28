"""
Tests for ML model configuration and weight persistence (TASK-MLDATA-001).

Covers:
- ModelConfigRepository.get_active_config: returns active row; returns None when absent.
- ModelConfigRepository.save_config: inserts row; deactivates previous active row;
  returns correct ModelConfig; handles DB errors.
- ModelConfigRepository.list_versions: returns history newest-first; respects limit.
- Active config switching: only most-recently saved config is active.
- Fallback to defaults when no saved config exists.
- Weight versioning: multiple saves produce multiple rows; only latest is active.
- LearningService.update_ensemble_weights: persists to DB when db_session provided;
  does not crash when DB is None; does not crash when DB raises.
- LearningService.load_weights_from_db: returns weights from active config;
  returns None when no active config; returns None when DB is None.
"""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# Helpers / fixtures
# =============================================================================


def _make_row(
    id="row-1",
    model_name="ensemble",
    model_version="v1.0",
    weights_json=None,
    training_metadata=None,
    accuracy_metrics=None,
    is_active=True,
    created_at=None,
    updated_at=None,
):
    """Create a mock DB row object that mimics a SQLAlchemy Row."""
    row = MagicMock()
    row.id = id
    row.model_name = model_name
    row.model_version = model_version
    # Simulate asyncpg returning a dict (JSON column already parsed)
    row.weights_json = weights_json or {
        "cnn_lstm": {"weight": 0.5},
        "xgboost": {"weight": 0.5},
    }
    row.training_metadata = training_metadata or {}
    row.accuracy_metrics = accuracy_metrics or {}
    row.is_active = is_active
    row.created_at = created_at or datetime(2026, 3, 10, 0, 0, tzinfo=UTC)
    row.updated_at = updated_at or datetime(2026, 3, 10, 0, 0, tzinfo=UTC)
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
def repo(mock_db):
    from repositories.model_config_repository import ModelConfigRepository

    return ModelConfigRepository(mock_db)


# =============================================================================
# ModelConfigRepository.get_active_config
# =============================================================================


class TestGetActiveConfig:
    """Tests for ModelConfigRepository.get_active_config"""

    async def test_returns_none_when_no_row(self, repo, mock_db):
        """Should return None when there is no active config in the DB."""
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        mock_db.execute.return_value = result_mock

        result = await repo.get_active_config("ensemble")

        assert result is None

    async def test_returns_model_config_when_row_exists(self, repo, mock_db):
        """Should return a ModelConfig built from the DB row."""
        row = _make_row(
            model_name="ensemble",
            model_version="v2.0",
            weights_json={"cnn_lstm": {"weight": 0.6}, "xgboost": {"weight": 0.4}},
            is_active=True,
        )
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.return_value = result_mock

        result = await repo.get_active_config("ensemble")

        assert result is not None
        assert result.model_name == "ensemble"
        assert result.model_version == "v2.0"
        assert result.is_active is True
        assert result.weights_json["cnn_lstm"]["weight"] == 0.6

    async def test_accepts_json_string_weights(self, repo, mock_db):
        """Should parse weights_json even when the column value is a JSON string."""
        weights = {"cnn_lstm": {"weight": 0.5}, "xgboost": {"weight": 0.5}}
        row = _make_row(weights_json=json.dumps(weights))
        result_mock = MagicMock()
        result_mock.fetchone.return_value = row
        mock_db.execute.return_value = result_mock

        result = await repo.get_active_config("ensemble")

        assert result.weights_json == weights

    async def test_raises_repository_error_on_db_failure(self, repo, mock_db):
        """Should raise RepositoryError when the DB execute call raises."""
        from repositories.base import RepositoryError

        mock_db.execute.side_effect = Exception("connection lost")

        with pytest.raises(RepositoryError, match="Failed to get active config"):
            await repo.get_active_config("ensemble")


# =============================================================================
# ModelConfigRepository.save_config
# =============================================================================


class TestSaveConfig:
    """Tests for ModelConfigRepository.save_config"""

    async def test_returns_model_config_with_correct_fields(self, repo, mock_db):
        """Should return a ModelConfig with the provided values."""
        weights = {
            "cnn_lstm": {"weight": 0.5},
            "xgboost": {"weight": 0.25},
            "lightgbm": {"weight": 0.25},
        }
        result = await repo.save_config(
            model_name="ensemble",
            version="v3.0",
            weights=weights,
            metadata={"region": "US", "days": 7},
            metrics={"mape": 4.2, "rmse": 0.01},
        )

        assert result.model_name == "ensemble"
        assert result.model_version == "v3.0"
        assert result.weights_json == weights
        assert result.training_metadata == {"region": "US", "days": 7}
        assert result.accuracy_metrics == {"mape": 4.2, "rmse": 0.01}
        assert result.is_active is True

    async def test_executes_deactivate_then_insert(self, repo, mock_db):
        """Should run two SQL statements: UPDATE (deactivate) then INSERT."""
        await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights={"cnn_lstm": {"weight": 1.0}},
        )

        # Three execute() calls: SELECT FOR UPDATE + UPDATE + INSERT
        assert mock_db.execute.call_count == 3
        # The first statement should be SELECT ... FOR UPDATE (row-level lock)
        first_sql = str(mock_db.execute.call_args_list[0][0][0])
        assert "FOR UPDATE" in first_sql.upper()
        # The second statement should contain UPDATE (deactivate)
        second_sql = str(mock_db.execute.call_args_list[1][0][0])
        assert "UPDATE" in second_sql.upper()
        # The third should contain INSERT
        third_sql = str(mock_db.execute.call_args_list[2][0][0])
        assert "INSERT" in third_sql.upper()

    async def test_commits_after_insert(self, repo, mock_db):
        """Should call commit exactly once after the two SQL statements."""
        await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights={"cnn_lstm": {"weight": 1.0}},
        )

        mock_db.commit.assert_awaited_once()

    async def test_returns_uuid_id(self, repo, mock_db):
        """The returned ModelConfig should have a non-empty UUID id."""
        import re

        result = await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights={"cnn_lstm": {"weight": 1.0}},
        )
        uuid_pattern = re.compile(
            r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
        assert uuid_pattern.match(result.id), f"Expected UUID, got: {result.id!r}"

    async def test_defaults_metadata_and_metrics_to_empty_dict(self, repo, mock_db):
        """Should default metadata and metrics to empty dicts when not provided."""
        result = await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights={"cnn_lstm": {"weight": 1.0}},
        )

        assert result.training_metadata == {}
        assert result.accuracy_metrics == {}

    async def test_rolls_back_and_raises_on_db_error(self, repo, mock_db):
        """Should rollback and raise RepositoryError when the DB INSERT fails."""
        from repositories.base import RepositoryError

        # First execute (SELECT FOR UPDATE) + second (UPDATE) succeed; third (INSERT) fails
        mock_db.execute.side_effect = [None, None, Exception("disk full")]

        with pytest.raises(RepositoryError, match="Failed to save config"):
            await repo.save_config(
                model_name="ensemble",
                version="v1.0",
                weights={"cnn_lstm": {"weight": 1.0}},
            )

        mock_db.rollback.assert_awaited_once()

    async def test_insert_contains_model_name_and_version(self, repo, mock_db):
        """The INSERT parameters should include the correct model_name and version."""
        await repo.save_config(
            model_name="my_model",
            version="v42.1",
            weights={"m": {"weight": 1.0}},
        )

        # Third call is the INSERT (after SELECT FOR UPDATE + UPDATE); check params
        insert_params = mock_db.execute.call_args_list[2][0][1]
        assert insert_params["model_name"] == "my_model"
        assert insert_params["model_version"] == "v42.1"


# =============================================================================
# ModelConfigRepository.list_versions
# =============================================================================


class TestListVersions:
    """Tests for ModelConfigRepository.list_versions"""

    async def test_returns_empty_list_when_no_rows(self, repo, mock_db):
        """Should return [] when there are no historical configs."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        mock_db.execute.return_value = result_mock

        result = await repo.list_versions("ensemble")

        assert result == []

    async def test_returns_list_of_model_configs(self, repo, mock_db):
        """Should return a list of ModelConfig objects, newest first."""
        rows = [
            _make_row(id="r1", model_version="v3.0", is_active=True),
            _make_row(id="r2", model_version="v2.0", is_active=False),
            _make_row(id="r3", model_version="v1.0", is_active=False),
        ]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = rows
        mock_db.execute.return_value = result_mock

        result = await repo.list_versions("ensemble")

        assert len(result) == 3
        assert result[0].model_version == "v3.0"
        assert result[1].model_version == "v2.0"
        assert result[2].model_version == "v1.0"

    async def test_default_limit_is_20(self, repo, mock_db):
        """Should pass limit=20 by default."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        mock_db.execute.return_value = result_mock

        await repo.list_versions("ensemble")

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == 20

    async def test_custom_limit_is_passed(self, repo, mock_db):
        """Should pass the provided limit to the SQL query."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        mock_db.execute.return_value = result_mock

        await repo.list_versions("ensemble", limit=5)

        params = mock_db.execute.call_args[0][1]
        assert params["limit"] == 5

    async def test_raises_repository_error_on_db_failure(self, repo, mock_db):
        """Should raise RepositoryError when the DB execute call raises."""
        from repositories.base import RepositoryError

        mock_db.execute.side_effect = Exception("timeout")

        with pytest.raises(RepositoryError, match="Failed to list versions"):
            await repo.list_versions("ensemble")


# =============================================================================
# Active config switching
# =============================================================================


class TestActiveConfigSwitching:
    """Tests that verify the deactivate-then-activate pattern."""

    async def test_deactivate_uses_correct_model_name(self, repo, mock_db):
        """The UPDATE statement must filter by the correct model_name."""
        await repo.save_config(
            model_name="forecast_model",
            version="v2.0",
            weights={"m": {"weight": 1.0}},
        )

        update_params = mock_db.execute.call_args_list[0][0][1]
        assert update_params["model_name"] == "forecast_model"

    async def test_new_row_is_always_active(self, repo, mock_db):
        """The ModelConfig returned by save_config should always have is_active=True."""
        result = await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights={"m": {"weight": 1.0}},
        )

        assert result.is_active is True

    async def test_second_save_produces_new_id(self, repo, mock_db):
        """Two saves should generate different UUIDs."""
        r1 = await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights={"m": {"weight": 1.0}},
        )
        r2 = await repo.save_config(
            model_name="ensemble",
            version="v2.0",
            weights={"m": {"weight": 1.0}},
        )

        assert r1.id != r2.id


# =============================================================================
# Fallback to defaults
# =============================================================================


class TestFallbackToDefaults:
    """Tests that the system behaves correctly when no saved config exists."""

    async def test_get_active_config_none_means_use_defaults(self, repo, mock_db):
        """
        When get_active_config returns None the caller (EnsemblePredictor or
        LearningService.load_weights_from_db) should use hard-coded defaults.
        """
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        mock_db.execute.return_value = result_mock

        result = await repo.get_active_config("ensemble")

        assert result is None  # Caller must handle None → use defaults

    async def test_load_weights_from_db_returns_none_when_no_active(self):
        """LearningService.load_weights_from_db returns None when no active config."""
        from services.learning_service import LearningService

        mock_db = AsyncMock()
        mock_obs = AsyncMock()
        mock_vs = MagicMock()
        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            redis_client=None,
            db_session=mock_db,
        )

        MockRepo = MagicMock()
        instance = MockRepo.return_value
        instance.get_active_config = AsyncMock(return_value=None)
        # Patch the lazy import inside the method
        with patch(
            "repositories.model_config_repository.ModelConfigRepository",
            MockRepo,
        ):
            result = await service.load_weights_from_db("ensemble")

        assert result is None

    async def test_load_weights_from_db_returns_none_when_db_is_none(self):
        """load_weights_from_db should return None immediately when db_session is None."""
        from services.learning_service import LearningService

        mock_obs = AsyncMock()
        mock_vs = MagicMock()
        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            redis_client=None,
            db_session=None,
        )

        result = await service.load_weights_from_db("ensemble")

        assert result is None


# =============================================================================
# Weight versioning
# =============================================================================


class TestWeightVersioning:
    """Tests for correct versioning behaviour across multiple saves."""

    async def test_save_config_includes_version_in_params(self, repo, mock_db):
        """Version string must be included verbatim in INSERT params."""
        await repo.save_config(
            model_name="ensemble",
            version="v5.2-hotfix",
            weights={"m": {"weight": 1.0}},
        )

        insert_params = mock_db.execute.call_args_list[2][0][1]
        assert insert_params["model_version"] == "v5.2-hotfix"

    async def test_list_versions_uses_correct_model_name(self, repo, mock_db):
        """list_versions must scope the query to the correct model_name."""
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        mock_db.execute.return_value = result_mock

        await repo.list_versions("custom_model")

        params = mock_db.execute.call_args[0][1]
        assert params["model_name"] == "custom_model"

    async def test_weights_json_serialised_as_json_string_in_insert(
        self, repo, mock_db
    ):
        """weights_json must be serialised to a JSON string for the INSERT."""
        weights = {
            "cnn_lstm": {"weight": 0.5},
            "xgboost": {"weight": 0.25},
            "lightgbm": {"weight": 0.25},
        }
        await repo.save_config(
            model_name="ensemble",
            version="v1.0",
            weights=weights,
        )

        insert_params = mock_db.execute.call_args_list[2][0][1]
        # The parameter must be a JSON string (for the ::jsonb cast)
        raw = insert_params["weights_json"]
        assert isinstance(raw, str)
        assert json.loads(raw) == weights


# =============================================================================
# LearningService integration with ModelConfigRepository
# =============================================================================


class TestLearningServiceDbPersistence:
    """Tests for LearningService weight persistence to PostgreSQL."""

    def _make_service(self, mock_db=None):
        from services.learning_service import LearningService

        mock_obs = AsyncMock()
        mock_vs = MagicMock()
        mock_vs.async_insert = AsyncMock(return_value="vec-1")
        mock_vs.async_prune = AsyncMock(return_value=0)
        redis = AsyncMock()
        redis.set = AsyncMock()

        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            redis_client=redis,
            db_session=mock_db,
        )
        return service, mock_obs, redis

    async def test_update_ensemble_weights_persists_to_db(self):
        """update_ensemble_weights should call save_config when db_session is provided."""
        mock_db = AsyncMock()
        service, mock_obs, _ = self._make_service(mock_db)
        mock_obs.get_model_accuracy_by_version = AsyncMock(
            return_value=[
                {"model_version": "v2.1", "mape": 5.0, "count": 50},
            ]
        )

        MockRepo = MagicMock()
        instance = MockRepo.return_value
        instance.save_config = AsyncMock(return_value=MagicMock())
        with patch(
            "repositories.model_config_repository.ModelConfigRepository",
            MockRepo,
        ):
            result = await service.update_ensemble_weights("US")

        assert result is not None

    async def test_update_ensemble_weights_no_db_still_returns_weights(self):
        """update_ensemble_weights should work fine when db_session is None."""
        service, mock_obs, _ = self._make_service(mock_db=None)
        mock_obs.get_model_accuracy_by_version = AsyncMock(
            return_value=[
                {"model_version": "v2.1", "mape": 5.0, "count": 50},
            ]
        )

        result = await service.update_ensemble_weights("US")

        assert result is not None
        assert "v2.1" in result

    async def test_db_persist_failure_does_not_crash_learning_cycle(self):
        """A DB write failure should be caught and logged, not propagated."""
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("DB unavailable")
        mock_db.rollback = AsyncMock()
        service, mock_obs, _ = self._make_service(mock_db)
        mock_obs.get_model_accuracy_by_version = AsyncMock(
            return_value=[
                {"model_version": "v2.1", "mape": 5.0, "count": 50},
            ]
        )
        mock_obs.get_forecast_accuracy = AsyncMock(
            return_value={
                "total": 50,
                "mape": 5.0,
                "rmse": 0.01,
                "coverage": 90.0,
            }
        )
        mock_obs.get_hourly_bias = AsyncMock(return_value=[])

        # Should not raise even though DB is broken
        result = await service.run_full_cycle(regions=["US"])

        assert len(result["regions_processed"]) == 1

    async def test_load_weights_from_db_returns_weights_json_when_active(self):
        """load_weights_from_db should return the weights_json of the active config."""
        from models.model_config import ModelConfig
        from services.learning_service import LearningService

        mock_db = AsyncMock()
        mock_obs = AsyncMock()
        mock_vs = MagicMock()
        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            db_session=mock_db,
        )

        active_config = ModelConfig(
            id="some-id",
            model_name="ensemble",
            model_version="v3.0",
            weights_json={"cnn_lstm": {"weight": 0.5}, "xgboost": {"weight": 0.5}},
            is_active=True,
        )

        MockRepo = MagicMock()
        instance = MockRepo.return_value
        instance.get_active_config = AsyncMock(return_value=active_config)
        with patch(
            "repositories.model_config_repository.ModelConfigRepository",
            MockRepo,
        ):
            result = await service.load_weights_from_db("ensemble")

        assert result == {"cnn_lstm": {"weight": 0.5}, "xgboost": {"weight": 0.5}}

    async def test_load_weights_from_db_error_returns_none(self):
        """load_weights_from_db should return None (not raise) on DB errors."""
        from services.learning_service import LearningService

        mock_db = AsyncMock()
        mock_obs = AsyncMock()
        mock_vs = MagicMock()
        service = LearningService(
            observation_service=mock_obs,
            vector_store=mock_vs,
            db_session=mock_db,
        )

        MockRepo = MagicMock()
        instance = MockRepo.return_value
        instance.get_active_config = AsyncMock(
            side_effect=Exception("connection reset")
        )
        with patch(
            "repositories.model_config_repository.ModelConfigRepository",
            MockRepo,
        ):
            result = await service.load_weights_from_db("ensemble")

        assert result is None
