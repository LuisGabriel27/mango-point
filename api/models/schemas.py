"""
MangoPoint API — Pydantic Schemas
===================================
Request and response schemas for the API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


# ═══════════════════════════════════════════════
#  Enums
# ═══════════════════════════════════════════════
class PestTypeEnum(str, Enum):
    """Pest type enumeration."""
    CECID = "cecid"
    FRUITFLY = "fruitfly"


class OrchardStageEnum(str, Enum):
    """
    Phenological growth stages of mango orchard.
    
    Based on 2022-2025 historical data analysis:
    - Cecid Fly (Gall Midge): Only active during FRUITLET stage
    - Fruit Fly (Bactrocera): Only active during MATURE stage
    """
    DORMANT = "dormant"      # Vegetative rest period, no flowering or fruit
    FLOWERING = "flowering"  # Active flowering, no fruit yet
    FRUITLET = "fruitlet"    # Post-flowering, young fruitlets forming (Cecid Fly vulnerable)
    MATURE = "mature"        # Fruit maturing/ripening (Fruit Fly attractive)


class AlertSeverityEnum(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatusEnum(str, Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


# ═══════════════════════════════════════════════
#  GeoJSON Schemas
# ═══════════════════════════════════════════════
class GeoJSONFeature(BaseModel):
    """GeoJSON Feature schema."""
    type: str = "Feature"
    geometry: Dict[str, Any]
    properties: Dict[str, Any] = {}
    id: Optional[str] = None


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection schema."""
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]


# ═══════════════════════════════════════════════
#  Simulation Schemas
# ═══════════════════════════════════════════════
class SimulationRequest(BaseModel):
    """Request schema for POST /run-simulation."""
    pest_type: PestTypeEnum = Field(..., description="Type of pest to simulate")
    orchard_geojson: Dict[str, Any] = Field(..., description="GeoJSON FeatureCollection of tree points or orchard boundary polygon")
    bagged_tree_ids: List[str] = Field(default=[], description="List of tree IDs that are bagged")
    hours: int = Field(default=48, ge=1, le=168, description="Simulation duration in hours")
    initial_infestation: List[Dict[str, int]] = Field(
        default=[],
        description="Initial infestation points as list of {'row': int, 'col': int}"
    )
    random_seed: Optional[int] = Field(
        default=None,
        description="Random seed for reproducibility. If not provided, a random seed is generated."
    )
    risk_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Risk threshold for alert generation (default: 0.7)"
    )
    orchard_stage: OrchardStageEnum = Field(
        default=OrchardStageEnum.MATURE,
        description="Current phenological stage of the orchard. Controls which pest gates can activate: "
                    "DORMANT/FLOWERING=no activity, FRUITLET=Cecid Fly, MATURE=Fruit Fly"
    )
    days_since_flowering: Optional[int] = Field(
        default=60,
        ge=0,
        le=180,
        description="Days since flowering ended. Used to compute fruit sugar index for Fruit Fly attraction. "
                    "Higher values = riper fruit = stronger attraction (default: 60)"
    )
    neighbor_threat: Optional[float] = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="External pest pressure from neighboring unmanaged orchards (0-1). "
                    "Historical data shows unmanaged orchards have ~2x higher CPTD values."
    )
    tree_overrides: Optional[Dict[str, str]] = Field(
        default=None,
        description="Dict mapping tree_id (str) -> status (str) for manual status overrides. "
                    "Valid statuses: healthy, infected, bagged, dead, history_infected, suspect. "
                    "Trees marked as 'dead' or 'bagged' are immune to pest spread."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "pest_type": "fruitfly",
                "orchard_geojson": {
                    "type": "FeatureCollection",
                    "features": [{
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [122.4025, 10.7913]
                        },
                        "properties": {"Tree_ID": 1, "Status": "Unbagged"}
                    },
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [122.4027, 10.7915]
                        },
                        "properties": {"Tree_ID": 2, "Status": "Unbagged"}
                    }]
                },
                "bagged_tree_ids": ["1", "2"],
                "hours": 48,
                "orchard_stage": "mature",
                "days_since_flowering": 60,
                "neighbor_threat": 0.3
            }
        }


class TimeSeriesSnapshot(BaseModel):
    """Single timestep snapshot in simulation output."""
    timestep: int
    datetime: str
    hour: int
    risk_geojson: Dict[str, Any]
    n_infested: int
    n_new: int
    weather: Dict[str, float]


class TimestepEntry(BaseModel):
    """Entry for timesteps array in time-series output."""
    hour: int
    geojson: Dict[str, Any]


class SimulationMetadata(BaseModel):
    """Metadata for simulation run."""
    run_id: str
    pest_type: str
    hours: int
    random_seed: int
    started_at: str
    completed_at: Optional[str]
    duration_seconds: Optional[float]
    peak_risk: float
    cells_at_risk: int
    n_infested_final: int
    risk_threshold: float
    orchard_stage: str
    days_since_flowering: int
    sugar_index: float
    neighbor_threat: float


class SimulationResponse(BaseModel):
    """Response schema for POST /run-simulation."""
    run_id: str
    pest_type: PestTypeEnum
    hours: int
    started_at: str
    completed_at: Optional[str]
    status: str
    
    # Summary statistics
    peak_risk: float
    cells_at_risk: int
    n_infested_final: int
    
    # Reproducibility
    random_seed: int
    risk_threshold: float
    
    # Metadata block for research output
    metadata: SimulationMetadata
    
    # Time-series output (detailed)
    time_series: List[TimeSeriesSnapshot]
    
    # Timesteps array (research format)
    timesteps: List[TimestepEntry]
    
    # Final risk heatmap as GeoJSON
    risk_geojson: Dict[str, Any]


# ═══════════════════════════════════════════════
#  Weather Schemas
# ═══════════════════════════════════════════════
class WeatherData(BaseModel):
    """Current weather data."""
    wind_speed_ms: float = Field(..., description="Wind speed in m/s")
    wind_direction_deg: float = Field(..., description="Wind direction in degrees (0=N, 90=E)")
    temperature_c: float = Field(..., description="Temperature in Celsius")
    humidity: Optional[float] = Field(None, description="Relative humidity percentage")
    datetime: str = Field(..., description="Observation timestamp")
    source: str = Field(default="openweathermap", description="Data source")


class WeatherResponse(BaseModel):
    """Response schema for GET /weather/live."""
    current: WeatherData
    location: Dict[str, float]
    cached: bool = Field(default=False, description="Whether data is from cache")
    cache_expires_at: Optional[str] = None


# ═══════════════════════════════════════════════
#  Observation Schemas
# ═══════════════════════════════════════════════
class ObservationSubmission(BaseModel):
    """Request schema for POST /submit-observation."""
    tree_id: str = Field(..., description="ID of the tree where pest was observed")
    observed_pest: PestTypeEnum = Field(..., description="Type of pest observed")
    timestamp: datetime = Field(..., description="Observation timestamp")
    severity: float = Field(..., ge=0.0, le=1.0, description="Severity level (0-1)")
    observer_id: Optional[str] = Field(None, description="Observer identifier")
    notes: Optional[str] = Field(None, description="Additional notes")
    image_url: Optional[str] = Field(None, description="URL to observation image")
    lon: Optional[float] = Field(None, description="Longitude of observation")
    lat: Optional[float] = Field(None, description="Latitude of observation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "tree_id": "tree_042",
                "observed_pest": "cecid",
                "timestamp": "2026-02-15T10:30:00Z",
                "severity": 0.7,
                "notes": "Moderate gall midge infestation on young leaves"
            }
        }


class ObservationResponse(BaseModel):
    """Response schema for observation submission."""
    id: int
    tree_id: str
    observed_pest: PestTypeEnum
    timestamp: str
    severity: float
    created_at: str


# ═══════════════════════════════════════════════
#  Evaluation Schemas
# ═══════════════════════════════════════════════
class EvaluationRequest(BaseModel):
    """Request schema for evaluation endpoint."""
    simulation_run_id: Optional[str] = Field(None, description="Specific simulation run to evaluate")
    time_window_start: Optional[datetime] = Field(None, description="Start of evaluation window")
    time_window_end: Optional[datetime] = Field(None, description="End of evaluation window")
    risk_threshold: float = Field(default=0.5, description="Threshold for binary risk classification")


class ConfusionMatrix(BaseModel):
    """Confusion matrix for evaluation."""
    true_positives: int
    true_negatives: int
    false_positives: int
    false_negatives: int


class EvaluationResponse(BaseModel):
    """Response schema for GET /evaluate."""
    simulation_run_id: Optional[str]
    evaluation_timestamp: str
    
    # Metrics
    precision: float
    recall: float
    f1_score: float
    accuracy: float
    spatial_overlap_percentage: float
    
    # Confusion matrix
    confusion_matrix: ConfusionMatrix
    
    # Details
    total_predictions: int
    total_observations: int
    matched_cells: int


# ═══════════════════════════════════════════════
#  Alert Schemas
# ═══════════════════════════════════════════════
class AlertCreate(BaseModel):
    """Internal schema for creating alerts."""
    alert_id: str
    simulation_run_id: Optional[str]
    severity: AlertSeverityEnum
    risk_value: float
    affected_cells: List[Dict[str, int]]
    affected_tree_ids: List[str]
    orchard_id: Optional[str]
    zone_name: Optional[str]
    message: str
    centroid_lon: Optional[float]
    centroid_lat: Optional[float]


class AlertResponse(BaseModel):
    """Response schema for alert data."""
    alert_id: str
    triggered_at: str
    severity: AlertSeverityEnum
    status: AlertStatusEnum
    risk_value: float
    affected_cells: List[Dict[str, int]]
    affected_tree_ids: List[str]
    orchard_id: Optional[str]
    zone_name: Optional[str]
    message: str
    email_sent: bool
    sms_sent: bool
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    resolved_at: Optional[str]


class AlertListResponse(BaseModel):
    """Response schema for GET /alerts."""
    total: int
    active_count: int
    alerts: List[AlertResponse]


class AlertAcknowledge(BaseModel):
    """Request schema for acknowledging an alert."""
    acknowledged_by: str
    notes: Optional[str] = None


# ═══════════════════════════════════════════════
#  Health Check
# ═══════════════════════════════════════════════
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str
    weather_api: str
