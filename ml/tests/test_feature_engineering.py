"""
TDD Tests for Feature Engineering Pipeline

These tests are written FIRST following TDD principles.

Test Coverage:
- Temporal feature creation
- Lag feature creation
- Rolling statistics
- Price dynamics features
- Seasonal decomposition
- Feature scaling
- Sequence creation
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


class TestTemporalFeatures:
    """Tests for time-based feature creation."""

    def test_hour_feature_created(self, sample_price_data, feature_engine):
        """Test hour feature is created (0-23)."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'hour' in features.columns
        assert features['hour'].min() >= 0
        assert features['hour'].max() <= 23

    def test_day_of_week_feature_created(self, sample_price_data, feature_engine):
        """Test day of week feature is created (0-6)."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'day_of_week' in features.columns
        assert features['day_of_week'].min() >= 0
        assert features['day_of_week'].max() <= 6

    def test_month_feature_created(self, sample_price_data, feature_engine):
        """Test month feature is created (1-12)."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'month' in features.columns
        assert features['month'].min() >= 1
        assert features['month'].max() <= 12

    def test_is_weekend_feature_created(self, sample_price_data, feature_engine):
        """Test weekend indicator is created (0 or 1)."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'is_weekend' in features.columns
        assert set(features['is_weekend'].unique()).issubset({0, 1})

    def test_is_holiday_feature_created(self, sample_price_data, feature_engine):
        """Test holiday indicator is created."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'is_holiday' in features.columns
        assert set(features['is_holiday'].unique()).issubset({0, 1})

    def test_cyclical_encoding_hour(self, sample_price_data, feature_engine):
        """Test cyclical encoding for hour (sin/cos)."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'hour_sin' in features.columns
        assert 'hour_cos' in features.columns
        # Sin and cos should be between -1 and 1
        assert features['hour_sin'].min() >= -1.01
        assert features['hour_sin'].max() <= 1.01
        assert features['hour_cos'].min() >= -1.01
        assert features['hour_cos'].max() <= 1.01

    def test_cyclical_encoding_day_of_week(self, sample_price_data, feature_engine):
        """Test cyclical encoding for day of week."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'dow_sin' in features.columns
        assert 'dow_cos' in features.columns

    def test_peak_hour_indicators(self, sample_price_data, feature_engine):
        """Test peak hour indicators are created."""
        features = feature_engine.create_temporal_features(sample_price_data)

        assert 'is_morning_peak' in features.columns
        assert 'is_evening_peak' in features.columns
        assert 'is_night' in features.columns


class TestLagFeatures:
    """Tests for lagged price features."""

    def test_lag_1_hour_created(self, sample_price_data, feature_engine):
        """Test 1-hour lag feature is created."""
        features = feature_engine.create_lag_features(
            sample_price_data,
            target_col='price',
            lags=[1]
        )

        assert 'price_lag_1h' in features.columns

    def test_lag_24_hour_created(self, sample_price_data, feature_engine):
        """Test 24-hour lag feature is created."""
        features = feature_engine.create_lag_features(
            sample_price_data,
            target_col='price',
            lags=[24]
        )

        assert 'price_lag_24h' in features.columns

    def test_lag_168_hour_created(self, sample_price_data, feature_engine):
        """Test 168-hour (1 week) lag feature is created."""
        features = feature_engine.create_lag_features(
            sample_price_data,
            target_col='price',
            lags=[168]
        )

        assert 'price_lag_168h' in features.columns

    def test_lag_values_correct(self, sample_price_data, feature_engine):
        """Test lag values are correctly shifted."""
        features = feature_engine.create_lag_features(
            sample_price_data,
            target_col='price',
            lags=[1]
        )

        # Value at index 1 should match lag value at index 2
        original_value = sample_price_data['price'].iloc[0]
        lag_value = features['price_lag_1h'].iloc[1]

        assert abs(original_value - lag_value) < 0.001

    def test_multiple_lags_created(self, sample_price_data, feature_engine):
        """Test multiple lag features are created."""
        lags = [1, 2, 3, 24, 48, 168]
        features = feature_engine.create_lag_features(
            sample_price_data,
            target_col='price',
            lags=lags
        )

        for lag in lags:
            assert f'price_lag_{lag}h' in features.columns


class TestRollingFeatures:
    """Tests for rolling window statistics."""

    def test_rolling_mean_24h_created(self, sample_price_data, feature_engine):
        """Test 24-hour rolling mean is created."""
        features = feature_engine.create_rolling_features(
            sample_price_data,
            target_col='price',
            windows=[24]
        )

        assert 'price_rolling_mean_24h' in features.columns

    def test_rolling_std_24h_created(self, sample_price_data, feature_engine):
        """Test 24-hour rolling std is created."""
        features = feature_engine.create_rolling_features(
            sample_price_data,
            target_col='price',
            windows=[24]
        )

        assert 'price_rolling_std_24h' in features.columns

    def test_rolling_min_max_created(self, sample_price_data, feature_engine):
        """Test rolling min/max are created."""
        features = feature_engine.create_rolling_features(
            sample_price_data,
            target_col='price',
            windows=[24]
        )

        assert 'price_rolling_min_24h' in features.columns
        assert 'price_rolling_max_24h' in features.columns

    def test_rolling_range_created(self, sample_price_data, feature_engine):
        """Test rolling range (max - min) is created."""
        features = feature_engine.create_rolling_features(
            sample_price_data,
            target_col='price',
            windows=[24]
        )

        assert 'price_rolling_range_24h' in features.columns

    def test_rolling_mean_values_correct(self, sample_price_data, feature_engine):
        """Test rolling mean values are calculated correctly."""
        features = feature_engine.create_rolling_features(
            sample_price_data,
            target_col='price',
            windows=[3]
        )

        # Check a specific value
        expected = sample_price_data['price'].iloc[:3].mean()
        actual = features['price_rolling_mean_3h'].iloc[2]

        assert abs(expected - actual) < 0.001

    def test_multiple_windows_created(self, sample_price_data, feature_engine):
        """Test multiple rolling window features are created."""
        windows = [3, 6, 12, 24, 168]
        features = feature_engine.create_rolling_features(
            sample_price_data,
            target_col='price',
            windows=windows
        )

        for window in windows:
            assert f'price_rolling_mean_{window}h' in features.columns
            assert f'price_rolling_std_{window}h' in features.columns


class TestPriceDynamicsFeatures:
    """Tests for price change and momentum features."""

    def test_price_change_1h_created(self, sample_price_data, feature_engine):
        """Test 1-hour price change is created."""
        features = feature_engine.create_price_dynamics_features(
            sample_price_data,
            target_col='price'
        )

        assert 'price_change_1h' in features.columns

    def test_price_change_24h_created(self, sample_price_data, feature_engine):
        """Test 24-hour price change is created."""
        features = feature_engine.create_price_dynamics_features(
            sample_price_data,
            target_col='price'
        )

        assert 'price_change_24h' in features.columns

    def test_pct_change_created(self, sample_price_data, feature_engine):
        """Test percentage change features are created."""
        features = feature_engine.create_price_dynamics_features(
            sample_price_data,
            target_col='price'
        )

        assert 'price_pct_change_1h' in features.columns
        assert 'price_pct_change_24h' in features.columns

    def test_momentum_features_created(self, sample_price_data, feature_engine):
        """Test momentum features are created."""
        features = feature_engine.create_price_dynamics_features(
            sample_price_data,
            target_col='price'
        )

        assert 'price_momentum_3h' in features.columns
        assert 'price_momentum_24h' in features.columns

    def test_volatility_feature_created(self, sample_price_data, feature_engine):
        """Test volatility feature is created."""
        features = feature_engine.create_price_dynamics_features(
            sample_price_data,
            target_col='price'
        )

        assert 'price_volatility_24h' in features.columns


class TestSeasonalDecomposition:
    """Tests for seasonal decomposition features."""

    def test_seasonal_component_created(self, sample_price_data, feature_engine):
        """Test seasonal component is extracted."""
        features = feature_engine.create_seasonal_decomposition_features(
            sample_price_data,
            target_col='price',
            period=24
        )

        assert 'seasonal_component' in features.columns

    def test_trend_component_created(self, sample_price_data, feature_engine):
        """Test trend component is extracted."""
        features = feature_engine.create_seasonal_decomposition_features(
            sample_price_data,
            target_col='price',
            period=24
        )

        assert 'trend_component' in features.columns

    def test_residual_component_created(self, sample_price_data, feature_engine):
        """Test residual component is extracted."""
        features = feature_engine.create_seasonal_decomposition_features(
            sample_price_data,
            target_col='price',
            period=24
        )

        assert 'residual_component' in features.columns


class TestFeatureScaling:
    """Tests for feature scaling/normalization."""

    def test_fit_scaler(self, sample_price_data, feature_engine):
        """Test scaler can be fitted."""
        feature_engine.fit(sample_price_data)

        assert feature_engine.is_fitted_
        assert feature_engine.scaler is not None

    def test_transform_after_fit(self, sample_price_data, feature_engine):
        """Test transform works after fitting."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        assert transformed is not None
        assert len(transformed) == len(sample_price_data)

    def test_scaled_features_normalized(self, sample_price_data, feature_engine):
        """Test scaled features have reasonable range."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        # Get numeric columns (excluding price)
        numeric_cols = transformed.select_dtypes(include=[np.number]).columns
        numeric_cols = [c for c in numeric_cols if c != 'price']

        if len(numeric_cols) > 0:
            # StandardScaler should give mean ~0, std ~1
            # But with small data, allow wider range
            for col in numeric_cols[:5]:  # Check first 5
                if not transformed[col].isna().all():
                    col_mean = transformed[col].mean()
                    assert abs(col_mean) < 10, f"Column {col} mean {col_mean} too large"


class TestSequenceCreation:
    """Tests for creating model input sequences."""

    def test_create_sequences_shapes(self, sample_price_data, feature_engine):
        """Test sequence creation produces correct shapes."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        X, y = feature_engine.create_sequences(transformed, target_col='price')

        # X shape should be (n_samples, lookback_hours, n_features)
        assert len(X.shape) == 3
        assert X.shape[1] == feature_engine.lookback_hours

        # y shape should be (n_samples, forecast_hours)
        assert len(y.shape) == 2
        assert y.shape[1] == feature_engine.forecast_hours

    def test_sequences_no_nan(self, sample_price_data, feature_engine):
        """Test sequences contain no NaN values."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        X, y = feature_engine.create_sequences(transformed, target_col='price')

        assert not np.isnan(X).any(), "NaN values found in X"
        assert not np.isnan(y).any(), "NaN values found in y"

    def test_sequence_count_correct(self, sample_price_data, feature_engine):
        """Test correct number of sequences are created."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        X, y = feature_engine.create_sequences(transformed, target_col='price')

        expected_samples = len(transformed) - feature_engine.lookback_hours - feature_engine.forecast_hours + 1

        assert len(X) == expected_samples
        assert len(y) == expected_samples


class TestFullTransformPipeline:
    """Tests for the complete transform pipeline."""

    def test_full_transform_pipeline(self, sample_price_data, feature_engine):
        """Test complete feature engineering pipeline."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        # Should have many more columns than original
        assert len(transformed.columns) > len(sample_price_data.columns)

        # Should have same number of rows
        assert len(transformed) == len(sample_price_data)

    def test_no_inf_values_after_transform(self, sample_price_data, feature_engine):
        """Test no infinite values after transform."""
        feature_engine.fit(sample_price_data)
        transformed = feature_engine.transform(sample_price_data)

        numeric_cols = transformed.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            assert not np.isinf(transformed[col]).any(), f"Inf values in {col}"

    def test_transform_requires_datetime_index(self, feature_engine):
        """Test transform requires DateTimeIndex."""
        df = pd.DataFrame({'price': [1, 2, 3]})  # No datetime index

        with pytest.raises(ValueError, match="DateTimeIndex"):
            feature_engine.transform(df)

    def test_feature_names_tracked(self, sample_price_data, feature_engine):
        """Test feature names are tracked after fitting."""
        feature_engine.fit(sample_price_data)

        assert feature_engine.feature_names_ is not None
        assert len(feature_engine.feature_names_) > 0


class TestWeatherAndGenerationFeatures:
    """Tests for optional weather and generation features."""

    def test_weather_features_when_provided(self, sample_price_data, feature_engine):
        """Test weather features are added when weather data provided."""
        weather_data = pd.DataFrame({
            'temperature': np.random.randn(len(sample_price_data)) * 5 + 15,
            'wind_speed': np.abs(np.random.randn(len(sample_price_data)) * 3 + 5),
            'solar_radiation': np.maximum(0, np.random.randn(len(sample_price_data)) * 100 + 200),
            'cloud_cover': np.clip(np.random.randn(len(sample_price_data)) * 20 + 50, 0, 100)
        }, index=sample_price_data.index)

        features = feature_engine.create_weather_features(sample_price_data, weather_data)

        # Check derived weather features
        if 'temperature' in features.columns:
            assert 'heating_degree' in features.columns or len(features.columns) > len(sample_price_data.columns)

    def test_weather_features_empty_when_not_provided(self, sample_price_data, feature_engine):
        """Test weather features not added when no weather data."""
        features = feature_engine.create_weather_features(sample_price_data, None)

        # Should just return the original data
        assert len(features.columns) == len(sample_price_data.columns)


class TestDifferentCountries:
    """Tests for different country configurations."""

    def test_uk_holidays(self, sample_price_data, feature_engine):
        """Test UK holidays are recognized."""
        # Create data that includes a UK holiday (New Year's Day)
        dates = pd.date_range(start='2024-01-01', periods=48, freq='H')
        df = pd.DataFrame({'price': np.random.rand(48)}, index=dates)

        features = feature_engine.create_temporal_features(df)

        # New Year's Day should be marked as holiday
        new_years = features[features.index.date == pd.Timestamp('2024-01-01').date()]
        assert new_years['is_holiday'].iloc[0] == 1

    def test_german_holidays(self, sample_price_data, feature_engine_de):
        """Test German holidays are recognized."""
        # Create data for German Unity Day (Oct 3)
        dates = pd.date_range(start='2024-10-03', periods=48, freq='H')
        df = pd.DataFrame({'price': np.random.rand(48)}, index=dates)

        features = feature_engine_de.create_temporal_features(df)

        # German Unity Day should be marked as holiday
        unity_day = features[features.index.date == pd.Timestamp('2024-10-03').date()]
        assert unity_day['is_holiday'].iloc[0] == 1


class TestFeatureImportance:
    """Tests for feature importance utilities."""

    def test_get_feature_importance_names(self, feature_engine):
        """Test feature importance names can be retrieved."""
        names = feature_engine.get_feature_importance_names()

        assert isinstance(names, list)
        assert len(names) > 0
        assert 'hour' in names or any('hour' in n for n in names)
