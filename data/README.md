# MangoPoint Data

This folder contains the bundled BPI Guimaras pest monitoring sample data and orchard/map assets used by the demo and validation tools.

The repository does not currently include a complete hourly historical weather archive. To run validation with real historical weather, add a CSV file and pass it to:

```bash
python -m scripts.run_validation --historical-weather-csv data/hourly_weather.csv
```

Expected hourly weather columns are `datetime`, `temperature_c`, `wind_speed_ms`, `wind_dir_deg`, and optional `rainfall_mm`.
