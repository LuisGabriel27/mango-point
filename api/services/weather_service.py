"""
MangoPoint API — Weather Service
==================================
Real-time weather integration with Open-Meteo API (free, no API key).
Falls back to synthetic weather if API fails.
"""

import logging
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, Tuple
import httpx
from functools import lru_cache
import asyncio

from ..core.config import settings
from utils.datetime_utils import format_rfc3339, utcnow_naive

logger = logging.getLogger(__name__)

# Open-Meteo base URL (free, no API key required)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
MANILA_TZ = ZoneInfo("Asia/Manila")
ANTECEDENT_HOURS = 72


class WeatherCache:
    """Simple in-memory cache for weather data."""
    
    def __init__(self, ttl_seconds: int = 600):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
        self._lock = asyncio.Lock()
    
    def _make_key(self, lat: float, lon: float) -> str:
        """Create cache key from coordinates (rounded to 2 decimals)."""
        return f"{lat:.2f},{lon:.2f}"
    
    async def get(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get cached weather if not expired."""
        key = self._make_key(lat, lon)
        async with self._lock:
            if key in self._cache:
                data, timestamp = self._cache[key]
                if utcnow_naive() - timestamp < timedelta(seconds=self.ttl):
                    return data
                else:
                    del self._cache[key]
        return None
    
    async def set(self, lat: float, lon: float, data: Dict[str, Any]) -> None:
        """Cache weather data."""
        key = self._make_key(lat, lon)
        async with self._lock:
            self._cache[key] = (data, utcnow_naive())
    
    async def get_expiry(self, lat: float, lon: float) -> Optional[datetime]:
        """Get cache expiry time."""
        key = self._make_key(lat, lon)
        async with self._lock:
            if key in self._cache:
                _, timestamp = self._cache[key]
                return timestamp + timedelta(seconds=self.ttl)
        return None


# Global cache instance
_weather_cache = WeatherCache(ttl_seconds=settings.WEATHER_CACHE_TTL_SECONDS)


class WeatherService:
    """
    Service for fetching weather data from Open-Meteo API (free, no API key).
    Includes caching and fallback to synthetic data.
    """
    
    def __init__(self):
        self.cache = _weather_cache
    
    async def get_live_weather(
        self,
        lat: float,
        lon: float,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Fetch live weather data from Open-Meteo.
        
        Parameters
        ----------
        lat : float
            Latitude
        lon : float
            Longitude
        use_cache : bool
            Whether to use cached data if available
            
        Returns
        -------
        dict
            Weather data with keys: wind_speed_ms, wind_dir_deg,
            temperature_c, humidity, datetime, source, cached. wind_dir_deg
            follows the meteorological wind-from convention.
        """
        # Check cache first
        if use_cache:
            cached = await self.cache.get(lat, lon)
            if cached:
                logger.debug(f"Using cached weather for ({lat}, {lon})")
                cached["cached"] = True
                cached["cache_expires_at"] = await self.cache.get_expiry(lat, lon)
                return cached
        
        # Fetch from Open-Meteo
        try:
            weather_data = await self._fetch_current_from_open_meteo(lat, lon)
            
            # Cache the result
            await self.cache.set(lat, lon, weather_data)
            
            weather_data["cached"] = False
            weather_data["cache_expires_at"] = await self.cache.get_expiry(lat, lon)
            
            return weather_data
            
        except Exception as e:
            logger.error(f"Failed to fetch weather from Open-Meteo: {e}")
            logger.info("Falling back to synthetic weather")
            return self._generate_synthetic_weather(lat, lon)
    
    async def _fetch_current_from_open_meteo(self, lat: float, lon: float) -> Dict[str, Any]:
        """Fetch current weather data from Open-Meteo API."""
        params = {
            "latitude":        lat,
            "longitude":       lon,
            "current":         "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "ms",
            "timezone":        "auto",
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()
        
        current = data.get("current", {})
        
        weather = {
            "wind_speed_ms":  current.get("wind_speed_10m", 0.0),
            "wind_dir_deg":   current.get("wind_direction_10m", 0.0),
            "temperature_c":  current.get("temperature_2m", 25.0),
            "humidity":       current.get("relative_humidity_2m", 70.0),
            "datetime":       current.get("time", utcnow_naive().isoformat()) + "Z",
            "source":         "open-meteo",
        }
        
        logger.info(f"Fetched current weather: {weather['temperature_c']:.1f}°C, "
                   f"wind {weather['wind_speed_ms']:.1f}m/s from {weather['wind_dir_deg']:.0f}°")
        
        return weather
    
    def _generate_synthetic_weather(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Generate synthetic weather data as fallback.
        Based on typical tropical maritime conditions.
        """
        import numpy as np
        
        now = utcnow_naive()
        hour = now.hour
        
        # Temperature: diurnal cycle (26-34°C for tropical)
        temp = 30.0 + 4.0 * np.sin(2 * np.pi * (hour - 6) / 24)
        temp += np.random.normal(0, 0.5)
        
        # Wind: moderate with variation
        wind_speed = 2.5 + 1.5 * np.sin(2 * np.pi * hour / 24 + 1.0)
        wind_speed += np.random.normal(0, 0.4)
        wind_speed = np.clip(wind_speed, 0.2, 8.0)
        
        # Wind direction: NE trade winds with variation
        wind_dir = 45 + np.random.normal(0, 15)
        wind_dir = wind_dir % 360
        
        # Humidity: higher at night
        humidity = 75 + 15 * np.sin(2 * np.pi * (hour - 12) / 24)
        humidity += np.random.normal(0, 5)
        humidity = np.clip(humidity, 40, 100)
        
        return {
            "wind_speed_ms": float(wind_speed),
            "wind_dir_deg": float(wind_dir),
            "temperature_c": float(temp),
            "humidity": float(humidity),
            "datetime": format_rfc3339(now),
            "source": "synthetic",
            "cached": False,
            "cache_expires_at": None,
        }
    
    async def get_forecast(
        self,
        lat: float,
        lon: float,
        hours: int = 48,
    ) -> list:
        """
        Get hourly weather forecast for simulation from Open-Meteo.
        Falls back to synthetic generation on failure.
        """
        try:
            return await self._fetch_forecast_from_open_meteo(lat, lon, hours)
        except Exception as e:
            logger.error(f"Failed to fetch forecast: {e}")
            return self._generate_synthetic_forecast(lat, lon, hours)
    
    async def _fetch_forecast_from_open_meteo(
        self,
        lat: float,
        lon: float,
        hours: int,
    ) -> list:
        """Fetch hourly forecast from Open-Meteo API (free, no API key)."""
        import numpy as np

        forecast_days = max(1, -(-hours // 24))  # ceil division

        params = {
            "latitude":        lat,
            "longitude":       lon,
            "hourly":          "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation",
            "wind_speed_unit": "ms",
            "timezone":        "auto",
            "forecast_days":   min(forecast_days, 16),
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()
        
        hourly = data.get("hourly", {})
        times_raw  = hourly.get("time", [])
        temps      = hourly.get("temperature_2m", [])
        humidities = hourly.get("relative_humidity_2m", [])
        winds      = hourly.get("wind_speed_10m", [])
        dirs       = hourly.get("wind_direction_10m", [])
        precip     = hourly.get("precipitation", [])

        if not times_raw:
            raise RuntimeError("Open-Meteo returned empty hourly data")

        n = min(hours, len(times_raw))
        forecasts = []

        for i in range(n):
            dt = datetime.fromisoformat(times_raw[i])
            forecasts.append({
                "datetime":       format_rfc3339(dt),
                "hour":           dt.hour,
                "wind_speed_ms":  float(winds[i])  if i < len(winds) else 2.0,
                "wind_dir_deg":   float(dirs[i])   if i < len(dirs)  else 45.0,
                "temperature_c":  float(temps[i])  if i < len(temps) else 28.0,
                "humidity":       float(humidities[i]) if i < len(humidities) else 70.0,
                "rainfall_mm":    float(precip[i]) if i < len(precip) else 0.0,
                "source":         "open-meteo",
            })

        logger.info(
            "Open-Meteo forecast: %d hours, temp %.1f–%.1f °C, wind %.1f–%.1f m/s, rain %.1f–%.1f mm",
            n,
            min(f["temperature_c"] for f in forecasts),
            max(f["temperature_c"] for f in forecasts),
            min(f["wind_speed_ms"] for f in forecasts),
            max(f["wind_speed_ms"] for f in forecasts),
            min(f["rainfall_mm"] for f in forecasts),
            max(f["rainfall_mm"] for f in forecasts),
        )
        
        return forecasts
    
    def _generate_synthetic_forecast(
        self,
        lat: float,
        lon: float,
        hours: int,
    ) -> list:
        """Generate synthetic forecast data."""
        import numpy as np
        
        rng = np.random.default_rng()
        start = utcnow_naive()
        forecasts = []
        
        for h in range(hours):
            dt = start + timedelta(hours=h)
            hour = dt.hour
            
            temp = 30.0 + 4.0 * np.sin(2 * np.pi * (hour - 6) / 24)
            temp += rng.normal(0, 0.5)
            
            wind_speed = 2.5 + 1.5 * np.sin(2 * np.pi * hour / 24 + 1.0)
            wind_speed += rng.normal(0, 0.4)
            wind_speed = np.clip(wind_speed, 0.2, 8.0)
            
            wind_dir = 45 + 20 * np.sin(2 * np.pi * h / 36)
            wind_dir += rng.normal(0, 10)
            wind_dir = wind_dir % 360
            
            humidity = 75 + 15 * np.sin(2 * np.pi * (hour - 12) / 24)
            humidity = np.clip(humidity + rng.normal(0, 5), 40, 100)

            if 13 <= hour <= 18:
                rain_prob = 0.3
            elif 6 <= hour <= 12 or 19 <= hour <= 21:
                rain_prob = 0.1
            else:
                rain_prob = 0.05

            if rng.random() < 0.3:
                rain_prob *= 2.0

            rainfall = float(np.clip(rng.exponential(3.0), 0.0, 25.0)) if rng.random() < rain_prob else 0.0
            
            forecasts.append({
                "datetime": format_rfc3339(dt),
                "hour": hour,
                "wind_speed_ms": float(wind_speed),
                "wind_dir_deg": float(wind_dir),
                "temperature_c": float(temp),
                "humidity": float(humidity),
                "rainfall_mm": rainfall,
                "source": "synthetic",
            })
        
        return forecasts


    # ------------------------------------------------------------------
    # Anchored weather bundle API (v2)
    # ------------------------------------------------------------------
    @staticmethod
    def _local_hour(value: Optional[datetime] = None) -> datetime:
        current = value or datetime.now(MANILA_TZ)
        if current.tzinfo is None:
            current = current.replace(tzinfo=MANILA_TZ)
        return current.astimezone(MANILA_TZ).replace(
            minute=0, second=0, microsecond=0,
        )

    @staticmethod
    def _deterministic_seed(
        lat: float,
        lon: float,
        anchor: datetime,
        purpose: str,
    ) -> int:
        material = f"{purpose}|{lat:.5f}|{lon:.5f}|{anchor.isoformat()}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(material).digest()[:8], "big") % (2**32)

    @staticmethod
    def _fallback_reason(exc: Exception) -> str:
        text = str(exc).strip() or "no error detail supplied"
        return f"{type(exc).__name__}: {text}"[:500]

    @staticmethod
    def _provenance(
        *,
        lat: float,
        lon: float,
        source: str,
        anchor: datetime,
        fallback_reason: Optional[str] = None,
        synthetic_seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        return {
            "provider": "open-meteo",
            "source": source,
            "coordinates": {"lat": float(lat), "lon": float(lon)},
            "timezone": "Asia/Manila",
            "anchor_time": format_rfc3339(anchor),
            "fetched_at": format_rfc3339(datetime.now(timezone.utc)),
            "fallback_reason": fallback_reason,
            "synthetic_seed": synthetic_seed,
        }

    async def get_live_weather(
        self,
        lat: float,
        lon: float,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        if use_cache:
            cached = await self.cache.get(lat, lon)
            if cached:
                result = dict(cached)
                result["cached"] = True
                result["cache_expires_at"] = await self.cache.get_expiry(lat, lon)
                return result

        anchor = self._local_hour()
        try:
            weather = await self._fetch_current_v2(lat, lon, anchor)
        except Exception as exc:
            reason = self._fallback_reason(exc)
            seed = self._deterministic_seed(lat, lon, anchor, "current")
            logger.error("Open-Meteo current weather failed; using deterministic fallback: %s", reason)
            weather = self._generate_synthetic_current_v2(lat, lon, anchor, seed, reason)

        await self.cache.set(lat, lon, dict(weather))
        result = dict(weather)
        result["cached"] = False
        result["cache_expires_at"] = await self.cache.get_expiry(lat, lon)
        return result

    async def _fetch_current_v2(
        self,
        lat: float,
        lon: float,
        anchor: datetime,
    ) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "ms",
            "timezone": "Asia/Manila",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()
        current = data.get("current") or {}
        if not current.get("time"):
            raise RuntimeError("Open-Meteo returned no current timestamp")
        observed = datetime.fromisoformat(str(current["time"]))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=MANILA_TZ)
        provenance = self._provenance(
            lat=lat, lon=lon, source="open-meteo", anchor=anchor,
        )
        return {
            "wind_speed_ms": float(current.get("wind_speed_10m", 0.0)),
            "wind_dir_deg": float(current.get("wind_direction_10m", 0.0)),
            "temperature_c": float(current.get("temperature_2m", 25.0)),
            "humidity": float(current.get("relative_humidity_2m", 70.0)),
            "datetime": format_rfc3339(observed),
            "source": "open-meteo",
            "provenance": provenance,
            "fallback_reason": None,
        }

    def _generate_synthetic_current_v2(
        self,
        lat: float,
        lon: float,
        anchor: datetime,
        seed: int,
        reason: str,
    ) -> Dict[str, Any]:
        entry = self._generate_synthetic_forecast(
            lat=lat, lon=lon, hours=1, seed=seed, start=anchor,
        )[0]
        provenance = self._provenance(
            lat=lat,
            lon=lon,
            source="synthetic",
            anchor=anchor,
            fallback_reason=reason,
            synthetic_seed=seed,
        )
        return {
            **entry,
            "humidity": float(entry.get("humidity", 75.0)),
            "source": "synthetic",
            "provenance": provenance,
            "fallback_reason": reason,
        }

    async def get_forecast_bundle(
        self,
        lat: float,
        lon: float,
        hours: int = 48,
    ) -> Dict[str, Any]:
        hours = max(1, min(168, int(hours)))
        anchor = self._local_hour()
        try:
            return await self._fetch_forecast_bundle_open_meteo(
                lat=lat, lon=lon, hours=hours, anchor=anchor,
            )
        except Exception as exc:
            reason = self._fallback_reason(exc)
            seed = self._deterministic_seed(lat, lon, anchor, f"bundle-{hours}")
            logger.error("Open-Meteo forecast failed; using deterministic fallback: %s", reason)
            return self._generate_synthetic_bundle(
                lat=lat,
                lon=lon,
                hours=hours,
                anchor=anchor,
                seed=seed,
                fallback_reason=reason,
            )

    async def get_forecast(
        self,
        lat: float,
        lon: float,
        hours: int = 48,
    ) -> list:
        """Backward-compatible forecast list with deterministic fallback."""
        try:
            return await self._fetch_forecast_from_open_meteo(lat, lon, hours)
        except Exception as exc:
            anchor = self._local_hour()
            reason = self._fallback_reason(exc)
            seed = self._deterministic_seed(lat, lon, anchor, f"forecast-{hours}")
            logger.error("Open-Meteo forecast failed; using deterministic fallback: %s", reason)
            return self._generate_synthetic_forecast(
                lat=lat, lon=lon, hours=hours, seed=seed, start=anchor,
            )

    async def _fetch_forecast_from_open_meteo(
        self,
        lat: float,
        lon: float,
        hours: int,
    ) -> list:
        bundle = await self._fetch_forecast_bundle_open_meteo(
            lat=lat,
            lon=lon,
            hours=hours,
            anchor=self._local_hour(),
        )
        return bundle["forecast"]

    async def _fetch_forecast_bundle_open_meteo(
        self,
        lat: float,
        lon: float,
        hours: int,
        anchor: datetime,
    ) -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation",
            "wind_speed_unit": "ms",
            "timezone": "Asia/Manila",
            "past_hours": ANTECEDENT_HOURS,
            "forecast_hours": hours,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            payload = response.json()

        hourly = payload.get("hourly") or {}
        records = self._records_from_hourly(hourly, source="open-meteo")
        antecedent = [record for record in records if record["_datetime"] < anchor][-ANTECEDENT_HOURS:]
        forecast = [record for record in records if record["_datetime"] >= anchor][:hours]
        if len(antecedent) != ANTECEDENT_HOURS or len(forecast) != hours:
            raise RuntimeError(
                f"Open-Meteo returned an incomplete anchored window "
                f"({len(antecedent)} antecedent, {len(forecast)} forecast)"
            )
        for record in antecedent + forecast:
            record.pop("_datetime", None)
        return {
            "antecedent": antecedent,
            "forecast": forecast,
            "provenance": self._provenance(
                lat=lat, lon=lon, source="open-meteo", anchor=anchor,
            ),
        }

    @staticmethod
    def _records_from_hourly(hourly: Dict[str, Any], source: str) -> list:
        times = hourly.get("time") or []
        if not times:
            raise RuntimeError("Open-Meteo returned empty hourly data")
        fields = {
            "temperature_c": hourly.get("temperature_2m") or [],
            "humidity": hourly.get("relative_humidity_2m") or [],
            "wind_speed_ms": hourly.get("wind_speed_10m") or [],
            "wind_dir_deg": hourly.get("wind_direction_10m") or [],
            "rainfall_mm": hourly.get("precipitation") or [],
        }
        defaults = {
            "temperature_c": 28.0,
            "humidity": 70.0,
            "wind_speed_ms": 2.0,
            "wind_dir_deg": 45.0,
            "rainfall_mm": 0.0,
        }
        records = []
        for index, raw_time in enumerate(times):
            parsed = datetime.fromisoformat(str(raw_time))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=MANILA_TZ)
            record = {
                "_datetime": parsed,
                "datetime": format_rfc3339(parsed),
                "hour": parsed.astimezone(MANILA_TZ).hour,
                "source": source,
            }
            for name, values in fields.items():
                record[name] = float(values[index]) if index < len(values) else defaults[name]
            records.append(record)
        return records

    def _generate_synthetic_forecast(
        self,
        lat: float,
        lon: float,
        hours: int,
        seed: Optional[int] = None,
        start: Optional[datetime] = None,
    ) -> list:
        """Generate a reproducible, explicitly labelled fallback forecast."""
        import numpy as np

        anchor = self._local_hour(start)
        resolved_seed = seed if seed is not None else self._deterministic_seed(
            lat, lon, anchor, f"synthetic-{hours}",
        )
        rng = np.random.default_rng(resolved_seed)
        forecasts = []
        rainy_day_flags: Dict[int, bool] = {}
        for index in range(max(0, int(hours))):
            current = anchor + timedelta(hours=index)
            hour = current.hour
            temperature = 30.0 + 4.0 * np.sin(2.0 * np.pi * (hour - 6) / 24.0)
            temperature += rng.normal(0.0, 0.5)
            wind_speed = 2.5 + 1.5 * np.sin(2.0 * np.pi * hour / 24.0 + 1.0)
            wind_speed = float(np.clip(wind_speed + rng.normal(0.0, 0.4), 0.2, 8.0))
            wind_direction = float((45.0 + 20.0 * np.sin(2.0 * np.pi * index / 36.0) + rng.normal(0.0, 10.0)) % 360.0)
            humidity = float(np.clip(75.0 + 15.0 * np.sin(2.0 * np.pi * (hour - 12) / 24.0) + rng.normal(0.0, 5.0), 40.0, 100.0))
            base_probability = 0.3 if 13 <= hour <= 18 else 0.1 if 6 <= hour <= 12 or 19 <= hour <= 21 else 0.05
            day_index = index // 24
            if day_index not in rainy_day_flags:
                rainy_day_flags[day_index] = bool(rng.random() < 0.3)
            if rainy_day_flags[day_index]:
                base_probability *= 2.0
            rainfall = float(np.clip(rng.exponential(3.0), 0.0, 25.0)) if rng.random() < base_probability else 0.0
            forecasts.append({
                "datetime": format_rfc3339(current),
                "hour": hour,
                "wind_speed_ms": wind_speed,
                "wind_dir_deg": wind_direction,
                "temperature_c": float(temperature),
                "humidity": humidity,
                "rainfall_mm": rainfall,
                "source": "synthetic",
            })
        return forecasts

    def _generate_synthetic_bundle(
        self,
        *,
        lat: float,
        lon: float,
        hours: int,
        anchor: datetime,
        seed: int,
        fallback_reason: str,
    ) -> Dict[str, Any]:
        combined = self._generate_synthetic_forecast(
            lat=lat,
            lon=lon,
            hours=ANTECEDENT_HOURS + hours,
            seed=seed,
            start=anchor - timedelta(hours=ANTECEDENT_HOURS),
        )
        return {
            "antecedent": combined[:ANTECEDENT_HOURS],
            "forecast": combined[ANTECEDENT_HOURS:],
            "provenance": self._provenance(
                lat=lat,
                lon=lon,
                source="synthetic",
                anchor=anchor,
                fallback_reason=fallback_reason,
                synthetic_seed=seed,
            ),
        }


# Singleton instance
weather_service = WeatherService()
