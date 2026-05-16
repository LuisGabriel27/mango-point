"""
MangoPoint API — Weather Routes
================================
GET /weather/live endpoint for real-time weather data.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..models.schemas import WeatherResponse, WeatherData
from ..services.weather_service import weather_service
from ..core.config import settings
from utils.datetime_utils import format_rfc3339

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weather", tags=["Weather"])


@router.get(
    "/live",
    response_model=WeatherResponse,
    summary="Get live weather data",
    description="""
    Fetch real-time weather data from Open-Meteo.
    
    **Returns:**
    - `wind_speed_ms`: Wind speed in meters/second
    - `wind_direction_deg`: Meteorological wind-from direction in degrees (0=N/from north, 90=E/from east)
    - `temperature_c`: Temperature in Celsius
    - `humidity`: Relative humidity percentage
    
    **Caching:**
    Results are cached for 10 minutes to reduce API calls.
    Falls back to synthetic weather if API is unavailable.
    """,
)
async def get_live_weather(
    lat: Optional[float] = Query(
        default=None,
        description="Latitude (default: Guimaras, Philippines)",
        ge=-90,
        le=90,
    ),
    lon: Optional[float] = Query(
        default=None,
        description="Longitude (default: Guimaras, Philippines)",
        ge=-180,
        le=180,
    ),
    bypass_cache: bool = Query(
        default=False,
        description="Bypass cache and fetch fresh data",
    ),
) -> WeatherResponse:
    """
    Get current weather data for the specified location.
    
    If no coordinates are provided, defaults to Guimaras, Philippines
    (the primary deployment location for MangoPoint).
    """
    # Use default location if not specified
    if lat is None:
        lat = settings.DEFAULT_LAT
    if lon is None:
        lon = settings.DEFAULT_LON
    
    try:
        weather = await weather_service.get_live_weather(
            lat=lat,
            lon=lon,
            use_cache=not bypass_cache,
        )
        
        return WeatherResponse(
            current=WeatherData(
                wind_speed_ms=weather["wind_speed_ms"],
                wind_direction_deg=weather["wind_dir_deg"],
                temperature_c=weather["temperature_c"],
                humidity=weather.get("humidity"),
                datetime=weather["datetime"],
                source=weather["source"],
            ),
            location={"lat": lat, "lon": lon},
            cached=weather.get("cached", False),
            cache_expires_at=format_rfc3339(weather["cache_expires_at"]) if weather.get("cache_expires_at") else None,
        )
        
    except Exception as e:
        logger.error(f"Failed to get weather: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Weather service temporarily unavailable: {str(e)}",
        )


@router.get(
    "/forecast",
    summary="Get weather forecast",
    description="Get hourly weather forecast for simulation planning.",
)
async def get_weather_forecast(
    lat: Optional[float] = Query(
        default=None,
        description="Latitude",
        ge=-90,
        le=90,
    ),
    lon: Optional[float] = Query(
        default=None,
        description="Longitude",
        ge=-180,
        le=180,
    ),
    hours: int = Query(
        default=48,
        description="Forecast hours (max 168)",
        ge=1,
        le=168,
    ),
):
    """
    Get hourly weather forecast.
    
    Used to plan simulations and preview expected conditions.
    """
    if lat is None:
        lat = settings.DEFAULT_LAT
    if lon is None:
        lon = settings.DEFAULT_LON
    
    try:
        forecast = await weather_service.get_forecast(
            lat=lat,
            lon=lon,
            hours=hours,
        )
        
        return {
            "location": {"lat": lat, "lon": lon},
            "hours": hours,
            "forecast": forecast,
        }
        
    except Exception as e:
        logger.error(f"Failed to get forecast: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Weather service temporarily unavailable: {str(e)}",
        )


@router.get(
    "/status",
    summary="Weather API status",
    description="Check if weather API is configured and operational.",
)
async def weather_status():
    """Check weather API configuration status."""
    status = {
        "provider": "open-meteo",
        "api_configured": True,
        "api_key_present": False,
        "cache_ttl_seconds": settings.WEATHER_CACHE_TTL_SECONDS,
        "default_location": {
            "lat": settings.DEFAULT_LAT,
            "lon": settings.DEFAULT_LON,
            "name": "Guimaras, Philippines",
        },
    }

    weather = await weather_service.get_live_weather(
        lat=settings.DEFAULT_LAT,
        lon=settings.DEFAULT_LON,
        use_cache=False,
    )
    status["last_response_source"] = weather.get("source", "unknown")
    if weather.get("source") == "open-meteo":
        status["api_status"] = "operational"
    else:
        status["api_status"] = "fallback_only"
        status["fallback"] = "synthetic_weather_enabled"
    
    return status
