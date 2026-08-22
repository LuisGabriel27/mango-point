"""Solar-time helpers for Guimaras-local biological gate checks.

The project only needs sunrise and sunset to the nearest few minutes, so this
module uses NOAA's compact sunrise/sunset approximation instead of adding a
runtime dependency.  All public helpers return timezone-aware datetimes and
interpret naive inputs as Asia/Manila wall time.
"""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo


MANILA_TZ = ZoneInfo("Asia/Manila")


def as_manila_time(value: datetime) -> datetime:
    """Return *value* in Asia/Manila; naive values are local wall time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=MANILA_TZ)
    return value.astimezone(MANILA_TZ)


def _normalize_degrees(value: float) -> float:
    return value % 360.0


def _solar_event_utc_hour(
    day: date,
    latitude: float,
    longitude: float,
    *,
    sunrise: bool,
) -> Optional[float]:
    """NOAA sunrise/sunset approximation, returned as a UTC decimal hour."""
    day_number = day.timetuple().tm_yday
    longitude_hour = longitude / 15.0
    estimate = day_number + (
        (6.0 - longitude_hour) / 24.0
        if sunrise
        else (18.0 - longitude_hour) / 24.0
    )

    mean_anomaly = (0.9856 * estimate) - 3.289
    true_longitude = _normalize_degrees(
        mean_anomaly
        + 1.916 * math.sin(math.radians(mean_anomaly))
        + 0.020 * math.sin(math.radians(2.0 * mean_anomaly))
        + 282.634
    )

    right_ascension = _normalize_degrees(
        math.degrees(math.atan(0.91764 * math.tan(math.radians(true_longitude))))
    )
    longitude_quadrant = math.floor(true_longitude / 90.0) * 90.0
    ascension_quadrant = math.floor(right_ascension / 90.0) * 90.0
    right_ascension = (right_ascension + longitude_quadrant - ascension_quadrant) / 15.0

    sin_declination = 0.39782 * math.sin(math.radians(true_longitude))
    cos_declination = math.cos(math.asin(sin_declination))
    latitude_rad = math.radians(latitude)
    zenith = math.radians(90.833)  # official sunrise/sunset incl. refraction
    denominator = cos_declination * math.cos(latitude_rad)
    if abs(denominator) < 1e-12:
        return None
    cos_hour_angle = (
        math.cos(zenith) - sin_declination * math.sin(latitude_rad)
    ) / denominator
    if cos_hour_angle < -1.0 or cos_hour_angle > 1.0:
        return None

    hour_angle = math.degrees(math.acos(cos_hour_angle))
    if sunrise:
        hour_angle = 360.0 - hour_angle
    hour_angle /= 15.0

    local_mean_time = hour_angle + right_ascension - (0.06571 * estimate) - 6.622
    return (local_mean_time - longitude_hour) % 24.0


def solar_times(
    day: date,
    latitude: float,
    longitude: float,
) -> Tuple[datetime, datetime]:
    """Return sunrise and sunset for *day* at the orchard coordinates."""
    sunrise_hour = _solar_event_utc_hour(
        day, latitude, longitude, sunrise=True,
    )
    sunset_hour = _solar_event_utc_hour(
        day, latitude, longitude, sunrise=False,
    )

    # Guimaras is never near a polar day/night boundary.  The fallback keeps
    # diagnostics usable if malformed coordinates somehow reach this helper.
    if sunrise_hour is None or sunset_hour is None:
        local_midnight = datetime.combine(day, time.min, tzinfo=MANILA_TZ)
        return local_midnight + timedelta(hours=6), local_midnight + timedelta(hours=18)

    local_midnight = datetime.combine(day, time.min, tzinfo=MANILA_TZ)
    utc_offset_hours = (
        local_midnight.utcoffset().total_seconds() / 3600.0
        if local_midnight.utcoffset() is not None
        else 8.0
    )
    sunrise_dt = local_midnight + timedelta(hours=(sunrise_hour + utc_offset_hours) % 24.0)
    sunset_dt = local_midnight + timedelta(hours=(sunset_hour + utc_offset_hours) % 24.0)
    return sunrise_dt, sunset_dt


def solar_twilight_context(
    value: datetime,
    latitude: float,
    longitude: float,
    window_hours: float = 1.0,
) -> dict:
    """Describe whether *value* is within the dawn or dusk activity window."""
    local_value = as_manila_time(value)
    sunrise_dt, sunset_dt = solar_times(local_value.date(), latitude, longitude)
    window = timedelta(hours=max(0.0, float(window_hours)))
    dawn = abs(local_value - sunrise_dt) <= window
    dusk = abs(local_value - sunset_dt) <= window
    return {
        "is_crepuscular": bool(dawn or dusk),
        "window": "dawn" if dawn else "dusk" if dusk else None,
        "sunrise": sunrise_dt,
        "sunset": sunset_dt,
        "local_datetime": local_value,
    }


__all__ = [
    "MANILA_TZ",
    "as_manila_time",
    "solar_times",
    "solar_twilight_context",
]
