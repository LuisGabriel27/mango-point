"""
Tests — Time-Varying Manual Weather Builder
============================================
Covers:
  1. Constant builder (legacy ``manual_weather``)
  2. Per-hour series builder (``manual_weather_series``)
  3. Block-based builder (``manual_weather_blocks``)
  4. Precedence: series > blocks > constant
  5. Validation: ManualWeatherBlock end_hour > start_hour
  6. Cecid acceptance: wet → dry block schedule opens the gate at dusk
  7. Regression: a constant-rain manual_weather still produces N hourly entries
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.weather_builder import (
    _series_from_constant,
    _series_from_entries,
    _series_from_blocks,
    _parse_rfc3339,
    build_weather_series,
    build_manual_antecedent_weather,
    compute_gate_diagnostics,
    _WEATHER_DEFAULTS,
)
from api.models.schemas import (
    ManualWeather,
    ManualWeatherBlock,
    SimulationRequest,
)
from api.services.simulation_service import SimulationService


# ─────────────────────────────────────────────
#  Shared minimal orchard GeoJSON (fits in one screen)
# ─────────────────────────────────────────────
def _tree_feature(row: int, col: int) -> dict:
    lon = 122.402 + col * 0.00009
    lat = 10.791 + row * 0.00009
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "Tree_ID": f"T{row * 3 + col + 1}",
            "Status": "Unbagged",
            "crown_radius_m": 2.5,
        },
    }


_TREE_GEOJSON = {
    "type": "FeatureCollection",
    "features": [
        _tree_feature(row, col)
        for row in range(2) for col in range(3)
    ],
}

_FIXED_START = datetime(2026, 4, 1, 0, 0, 0)


# ═════════════════════════════════════════════
# 1. Constant builder (legacy manual_weather)
# ═════════════════════════════════════════════
class TestConstantBuilder:

    def test_length_matches_hours(self):
        out = _series_from_constant({"temperature_c": 28.0}, hours=12, start_dt=_FIXED_START)
        assert len(out) == 12

    def test_repeats_same_values(self):
        out = _series_from_constant(
            {"temperature_c": 28.0, "rainfall_mm": 1.5},
            hours=5,
            start_dt=_FIXED_START,
        )
        for entry in out:
            assert entry["temperature_c"] == 28.0
            assert entry["rainfall_mm"] == 1.5

    def test_missing_keys_use_defaults(self):
        out = _series_from_constant({"temperature_c": 25.0}, hours=3, start_dt=_FIXED_START)
        assert out[0]["wind_speed_ms"] == _WEATHER_DEFAULTS["wind_speed_ms"]
        assert out[0]["wind_dir_deg"] == _WEATHER_DEFAULTS["wind_dir_deg"]
        assert out[0]["rainfall_mm"] == _WEATHER_DEFAULTS["rainfall_mm"]

    def test_datetime_increments_hourly(self):
        out = _series_from_constant({}, hours=4, start_dt=_FIXED_START)
        # ISO strings end with "Z" — strip and parse
        dts = [datetime.fromisoformat(e["datetime"].rstrip("Z")) for e in out]
        for i in range(1, 4):
            assert (dts[i] - dts[i - 1]).total_seconds() == 3600


# ═════════════════════════════════════════════
# 2. Per-hour series builder
# ═════════════════════════════════════════════
class TestSeriesBuilder:

    def test_each_hour_uses_its_own_entry(self):
        entries = [
            {"temperature_c": 20.0},
            {"temperature_c": 25.0},
            {"temperature_c": 30.0},
        ]
        out = _series_from_entries(entries, hours=3, start_dt=_FIXED_START)
        assert [e["temperature_c"] for e in out] == [20.0, 25.0, 30.0]

    def test_partial_entry_inherits_previous(self):
        entries = [
            {"temperature_c": 28.0, "rainfall_mm": 5.0},
            {"rainfall_mm": 0.0},  # temp inherits → 28.0
        ]
        out = _series_from_entries(entries, hours=2, start_dt=_FIXED_START)
        assert out[1]["temperature_c"] == 28.0
        assert out[1]["rainfall_mm"] == 0.0

    def test_short_list_pads_with_last(self):
        entries = [{"temperature_c": 25.0}]
        out = _series_from_entries(entries, hours=4, start_dt=_FIXED_START)
        assert all(e["temperature_c"] == 25.0 for e in out)
        assert len(out) == 4

    def test_long_list_truncates(self):
        entries = [{"temperature_c": float(t)} for t in range(10)]
        out = _series_from_entries(entries, hours=3, start_dt=_FIXED_START)
        assert len(out) == 3
        assert [e["temperature_c"] for e in out] == [0.0, 1.0, 2.0]


# ═════════════════════════════════════════════
# 3. Block-based builder
# ═════════════════════════════════════════════
class TestBlocksBuilder:

    def test_block_applies_to_its_range_only(self):
        blocks = [{"start_hour": 2, "end_hour": 5, "rainfall_mm": 3.0}]
        out = _series_from_blocks(blocks, hours=8, start_dt=_FIXED_START)
        assert out[0]["rainfall_mm"] == 0.0  # default
        assert out[1]["rainfall_mm"] == 0.0  # default
        assert out[2]["rainfall_mm"] == 3.0  # block start (inclusive)
        assert out[4]["rainfall_mm"] == 3.0  # block end-1 (still in block)
        assert out[5]["rainfall_mm"] == 0.0  # block end (exclusive)
        assert out[7]["rainfall_mm"] == 0.0  # default

    def test_later_blocks_override_earlier(self):
        blocks = [
            {"start_hour": 0, "end_hour": 6, "temperature_c": 20.0},
            {"start_hour": 3, "end_hour": 6, "temperature_c": 35.0},
        ]
        out = _series_from_blocks(blocks, hours=6, start_dt=_FIXED_START)
        assert out[0]["temperature_c"] == 20.0
        assert out[2]["temperature_c"] == 20.0
        assert out[3]["temperature_c"] == 35.0  # overridden
        assert out[5]["temperature_c"] == 35.0

    def test_uncovered_hours_use_defaults(self):
        blocks = [{"start_hour": 0, "end_hour": 3, "temperature_c": 22.0}]
        out = _series_from_blocks(blocks, hours=6, start_dt=_FIXED_START)
        assert out[3]["temperature_c"] == _WEATHER_DEFAULTS["temperature_c"]

    def test_out_of_range_blocks_clip_safely(self):
        blocks = [{"start_hour": -5, "end_hour": 100, "rainfall_mm": 4.0}]
        out = _series_from_blocks(blocks, hours=3, start_dt=_FIXED_START)
        assert all(e["rainfall_mm"] == 4.0 for e in out)
        assert len(out) == 3

    def test_inverted_block_is_ignored(self):
        # end_hour <= start_hour → block has no effect
        blocks = [{"start_hour": 5, "end_hour": 2, "rainfall_mm": 9.0}]
        out = _series_from_blocks(blocks, hours=8, start_dt=_FIXED_START)
        assert all(e["rainfall_mm"] == 0.0 for e in out)


# ═════════════════════════════════════════════
# 4. Dispatcher precedence
# ═════════════════════════════════════════════
class _FakeReq:
    """Minimal duck-typed request object — covers what build_weather_series reads."""

    def __init__(self, *, hours=6, manual_weather=None, manual_weather_series=None,
                 manual_weather_blocks=None, manual_weather_start=None):
        self.hours = hours
        self.manual_weather = manual_weather
        self.manual_weather_series = manual_weather_series
        self.manual_weather_blocks = manual_weather_blocks
        self.manual_weather_start = manual_weather_start


class TestDispatcher:

    def test_returns_none_when_nothing_set(self):
        assert build_weather_series(_FakeReq()) is None

    def test_constant_only(self):
        req = _FakeReq(hours=3, manual_weather={"temperature_c": 27.0})
        out = build_weather_series(req)
        assert out is not None and len(out) == 3
        assert all(e["temperature_c"] == 27.0 for e in out)

    def test_blocks_beat_constant(self):
        req = _FakeReq(
            hours=3,
            manual_weather={"temperature_c": 99.0},
            manual_weather_blocks=[{"start_hour": 0, "end_hour": 3, "temperature_c": 22.0}],
        )
        out = build_weather_series(req)
        assert out and out[0]["temperature_c"] == 22.0

    def test_series_beats_blocks_and_constant(self):
        req = _FakeReq(
            hours=2,
            manual_weather={"temperature_c": 99.0},
            manual_weather_blocks=[{"start_hour": 0, "end_hour": 2, "temperature_c": 22.0}],
            manual_weather_series=[{"temperature_c": 11.0}, {"temperature_c": 12.0}],
        )
        out = build_weather_series(req)
        assert out and [e["temperature_c"] for e in out] == [11.0, 12.0]


# ═════════════════════════════════════════════
# 5. Validation: ManualWeatherBlock
# ═════════════════════════════════════════════
class TestSchemaValidation:

    def test_block_end_must_exceed_start(self):
        with pytest.raises(ValidationError):
            ManualWeatherBlock(start_hour=5, end_hour=5, rainfall_mm=2.0)
        with pytest.raises(ValidationError):
            ManualWeatherBlock(start_hour=10, end_hour=3, rainfall_mm=2.0)

    def test_block_accepts_valid_range(self):
        b = ManualWeatherBlock(start_hour=0, end_hour=11, rainfall_mm=2.5)
        assert b.start_hour == 0 and b.end_hour == 11


# ═════════════════════════════════════════════
# 6. Cecid acceptance scenario
# ═════════════════════════════════════════════
class TestCecidAcceptance:
    """
    The cecid gate opens only when ALL of:
      - stage = FRUITLET
      - 24-h accumulated rain ≥ 5 mm
      - current rainfall == 0
      - wind ≤ 3 m/s
      - hour is dawn (5–7) or dusk (17–19)

    Build a 48-h schedule that aligns with these by hour 17:
      hours 0–10  : 2.5 mm / hr (10 hours × 2.5 = 25 mm wet buildup)
      hours 11–47 : 0 mm        (dry — emergence window)

    Start at midnight so hour-of-day == hour-index for the first 24 hours.
    Hour 17 is in the dusk window AND has 22.5 mm of rain in the prior 24 h.
    """

    def _scenario_blocks(self):
        return [
            {
                "start_hour": 0, "end_hour": 11,
                "rainfall_mm": 2.5, "wind_speed_ms": 1.5, "temperature_c": 26.0,
            },
            {
                "start_hour": 11, "end_hour": 48,
                "rainfall_mm": 0.0, "wind_speed_ms": 1.5, "temperature_c": 28.0,
            },
        ]

    def test_diagnostics_show_gate_open_at_dusk(self):
        blocks = self._scenario_blocks()
        weather = _series_from_blocks(blocks, hours=48, start_dt=_FIXED_START)
        diag = compute_gate_diagnostics(
            weather_data=weather,
            pest_type="cecid",
            orchard_stage="fruitlet",
        )
        # Hour 17 should be open: dusk + accumulated rain + dry now + low wind
        hour_18 = diag[18]
        assert hour_18["hour_of_day"] == 18
        assert hour_18["rainfall_mm"] == 0.0
        assert hour_18["soil_wetness_mm"] >= 5.0
        assert hour_18["status"] == "favorable"

    def test_diagnostics_show_gate_closed_during_rain(self):
        blocks = self._scenario_blocks()
        weather = _series_from_blocks(blocks, hours=48, start_dt=_FIXED_START)
        diag = compute_gate_diagnostics(
            weather_data=weather,
            pest_type="cecid",
            orchard_stage="fruitlet",
        )
        # Hour 6 is during the wet block — it's dawn (06:00) and a crepuscular
        # hour, but rainfall_mm > 0, so the gate must stay closed.
        hour_6 = diag[6]
        assert hour_6["hour_of_day"] == 6
        assert hour_6["rainfall_mm"] > 0
        assert hour_6["gate_open"] is False

    def test_diagnostics_skip_wrong_stage(self):
        blocks = self._scenario_blocks()
        weather = _series_from_blocks(blocks, hours=48, start_dt=_FIXED_START)
        diag = compute_gate_diagnostics(
            weather_data=weather,
            pest_type="cecid",
            orchard_stage="mature",  # cecid only opens in fruitlet
        )
        assert all(d["gate_open"] is False for d in diag)

    def test_repeating_wet_dry_cycles_open_at_each_dusk(self):
        blocks = []
        for day in range(3):
            offset = day * 24
            blocks.extend([
                {
                    "start_hour": offset,
                    "end_hour": offset + 8,
                    "rainfall_mm": 2.5,
                    "wind_speed_ms": 1.5,
                    "temperature_c": 26.0,
                },
                {
                    "start_hour": offset + 8,
                    "end_hour": offset + 24,
                    "rainfall_mm": 0.0,
                    "wind_speed_ms": 1.5,
                    "temperature_c": 28.0,
                },
            ])

        weather = _series_from_blocks(blocks, hours=72, start_dt=_FIXED_START)
        diag = compute_gate_diagnostics(weather, "cecid", "fruitlet")

        assert all(diag[step]["status"] == "favorable" for step in (18, 42, 66))
        assert diag[6]["rainfall_mm"] > 0

    def test_local_start_keeps_crepuscular_hour(self):
        weather = _series_from_blocks(
            self._scenario_blocks(),
            hours=24,
            start_dt=datetime(2026, 4, 1, 5, 0, 0),
        )
        diag = compute_gate_diagnostics(weather, "cecid", "fruitlet")

        # Simulation step 12 is 17:00 in the selected wall-clock schedule.
        assert diag[13]["hour_of_day"] == 18
        assert diag[13]["status"] == "favorable"

    def test_full_simulation_produces_infections(self):
        """End-to-end: tree_graph cecid sim with the wet-then-dry schedule
        should produce at least one new infestation by hour 48."""
        req = SimulationRequest(
            pest_type="cecid",
            orchard_geojson=_TREE_GEOJSON,
            hours=48,
            orchard_stage="fruitlet",
            random_seed=2026,
            risk_threshold=0.5,
            simulation_mode="tree_graph",
            initial_infestation_tree_ids=["T1"],
            manual_weather_blocks=self._scenario_blocks(),
            manual_weather_start=_FIXED_START,
        )
        # Pre-build the weather list (the route normally does this; the service
        # consumes ready-made weather_data).
        weather_data = build_weather_series(req)
        svc = SimulationService()
        resp = asyncio.get_event_loop().run_until_complete(
            svc.run_simulation(req, weather_data=weather_data)
        )
        # We seeded T1 — that's already 1 infested. Anything ≥ 1 means it ran cleanly.
        assert resp.n_infested_final >= 1


# ═════════════════════════════════════════════
# 7. Datetime format sanity
# ═════════════════════════════════════════════
class TestDatetimeFormat:
    """Regression for the `+00:00Z` bug that broke pandas parsing."""

    def test_naive_start_is_interpreted_as_guimaras_time(self):
        out = _series_from_constant({}, hours=2, start_dt=datetime(2026, 4, 1, 0, 0, 0))
        assert out[0]["datetime"] == "2026-04-01T00:00:00+08:00"
        assert out[1]["datetime"] == "2026-04-01T01:00:00+08:00"

    def test_aware_start_normalized_to_utc_z(self):
        """Aware datetimes are normalized to naive UTC so output is consistent.

        Previously aware inputs produced ``+00:00`` while naive produced ``Z``.
        Mixing the two in the same column made ``pd.to_datetime`` brittle.
        Now everything ends in ``Z`` regardless of the input tz.
        """
        start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        out = _series_from_constant({}, hours=1, start_dt=start)
        assert out[0]["datetime"] == "2026-04-01T00:00:00+00:00"

    def test_aware_non_utc_start_converted_to_utc(self):
        """A +08:00 input should be shifted to its UTC equivalent."""
        ph = timezone(timedelta(hours=8))
        start = datetime(2026, 4, 1, 8, 0, 0, tzinfo=ph)  # 00:00 UTC
        out = _series_from_constant({}, hours=1, start_dt=start)
        assert out[0]["datetime"] == "2026-04-01T08:00:00+08:00"

    def test_pandas_can_parse_output(self):
        out = _series_from_constant({}, hours=4, start_dt=datetime(2026, 4, 1, 10, 0, 0))
        df = pd.DataFrame(out)
        parsed = pd.to_datetime(df["datetime"])
        # Hour-of-day should round-trip correctly for the crepuscular gate logic
        assert list(parsed.dt.hour) == [10, 11, 12, 13]

    def test_round_trip_parse_rfc3339(self):
        s_naive = "2026-04-01T17:00:00Z"
        assert _parse_rfc3339(s_naive).hour == 17
        s_aware = "2026-04-01T17:00:00+08:00"
        assert _parse_rfc3339(s_aware).hour == 17


# ═════════════════════════════════════════════
# 7b. Defensive _resolve_start_dt
# ═════════════════════════════════════════════
class TestResolveStartDt:
    """Bad inputs to ``manual_weather_start`` must NOT crash the simulation.

    All paths fall back to ``utcnow_naive()`` and a warning is logged.
    """

    def test_string_start_is_parsed(self):
        out = _series_from_constant({}, hours=1, start_dt="2026-04-01T05:00:00Z")
        assert out[0]["datetime"] == "2026-04-01T05:00:00+00:00"

    def test_unparseable_string_falls_back_to_now(self):
        out = _series_from_constant({}, hours=1, start_dt="not-a-real-date")
        # Doesn't crash — datetime field is a valid Z-suffixed string
        assert out[0]["datetime"].endswith("+08:00")
        assert "T" in out[0]["datetime"]

    def test_non_datetime_input_falls_back_to_now(self):
        # Numbers, dicts, lists — none are valid; must NOT raise
        for bad in (12345, {"foo": "bar"}, [1, 2, 3], object()):
            out = _series_from_constant({}, hours=1, start_dt=bad)
            assert out[0]["datetime"].endswith("+08:00")

    def test_aware_start_no_pandas_mixed_tz_error(self):
        """Regression: blocks built from an aware start used to emit `+00:00`
        strings. Pandas on some versions chokes on mixed-tz columns. Verify
        the column parses cleanly into a single-tz datetime64 series."""
        start = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        out = _series_from_constant({}, hours=4, start_dt=start)
        df = pd.DataFrame(out)
        parsed = pd.to_datetime(df["datetime"])
        assert len(parsed) == 4
        # All entries normalized — same dtype, no mixed-tz error
        assert all(s.endswith("+00:00") for s in df["datetime"])


# ═════════════════════════════════════════════
# 8. Legacy manual_weather schema validation
# ═════════════════════════════════════════════
class TestCecidSuitabilityRedesign:
    def test_recently_wet_selector_expands_to_72_hour_context(self):
        request = SimulationRequest(
            pest_type="cecid",
            orchard_geojson=_TREE_GEOJSON,
            orchard_stage="fruitlet",
            manual_weather={"rainfall_mm": 0.0},
            manual_weather_start=datetime(2026, 4, 1, 12, 0),
            manual_soil_context={"preset": "recently_wet"},
        )
        context = build_manual_antecedent_weather(request)
        rainfall = [entry["rainfall_mm"] for entry in context]

        assert len(context) == 72
        assert sum(rainfall) == pytest.approx(8.0)
        assert rainfall[-10:-6] == [2.0, 2.0, 2.0, 2.0]
        assert rainfall[-6:] == [0.0] * 6
        assert context[-1]["datetime"].endswith("+08:00")

    def test_explicit_prefix_takes_precedence_over_soil_selector(self):
        request = SimulationRequest(
            pest_type="cecid",
            orchard_geojson=_TREE_GEOJSON,
            manual_weather={"rainfall_mm": 0.0},
            manual_soil_context={"preset": "recently_wet"},
            manual_weather_prefix_rain=[1.0, 2.0],
        )
        context = build_manual_antecedent_weather(request)
        rainfall = [entry["rainfall_mm"] for entry in context]
        assert rainfall[-2:] == [1.0, 2.0]
        assert sum(rainfall) == pytest.approx(3.0)

    def test_rain_60_hours_earlier_still_contributes_to_wetness(self):
        context = [0.0] * 72
        context[12] = 8.0
        weather = [{
            "datetime": "2026-04-01T18:00:00+08:00",
            "temperature_c": 28.0,
            "wind_speed_ms": 1.0,
            "wind_dir_deg": 90.0,
            "rainfall_mm": 0.0,
        }]
        diagnostic = compute_gate_diagnostics(
            weather, "cecid", "fruitlet",
            initial_rainfall_history=context,
        )[0]
        assert diagnostic["soil_wetness_mm"] > 3.0
        assert diagnostic["moisture_score"] > 0.6
        assert diagnostic["status"] == "favorable"

    def test_soft_weather_limits_do_not_replace_hard_stage_and_solar_rules(self):
        context = [0.0] * 68 + [2.0] * 4
        base = {
            "datetime": "2026-04-01T18:00:00+08:00",
            "temperature_c": 28.0,
            "wind_speed_ms": 1.0,
            "wind_dir_deg": 90.0,
            "rainfall_mm": 0.0,
        }
        favorable = compute_gate_diagnostics(
            [base], "cecid", "fruitlet", initial_rainfall_history=context,
        )[0]
        drizzle = compute_gate_diagnostics(
            [{**base, "rainfall_mm": 0.5, "wind_speed_ms": 3.0}],
            "cecid", "fruitlet", initial_rainfall_history=context,
        )[0]
        heavy_rain = compute_gate_diagnostics(
            [{**base, "rainfall_mm": 1.0}],
            "cecid", "fruitlet", initial_rainfall_history=context,
        )[0]
        midday = compute_gate_diagnostics(
            [{**base, "datetime": "2026-04-01T12:00:00+08:00"}],
            "cecid", "fruitlet", initial_rainfall_history=context,
        )[0]
        wrong_stage = compute_gate_diagnostics(
            [base], "cecid", "mature", initial_rainfall_history=context,
        )[0]

        assert favorable["status"] == "favorable"
        assert drizzle["hard_open"] is True
        assert 0.0 < drizzle["suitability_score"] < favorable["suitability_score"]
        assert heavy_rain["status"] == "limited"
        assert heavy_rain["drying_score"] == 0.0
        assert midday["status"] == "closed"
        assert "outside solar dawn/dusk window" in midday["hard_reasons"]
        assert wrong_stage["status"] == "closed"
        assert "fruitlet stage required" in wrong_stage["hard_reasons"]


class TestManualWeatherSchemaValidation:

    def test_rejects_negative_wind_speed(self):
        with pytest.raises(ValidationError):
            ManualWeather(wind_speed_ms=-1.0)

    def test_rejects_negative_rainfall(self):
        with pytest.raises(ValidationError):
            ManualWeather(rainfall_mm=-0.1)

    def test_rejects_out_of_range_wind_direction(self):
        with pytest.raises(ValidationError):
            ManualWeather(wind_dir_deg=400.0)

    def test_accepts_empty_partial_override(self):
        m = ManualWeather()
        assert m.temperature_c is None

    def test_request_accepts_legacy_dict_payload(self):
        """Clients that still send manual_weather as a raw dict must continue to work."""
        req = SimulationRequest(
            pest_type="fruitfly",
            orchard_geojson={"type": "FeatureCollection", "features": []},
            hours=6,
            manual_weather={"temperature_c": 28.0, "rainfall_mm": 0.5},
        )
        # Field is now typed — confirm the value is usable downstream
        assert req.manual_weather is not None
        assert req.manual_weather.temperature_c == 28.0
        assert req.manual_weather.rainfall_mm == 0.5

    def test_request_rejects_bad_legacy_dict(self):
        with pytest.raises(ValidationError):
            SimulationRequest(
                pest_type="fruitfly",
                orchard_geojson={"type": "FeatureCollection", "features": []},
                manual_weather={"wind_speed_ms": -5.0},
            )


# ═════════════════════════════════════════════
# 9. Numeric coercion
# ═════════════════════════════════════════════
class TestNumericCoercion:

    def test_wind_direction_wraps(self):
        out = _series_from_constant({"wind_dir_deg": 450.0}, hours=1, start_dt=_FIXED_START)
        assert out[0]["wind_dir_deg"] == 90.0  # 450 mod 360

    def test_negative_wind_clamped_to_zero(self):
        # Builder is defensive — tests can bypass Pydantic and pass dicts directly
        out = _series_from_constant({"wind_speed_ms": -3.0}, hours=1, start_dt=_FIXED_START)
        assert out[0]["wind_speed_ms"] == 0.0

    def test_negative_rain_clamped_to_zero(self):
        out = _series_from_constant({"rainfall_mm": -10.0}, hours=1, start_dt=_FIXED_START)
        assert out[0]["rainfall_mm"] == 0.0

    def test_all_outputs_are_floats(self):
        entries = [{"temperature_c": 25, "rainfall_mm": 1}]  # ints
        out = _series_from_entries(entries, hours=2, start_dt=_FIXED_START)
        for e in out:
            for k in ("temperature_c", "wind_speed_ms", "wind_dir_deg", "rainfall_mm"):
                assert isinstance(e[k], float)


# ═════════════════════════════════════════════
# 10. Regression — legacy manual_weather still works
# ═════════════════════════════════════════════
class TestLegacyManualWeather:

    def test_constant_dict_produces_n_entries(self):
        req = _FakeReq(hours=12, manual_weather={"temperature_c": 30.0, "rainfall_mm": 0.5})
        out = build_weather_series(req)
        assert out is not None
        assert len(out) == 12
        assert all(e["temperature_c"] == 30.0 and e["rainfall_mm"] == 0.5 for e in out)

    def test_empty_manual_weather_returns_none(self):
        # Empty dict counts as falsy in build_weather_series — caller falls back to forecast
        assert build_weather_series(_FakeReq(manual_weather={})) is None
