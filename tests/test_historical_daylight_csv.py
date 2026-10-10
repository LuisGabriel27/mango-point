"""Historical light evidence must retain its interval and missing-value meaning."""

import pandas as pd
import pytest

from utils.weather import WeatherTimeSeries
from validation.weather_scenarios import HistoricalWeatherGenerator


@pytest.mark.parametrize("names", [
    ("shortwave_radiation_wm2", "direct_normal_irradiance_wm2"),
    ("shortwave_radiation_instant", "direct_normal_irradiance_instant"),
])
def test_historical_csv_preserves_instant_radiation_zero_and_unknown(tmp_path, names):
    path = tmp_path / "light.csv"
    pd.DataFrame({"datetime": ["2024-04-15T12:00", "2024-04-15T13:00"],
        "temperature_c": [28, 28], "wind_speed_ms": [1, 1], "wind_dir_deg": [90, 90],
        "cloud_cover_pct": [100, 100], names[0]: [0, -1], names[1]: [0, float("inf")],
        "daylight_condition": ["dim_overcast", "invalid"], "daylight_condition_basis": ["observed", "invalid"],
    }).to_csv(path, index=False)
    frame = HistoricalWeatherGenerator(historical_weather_path=path).generate(2024, 4, hours=2)
    weather = WeatherTimeSeries.from_dataframe(frame)
    assert weather.at(0)["shortwave_radiation_wm2"] == 0
    assert weather.at(0)["direct_normal_irradiance_wm2"] == 0
    assert weather.at(0)["daylight_condition_basis"] == "observed"
    assert weather.at(1)["shortwave_radiation_wm2"] is None
    assert weather.at(1)["direct_normal_irradiance_wm2"] is None
    assert weather.at(1)["daylight_condition"] is None


def test_historical_hour_average_columns_are_not_used_as_instant_readings(tmp_path):
    path = tmp_path / "average.csv"
    path.write_text("datetime,temperature_c,wind_speed_ms,wind_dir_deg,cloud_cover,shortwave_radiation,direct_normal_irradiance\n"
                    "2024-04-15T12:00,28,1,90,100,100,0\n", encoding="utf-8")
    frame = HistoricalWeatherGenerator(historical_weather_path=path).generate(2024, 4, hours=1)
    entry = WeatherTimeSeries.from_dataframe(frame).at(0)
    assert entry["cloud_cover_pct"] == 100
    assert entry["shortwave_radiation_wm2"] is None
    assert entry["direct_normal_irradiance_wm2"] is None


def test_normalized_columns_take_precedence_over_api_aliases(tmp_path):
    path = tmp_path / "aliases.csv"
    path.write_text("datetime,temperature_c,wind_speed_ms,wind_dir_deg,cloud_cover_pct,cloud_cover,shortwave_radiation_wm2,shortwave_radiation_instant\n"
                    "2024-04-15T12:00,28,1,90,65,100,100,900\n", encoding="utf-8")
    frame = HistoricalWeatherGenerator(historical_weather_path=path).generate(2024, 4, hours=1)
    entry = WeatherTimeSeries.from_dataframe(frame).at(0)
    assert entry["cloud_cover_pct"] == 65
    assert entry["shortwave_radiation_wm2"] == 100
