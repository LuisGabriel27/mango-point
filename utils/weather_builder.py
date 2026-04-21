"""
MangoPoint — Time-Varying Manual Weather Builder
=================================================
Standalone module that converts the various ``manual_weather*`` request
fields into a single hourly weather list compatible with
``WeatherTimeSeries.from_dataframe``.

Three input forms are supported, in order of precedence:

    1. ``manual_weather_series`` — explicit per-hour list
    2. ``manual_weather_blocks`` — block-based schedule (``start_hour``, ``end_hour``)
    3. ``manual_weather``        — single dict, repeated for every hour
                                   (legacy / backward compatible)

If none are present, callers should fall back to the live forecast.

Why standalone?
    The builder is imported from FastAPI routes AND from unit tests. Putting
    it in ``utils/`` (alongside ``weather.py``) lets tests import it without
    pulling in the FastAPI app and its database session machinery.

Gate diagnostics
    ``compute_gate_diagnostics`` replays the per-hour weather through the
    pest gate's ``is_open`` predicate and returns a list of dicts describing
    why each hour was open or closed. Useful for calibrating cecid scenarios
    (which require fruitlet stage + 24 h rain ≥ 5 mm + dry current hour +
    crepuscular hour + low wind to all align).
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from utils.datetime_utils import (
    format_rfc3339 as _format_rfc3339,
    parse_rfc3339 as _parse_rfc3339,
    utcnow_naive,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  Defaults — used to fill gaps in partial overrides
# ─────────────────────────────────────────────
_WEATHER_DEFAULTS: Dict[str, float] = {
    "temperature_c": 30.0,
    "wind_speed_ms": 2.0,
    "wind_dir_deg":  90.0,
    "rainfall_mm":   0.0,
}

_WEATHER_KEYS = tuple(_WEATHER_DEFAULTS.keys())


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────
def _coerce_weather_value(key: str, value: Any) -> float:
    """
    Normalize one weather value to a safe float.

    - ``wind_speed_ms`` and ``rainfall_mm`` are clamped to ≥ 0 (defensive;
      Pydantic rejects negatives at the API boundary, but the builder is
      also called directly from tests and internal code).
    - ``wind_dir_deg`` is wrapped into [0, 360).
    """
    f = float(value)
    if key in ("wind_speed_ms", "rainfall_mm"):
        return max(0.0, f)
    if key == "wind_dir_deg":
        return f % 360.0
    return f


def _to_weather_dict(
    overrides: Optional[Dict[str, Any]],
    base: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Normalize a partial override dict to all four numeric weather keys."""
    out = dict(_WEATHER_DEFAULTS if base is None else base)
    if overrides:
        for k in _WEATHER_KEYS:
            v = overrides.get(k)
            if v is not None:
                try:
                    out[k] = _coerce_weather_value(k, v)
                except (TypeError, ValueError):
                    # Ignore unparseable values — default / inherited stays
                    pass
    return out


def _make_entry(start_dt: datetime, hour_index: int, weather: Dict[str, float]) -> Dict[str, Any]:
    """Assemble a single hourly weather record."""
    return {
        "datetime":      _format_rfc3339(start_dt + timedelta(hours=hour_index)),
        "temperature_c": float(weather["temperature_c"]),
        "wind_speed_ms": float(weather["wind_speed_ms"]),
        "wind_dir_deg":  float(weather["wind_dir_deg"]),
        "rainfall_mm":   float(weather["rainfall_mm"]),
    }


def _resolve_start_dt(start_dt: Any) -> datetime:
    """
    Normalize ``start_dt`` to a *naive* UTC datetime suitable for use as the
    anchor for a manual weather series.

    Accepts:
        - ``None``            → current UTC time
        - ``datetime`` (any)  → coerced to naive UTC (aware values are converted)
        - ``str``             → parsed via RFC3339, then coerced as above
        - anything else       → logged + fallback to current UTC

    Coercing to *naive* UTC keeps every entry's ``datetime`` field in a single
    consistent format (trailing ``Z``), which pandas can parse without raising
    ``DateParseError`` from mixed-tz columns later in the pipeline.
    """
    if start_dt is None:
        return utcnow_naive()
    if isinstance(start_dt, str):
        try:
            start_dt = _parse_rfc3339(start_dt)
        except (ValueError, TypeError):
            logger.warning("manual_weather_start: unparseable string %r — using current UTC", start_dt)
            return utcnow_naive()
    if not isinstance(start_dt, datetime):
        logger.warning("manual_weather_start: expected datetime, got %s — using current UTC", type(start_dt).__name__)
        return utcnow_naive()
    if start_dt.tzinfo is not None:
        # Convert aware → naive UTC for output consistency
        start_dt = start_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return start_dt


# ─────────────────────────────────────────────
#  Builder: constant (legacy)
# ─────────────────────────────────────────────
def _series_from_constant(
    overrides: Dict[str, Any],
    hours: int,
    start_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Repeat one weather dict for every hour (legacy ``manual_weather``)."""
    base = _to_weather_dict(overrides)
    base_dt = _resolve_start_dt(start_dt)
    return [_make_entry(base_dt, h, base) for h in range(hours)]


# ─────────────────────────────────────────────
#  Builder: explicit per-hour list
# ─────────────────────────────────────────────
def _series_from_entries(
    entries: List[Dict[str, Any]],
    hours: int,
    start_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Build a series from an explicit per-hour list.

    Each entry may be a partial dict; missing keys are inherited from the
    previous hour (or defaults for hour 0). If the list is shorter than
    ``hours``, the last entry is repeated to pad the tail. If longer, it is
    truncated.
    """
    base_dt = _resolve_start_dt(start_dt)
    out: List[Dict[str, Any]] = []
    last = dict(_WEATHER_DEFAULTS)
    for h in range(hours):
        if h < len(entries):
            last = _to_weather_dict(entries[h], base=last)
        # else: re-use last (pad)
        out.append(_make_entry(base_dt, h, last))
    return out


# ─────────────────────────────────────────────
#  Builder: block-based schedule
# ─────────────────────────────────────────────
def _series_from_blocks(
    blocks: List[Dict[str, Any]],
    hours: int,
    start_dt: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Build a series from a list of ``{start_hour, end_hour, ...weather}`` blocks.

    Semantics:
        - ``start_hour`` inclusive, ``end_hour`` exclusive
        - Blocks are applied in list order, so later blocks override earlier
          ones in overlapping ranges
        - Hours not covered by any block fall back to defaults
        - Each block's weather keys are independent — unspecified keys fall
          back to defaults, NOT the previous block (predictable, declarative)
    """
    base_dt = _resolve_start_dt(start_dt)

    # Initialize every hour with defaults
    per_hour: List[Dict[str, float]] = [dict(_WEATHER_DEFAULTS) for _ in range(hours)]

    for block in blocks:
        start_h = int(block.get("start_hour", 0))
        end_h   = int(block.get("end_hour", hours))
        start_h = max(0, start_h)
        end_h   = min(hours, end_h)
        if end_h <= start_h:
            continue
        block_weather = _to_weather_dict(block)
        for h in range(start_h, end_h):
            per_hour[h] = dict(block_weather)

    return [_make_entry(base_dt, h, per_hour[h]) for h in range(hours)]


# ─────────────────────────────────────────────
#  Pre-seed rainfall history
# ─────────────────────────────────────────────
def extract_initial_rainfall_history(
    request_obj: Any,
    weather_data: List[Dict[str, Any]],
    history_hours: int = 24,
) -> Optional[List[float]]:
    """
    Extract a pre-seed rainfall history from the request, if provided.

    Looks for ``manual_weather_prefix_rain`` (a list of mm values representing
    rainfall in the hours BEFORE the simulation starts). Useful for cecid
    scenarios where you want the engine to start with rain already
    accumulated in the 24-hour buffer.
    """
    prefix = getattr(request_obj, "manual_weather_prefix_rain", None)
    if not prefix:
        return None
    return [float(x) for x in prefix][-history_hours:]


# ─────────────────────────────────────────────
#  Dispatcher (precedence)
# ─────────────────────────────────────────────
def build_weather_series(request_obj: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Build an hourly weather list from the ``manual_weather*`` fields on a
    SimulationRequest-like object. Returns ``None`` if no override fields
    are populated (caller should then fetch the live forecast).

    Precedence (highest first):
        1. ``manual_weather_series``  — explicit per-hour list
        2. ``manual_weather_blocks``  — block-based schedule
        3. ``manual_weather``         — single constant dict (legacy)
    """
    hours = int(getattr(request_obj, "hours", 48))
    # _resolve_start_dt (called by each builder) handles None/str/datetime/garbage.
    start_dt = getattr(request_obj, "manual_weather_start", None)

    def _to_dict(obj: Any) -> Dict[str, Any]:
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "dict"):
            return obj.dict()
        return dict(obj)

    series = getattr(request_obj, "manual_weather_series", None)
    if series:
        logger.info("Manual weather: per-hour series (%d entries, requested %d hours)", len(series), hours)
        return _series_from_entries([_to_dict(e) for e in series], hours, start_dt)

    blocks = getattr(request_obj, "manual_weather_blocks", None)
    if blocks:
        logger.info("Manual weather: %d blocks over %d hours", len(blocks), hours)
        return _series_from_blocks([_to_dict(b) for b in blocks], hours, start_dt)

    constant = getattr(request_obj, "manual_weather", None)
    if constant:
        logger.info("Manual weather: constant override over %d hours", hours)
        return _series_from_constant(_to_dict(constant), hours, start_dt)

    return None


# ─────────────────────────────────────────────
#  Diagnostics — replay gates against the series
# ─────────────────────────────────────────────
def compute_gate_diagnostics(
    weather_data: List[Dict[str, Any]],
    pest_type: str,
    orchard_stage: str,
    sugar_index: float = 0.5,
    initial_rainfall_history: Optional[List[float]] = None,
    history_hours: int = 24,
) -> List[Dict[str, Any]]:
    """
    Replay the gate's ``is_open`` predicate hour-by-hour over ``weather_data``
    and return a per-hour diagnostic record.

    This is a calibration aid: when a cecid scenario produces zero infections
    you can inspect this list to see exactly which hours the gate was open
    (or which conditions failed when it stayed closed).
    """
    # Local import to avoid a hard dependency at module import time
    from core.biological_rules import CecidFlyGate, FruitFlyGate
    from core.config import OrchardStage

    pest = (pest_type or "").lower()
    if pest == "cecid":
        gate = CecidFlyGate()
    elif pest == "fruitfly":
        gate = FruitFlyGate()
    else:
        return []

    # OrchardStage is int-valued; look up by uppercase name (e.g. "fruitlet" → FRUITLET)
    try:
        stage_enum = OrchardStage[(orchard_stage or "").upper()]
    except (KeyError, AttributeError):
        stage_enum = OrchardStage.MATURE

    history: deque = deque(maxlen=history_hours)
    if initial_rainfall_history:
        seed = [0.0] * history_hours + [float(r) for r in initial_rainfall_history]
        for r in seed[-history_hours:]:
            history.append(r)
    else:
        for _ in range(history_hours):
            history.append(0.0)

    out: List[Dict[str, Any]] = []
    for h, entry in enumerate(weather_data):
        try:
            dt_str = entry.get("datetime", "")
            hour_of_day = int(_parse_rfc3339(dt_str).hour) if dt_str else h % 24
        except (ValueError, AttributeError, TypeError):
            hour_of_day = h % 24

        rainfall = float(entry.get("rainfall_mm", 0.0))
        wind_speed = float(entry.get("wind_speed_ms", 0.0))
        temp = float(entry.get("temperature_c", 30.0))

        # Mirror engine ordering: append CURRENT rainfall to history BEFORE
        # evaluating the gate. The cecid gate checks `rainfall_mm` (current
        # hour, must be 0) separately from `rainfall_history` (24-h rolling
        # window, must total ≥ threshold).
        history.append(rainfall)

        is_open = gate.is_open(
            hour=hour_of_day,
            wind_speed_ms=wind_speed,
            temperature_c=temp,
            rainfall_mm=rainfall,
            rainfall_history=history,
            orchard_stage=stage_enum,
            sugar_index=sugar_index,
        )

        out.append({
            "step": h,
            "datetime": entry.get("datetime"),
            "hour_of_day": hour_of_day,
            "rainfall_mm": rainfall,
            "rain_24h_sum": float(sum(history)),
            "wind_speed_ms": wind_speed,
            "temperature_c": temp,
            "gate_open": bool(is_open),
        })

    return out
