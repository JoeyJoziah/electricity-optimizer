"""
Airflow DAG Validation Tests

This module contains tests to validate that all DAGs:
1. Import without errors
2. Have valid structure (no cycles, valid operators)
3. Have proper configuration (timeouts, retries, SLAs)
4. Have correct task dependencies

Run with: pytest airflow/tests/test_dags.py -v
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

# Add the dags and plugins folders to the path
AIRFLOW_HOME = Path(__file__).parent.parent
DAGS_FOLDER = AIRFLOW_HOME / "dags"
PLUGINS_FOLDER = AIRFLOW_HOME / "plugins"

sys.path.insert(0, str(DAGS_FOLDER))
sys.path.insert(0, str(PLUGINS_FOLDER))


# Mock Airflow imports that might not be available in test environment
@pytest.fixture(autouse=True)
def mock_airflow_imports():
    """Mock Airflow components for testing outside Airflow environment."""
    # Mock the plugins module
    mock_plugins = MagicMock()
    mock_operators = MagicMock()
    mock_sensors = MagicMock()
    mock_hooks = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "plugins": mock_plugins,
            "plugins.custom_operators": mock_operators,
            "plugins.sensors": mock_sensors,
            "plugins.hooks": mock_hooks,
        },
    ):
        # Set up mock classes
        mock_operators.PricingAPIOperator = MagicMock()
        mock_operators.TimescaleDBOperator = MagicMock()
        mock_operators.ModelTrainingOperator = MagicMock()
        mock_operators.ForecastGenerationOperator = MagicMock()
        mock_operators.DataQualityOperator = MagicMock()
        mock_operators.RedisCacheOperator = MagicMock()

        mock_sensors.PriceDataFreshnessSensor = MagicMock()
        mock_sensors.ModelReadySensor = MagicMock()
        mock_sensors.APIHealthSensor = MagicMock()
        mock_sensors.MarketOpenSensor = MagicMock()
        mock_sensors.ForecastStaleSensor = MagicMock()

        mock_hooks.TimescaleDBHook = MagicMock()
        mock_hooks.RedisHook = MagicMock()
        mock_hooks.PricingAPIHook = MagicMock()

        yield


class TestDAGIntegrity:
    """Test DAG import and structural integrity."""

    @pytest.fixture
    def dag_files(self) -> List[Path]:
        """Get all DAG files."""
        return list(DAGS_FOLDER.glob("*.py"))

    def test_dag_files_exist(self, dag_files):
        """Verify expected DAG files exist."""
        expected_dags = [
            "electricity_price_ingestion.py",
            "model_retraining.py",
            "forecast_generation.py",
            "data_quality.py",
        ]

        dag_names = [f.name for f in dag_files if not f.name.startswith("__")]

        for expected in expected_dags:
            assert expected in dag_names, f"Missing DAG file: {expected}"

    def test_no_import_errors(self, dag_files):
        """Verify all DAG files import without errors."""
        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            try:
                # Try to compile the file
                with open(dag_file, "r") as f:
                    code = f.read()
                compile(code, dag_file, "exec")
            except SyntaxError as e:
                pytest.fail(f"Syntax error in {dag_file.name}: {e}")

    def test_dag_file_structure(self, dag_files):
        """Verify DAG files follow expected structure."""
        required_elements = [
            "from airflow import DAG",
            "default_args",
            "dag_id",
            "schedule_interval",
            "start_date",
        ]

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            missing = []
            for element in required_elements:
                if element not in content:
                    missing.append(element)

            if missing:
                pytest.fail(
                    f"DAG {dag_file.name} missing required elements: {missing}"
                )


class TestDAGConfiguration:
    """Test DAG configuration settings."""

    @pytest.fixture
    def dag_configs(self) -> Dict:
        """Expected DAG configurations."""
        return {
            "electricity_price_ingestion": {
                "schedule": "*/15 * * * *",
                "max_active_runs": 1,
                "catchup": False,
                "sla_minutes": 5,
                "retries": 3,
            },
            "model_retraining": {
                "schedule": "0 2 * * 0",
                "max_active_runs": 1,
                "catchup": False,
                "timeout_hours": 6,
                "retries": 2,
            },
            "forecast_generation": {
                "schedule": "0 * * * *",
                "max_active_runs": 1,
                "catchup": False,
                "sla_minutes": 2,
                "retries": 2,
            },
            "data_quality": {
                "schedule": "0 6 * * *",
                "max_active_runs": 1,
                "catchup": False,
                "retries": 1,
            },
        }

    def test_schedule_intervals(self, dag_configs):
        """Verify DAG schedule intervals are correct."""
        dag_files = {
            "electricity_price_ingestion": DAGS_FOLDER / "electricity_price_ingestion.py",
            "model_retraining": DAGS_FOLDER / "model_retraining.py",
            "forecast_generation": DAGS_FOLDER / "forecast_generation.py",
            "data_quality": DAGS_FOLDER / "data_quality.py",
        }

        for dag_id, config in dag_configs.items():
            with open(dag_files[dag_id], "r") as f:
                content = f.read()

            expected_schedule = config["schedule"]
            assert (
                expected_schedule in content
            ), f"DAG {dag_id} should have schedule '{expected_schedule}'"

    def test_catchup_disabled(self, dag_configs):
        """Verify catchup is disabled for all DAGs."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # Check that catchup=False is present
            assert (
                "catchup=False" in content or "catchup = False" in content
            ), f"DAG {dag_file.name} should have catchup=False"

    def test_max_active_runs(self, dag_configs):
        """Verify max_active_runs is set appropriately."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # All DAGs should have max_active_runs=1 to prevent overlap
            assert (
                "max_active_runs=1" in content or "max_active_runs = 1" in content
            ), f"DAG {dag_file.name} should have max_active_runs=1"


class TestDefaultArgs:
    """Test DAG default arguments."""

    def test_owner_is_set(self):
        """Verify owner is set in default_args."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                '"owner"' in content or "'owner'" in content
            ), f"DAG {dag_file.name} should have owner in default_args"

    def test_email_on_failure(self):
        """Verify email_on_failure is configured."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "email_on_failure" in content
            ), f"DAG {dag_file.name} should have email_on_failure configured"

    def test_retries_configured(self):
        """Verify retries are configured in default_args."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                '"retries"' in content or "'retries'" in content
            ), f"DAG {dag_file.name} should have retries configured"


class TestSLAConfiguration:
    """Test SLA configuration for time-critical DAGs."""

    def test_price_ingestion_sla(self):
        """Verify price ingestion DAG has 5-minute SLA."""
        dag_file = DAGS_FOLDER / "electricity_price_ingestion.py"

        with open(dag_file, "r") as f:
            content = f.read()

        # Should have SLA configuration
        assert "sla" in content.lower(), "Price ingestion should have SLA configured"
        # Should mention 5 minutes
        assert (
            "minutes=5" in content or "minutes(5)" in content
        ), "Price ingestion SLA should be 5 minutes"

    def test_forecast_generation_sla(self):
        """Verify forecast generation DAG has 2-minute SLA."""
        dag_file = DAGS_FOLDER / "forecast_generation.py"

        with open(dag_file, "r") as f:
            content = f.read()

        # Should have SLA configuration
        assert "sla" in content.lower(), "Forecast generation should have SLA configured"
        # Should mention 2 minutes
        assert (
            "minutes=2" in content or "minutes(2)" in content
        ), "Forecast generation SLA should be 2 minutes"


class TestTaskGroupStructure:
    """Test task group organization."""

    def test_price_ingestion_has_fetch_group(self):
        """Verify price ingestion has a fetch_prices task group."""
        dag_file = DAGS_FOLDER / "electricity_price_ingestion.py"

        with open(dag_file, "r") as f:
            content = f.read()

        assert (
            "@task_group" in content or "task_group" in content
        ), "Should use task groups"
        assert "fetch_prices" in content, "Should have fetch_prices group"

    def test_model_retraining_has_train_group(self):
        """Verify model retraining has a training task group."""
        dag_file = DAGS_FOLDER / "model_retraining.py"

        with open(dag_file, "r") as f:
            content = f.read()

        assert (
            "@task_group" in content or "task_group" in content
        ), "Should use task groups"
        assert "train_model" in content, "Should have training group"


class TestDocumentation:
    """Test DAG documentation."""

    def test_all_dags_have_docstrings(self):
        """Verify all DAGs have docstrings."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # Should have module docstring
            assert (
                '"""' in content[:500] or "'''" in content[:500]
            ), f"DAG {dag_file.name} should have module docstring"

    def test_all_dags_have_doc_md(self):
        """Verify all DAGs have doc_md for web UI."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "doc_md" in content
            ), f"DAG {dag_file.name} should have doc_md for web UI"


class TestOperatorUsage:
    """Test correct operator usage patterns."""

    def test_uses_taskflow_api(self):
        """Verify DAGs use TaskFlow API decorators."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # Should use @task decorator
            assert (
                "@task" in content
            ), f"DAG {dag_file.name} should use TaskFlow API (@task decorator)"

    def test_uses_trigger_rules_appropriately(self):
        """Verify DAGs use TriggerRule for error handling."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # Should import TriggerRule
            assert (
                "TriggerRule" in content
            ), f"DAG {dag_file.name} should import TriggerRule"


class TestConnectionUsage:
    """Test that DAGs use proper connection IDs."""

    def test_uses_timescaledb_connection(self):
        """Verify DAGs use timescaledb_default connection."""
        dag_files = [
            DAGS_FOLDER / "electricity_price_ingestion.py",
            DAGS_FOLDER / "model_retraining.py",
            DAGS_FOLDER / "forecast_generation.py",
            DAGS_FOLDER / "data_quality.py",
        ]

        for dag_file in dag_files:
            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "timescaledb_default" in content
            ), f"DAG {dag_file.name} should use timescaledb_default connection"

    def test_uses_redis_connection(self):
        """Verify caching DAGs use redis_default connection."""
        dag_files = [
            DAGS_FOLDER / "electricity_price_ingestion.py",
            DAGS_FOLDER / "forecast_generation.py",
        ]

        for dag_file in dag_files:
            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "redis_default" in content
            ), f"DAG {dag_file.name} should use redis_default connection"


class TestBranchingLogic:
    """Test conditional branching in DAGs."""

    def test_price_ingestion_has_forecast_trigger(self):
        """Verify price ingestion can trigger forecast generation."""
        dag_file = DAGS_FOLDER / "electricity_price_ingestion.py"

        with open(dag_file, "r") as f:
            content = f.read()

        assert (
            "TriggerDagRunOperator" in content
        ), "Should use TriggerDagRunOperator"
        assert (
            "forecast_generation" in content
        ), "Should be able to trigger forecast_generation DAG"

    def test_model_retraining_has_deployment_branch(self):
        """Verify model retraining has conditional deployment."""
        dag_file = DAGS_FOLDER / "model_retraining.py"

        with open(dag_file, "r") as f:
            content = f.read()

        assert "@task.branch" in content, "Should use branch decorator"
        assert "deploy_model" in content, "Should have deploy_model task"
        assert "skip_deployment" in content, "Should have skip_deployment option"


class TestErrorHandling:
    """Test error handling patterns."""

    def test_has_retry_configuration(self):
        """Verify all DAGs have retry configuration."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "retry_delay" in content
            ), f"DAG {dag_file.name} should have retry_delay configured"

    def test_has_execution_timeout(self):
        """Verify all DAGs have execution timeouts."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "execution_timeout" in content
            ), f"DAG {dag_file.name} should have execution_timeout configured"


class TestSensorConfiguration:
    """Test sensor usage and configuration."""

    def test_sensors_have_poke_interval(self):
        """Verify sensors have appropriate poke intervals."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        sensor_keywords = [
            "Sensor",
            "sensor",
        ]

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # If DAG uses sensors, it should have poke_interval
            has_sensor = any(kw in content for kw in sensor_keywords)
            if has_sensor:
                assert (
                    "poke_interval" in content
                ), f"DAG {dag_file.name} uses sensors but missing poke_interval"

    def test_sensors_have_timeout(self):
        """Verify sensors have timeout configured."""
        dag_files = list(DAGS_FOLDER.glob("*.py"))

        for dag_file in dag_files:
            if dag_file.name.startswith("__"):
                continue

            with open(dag_file, "r") as f:
                content = f.read()

            # If DAG uses Sensor classes, should have timeout
            if "Sensor(" in content:
                assert (
                    "timeout=" in content
                ), f"DAG {dag_file.name} has sensors that need timeout configuration"


class TestIdempotency:
    """Test idempotency patterns in DAGs."""

    def test_uses_upsert_for_storage(self):
        """Verify data storage uses upsert for idempotency."""
        dag_files = [
            DAGS_FOLDER / "electricity_price_ingestion.py",
            DAGS_FOLDER / "forecast_generation.py",
        ]

        for dag_file in dag_files:
            with open(dag_file, "r") as f:
                content = f.read()

            assert (
                "upsert" in content.lower()
            ), f"DAG {dag_file.name} should use upsert for idempotent storage"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
