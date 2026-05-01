# MangoPoint Data

This folder contains orchard/map assets, BPI Guimaras pest monitoring records, and the historical hourly weather archive used by validation tools.

## Files

| File | Purpose |
|---|---|
| `guimaras_pest_data_2022_2025.csv` | Monthly BPI Guimaras pest monitoring records used for historical validation |
| `hourly_weather.csv` | Normalized Open-Meteo historical hourly weather archive for 2022-2025 |
| `open_meteo_hourly_raw.csv` | Raw Open-Meteo CSV response retained for source traceability |
| `trees.geojson` | Tree point/crown data for tree-graph simulation |
| `Dummy_Mango_Data.geojson` | Sample orchard GeoJSON used by demo paths |
| `bpi_map.tif`, `bpi_dsm.tif`, `bpi_dtm.tif` | Local raster inputs used for GIS display and orchard location, when present |

Large raster files are ignored by git and may need to be provided separately on another machine.

## Historical Weather

`hourly_weather.csv` must contain these validator columns:

- `datetime`
- `temperature_c`
- `humidity_pct`
- `rainfall_mm`
- `wind_speed_ms`
- `wind_dir_deg`

The bundled archive was created from the Open-Meteo historical weather archive for the orchard coordinates used by the project. It covers 2022-01-01 through 2025-12-31 hourly.

Run strict coverage validation with:

```bash
python -m scripts.run_validation --historical-weather-csv data\hourly_weather.csv --require-historical-weather --test-years 2025
```

If you replace this with a PAGASA or station-derived CSV, keep the normalized column names above. The validation loader accepts several common aliases, but the normalized names are the least ambiguous.

## Source Caveats

- BPI pest data is monthly aggregate monitoring data, not tree-level labels.
- Open-Meteo historical weather is model/reanalysis data, not official PAGASA station observations.
- For the strongest research claim, document the weather source used in each validation run and prefer station observations when available.
