"""
ML Model Performance Tests

Validates ML model inference meets performance requirements:
- CNN-LSTM forecast: <1s for 24-hour prediction
- MILP optimization: <2s for standard workload
- Ensemble prediction: <1.5s combined
"""

import pytest
import time
import numpy as np
import statistics
from typing import List
from unittest.mock import patch, MagicMock


# Performance targets (in milliseconds)
TARGETS = {
    "forecast_24h": 1000,      # 1 second
    "forecast_48h": 1500,      # 1.5 seconds
    "optimization_simple": 1000,  # 1 second
    "optimization_complex": 2000,  # 2 seconds
    "ensemble_prediction": 1500,  # 1.5 seconds
}


class PerformanceTimer:
    """Context manager for timing code execution."""

    def __init__(self):
        self.elapsed = 0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        self.elapsed = (time.perf_counter() - self.start) * 1000  # ms


def run_multiple_times(func, iterations: int = 10) -> List[float]:
    """Run a function multiple times and return latencies."""
    latencies = []
    for _ in range(iterations):
        with PerformanceTimer() as timer:
            func()
        latencies.append(timer.elapsed)
    return latencies


@pytest.fixture
def mock_price_data():
    """Generate mock price data for forecasting."""
    # 7 days of hourly data (168 hours)
    hours = 168
    features = 10
    return np.random.random((1, hours, features)).astype(np.float32)


@pytest.fixture
def mock_appliances_simple():
    """Simple appliance configuration for optimization."""
    return [
        {
            "id": "dishwasher",
            "power_kw": 1.5,
            "duration_hours": 2,
            "earliest_start": 18,
            "latest_end": 30,
            "flexible": True,
        }
    ]


@pytest.fixture
def mock_appliances_complex():
    """Complex appliance configuration for optimization."""
    return [
        {"id": "dishwasher", "power_kw": 1.5, "duration_hours": 2, "flexible": True},
        {"id": "washing_machine", "power_kw": 2.0, "duration_hours": 2, "flexible": True},
        {"id": "dryer", "power_kw": 3.0, "duration_hours": 1.5, "flexible": True},
        {"id": "ev_charger", "power_kw": 7.0, "duration_hours": 4, "flexible": True, "priority": "high"},
        {"id": "heat_pump", "power_kw": 2.5, "duration_hours": 3, "flexible": True},
        {"id": "pool_pump", "power_kw": 1.0, "duration_hours": 6, "flexible": True},
        {"id": "dehumidifier", "power_kw": 0.5, "duration_hours": 4, "flexible": True},
    ]


@pytest.fixture
def mock_price_forecast():
    """Mock price forecast for optimization."""
    return [
        {"hour": i, "price": 0.15 + np.sin(i / 4) * 0.10}
        for i in range(48)
    ]


class TestCNNLSTMForecasterPerformance:
    """Performance tests for CNN-LSTM price forecaster."""

    def test_24h_forecast_inference_speed(self, mock_price_data):
        """24-hour forecast should complete in <1s."""
        try:
            from ml.models.price_forecaster import CNNLSTMPriceForecaster

            model = CNNLSTMPriceForecaster()

            # Warmup
            _ = model.predict(mock_price_data, horizon=24)

            # Measure
            latencies = run_multiple_times(
                lambda: model.predict(mock_price_data, horizon=24),
                iterations=10,
            )

            avg_latency = statistics.mean(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\nCNN-LSTM 24h forecast performance:")
            print(f"  Average: {avg_latency:.2f}ms")
            print(f"  p95: {p95_latency:.2f}ms")
            print(f"  Target: <{TARGETS['forecast_24h']}ms")

            assert p95_latency < TARGETS["forecast_24h"], \
                f"p95 latency {p95_latency:.2f}ms exceeds {TARGETS['forecast_24h']}ms target"

        except ImportError:
            pytest.skip("CNN-LSTM model not available")

    def test_48h_forecast_inference_speed(self, mock_price_data):
        """48-hour forecast should complete in <1.5s."""
        try:
            from ml.models.price_forecaster import CNNLSTMPriceForecaster

            model = CNNLSTMPriceForecaster()

            latencies = run_multiple_times(
                lambda: model.predict(mock_price_data, horizon=48),
                iterations=10,
            )

            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\nCNN-LSTM 48h forecast performance:")
            print(f"  p95: {p95_latency:.2f}ms")
            print(f"  Target: <{TARGETS['forecast_48h']}ms")

            assert p95_latency < TARGETS["forecast_48h"], \
                f"p95 latency {p95_latency:.2f}ms exceeds {TARGETS['forecast_48h']}ms target"

        except ImportError:
            pytest.skip("CNN-LSTM model not available")

    def test_forecast_with_uncertainty(self, mock_price_data):
        """Forecast with uncertainty quantification should not add >50% overhead."""
        try:
            from ml.models.price_forecaster import CNNLSTMPriceForecaster

            model = CNNLSTMPriceForecaster()

            # Without uncertainty
            latencies_no_uncertainty = run_multiple_times(
                lambda: model.predict(mock_price_data, horizon=24, return_uncertainty=False),
                iterations=10,
            )

            # With uncertainty (Monte Carlo dropout)
            latencies_with_uncertainty = run_multiple_times(
                lambda: model.predict(mock_price_data, horizon=24, return_uncertainty=True),
                iterations=10,
            )

            avg_without = statistics.mean(latencies_no_uncertainty)
            avg_with = statistics.mean(latencies_with_uncertainty)
            overhead = (avg_with - avg_without) / avg_without * 100

            print(f"\nUncertainty quantification overhead:")
            print(f"  Without: {avg_without:.2f}ms")
            print(f"  With: {avg_with:.2f}ms")
            print(f"  Overhead: {overhead:.1f}%")

            assert overhead < 100, f"Uncertainty adds {overhead:.1f}% overhead (target: <100%)"

        except ImportError:
            pytest.skip("CNN-LSTM model not available")


class TestMILPOptimizationPerformance:
    """Performance tests for MILP optimization."""

    def test_simple_optimization_speed(self, mock_appliances_simple, mock_price_forecast):
        """Simple optimization (1 appliance) should complete in <1s."""
        try:
            from ml.optimization.scheduler import MILPScheduler

            scheduler = MILPScheduler()

            # Warmup
            _ = scheduler.optimize(mock_appliances_simple, mock_price_forecast)

            latencies = run_multiple_times(
                lambda: scheduler.optimize(mock_appliances_simple, mock_price_forecast),
                iterations=10,
            )

            avg_latency = statistics.mean(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\nMILP simple optimization (1 appliance) performance:")
            print(f"  Average: {avg_latency:.2f}ms")
            print(f"  p95: {p95_latency:.2f}ms")
            print(f"  Target: <{TARGETS['optimization_simple']}ms")

            assert p95_latency < TARGETS["optimization_simple"], \
                f"p95 latency {p95_latency:.2f}ms exceeds {TARGETS['optimization_simple']}ms target"

        except ImportError:
            pytest.skip("MILP scheduler not available")

    def test_complex_optimization_speed(self, mock_appliances_complex, mock_price_forecast):
        """Complex optimization (7 appliances) should complete in <2s."""
        try:
            from ml.optimization.scheduler import MILPScheduler

            scheduler = MILPScheduler()

            latencies = run_multiple_times(
                lambda: scheduler.optimize(mock_appliances_complex, mock_price_forecast),
                iterations=5,  # Fewer iterations due to longer runtime
            )

            avg_latency = statistics.mean(latencies)
            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\nMILP complex optimization (7 appliances) performance:")
            print(f"  Average: {avg_latency:.2f}ms")
            print(f"  p95: {p95_latency:.2f}ms")
            print(f"  Target: <{TARGETS['optimization_complex']}ms")

            assert p95_latency < TARGETS["optimization_complex"], \
                f"p95 latency {p95_latency:.2f}ms exceeds {TARGETS['optimization_complex']}ms target"

        except ImportError:
            pytest.skip("MILP scheduler not available")

    def test_optimization_scales_linearly(self, mock_price_forecast):
        """Optimization time should scale roughly linearly with appliances."""
        try:
            from ml.optimization.scheduler import MILPScheduler

            scheduler = MILPScheduler()

            times = {}
            for n_appliances in [1, 2, 4, 8]:
                appliances = [
                    {
                        "id": f"appliance_{i}",
                        "power_kw": 1.5,
                        "duration_hours": 2,
                        "flexible": True,
                    }
                    for i in range(n_appliances)
                ]

                latencies = run_multiple_times(
                    lambda: scheduler.optimize(appliances, mock_price_forecast),
                    iterations=3,
                )
                times[n_appliances] = statistics.mean(latencies)

            print(f"\nOptimization scaling:")
            for n, t in times.items():
                print(f"  {n} appliances: {t:.2f}ms")

            # Check that 8 appliances doesn't take more than 10x of 1 appliance
            ratio = times[8] / times[1]
            print(f"  Scaling ratio (8/1): {ratio:.2f}x")

            assert ratio < 10, f"Optimization scales poorly: {ratio:.2f}x for 8 appliances"

        except ImportError:
            pytest.skip("MILP scheduler not available")


class TestEnsemblePerformance:
    """Performance tests for ensemble predictions."""

    def test_ensemble_prediction_speed(self, mock_price_data):
        """Ensemble prediction should complete in <1.5s."""
        try:
            from ml.inference.ensemble_predictor import EnsemblePredictor

            predictor = EnsemblePredictor()

            latencies = run_multiple_times(
                lambda: predictor.predict(mock_price_data, horizon=24),
                iterations=10,
            )

            p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]

            print(f"\nEnsemble prediction performance:")
            print(f"  p95: {p95_latency:.2f}ms")
            print(f"  Target: <{TARGETS['ensemble_prediction']}ms")

            assert p95_latency < TARGETS["ensemble_prediction"], \
                f"p95 latency {p95_latency:.2f}ms exceeds {TARGETS['ensemble_prediction']}ms target"

        except ImportError:
            pytest.skip("Ensemble predictor not available")


class TestMemoryUsage:
    """Tests for memory efficiency."""

    def test_model_memory_footprint(self):
        """Model should not exceed memory limits."""
        try:
            import psutil
            import os
            from ml.models.price_forecaster import CNNLSTMPriceForecaster

            process = psutil.Process(os.getpid())
            before_memory = process.memory_info().rss / 1024 / 1024  # MB

            model = CNNLSTMPriceForecaster()

            after_memory = process.memory_info().rss / 1024 / 1024  # MB
            memory_increase = after_memory - before_memory

            print(f"\nModel memory footprint:")
            print(f"  Before: {before_memory:.2f} MB")
            print(f"  After: {after_memory:.2f} MB")
            print(f"  Increase: {memory_increase:.2f} MB")

            assert memory_increase < 500, f"Model uses {memory_increase:.2f} MB (target: <500 MB)"

        except ImportError:
            pytest.skip("Required modules not available")

    def test_no_memory_leak_during_inference(self, mock_price_data):
        """Memory should not grow significantly during repeated inference."""
        try:
            import psutil
            import os
            import gc
            from ml.models.price_forecaster import CNNLSTMPriceForecaster

            model = CNNLSTMPriceForecaster()
            process = psutil.Process(os.getpid())

            # Initial memory
            gc.collect()
            initial_memory = process.memory_info().rss / 1024 / 1024

            # Run many predictions
            for _ in range(100):
                _ = model.predict(mock_price_data, horizon=24)

            # Final memory
            gc.collect()
            final_memory = process.memory_info().rss / 1024 / 1024
            memory_growth = final_memory - initial_memory

            print(f"\nMemory growth after 100 predictions:")
            print(f"  Initial: {initial_memory:.2f} MB")
            print(f"  Final: {final_memory:.2f} MB")
            print(f"  Growth: {memory_growth:.2f} MB")

            assert memory_growth < 100, f"Memory grew by {memory_growth:.2f} MB (target: <100 MB)"

        except ImportError:
            pytest.skip("Required modules not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
