"""
MangoPoint — Weather Data Handler
==================================
Provides weather data to the simulation engine on a per-timestep basis.

Supports three modes:
    1. Forecast — fetch real hourly forecasts from Open-Meteo (default, free, no API key)
    2. Synthetic — generate realistic 48-hour weather profiles for demo / testing
    3. External  — ingest a DataFrame with columns:
         datetime, wind_speed_ms, wind_dir_deg, temperature_c, rainfall_mm

Phenology-calibrated model:
    - Rainfall data is critical for Cecid Fly emergence (larvae emerge after rain)
    - Historical 2022-2025 data shows episodic Cecid activity in dry-to-wet transitions
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

from spatial.orchard_location import ORCHARD_LAT, ORCHARD_LON

logger = logging.getLogger(__name__)

# ── Open-Meteo defaults (aligned to orchard centroid) ──────────
DEFAULT_LAT = ORCHARD_LAT
DEFAULT_LON = ORCHARD_LON
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class WeatherTimeSeries:
    """
    Hourly weather data container for the simulation window.

    Attributes
    ----------
    df : pd.DataFrame
        Columns: datetime, hour, wind_speed_ms, wind_dir_deg, temperature_c, rainfall_mm
    source : str
        'open-meteo', 'synthetic', or 'external'
    """

    def __init__(self, df: pd.DataFrame, source: str = "external"):
        required = {"datetime", "wind_speed_ms", "wind_dir_deg", "temperature_c"}
        if not required.issubset(df.columns):
            raise ValueError(f"Weather DataFrame must contain columns: {required}")
        self.df = df.copy()
        self.df["hour"] = self.df["datetime"].dt.hour  # type: ignore[union-attr]
        # Ensure rainfall_mm column exists (default to 0 if not provided)
        if "rainfall_mm" not in self.df.columns:
            self.df["rainfall_mm"] = 0.0
        self.source = source
        self._records = [
            {
                "hour": int(row.hour),
                "wind_speed_ms": float(row.wind_speed_ms),
                "wind_dir_deg": float(row.wind_dir_deg),
                "temperature_c": float(row.temperature_c),
                "rainfall_mm": float(row.rainfall_mm),
                "datetime": row.datetime,
            }
            for row in self.df.itertuples(index=False)
        ]

    # ── query ───────────────────────────────────────────────────
    def at(self, step: int) -> dict:
        """Return a dict of weather values for timestep index *step*."""
        return self._records[step]

    def __len__(self):
        return len(self.df)

    # ── factory: real forecast (Open-Meteo) ─────────────────────
    @classmethod
    def from_forecast(
        cls,
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        hours: int = 48,
    ) -> "WeatherTimeSeries":
        """
        Fetch a real hourly weather forecast from the **Open-Meteo** API.

        Open-Meteo is free, requires no API key, and provides high-quality
        hourly forecasts sourced from ECMWF / GFS / JMA models.

        Parameters
        ----------
        lat, lon : float
            Location (defaults to Guimaras, Philippines).
        hours : int
            Forecast horizon in hours (max ~384 depending on model).

        Returns
        -------
        WeatherTimeSeries
            Hourly weather data with columns:
            datetime, wind_speed_ms, wind_dir_deg, temperature_c

        Raises
        ------
        RuntimeError
            If the API call fails (caller can fall back to ``synthetic``).
        """
        import requests

        params = {
            "latitude":       lat,
            "longitude":      lon,
            "hourly":         "temperature_2m,wind_speed_10m,wind_direction_10m,precipitation",
            "wind_speed_unit": "ms",
            "timezone":       "Asia/Manila",
            "forecast_hours": min(int(hours), 168),
        }

        logger.info(
            "Fetching Open-Meteo forecast for (%.4f, %.4f), %d hours …",
            lat, lon, hours,
        )

        try:
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            raise RuntimeError(f"Open-Meteo request failed: {exc}") from exc

        hourly = data.get("hourly", {})
        times_raw = hourly.get("time", [])
        temps     = hourly.get("temperature_2m", [])
        winds     = hourly.get("wind_speed_10m", [])
        dirs      = hourly.get("wind_direction_10m", [])
        precip    = hourly.get("precipitation", [])

        if not times_raw:
            raise RuntimeError("Open-Meteo returned empty hourly data")

        manila = ZoneInfo("Asia/Manila")
        anchor = datetime.now(manila).replace(minute=0, second=0, microsecond=0)
        parsed_times = [
            datetime.fromisoformat(value).replace(tzinfo=manila)
            if datetime.fromisoformat(value).tzinfo is None
            else datetime.fromisoformat(value).astimezone(manila)
            for value in times_raw
        ]
        selected_indices = [
            index for index, value in enumerate(parsed_times) if value >= anchor
        ][:hours]
        n = len(selected_indices)
        if n != hours:
            raise RuntimeError(f"Open-Meteo returned {n} of {hours} anchored forecast hours")
        df = pd.DataFrame({
            "datetime":       pd.to_datetime([parsed_times[i] for i in selected_indices]),
            "wind_speed_ms":  np.array([winds[i] for i in selected_indices], dtype=float),
            "wind_dir_deg":   np.array([dirs[i] for i in selected_indices], dtype=float),
            "temperature_c":  np.array([temps[i] for i in selected_indices], dtype=float),
            "rainfall_mm":    np.array([precip[i] if precip else 0.0 for i in selected_indices], dtype=float),
        })

        logger.info(
            "Open-Meteo forecast OK — %d hours, temp %.1f–%.1f °C, "
            "wind %.1f–%.1f m/s, rain %.1f–%.1f mm",
            n,
            df["temperature_c"].min(), df["temperature_c"].max(),
            df["wind_speed_ms"].min(), df["wind_speed_ms"].max(),
            df["rainfall_mm"].min(), df["rainfall_mm"].max(),
        )

        return cls(df, source="open-meteo")

    # ── convenience: forecast with synthetic fallback ───────────
    @classmethod
    def forecast_or_synthetic(
        cls,
        lat: float = DEFAULT_LAT,
        lon: float = DEFAULT_LON,
        hours: int = 48,
        seed: int = 42,
    ) -> "WeatherTimeSeries":
        """
        Try to fetch a real forecast; fall back to synthetic on failure.

        This is the **recommended entry point** for scripts and notebooks.
        """
        try:
            return cls.from_forecast(lat=lat, lon=lon, hours=hours)
        except Exception as exc:
            logger.warning("Real forecast unavailable (%s) — using synthetic", exc)
            return cls.synthetic(hours=hours, seed=seed)

    # ── factory: synthetic ──────────────────────────────────────
    @classmethod
    def synthetic(
        cls,
        start: Optional[datetime] = None,
        hours: int = 48,
        seed: int = 42,
    ) -> "WeatherTimeSeries":
        """
        Generate a plausible 48-hour weather profile for a tropical
        maritime location like Guimaras, Philippines.

        - Temperature follows a sinusoidal diurnal cycle (26–34 °C)
        - Wind speed is moderate (1–6 m/s) with random variation
        - Wind direction drifts slowly (prevailing NE trade winds)
        - Rainfall follows tropical pattern (afternoon showers, episodic)
        """
        rng = np.random.default_rng(seed)
        if start is None:
            start = datetime(2025, 3, 15, 0, 0)  # mango season

        times = [start + timedelta(hours=h) for h in range(hours)]
        hours_arr = np.array([t.hour for t in times], dtype=float)

        # Temperature: diurnal sinusoid + noise
        temp = 30.0 + 4.0 * np.sin(2 * np.pi * (hours_arr - 6) / 24)
        temp += rng.normal(0, 0.5, size=hours)

        # Wind speed: base + slow variation + noise
        wind_speed = 2.5 + 1.5 * np.sin(2 * np.pi * hours_arr / 24 + 1.0)
        wind_speed += rng.normal(0, 0.4, size=hours)
        wind_speed = np.clip(wind_speed, 0.2, 8.0)

        # Wind direction: slow drift from NE (~45°) with noise
        wind_dir = 45 + 20 * np.sin(2 * np.pi * np.arange(hours) / 36)
        wind_dir += rng.normal(0, 10, size=hours)
        wind_dir = wind_dir % 360

        # Rainfall: tropical pattern with afternoon thunderstorms
        # Probability peaks in afternoon (13:00-18:00), occasional episodic events
        rainfall = np.zeros(hours)
        for i, h in enumerate(hours_arr):
            # Base probability: higher in afternoon
            if 13 <= h <= 18:
                prob = 0.3
            elif 6 <= h <= 12 or 19 <= h <= 21:
                prob = 0.1
            else:
                prob = 0.05
            
            # Episodic events: some days have higher rainfall probability
            day_idx = i // 24
            if rng.random() < 0.3:  # 30% chance of rainy day
                prob *= 2.0
            
            if rng.random() < prob:
                # Rainfall amount follows exponential distribution
                rainfall[i] = rng.exponential(3.0)  # mean 3mm when it rains
        
        rainfall = np.clip(rainfall, 0, 25.0)  # cap at 25mm/hour

        df = pd.DataFrame({
            "datetime":       times,
            "wind_speed_ms":  wind_speed,
            "wind_dir_deg":   wind_dir,
            "temperature_c":  temp,
            "rainfall_mm":    rainfall,
        })
        return cls(df, source="synthetic")

    # ── factory: from external ──────────────────────────────────
    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "WeatherTimeSeries":
        return cls(df, source="external")

    # ── repr ────────────────────────────────────────────────────
    def __repr__(self) -> str:
        return (
            f"WeatherTimeSeries({len(self.df)} steps, "
            f"source={self.source!r}, "
            f"{self.df['datetime'].iloc[0]} → {self.df['datetime'].iloc[-1]})"
        )
