"""Daytime light evidence for fruit-attacking Cecid; canopy shade is not a trigger."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping, Optional

from core.config import (
    CECID_DAY_CLOUD_MIN_PCT, CECID_DAY_CLOUD_FULL_PCT,
    CECID_LIGHT_DIM_RATIO, CECID_LIGHT_BRIGHT_RATIO, CECID_LIGHT_DNI_REFERENCE_WM2,
)
from utils.solar import clear_sky_shortwave_reference


DAYLIGHT_CONDITION_SCORES = {
    "bright_sunshine": 0.0,
    "intermittent_sunshine": 0.5,
    "dim_overcast": 1.0,
}
DAYLIGHT_WEATHER_FIELDS = (
    "shortwave_radiation_wm2", "direct_normal_irradiance_wm2",
    "daylight_condition", "daylight_condition_basis",
)


def nonnegative_finite(value: Any) -> Optional[float]:
    try:
        number = float(value) if value is not None else None
    except (ValueError, TypeError):
        return None
    return number if number is not None and math.isfinite(number) and number >= 0 else None


def daylight_light_components(weather: Mapping[str, Any], value: Optional[datetime], latitude: float, longitude: float) -> dict:
    """Resolve explicit scenario light, otherwise cloud + instant GHI/DNI.

    Both radiation fields are instantaneous estimates for the indicated time.
    The clearness and cloud response scales are transparent project assumptions.
    Missing/invalid radiation remains unknown; it is never fabricated from cloud.
    """
    condition = weather.get("daylight_condition")
    basis = weather.get("daylight_condition_basis")
    ghi = nonnegative_finite(weather.get("shortwave_radiation_wm2"))
    dni = nonnegative_finite(weather.get("direct_normal_irradiance_wm2"))
    cloud = nonnegative_finite(weather.get("cloud_cover_pct"))
    reference = clear_sky_shortwave_reference(value, latitude, longitude) if value is not None else None
    result = {
        "daylight_condition": condition if condition in DAYLIGHT_CONDITION_SCORES else None,
        "daylight_condition_basis": basis if basis in ("observed", "assumed") else "assumed" if condition in DAYLIGHT_CONDITION_SCORES else None,
        "shortwave_radiation_wm2": ghi,
        "direct_normal_irradiance_wm2": dni,
        "clear_sky_shortwave_reference_wm2": reference,
        "daylight_brightness_ratio": None,
        "daylight_light_score": 0.0,
        "daylight_light_status": "unknown",
        "daylight_light_basis": "unknown",
        "daylight_light_limiting_reason": "daytime light unknown; cloud cover alone cannot enable activity",
        "canopy_shade_enables_activity": False,
        "light_response_is_calibrated": False,
    }
    if condition in DAYLIGHT_CONDITION_SCORES:
        result.update({
            "daylight_light_score": DAYLIGHT_CONDITION_SCORES[condition],
            "daylight_light_status": condition,
            "daylight_light_basis": f"custom_{result['daylight_condition_basis']}",
            "daylight_light_limiting_reason": "bright sunshine closes the daytime exception" if condition == "bright_sunshine" else None,
        })
        return result
    if ghi is None or dni is None or cloud is None or reference is None or reference <= 0:
        return result
    # Either substantial direct sun or bright diffuse daylight can close the
    # exception. A low horizontal reading near sunset is not itself overcast.
    brightness = max(ghi / reference, dni / CECID_LIGHT_DNI_REFERENCE_WM2)
    dimness = max(0.0, min(1.0, (CECID_LIGHT_BRIGHT_RATIO - brightness) / (CECID_LIGHT_BRIGHT_RATIO - CECID_LIGHT_DIM_RATIO)))
    cloud_strength = max(0.0, min(1.0, (cloud - CECID_DAY_CLOUD_MIN_PCT) / (CECID_DAY_CLOUD_FULL_PCT - CECID_DAY_CLOUD_MIN_PCT)))
    score = dimness * cloud_strength
    status = "bright_sunshine" if dimness == 0 else "dim_overcast" if score == 1 else "intermittent_sunshine" if score > 0 else "insufficient_cloud"
    result.update({
        "daylight_brightness_ratio": brightness,
        "daylight_light_score": score,
        "daylight_light_status": status,
        "daylight_light_basis": "radiation_estimate",
        "daylight_light_limiting_reason": (
            "strong sunlight closes the daytime exception" if dimness == 0
            else "insufficient cloud cover for the daytime exception" if cloud_strength == 0 else None
        ),
    })
    return result


def daylight_model_assumptions() -> dict:
    return {
        "daytime_light_model": "explicit observed/assumed condition, otherwise cloud plus instant GHI/DNI",
        "cloud_cover_alone_enables_activity": False,
        "canopy_shade_enables_activity": False,
        "missing_radiation_policy": "daytime exception closed unless explicit daylight condition supplied",
        "solar_radiation_interval": "instantaneous estimate at indicated time",
        "clear_sky_reference": "NOAA solar position + Haurwitz GHI; not measured orchard light",
        "cloud_min_pct": CECID_DAY_CLOUD_MIN_PCT,
        "cloud_full_pct": CECID_DAY_CLOUD_FULL_PCT,
        "dim_brightness_ratio": CECID_LIGHT_DIM_RATIO,
        "bright_brightness_ratio": CECID_LIGHT_BRIGHT_RATIO,
        "dni_reference_wm2": CECID_LIGHT_DNI_REFERENCE_WM2,
        "custom_light_scores": dict(DAYLIGHT_CONDITION_SCORES),
        "light_response_is_calibrated": False,
    }
