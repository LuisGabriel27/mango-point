"""
MangoPoint Validation — Historical Weather Scenarios
=====================================================
Generates realistic weather scenarios based on historical climate patterns
for reproducing past pest monitoring conditions in simulations.

This module creates weather time series that match the typical climate
conditions for specific months and seasons in Guimaras, Philippines.

Climate Data Source: Philippine Atmospheric, Geophysical and Astronomical
Services Administration (PAGASA) historical averages for Western Visayas.

Guimaras Climate Characteristics:
- Tropical maritime climate (Type IV - no dry season)
- Temperature range: 24-34°C (relatively stable year-round)
- Dry Season: December - May (less rainfall, lower humidity)
- Wet Season: June - November (monsoon, frequent rainfall)
- Prevailing winds: NE monsoon (Nov-Apr), SW monsoon (May-Oct)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any


@dataclass
class SeasonalWeatherProfile:
    """
    Monthly climate profile for Guimaras, Philippines.
    
    Based on PAGASA historical data for Western Visayas region.
    
    Attributes
    ----------
    month : int
        Month number (1-12)
    temp_mean : float
        Mean temperature (°C)
    temp_range : float
        Daily temperature range (°C)
    humidity_mean : float
        Mean relative humidity (%)
    rainfall_prob : float
        Daily probability of rainfall (0-1)
    rainfall_mean_mm : float
        Mean rainfall when it occurs (mm)
    wind_speed_mean : float
        Mean wind speed (m/s)
    wind_dir_mean : float
        Mean wind direction (degrees from N)
    """
    month: int
    temp_mean: float
    temp_range: float
    humidity_mean: float
    rainfall_prob: float
    rainfall_mean_mm: float
    wind_speed_mean: float
    wind_dir_mean: float


# ─────────────────────────────────────────────
# Monthly Climate Profiles for Guimaras
# ─────────────────────────────────────────────
# Based on PAGASA historical data (1991-2020 averages)
# and local orchard monitoring records

GUIMARAS_CLIMATE_PROFILES: Dict[int, SeasonalWeatherProfile] = {
    1: SeasonalWeatherProfile(  # January - Dry, NE Monsoon
        month=1, temp_mean=27.0, temp_range=6.0,
        humidity_mean=78, rainfall_prob=0.15, rainfall_mean_mm=4.0,
        wind_speed_mean=3.5, wind_dir_mean=45  # NE
    ),
    2: SeasonalWeatherProfile(  # February - Dry, NE Monsoon
        month=2, temp_mean=27.5, temp_range=7.0,
        humidity_mean=75, rainfall_prob=0.12, rainfall_mean_mm=3.5,
        wind_speed_mean=3.0, wind_dir_mean=50  # NE
    ),
    3: SeasonalWeatherProfile(  # March - Dry, transition
        month=3, temp_mean=28.5, temp_range=8.0,
        humidity_mean=72, rainfall_prob=0.10, rainfall_mean_mm=3.0,
        wind_speed_mean=2.5, wind_dir_mean=60  # ENE
    ),
    4: SeasonalWeatherProfile(  # April - Hot dry, pre-monsoon
        month=4, temp_mean=30.0, temp_range=8.5,
        humidity_mean=70, rainfall_prob=0.15, rainfall_mean_mm=4.5,
        wind_speed_mean=2.0, wind_dir_mean=90  # E
    ),
    5: SeasonalWeatherProfile(  # May - Hot, early wet season transition
        month=5, temp_mean=30.5, temp_range=7.0,
        humidity_mean=75, rainfall_prob=0.30, rainfall_mean_mm=8.0,
        wind_speed_mean=2.5, wind_dir_mean=180  # S
    ),
    6: SeasonalWeatherProfile(  # June - Wet, SW Monsoon begins
        month=6, temp_mean=29.0, temp_range=5.5,
        humidity_mean=82, rainfall_prob=0.50, rainfall_mean_mm=12.0,
        wind_speed_mean=3.0, wind_dir_mean=225  # SW
    ),
    7: SeasonalWeatherProfile(  # July - Wet, SW Monsoon
        month=7, temp_mean=28.5, temp_range=5.0,
        humidity_mean=84, rainfall_prob=0.55, rainfall_mean_mm=14.0,
        wind_speed_mean=3.5, wind_dir_mean=235  # WSW
    ),
    8: SeasonalWeatherProfile(  # August - Wet, SW Monsoon peak
        month=8, temp_mean=28.5, temp_range=5.0,
        humidity_mean=85, rainfall_prob=0.55, rainfall_mean_mm=15.0,
        wind_speed_mean=3.5, wind_dir_mean=235  # WSW
    ),
    9: SeasonalWeatherProfile(  # September - Wet, late monsoon
        month=9, temp_mean=28.5, temp_range=5.5,
        humidity_mean=84, rainfall_prob=0.50, rainfall_mean_mm=13.0,
        wind_speed_mean=2.5, wind_dir_mean=220  # SW
    ),
    10: SeasonalWeatherProfile(  # October - Wet, transition
        month=10, temp_mean=28.0, temp_range=5.5,
        humidity_mean=82, rainfall_prob=0.45, rainfall_mean_mm=11.0,
        wind_speed_mean=2.0, wind_dir_mean=180  # S
    ),
    11: SeasonalWeatherProfile(  # November - Transition to dry
        month=11, temp_mean=28.0, temp_range=5.5,
        humidity_mean=80, rainfall_prob=0.35, rainfall_mean_mm=8.0,
        wind_speed_mean=2.5, wind_dir_mean=90  # E
    ),
    12: SeasonalWeatherProfile(  # December - Dry, NE Monsoon
        month=12, temp_mean=27.5, temp_range=6.0,
        humidity_mean=79, rainfall_prob=0.25, rainfall_mean_mm=6.0,
        wind_speed_mean=3.0, wind_dir_mean=45  # NE
    ),
}


class HistoricalWeatherGenerator:
    """
    Generates weather time series for historical validation scenarios.
    
    Creates realistic hourly weather data based on:
    - Monthly climate profiles for Guimaras
    - Diurnal temperature and humidity cycles
    - Stochastic rainfall events (calibrated by season)
    - Wind patterns reflecting monsoon influences
    
    Usage
    -----
        generator = HistoricalWeatherGenerator()
        
        # Generate weather for a specific historical month
        weather = generator.generate(year=2023, month=5, hours=48)
        
        # Create WeatherTimeSeries for simulation engine
        weather_ts = generator.create_weather_timeseries(2023, 5, 48)
    """
    
    def __init__(
        self,
        seed: Optional[int] = None,
        historical_weather_path: Optional[str | Path] = None,
    ):
        """
        Initialize the weather generator.
        
        Parameters
        ----------
        seed : int, optional
            Random seed for reproducibility
        historical_weather_path : str or Path, optional
            Hourly historical weather CSV. When rows are available for a
            validation case's year/month, they are used before synthetic
            seasonal profiles.
        """
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        self.historical_weather_path = (
            Path(historical_weather_path) if historical_weather_path else None
        )
        self._historical_weather = self._load_historical_weather()
    
    def reset_seed(self, seed: int) -> None:
        """Reset the random number generator with a new seed."""
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    @staticmethod
    def _normalize_column_name(name: str) -> str:
        """Normalize CSV column names for flexible matching."""
        normalized = name.strip().lower()
        for char in (" ", "-", "/", "."):
            normalized = normalized.replace(char, "_")
        return normalized

    @classmethod
    def _find_column(
        cls,
        columns_by_key: Dict[str, str],
        aliases: tuple[str, ...],
    ) -> Optional[str]:
        """Find a CSV column by normalized alias."""
        normalized_aliases = {cls._normalize_column_name(alias) for alias in aliases}
        for alias in normalized_aliases:
            if alias in columns_by_key:
                return columns_by_key[alias]
        return None

    def _load_historical_weather(self) -> Optional[pd.DataFrame]:
        """Load and normalize optional hourly historical weather CSV data."""
        if self.historical_weather_path is None:
            return None

        if not self.historical_weather_path.exists():
            raise FileNotFoundError(
                f"Historical weather CSV not found: {self.historical_weather_path}"
            )

        raw = pd.read_csv(self.historical_weather_path)
        columns_by_key = {
            self._normalize_column_name(column): column
            for column in raw.columns
        }

        datetime_col = self._find_column(
            columns_by_key,
            ("datetime", "date_time", "timestamp", "time", "date"),
        )
        temp_col = self._find_column(
            columns_by_key,
            ("temperature_c", "temp_c", "temperature", "temperature_2m"),
        )
        wind_speed_col = self._find_column(
            columns_by_key,
            ("wind_speed_ms", "wind_speed_m_s", "wind_speed", "wind_speed_10m"),
        )
        wind_dir_col = self._find_column(
            columns_by_key,
            (
                "wind_dir_deg",
                "wind_direction_deg",
                "wind_direction",
                "wind_direction_10m",
            ),
        )
        rainfall_col = self._find_column(
            columns_by_key,
            ("rainfall_mm", "rain_mm", "precipitation_mm", "precipitation"),
        )
        humidity_col = self._find_column(
            columns_by_key,
            ("humidity_pct", "relative_humidity", "relative_humidity_2m"),
        )

        required = {
            "datetime": datetime_col,
            "temperature_c": temp_col,
            "wind_speed_ms": wind_speed_col,
            "wind_dir_deg": wind_dir_col,
        }
        missing = [name for name, column in required.items() if column is None]
        if missing:
            missing_text = ", ".join(missing)
            raise ValueError(
                "Historical weather CSV is missing required column(s): "
                f"{missing_text}"
            )

        df = pd.DataFrame({
            "datetime": pd.to_datetime(raw[datetime_col], errors="coerce"),
            "temperature_c": pd.to_numeric(raw[temp_col], errors="coerce"),
            "wind_speed_ms": pd.to_numeric(raw[wind_speed_col], errors="coerce"),
            "wind_dir_deg": pd.to_numeric(raw[wind_dir_col], errors="coerce") % 360,
            "rainfall_mm": (
                pd.to_numeric(raw[rainfall_col], errors="coerce").fillna(0.0)
                if rainfall_col
                else 0.0
            ),
        })

        if humidity_col:
            df["humidity_pct"] = pd.to_numeric(raw[humidity_col], errors="coerce")

        df = df.dropna(
            subset=["datetime", "temperature_c", "wind_speed_ms", "wind_dir_deg"]
        )
        df["rainfall_mm"] = df["rainfall_mm"].clip(lower=0.0)
        df["wind_speed_ms"] = df["wind_speed_ms"].clip(lower=0.0)
        df = df.sort_values("datetime").reset_index(drop=True)

        if df.empty:
            raise ValueError("Historical weather CSV contains no usable weather rows")

        return df

    def _generate_from_historical(
        self,
        year: int,
        month: int,
        hours: int,
        scenario: str,
    ) -> Optional[pd.DataFrame]:
        """Return historical weather for a case when enough rows are available."""
        if self._historical_weather is None:
            return None

        data = self._historical_weather
        month_rows = data[
            (data["datetime"].dt.year == year)
            & (data["datetime"].dt.month == month)
        ]
        if len(month_rows) < hours:
            return None

        preferred_start = datetime(year, month, 15, 6, 0)
        from_preferred = month_rows[month_rows["datetime"] >= preferred_start]
        if len(from_preferred) >= hours:
            selected = from_preferred.head(hours).copy()
        else:
            selected = month_rows.head(hours).copy()

        selected.attrs["source"] = "historical_weather_csv"
        selected.attrs["scenario"] = scenario
        selected.attrs["historical_weather_path"] = str(self.historical_weather_path)
        selected.attrs["weather_rows_available"] = int(len(month_rows))
        return selected.reset_index(drop=True)
    
    def get_profile(self, month: int) -> SeasonalWeatherProfile:
        """
        Get the climate profile for a specific month.
        
        Parameters
        ----------
        month : int
            Month number (1-12)
        
        Returns
        -------
        SeasonalWeatherProfile
            Climate profile with typical values for that month
        """
        if month not in GUIMARAS_CLIMATE_PROFILES:
            raise ValueError(f"Invalid month: {month}. Must be 1-12.")
        return GUIMARAS_CLIMATE_PROFILES[month]
    
    def generate(
        self,
        year: int,
        month: int,
        hours: int = 48,
        scenario: str = "typical",
    ) -> pd.DataFrame:
        """
        Generate hourly weather data for a historical month.
        
        Parameters
        ----------
        year : int
            Year (used for datetime column)
        month : int
            Month (1-12)
        hours : int
            Duration in hours (default: 48)
        scenario : str
            Weather scenario type:
            - 'typical': Normal conditions for the month
            - 'rainy': Above-average rainfall (for Cecid Fly triggers)
            - 'dry': Below-average rainfall
            - 'hot': Above-average temperature
        
        Returns
        -------
        pd.DataFrame
            Hourly weather data with columns:
            datetime, wind_speed_ms, wind_dir_deg, temperature_c, rainfall_mm
        """
        profile = self.get_profile(month)

        fallback_reason = None
        if self._historical_weather is not None:
            historical = self._generate_from_historical(
                year=year,
                month=month,
                hours=hours,
                scenario=scenario,
            )
            if historical is not None:
                return historical
            fallback_reason = (
                "historical_weather_csv_has_insufficient_rows_for_case_month"
            )
        
        # Create datetime array starting from 6:00 AM on the 15th
        start = datetime(year, month, 15, 6, 0)
        times = [start + timedelta(hours=h) for h in range(hours)]
        hours_arr = np.array([t.hour for t in times], dtype=float)
        
        # ── Temperature: diurnal cycle ──
        # Peak around 14:00, trough around 05:00
        temp_base = profile.temp_mean
        temp_amplitude = profile.temp_range / 2
        
        # Adjust for scenario
        if scenario == "hot":
            temp_base += 2.0
        
        # Sinusoidal diurnal pattern with noise
        temp = temp_base + temp_amplitude * np.sin(2 * np.pi * (hours_arr - 6) / 24)
        temp += self._rng.normal(0, 0.5, size=hours)
        
        # ── Humidity: inversely related to temperature ──
        humidity_base = profile.humidity_mean
        # Higher humidity at night, lower during day
        humidity = humidity_base - 10 * np.sin(2 * np.pi * (hours_arr - 6) / 24)
        humidity += self._rng.normal(0, 3, size=hours)
        humidity = np.clip(humidity, 40, 100)
        
        # ── Wind: seasonal pattern with variation ──
        wind_base = profile.wind_speed_mean
        wind_dir_base = profile.wind_dir_mean
        
        # Wind typically stronger during day
        wind_speed = wind_base + 0.5 * np.sin(2 * np.pi * (hours_arr - 6) / 24)
        wind_speed += self._rng.normal(0, 0.5, size=hours)
        wind_speed = np.clip(wind_speed, 0.2, 8.0)
        
        # Wind direction varies around seasonal mean
        wind_dir = wind_dir_base + self._rng.normal(0, 15, size=hours)
        wind_dir = wind_dir % 360
        
        # ── Rainfall: stochastic based on monthly probability ──
        rainfall_prob = profile.rainfall_prob
        rainfall_mean = profile.rainfall_mean_mm
        
        # Adjust for scenario
        if scenario == "rainy":
            rainfall_prob = min(0.8, rainfall_prob * 2.0)
            rainfall_mean *= 1.5
        elif scenario == "dry":
            rainfall_prob *= 0.3
            rainfall_mean *= 0.5
        
        rainfall = np.zeros(hours)
        for i, h in enumerate(hours_arr):
            # Higher probability in afternoon (tropical convection pattern)
            hour_prob = rainfall_prob
            if 13 <= h <= 18:
                hour_prob *= 1.5
            elif h < 6 or h > 21:
                hour_prob *= 0.5
            
            if self._rng.random() < hour_prob:
                # Rainfall amount follows gamma distribution
                rainfall[i] = self._rng.gamma(2.0, rainfall_mean / 2.0)
        
        rainfall = np.clip(rainfall, 0, 30.0)  # Cap at 30 mm/hour
        
        # For Cecid Fly validation: create a rainfall event sequence
        # that triggers emergence (>5mm accumulated over 24h, then dry period)
        if scenario == "rainy" and hours >= 48:
            # Ensure there's a significant rainfall event in first 24 hours
            rain_hours = self._rng.choice(range(12, 20), size=3, replace=False)
            for h in rain_hours:
                if h < hours:
                    rainfall[h] = max(rainfall[h], self._rng.uniform(3, 8))
        
        df = pd.DataFrame({
            "datetime": times,
            "wind_speed_ms": wind_speed,
            "wind_dir_deg": wind_dir,
            "temperature_c": temp,
            "rainfall_mm": rainfall,
            "humidity_pct": humidity,  # Extra column for reference
        })
        df.attrs["source"] = "seasonal_profile_synthetic"
        df.attrs["scenario"] = scenario
        if self.historical_weather_path:
            df.attrs["historical_weather_path"] = str(self.historical_weather_path)
        if fallback_reason:
            df.attrs["fallback_reason"] = fallback_reason
        
        return df
    
    def create_weather_timeseries(
        self,
        year: int,
        month: int,
        hours: int = 48,
        scenario: str = "typical",
    ) -> "WeatherTimeSeries":
        """
        Create a WeatherTimeSeries object for the simulation engine.
        
        Parameters
        ----------
        year : int
            Year for the scenario
        month : int
            Month (1-12)
        hours : int
            Duration in hours
        scenario : str
            Weather scenario type ('typical', 'rainy', 'dry', 'hot')
        
        Returns
        -------
        WeatherTimeSeries
            Weather data ready for simulation engine
        """
        from utils.weather import WeatherTimeSeries
        
        df = self.generate(year, month, hours, scenario)
        return WeatherTimeSeries.from_dataframe(df)
    
    def generate_validation_weather(
        self,
        year: int,
        month: int,
        pest_type: str,
        hours: int = 48,
    ) -> pd.DataFrame:
        """
        Generate weather optimized for validating a specific pest type.
        
        For Cecid Fly: Generates rainy scenario to trigger emergence
        For Fruit Fly: Generates typical hot/humid conditions
        
        Parameters
        ----------
        year : int
            Historical year
        month : int
            Historical month
        pest_type : str
            'cecid' or 'fruitfly'
        hours : int
            Simulation duration
        
        Returns
        -------
        pd.DataFrame
            Weather data tailored for the pest type
        """
        if pest_type == "cecid":
            # Cecid Fly needs rainfall accumulation then dry emergence period
            scenario = "rainy"
        else:
            # Fruit Fly is more active in hot conditions with ripe fruit
            scenario = "typical"
            # In mature stage (May-Jul), conditions are typically warm/humid
            if month in [5, 6, 7]:
                scenario = "hot"
        
        return self.generate(year, month, hours, scenario)
    
    def get_scenario_description(self, scenario: str, month: int) -> str:
        """
        Get a human-readable description of a weather scenario.
        
        Parameters
        ----------
        scenario : str
            Scenario type
        month : int
            Month number
        
        Returns
        -------
        str
            Description for reporting
        """
        profile = self.get_profile(month)
        month_name = datetime(2000, month, 1).strftime("%B")
        season = "dry season" if month in [12, 1, 2, 3, 4, 5] else "wet season"
        
        descriptions = {
            "typical": (
                f"Typical {month_name} conditions ({season}): "
                f"~{profile.temp_mean:.0f}°C, {profile.humidity_mean:.0f}% humidity, "
                f"{profile.rainfall_prob*100:.0f}% rain probability"
            ),
            "rainy": (
                f"Above-average rainfall for {month_name}: "
                f"Enhanced convective activity, rainfall events for Cecid Fly emergence"
            ),
            "dry": (
                f"Below-average rainfall for {month_name}: "
                f"Reduced precipitation, typical during El Niño conditions"
            ),
            "hot": (
                f"Above-average temperature for {month_name}: "
                f"~{profile.temp_mean + 2:.0f}°C, conducive to Fruit Fly activity"
            ),
        }
        
        return descriptions.get(scenario, f"Custom scenario for {month_name}")
    
    def get_summary_stats(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Compute summary statistics for generated weather data.
        
        Parameters
        ----------
        df : pd.DataFrame
            Weather DataFrame
        
        Returns
        -------
        dict
            Summary statistics
        """
        stats = {
            "hours": len(df),
            "temp_min_c": float(df["temperature_c"].min()),
            "temp_max_c": float(df["temperature_c"].max()),
            "temp_mean_c": float(df["temperature_c"].mean()),
            "rainfall_total_mm": float(df["rainfall_mm"].sum()),
            "rainfall_hours": int((df["rainfall_mm"] > 0).sum()),
            "rainfall_max_mm": float(df["rainfall_mm"].max()),
            "wind_mean_ms": float(df["wind_speed_ms"].mean()),
            "wind_max_ms": float(df["wind_speed_ms"].max()),
        }
        stats.update({
            "source": df.attrs.get("source", "unknown"),
            "scenario": df.attrs.get("scenario", "unknown"),
        })
        for key in (
            "historical_weather_path",
            "weather_rows_available",
            "fallback_reason",
        ):
            if key in df.attrs:
                stats[key] = df.attrs[key]
        return stats


def create_weather_for_validation_case(
    year: int,
    month: int,
    pest_type: str,
    hours: int = 48,
    seed: Optional[int] = None,
) -> pd.DataFrame:
    """
    Convenience function to create weather data for a validation case.
    
    Parameters
    ----------
    year : int
        Historical year
    month : int
        Historical month
    pest_type : str
        'cecid' or 'fruitfly'
    hours : int
        Simulation duration
    seed : int, optional
        Random seed for reproducibility
    
    Returns
    -------
    pd.DataFrame
        Weather data
    """
    generator = HistoricalWeatherGenerator(seed=seed)
    return generator.generate_validation_weather(year, month, pest_type, hours)
