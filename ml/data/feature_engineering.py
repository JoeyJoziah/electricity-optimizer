"""
Feature Engineering Pipeline for Electricity Price Forecasting

Transforms raw time-series data into model-ready features with:
- Temporal features (time of day, day of week, seasonality)
- Weather integration
- Generation mix features
- Lag and rolling statistics
- Holiday indicators
- Seasonal decomposition

Enhanced for CNN-LSTM model with attention mechanism.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass, field
import logging
from abc import ABC, abstractmethod
import holidays

from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler
from sklearn.base import BaseEstimator, TransformerMixin

try:
    from statsmodels.tsa.seasonal import seasonal_decompose
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False

logger = logging.getLogger(__name__)


@dataclass
class FeatureConfig:
    """Configuration for feature engineering."""

    # Sequence parameters
    sequence_length: int = 168  # 7 days of hourly data
    forecast_horizon: int = 24   # 24-hour ahead forecast

    # Lag features
    price_lags: List[int] = field(default_factory=lambda: [1, 2, 3, 6, 12, 24, 48, 168])
    demand_lags: List[int] = field(default_factory=lambda: [1, 24, 168])

    # Rolling window sizes
    rolling_windows: List[int] = field(default_factory=lambda: [3, 6, 12, 24, 168])

    # Scaling method
    scaling_method: str = "standard"  # standard, minmax, robust

    # Holiday calendar
    country_code: str = "DE"  # Germany as default for European electricity

    # Feature groups to include
    include_temporal: bool = True
    include_lags: bool = True
    include_rolling: bool = True
    include_weather: bool = True
    include_generation: bool = True
    include_seasonal: bool = True


class ElectricityPriceFeatureEngine:
    """
    Feature engineering for electricity price forecasting

    Creates 10+ features from raw price data:
    1. Temporal: hour, day_of_week, month, is_holiday, is_weekend
    2. Cyclical: sin/cos transforms for hour and day_of_week
    3. Lags: price_lag_1h, price_lag_24h, price_lag_168h
    4. Rolling: rolling_mean_24h, rolling_std_24h, rolling_min_24h, rolling_max_24h
    5. Price dynamics: price_change_1h, price_change_24h, volatility
    """

    def __init__(
        self,
        country: str = "UK",
        lookback_hours: int = 168,
        forecast_hours: int = 24
    ):
        self.country = country
        self.lookback_hours = lookback_hours
        self.forecast_hours = forecast_hours
        self.holiday_calendar = holidays.country_holidays(country)
        self.scaler = None
        self.feature_names_ = None
        self.is_fitted_ = False

    def create_temporal_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create time-based features"""
        df = df.copy()

        # Basic time features
        df['hour'] = df.index.hour
        df['day_of_week'] = df.index.dayofweek
        df['day_of_month'] = df.index.day
        df['month'] = df.index.month
        df['quarter'] = df.index.quarter
        df['week_of_year'] = df.index.isocalendar().week

        # Binary indicators
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        df['is_holiday'] = df.index.to_series().apply(
            lambda x: x.date() in self.holiday_calendar
        ).astype(int)

        # Cyclical encoding (sin/cos transform for hour and day_of_week)
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['dow_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

        # Peak hour indicators
        df['is_morning_peak'] = ((df['hour'] >= 7) & (df['hour'] <= 9)).astype(int)
        df['is_evening_peak'] = ((df['hour'] >= 17) & (df['hour'] <= 21)).astype(int)
        df['is_night'] = ((df['hour'] >= 23) | (df['hour'] <= 5)).astype(int)

        return df

    def create_lag_features(
        self,
        df: pd.DataFrame,
        target_col: str = 'price',
        lags: List[int] = None
    ) -> pd.DataFrame:
        """Create lagged price features"""
        df = df.copy()

        if lags is None:
            lags = [1, 2, 3, 24, 48, 168]

        for lag in lags:
            df[f'{target_col}_lag_{lag}h'] = df[target_col].shift(lag)

        return df

    def create_rolling_features(
        self,
        df: pd.DataFrame,
        target_col: str = 'price',
        windows: List[int] = None
    ) -> pd.DataFrame:
        """Create rolling statistics features"""
        df = df.copy()

        if windows is None:
            windows = [3, 6, 12, 24, 168]

        for window in windows:
            # Rolling mean
            df[f'{target_col}_rolling_mean_{window}h'] = (
                df[target_col].rolling(window=window, min_periods=1).mean()
            )

            # Rolling std (volatility)
            df[f'{target_col}_rolling_std_{window}h'] = (
                df[target_col].rolling(window=window, min_periods=1).std()
            )

            # Rolling min/max
            df[f'{target_col}_rolling_min_{window}h'] = (
                df[target_col].rolling(window=window, min_periods=1).min()
            )
            df[f'{target_col}_rolling_max_{window}h'] = (
                df[target_col].rolling(window=window, min_periods=1).max()
            )

            # Rolling range
            df[f'{target_col}_rolling_range_{window}h'] = (
                df[f'{target_col}_rolling_max_{window}h'] -
                df[f'{target_col}_rolling_min_{window}h']
            )

        return df

    def create_price_dynamics_features(
        self,
        df: pd.DataFrame,
        target_col: str = 'price'
    ) -> pd.DataFrame:
        """Create price change and momentum features"""
        df = df.copy()

        # Price changes
        df[f'{target_col}_change_1h'] = df[target_col].diff(1)
        df[f'{target_col}_change_3h'] = df[target_col].diff(3)
        df[f'{target_col}_change_24h'] = df[target_col].diff(24)

        # Percentage changes
        df[f'{target_col}_pct_change_1h'] = df[target_col].pct_change(1)
        df[f'{target_col}_pct_change_24h'] = df[target_col].pct_change(24)

        # Momentum indicators
        df[f'{target_col}_momentum_3h'] = (
            df[target_col] - df[target_col].shift(3)
        )
        df[f'{target_col}_momentum_24h'] = (
            df[target_col] - df[target_col].shift(24)
        )

        # Volatility (rolling std of returns)
        df[f'{target_col}_volatility_24h'] = (
            df[f'{target_col}_pct_change_1h'].rolling(window=24, min_periods=1).std()
        )

        # Distance from mean (check if column exists first)
        mean_col = f'{target_col}_rolling_mean_24h'
        if mean_col in df.columns:
            df[f'{target_col}_dist_from_mean_24h'] = (
                df[target_col] - df[mean_col]
            )

        return df

    def create_seasonal_decomposition_features(
        self,
        df: pd.DataFrame,
        target_col: str = 'price',
        period: int = 24
    ) -> pd.DataFrame:
        """Create seasonal decomposition features using statsmodels"""
        df = df.copy()

        if not HAS_STATSMODELS:
            logger.warning("statsmodels not available, skipping seasonal decomposition")
            df['seasonal_component'] = 0
            df['trend_component'] = df[target_col]
            df['residual_component'] = 0
            return df

        try:
            series = df[target_col].dropna()

            if len(series) >= period * 2:
                decomposition = seasonal_decompose(
                    series,
                    model='additive',
                    period=period,
                    extrapolate_trend='freq'
                )

                df['seasonal_component'] = decomposition.seasonal
                df['trend_component'] = decomposition.trend
                df['residual_component'] = decomposition.resid
            else:
                df['seasonal_component'] = 0
                df['trend_component'] = df[target_col]
                df['residual_component'] = 0

        except Exception as e:
            logger.warning(f"Seasonal decomposition failed: {e}")
            df['seasonal_component'] = 0
            df['trend_component'] = df[target_col]
            df['residual_component'] = 0

        return df

    def create_weather_features(
        self,
        df: pd.DataFrame,
        weather_data: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Integrate weather features if available

        Expected weather_data columns:
        - temperature (C)
        - wind_speed (m/s)
        - solar_radiation (W/m2)
        - cloud_cover (%)
        """
        df = df.copy()

        if weather_data is not None:
            # Merge weather data
            df = df.join(weather_data, how='left')

            # Fill missing weather with forward fill then backward fill
            weather_cols = ['temperature', 'wind_speed', 'solar_radiation', 'cloud_cover']
            for col in weather_cols:
                if col in df.columns:
                    df[col] = df[col].ffill().bfill()

            # Derived weather features
            if 'temperature' in df.columns:
                # Heating/cooling degree days
                df['heating_degree'] = np.maximum(18 - df['temperature'], 0)
                df['cooling_degree'] = np.maximum(df['temperature'] - 24, 0)
                df['temp_change_1h'] = df['temperature'].diff(1)
                df['temp_change_24h'] = df['temperature'].diff(24)

            if 'wind_speed' in df.columns and 'solar_radiation' in df.columns:
                # Renewable generation potential
                df['renewable_potential'] = (
                    df['wind_speed'] * 0.5 + df['solar_radiation'] * 0.001
                )
                # Wind power approximation (cubic relationship)
                df['wind_power_potential'] = np.clip(df['wind_speed'] ** 3, 0, 15000)

        return df

    def create_generation_mix_features(
        self,
        df: pd.DataFrame,
        generation_data: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """Create generation mix features"""
        df = df.copy()

        if generation_data is not None:
            df = df.join(generation_data, how='left')

            # Calculate percentages if raw values provided
            gen_columns = ['renewable_gen', 'fossil_gen', 'nuclear_gen']
            available_gen = [c for c in gen_columns if c in df.columns]

            if len(available_gen) > 0:
                total_gen = df[available_gen].sum(axis=1)

                for col in available_gen:
                    pct_col = col.replace('_gen', '_percentage')
                    df[pct_col] = df[col] / total_gen.replace(0, np.nan)

            # Create generation stability features
            if 'renewable_percentage' in df.columns:
                df['renewable_volatility'] = df['renewable_percentage'].rolling(
                    window=24, min_periods=1
                ).std()
                df['is_high_renewable'] = (
                    df['renewable_percentage'] > 0.5
                ).astype(int)

        return df

    def create_demand_proxy_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create proxy features for electricity demand
        (useful when actual demand data not available)
        """
        df = df.copy()

        # Time-based demand proxies
        df['demand_proxy_hour'] = df['hour'].apply(lambda x:
            1.0 if x in [7, 8, 9, 18, 19, 20] else  # Peak hours
            0.5 if x in range(10, 17) else          # Mid-day
            0.3                                      # Night
        )

        # Weekend adjustment (lower demand)
        df['demand_proxy_adjusted'] = df['demand_proxy_hour'] * (
            np.where(df['is_weekend'] == 1, 0.7, 1.0)
        )

        return df

    def fit(self, df: pd.DataFrame, target_col: str = 'price') -> 'ElectricityPriceFeatureEngine':
        """Fit the scaler on training data"""
        # Transform data to get all features
        df_transformed = self.transform(df, target_col=target_col, fit_scaler=False)

        # Fit scaler
        feature_cols = [c for c in df_transformed.columns if c != target_col]
        self.feature_names_ = feature_cols

        self.scaler = StandardScaler()
        self.scaler.fit(df_transformed[feature_cols].fillna(0))

        self.is_fitted_ = True
        return self

    def transform(
        self,
        df: pd.DataFrame,
        target_col: str = 'price',
        weather_data: Optional[pd.DataFrame] = None,
        generation_data: Optional[pd.DataFrame] = None,
        fit_scaler: bool = False,
        include_seasonal: bool = True
    ) -> pd.DataFrame:
        """
        Complete feature engineering pipeline

        Args:
            df: DataFrame with DateTimeIndex and price column
            target_col: Name of target column (default: 'price')
            weather_data: Optional weather DataFrame
            generation_data: Optional generation mix DataFrame
            fit_scaler: Whether to fit scaler (use True only for training)
            include_seasonal: Whether to include seasonal decomposition

        Returns:
            DataFrame with all engineered features
        """
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have DateTimeIndex")

        # Apply all feature engineering steps
        df = self.create_temporal_features(df)
        df = self.create_lag_features(df, target_col)
        df = self.create_rolling_features(df, target_col)
        df = self.create_price_dynamics_features(df, target_col)

        if include_seasonal:
            df = self.create_seasonal_decomposition_features(df, target_col)

        df = self.create_weather_features(df, weather_data)
        df = self.create_generation_mix_features(df, generation_data)
        df = self.create_demand_proxy_features(df)

        # Replace inf values with NaN then fill
        df = df.replace([np.inf, -np.inf], np.nan)

        # Fill NaN with forward fill then backward fill
        df = df.ffill().bfill()

        # If scaler is fitted, apply scaling
        if self.is_fitted_ and self.scaler is not None:
            feature_cols = [c for c in self.feature_names_ if c in df.columns]
            df[feature_cols] = self.scaler.transform(df[feature_cols].fillna(0))

        return df

    def create_sequences(
        self,
        df: pd.DataFrame,
        target_col: str = 'price',
        feature_cols: Optional[List[str]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for time series prediction

        Returns:
            X: (n_samples, lookback_hours, n_features)
            y: (n_samples, forecast_hours)
        """
        if feature_cols is None:
            # Auto-select feature columns (exclude target)
            feature_cols = [col for col in df.columns if col != target_col]

        X, y = [], []

        for i in range(len(df) - self.lookback_hours - self.forecast_hours + 1):
            # Input sequence
            X.append(df[feature_cols].iloc[i:i + self.lookback_hours].values)

            # Target sequence (next 24 hours of prices)
            y.append(
                df[target_col].iloc[
                    i + self.lookback_hours:i + self.lookback_hours + self.forecast_hours
                ].values
            )

        return np.array(X), np.array(y)

    def get_feature_importance_names(self) -> List[str]:
        """Return list of all feature names created"""
        feature_groups = {
            'temporal': [
                'hour', 'day_of_week', 'month', 'is_weekend', 'is_holiday',
                'hour_sin', 'hour_cos', 'dow_sin', 'dow_cos',
                'is_morning_peak', 'is_evening_peak', 'is_night'
            ],
            'lags': [
                'price_lag_1h', 'price_lag_2h', 'price_lag_3h',
                'price_lag_24h', 'price_lag_48h', 'price_lag_168h'
            ],
            'rolling': [
                'price_rolling_mean_24h', 'price_rolling_std_24h',
                'price_rolling_min_24h', 'price_rolling_max_24h'
            ],
            'dynamics': [
                'price_change_1h', 'price_change_24h',
                'price_pct_change_1h', 'price_momentum_24h',
                'price_volatility_24h'
            ],
            'seasonal': [
                'seasonal_component', 'trend_component', 'residual_component'
            ]
        }

        all_features = []
        for group in feature_groups.values():
            all_features.extend(group)

        return all_features


def create_dummy_data(
    n_hours: int = 8760,  # 1 year of hourly data
    start_date: str = '2024-01-01',
    include_weather: bool = True,
    include_generation: bool = True
) -> pd.DataFrame:
    """
    Create dummy electricity price data for testing.

    Args:
        n_hours: Number of hours to generate
        start_date: Start date for the time series
        include_weather: Include weather features
        include_generation: Include generation mix features

    Returns:
        DataFrame with dummy electricity data
    """
    np.random.seed(42)

    # Create datetime index
    dates = pd.date_range(
        start=start_date,
        periods=n_hours,
        freq='H'
    )

    # Base price with daily and weekly seasonality
    hours = np.arange(n_hours)

    # Daily pattern (higher during day, lower at night)
    daily_pattern = 20 * np.sin(2 * np.pi * (hours % 24 - 6) / 24)

    # Weekly pattern (lower on weekends)
    weekly_pattern = 10 * np.sin(2 * np.pi * (hours % 168) / 168)

    # Annual pattern (higher in winter, lower in summer)
    annual_pattern = 15 * np.cos(2 * np.pi * hours / 8760)

    # Trend
    trend = 0.001 * hours

    # Noise
    noise = np.random.normal(0, 10, n_hours)

    # Combined price (base price = 50 EUR/MWh)
    price = 50 + daily_pattern + weekly_pattern + annual_pattern + trend + noise
    price = np.maximum(price, 0)  # No negative prices

    # Create DataFrame
    data = {
        'price': price,
        'spot_price': price,
        'day_ahead_price': price + np.random.normal(0, 2, n_hours),
    }

    if include_weather:
        data.update({
            'temperature': 10 + 10 * np.sin(2 * np.pi * hours / 8760) + np.random.normal(0, 3, n_hours),
            'wind_speed': np.abs(5 + np.random.normal(0, 3, n_hours)),
            'solar_radiation': np.maximum(0, 300 * np.sin(np.pi * (hours % 24) / 24) * (1 - 0.3 * np.random.random(n_hours))),
            'cloud_cover': np.clip(np.random.normal(50, 20, n_hours), 0, 100),
        })

    if include_generation:
        renewable_pct = np.clip(0.3 + 0.2 * np.sin(2 * np.pi * hours / 8760) + np.random.normal(0, 0.1, n_hours), 0, 1)
        nuclear_pct = 0.2 + np.random.normal(0, 0.02, n_hours)
        data.update({
            'load_forecast': 50000 + 10000 * np.sin(2 * np.pi * (hours % 24 - 6) / 24) + np.random.normal(0, 2000, n_hours),
            'renewable_percentage': renewable_pct,
            'fossil_percentage': np.clip(1 - renewable_pct - nuclear_pct, 0, 1),
            'nuclear_percentage': nuclear_pct
        })

    df = pd.DataFrame(data, index=dates)
    return df


def example_usage():
    """Example of using the feature engineering pipeline"""
    # Create sample data
    dates = pd.date_range('2024-01-01', periods=24*30, freq='H')
    prices = 0.20 + 0.05 * np.sin(np.arange(len(dates)) * 2 * np.pi / 24) + np.random.normal(0, 0.02, len(dates))

    df = pd.DataFrame({
        'price': prices
    }, index=dates)

    # Initialize feature engine
    feature_engine = ElectricityPriceFeatureEngine(
        country='UK',
        lookback_hours=168,
        forecast_hours=24
    )

    # Fit and transform data
    feature_engine.fit(df)
    df_features = feature_engine.transform(df)

    print(f"Original shape: {df.shape}")
    print(f"Features shape: {df_features.shape}")
    print(f"Feature columns: {list(df_features.columns)[:20]}...")

    # Create sequences for model training
    X, y = feature_engine.create_sequences(df_features)
    print(f"X shape: {X.shape}")  # (samples, 168, n_features)
    print(f"y shape: {y.shape}")  # (samples, 24)


if __name__ == '__main__':
    example_usage()
