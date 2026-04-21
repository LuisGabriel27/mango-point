"""
MangoPoint API — Main Application
===================================
FastAPI-based REST backend for pest risk simulation.

Endpoints:
    POST /run-simulation      - Run pest dispersal simulation
    GET  /weather/live        - Get real-time weather data
    POST /submit-observation  - Submit ground truth data
    GET  /evaluate            - Compare predictions vs observations
    GET  /alerts              - Get risk alerts
"""

import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager

import asyncpg
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.core.config import settings
from api.core.database import (
    DATABASE_UNAVAILABLE_DETAIL,
    async_session_maker,
    close_db,
    init_db,
    is_database_unavailable,
)
from api.core.security import AuthConfigurationError, get_current_active_user
from api.routes import auth, alerts, evaluation, monitoring, observations, simulation, validation, weather
from api.services.auth_service import auth_service

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting MangoPoint API...")
    try:
        import db.models  # noqa: F401  — register all ORM models with Base
        import db.models  # noqa: F401  — register all ORM models with Base
        await init_db()
        logger.info("Database initialized")
        try:
            async with async_session_maker() as session:
                admin_status, admin_user = await auth_service.ensure_default_admin(session)
                await session.commit()
            if admin_user is not None and admin_status in {"created", "updated"}:
                logger.info("Default admin account %s for '%s'", admin_status, admin_user.username)
        except AuthConfigurationError as exc:
            logger.warning("Default admin provisioning skipped: %s", exc)
        except Exception as exc:
            logger.warning("Default admin provisioning failed: %s", exc)
    except Exception as e:
        logger.warning(f"Database initialization skipped (may not be configured): {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down MangoPoint API...")
    try:
        await close_db()
    except Exception as e:
        logger.warning(f"Database close error: {e}")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## MangoPoint Pest Risk Simulation API

A GIS-based spatiotemporal simulation system for predicting the spread of 
Cecid Fly (Mango Gall Midge) and Fruit Fly (Bactrocera spp.) in mango orchards.

### Features

- **Cellular Automata Simulation**: Model pest dispersal based on biological rules
- **Real-time Weather**: Integration with OpenWeatherMap API
- **Alert System**: Automatic alerts when risk exceeds thresholds
- **Model Evaluation**: Compare predictions against ground truth observations

### Pest Types

- `cecid`: Mango Gall Midge - crepuscular, wind-sensitive
- `fruitfly`: Bactrocera spp. - warm daytime, wind-direction biased
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler
@app.exception_handler(SQLAlchemyError)
@app.exception_handler(asyncpg.PostgresError)
async def database_exception_handler(request: Request, exc: Exception):
    logger.error(f"Database error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=503,
        content={"detail": DATABASE_UNAVAILABLE_DETAIL},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if is_database_unavailable(exc):
        logger.error(f"Database unavailable on {request.method} {request.url.path}: {exc}")
        return JSONResponse(
            status_code=503,
            content={"detail": DATABASE_UNAVAILABLE_DETAIL},
        )

    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# Include routers
app.include_router(auth.router)

# Public routes remain limited to auth, health, root, and the generated docs.
protected_router_dependencies = [Depends(get_current_active_user)]
app.include_router(simulation.router, dependencies=protected_router_dependencies)
app.include_router(weather.router, dependencies=protected_router_dependencies)
app.include_router(observations.router, dependencies=protected_router_dependencies)
app.include_router(evaluation.router, dependencies=protected_router_dependencies)
app.include_router(alerts.router, dependencies=protected_router_dependencies)
app.include_router(validation.router, dependencies=protected_router_dependencies)
app.include_router(monitoring.router, dependencies=protected_router_dependencies)


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Check API health status."""
    from api.models.schemas import HealthResponse
    
    # Check database
    db_status = "unknown"
    try:
        from api.core.database import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)[:50]}"
    
    # Check weather API (Open-Meteo, no key required)
    weather_status = "configured (Open-Meteo)"
    
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        database=db_status,
        weather_api=weather_status,
    )


@app.get("/", tags=["System"])
async def root():
    """API root - redirects to documentation."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "auth": "/auth/login",
            "simulation": "/simulation/run-simulation",
            "weather": "/weather/live",
            "observations": "/observations/submit-observation",
            "evaluation": "/evaluation/evaluate",
            "alerts": "/alerts",
            "monitoring": "/monitoring/metrics",
            "validation": "/validation/run",
        },
    }


# For running directly with uvicorn
if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info",
    )
