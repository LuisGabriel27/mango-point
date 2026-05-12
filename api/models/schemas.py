"""
MangoPoint API — Pydantic Schemas
===================================
Request and response schemas for the API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum
from core.config import (
    TG_LAMBDA0,
    TG_ALPHA,
    TG_BETA,
    TG_WIND_BIAS,
    TG_MAX_NEIGHBOR_DIST_M,
    TG_DEFAULT_CROWN_RADIUS_M,
    CECID_RAINFALL_THRESHOLD_MM,
    CECID_BASE_DISPERSAL_PROB,
    FRUIT_FLY_TEMP_THRESHOLD_C,
    FRUIT_FLY_BASE_DISPERSAL_PROB,
)


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


class SimulationModeEnum(str, Enum):
    """
    Spatial spread model to use.

    grid       — 2-D cellular automata on a regular 5 m grid (baseline).
    tree_graph — Crown-aware, tree-to-tree hazard model using a spatial graph.
                 Uses per-tree crown radius/width fields when present, or the global fallback.
    """
    GRID       = "grid"
    TREE_GRAPH = "tree_graph"


class TreatmentTypeEnum(str, Enum):
    """Treatment scenario type for forecast what-if modelling."""
    PROTECTIVE_SPRAY = "protective_spray"
    TARGETED_SPRAY = "targeted_spray"
    SANITATION = "sanitation"
    COMBINED = "combined"


class TreatmentCoverageEnum(str, Enum):
    """Spatial coverage of a treatment application."""
    WHOLE_ORCHARD = "whole_orchard"
    TARGETED = "targeted"


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


class AlertActionStatusEnum(str, Enum):
    """Operational action workflow status for an alert."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DISMISSED = "dismissed"


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


class OrchardCreate(BaseModel):
    """Request schema for creating a managed orchard."""
    name: str = Field(..., min_length=1, max_length=200)
    orchard_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Stable public orchard identifier. If omitted, one is generated from the name.",
    )
    owner_name: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=500)
    area_size: Optional[float] = Field(default=None, ge=0.0)
    tree_count: Optional[int] = Field(default=None, ge=0)
    geojson: Optional[Dict[str, Any]] = Field(default=None)
    description: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    monitoring_enabled: bool = Field(default=True)
    orchard_stage: OrchardStageEnum = Field(default=OrchardStageEnum.MATURE)
    days_since_flowering: int = Field(default=60, ge=0, le=180)
    monitored_pest_types: List[PestTypeEnum] = Field(
        default_factory=lambda: [PestTypeEnum.CECID, PestTypeEnum.FRUITFLY]
    )

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class OrchardUpdate(BaseModel):
    """Request schema for updating a managed orchard."""
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    orchard_id: Optional[str] = Field(default=None, max_length=100)
    owner_name: Optional[str] = Field(default=None, max_length=200)
    location: Optional[str] = Field(default=None, max_length=500)
    area_size: Optional[float] = Field(default=None, ge=0.0)
    tree_count: Optional[int] = Field(default=None, ge=0)
    geojson: Optional[Dict[str, Any]] = Field(default=None)
    description: Optional[str] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)
    monitoring_enabled: Optional[bool] = Field(default=None)
    orchard_stage: Optional[OrchardStageEnum] = Field(default=None)
    days_since_flowering: Optional[int] = Field(default=None, ge=0, le=180)
    monitored_pest_types: Optional[List[PestTypeEnum]] = Field(default=None)

    @field_validator("name")
    @classmethod
    def optional_name_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class OrchardResponse(BaseModel):
    """Response schema for orchard metadata."""
    database_id: int
    orchard_id: str
    name: str
    owner_name: Optional[str] = None
    location: Optional[str] = None
    area_size: Optional[float] = None
    tree_count: int
    geojson: Optional[Dict[str, Any]] = None
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    orthophoto_url: Optional[str] = None
    orthophoto_bounds: Optional[List[float]] = None
    orthophoto_coordinates: Optional[List[List[float]]] = None
    has_dtm: bool = False
    has_dsm: bool = False
    description: Optional[str] = None
    is_active: bool
    monitoring_enabled: bool
    orchard_stage: OrchardStageEnum
    days_since_flowering: int
    monitored_pest_types: List[PestTypeEnum]
    last_monitoring_scan_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OrchardListResponse(BaseModel):
    """Response schema for listing orchards."""
    total: int
    orchards: List[OrchardResponse]


class TreatmentApplication(BaseModel):
    """A field treatment scenario applied at the start of a simulation."""
    treatment_type: TreatmentTypeEnum = Field(default=TreatmentTypeEnum.TARGETED_SPRAY)
    coverage: TreatmentCoverageEnum = Field(default=TreatmentCoverageEnum.TARGETED)
    target_tree_ids: List[str] = Field(default_factory=list)
    target_cells: List[Dict[str, int]] = Field(default_factory=list)
    efficacy: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Fractional reduction in treated-tree susceptibility.",
    )
    source_reduction: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional fractional reduction in treated infested-tree infectiousness.",
    )
    label: Optional[str] = Field(default=None, max_length=120)

    @field_validator("target_cells")
    @classmethod
    def target_cells_need_row_col(cls, value: List[Dict[str, int]]) -> List[Dict[str, int]]:
        for cell in value:
            if "row" not in cell or "col" not in cell:
                raise ValueError("Each target cell must include row and col")
        return value


# ═══════════════════════════════════════════════
#  Manual Weather Override Schemas
# ═══════════════════════════════════════════════
class ManualWeather(BaseModel):
    """
    Constant weather override (legacy ``manual_weather`` payload).

    Same four keys accepted before, but now rejects negative wind/rain and
    out-of-range wind direction. Clients that posted raw dicts continue to
    work — FastAPI coerces ``Dict[str, float]`` → ``ManualWeather`` via the
    union type on the request field.
    """
    temperature_c: Optional[float] = Field(default=None, description="Air temperature in °C.")
    wind_speed_ms: Optional[float] = Field(default=None, ge=0.0, description="Wind speed (m/s). Must be ≥ 0.")
    wind_dir_deg:  Optional[float] = Field(default=None, ge=0.0, le=360.0,
                                           description="Wind direction in degrees [0, 360]. "
                                                       "Values equal to 360 are normalized to 0 downstream.")
    rainfall_mm:   Optional[float] = Field(default=None, ge=0.0, description="Rainfall (mm/h). Must be ≥ 0.")


class ManualWeatherEntry(BaseModel):
    """A single hour of weather for manual_weather_series. All fields optional;
    missing keys inherit from the previous hour (defaults for hour 0)."""
    temperature_c: Optional[float] = Field(default=None, description="Air temperature in °C.")
    wind_speed_ms: Optional[float] = Field(default=None, ge=0.0, description="Wind speed in m/s.")
    wind_dir_deg:  Optional[float] = Field(default=None, ge=0.0, le=360.0, description="Wind direction (0=N, 90=E).")
    rainfall_mm:   Optional[float] = Field(default=None, ge=0.0, description="Rainfall in mm for this hour.")


class QuadrantStages(BaseModel):
    """Dominant phenological stage per 2×2 quadrant of the orchard bounding box.

    Quadrants are computed at request time from the orchard's lon/lat extents:
    ``nw`` = north-west, ``ne`` = north-east, ``sw`` = south-west, ``se`` = south-east.

    Within each quadrant, trees are assigned their quadrant's dominant stage with
    probability 0.7, an adjacent stage (±1 in the phenological cycle) with
    probability 0.2, and the opposite stage with probability 0.1. This yields a
    realistic mixed-stage distribution while preserving spatial identifiability
    ("the NW block is a flowering zone").
    """
    nw: OrchardStageEnum = Field(..., description="Dominant stage for the NW quadrant.")
    ne: OrchardStageEnum = Field(..., description="Dominant stage for the NE quadrant.")
    sw: OrchardStageEnum = Field(..., description="Dominant stage for the SW quadrant.")
    se: OrchardStageEnum = Field(..., description="Dominant stage for the SE quadrant.")


class ManualWeatherBlock(BaseModel):
    """
    A contiguous block of hours sharing the same weather profile.

    ``start_hour`` is inclusive, ``end_hour`` is exclusive. Blocks may overlap;
    later blocks override earlier ones. Hours not covered by any block fall
    back to defaults (30 °C, 2 m/s, 90°, 0 mm).
    """
    start_hour: int = Field(..., ge=0, description="First hour the block applies to (inclusive).")
    end_hour:   int = Field(..., gt=0, description="One past the last hour the block applies to (exclusive).")
    temperature_c: Optional[float] = Field(default=None)
    wind_speed_ms: Optional[float] = Field(default=None, ge=0.0)
    wind_dir_deg:  Optional[float] = Field(default=None, ge=0.0, le=360.0)
    rainfall_mm:   Optional[float] = Field(default=None, ge=0.0)

    @field_validator("end_hour")
    @classmethod
    def _end_after_start(cls, v, info):
        start = info.data.get("start_hour")
        if start is not None and v <= start:
            raise ValueError(f"end_hour ({v}) must be greater than start_hour ({start})")
        return v


# ═══════════════════════════════════════════════
#  Simulation Schemas
# ═══════════════════════════════════════════════
class SimulationRequest(BaseModel):
    """Request schema for POST /run-simulation."""
    pest_type: PestTypeEnum = Field(..., description="Type of pest to simulate")
    orchard_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Stable orchard identifier for multi-orchard deployments. "
                    "If omitted, the API derives one from orchard_geojson properties.",
    )
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
                    "DORMANT/FLOWERING=no activity, FRUITLET=Cecid Fly, MATURE=Fruit Fly. "
                    "Used as the fallback when `quadrant_stages` is not provided."
    )
    quadrant_stages: Optional[QuadrantStages] = Field(
        default=None,
        description="Per-quadrant phenology. When provided, replaces the scalar `orchard_stage` "
                    "by assigning each tree a stage based on which 2×2 quadrant of the orchard "
                    "bounding box it falls in. Within each quadrant the stage is mixed 70/20/10 "
                    "(dominant / adjacent / opposite) for realistic variation while preserving "
                    "spatial identifiability. When absent, all trees inherit `orchard_stage` "
                    "(backward compatible)."
    )
    tree_stage_overrides: Optional[Dict[str, OrchardStageEnum]] = Field(
        default=None,
        description="Optional per-tree phenology map from tree_id to growth stage. "
                    "Applied after the orchard-wide or quadrant stage assignment.",
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
    neighbor_direction: Optional[str] = Field(
        default=None,
        description="Compass direction of the neighbouring orchard. "
                    "One of: N, NE, E, SE, S, SW, W, NW. "
                    "When set, threat is applied as a gradient on the cells nearest that edge; "
                    "wind blowing FROM this direction further amplifies the threat. "
                    "If None, threat is distributed uniformly (original behaviour).",
    )
    tree_overrides: Optional[Dict[str, str]] = Field(
        default=None,
        description="Dict mapping tree_id (str) -> status (str) for manual status overrides. "
                    "Valid statuses: healthy, infected, bagged, dead, history_infected, suspect. "
                    "Trees marked as 'bagged' have reduced infection risk, while 'dead' trees are immune to pest spread."
    )

    # ── simulation mode ──────────────────────────────────────────
    treatment_applications: List[TreatmentApplication] = Field(
        default_factory=list,
        description="Treatment scenarios applied at simulation start. These reduce treated-tree "
                    "susceptibility and, optionally, infectiousness. No pesticide product or dose is implied.",
    )

    simulation_mode: SimulationModeEnum = Field(
        default=SimulationModeEnum.GRID,
        description="Spatial spread model: 'grid' (default, cellular automata) or "
                    "'tree_graph' (crown-aware tree-to-tree model).",
    )

    # ── tree_graph mode — initial infestation (by tree ID) ───────
    initial_infestation_tree_ids: Optional[List[str]] = Field(
        default=None,
        description="(tree_graph mode only) IDs of trees to seed as initially infested. "
                    "Takes precedence over initial_infestation row/col pairs when mode=tree_graph.",
    )

    # ── tree_graph mode — crown fallback ─────────────────────────
    crown_radius_m: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="(tree_graph mode) Fallback crown radius (m) applied to any tree that "
                    f"does not supply crown_radius_m, Crown_Width, or crown_size in its GeoJSON properties. "
                    f"Defaults to TG_DEFAULT_CROWN_RADIUS_M = {TG_DEFAULT_CROWN_RADIUS_M} m.",
    )

    # ── tree_graph model constants (optional overrides) ──────────
    tg_lambda0: Optional[float] = Field(
        default=None,
        gt=0.0,
        description=f"(tree_graph) Base hazard rate (hr⁻¹). Default: {TG_LAMBDA0}.",
    )
    tg_alpha: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=f"(tree_graph) Gap-decay coefficient (m⁻¹). Default: {TG_ALPHA}.",
    )
    tg_beta: Optional[float] = Field(
        default=None,
        ge=0.0,
        description=f"(tree_graph) Overlap-bonus coefficient. Default: {TG_BETA}.",
    )
    tg_wind_bias: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=f"(tree_graph) Wind directional amplification [0,1]. Default: {TG_WIND_BIAS}.",
    )
    tg_max_neighbor_dist_m: Optional[float] = Field(
        default=None,
        gt=0.0,
        description="(tree_graph) Maximum centre-to-centre distance for graph edges (m). "
                    f"Default: {TG_MAX_NEIGHBOR_DIST_M}.",
    )

    # ── manual weather override ───────────────────────────────────
    manual_weather: Optional[ManualWeather] = Field(
        default=None,
        description="If provided, the API uses these constant weather values for every "
                    "timestep instead of fetching a real forecast. Useful for scenario "
                    "testing ('what if it rains heavily?'). "
                    "Keys: temperature_c, wind_speed_ms, wind_dir_deg, rainfall_mm. "
                    "Missing keys fall back to synthetic defaults. "
                    "Negative wind/rain or out-of-range direction are rejected.",
    )
    manual_weather_series: Optional[List[ManualWeatherEntry]] = Field(
        default=None,
        description="Per-hour list of weather overrides. Index 0 = first hour of the "
                    "simulation, index N-1 = hour N. Missing keys in any entry are "
                    "inherited from the previous hour (defaults for index 0). If the "
                    "list is shorter than `hours`, the last entry is repeated. "
                    "Takes precedence over `manual_weather_blocks` and `manual_weather`.",
    )
    manual_weather_blocks: Optional[List[ManualWeatherBlock]] = Field(
        default=None,
        description="Block-based weather schedule. Each block specifies a half-open "
                    "[start_hour, end_hour) range and the weather values that apply. "
                    "Later blocks override earlier ones in overlapping ranges. Hours "
                    "not covered by any block fall back to defaults. Ideal for cecid "
                    "scenarios (wet buildup → dry emergence). Takes precedence over "
                    "`manual_weather`.",
    )
    manual_weather_start: Optional[datetime] = Field(
        default=None,
        description="Optional start datetime for the manual weather series. Controls "
                    "the hour-of-day stamped on each entry, which the engine uses for "
                    "crepuscular gate checks. Defaults to current UTC time.",
    )
    manual_weather_prefix_rain: Optional[List[float]] = Field(
        default=None,
        description="Optional pre-seed for the engine's 24-hour rainfall history "
                    "(mm per hour, oldest first). Lets cecid scenarios start with "
                    "rain already accumulated. Length is clipped to the engine's "
                    "history window (24 h).",
    )
    # ── biological gate parameter overrides ──────────────────────
    cecid_rainfall_threshold_mm: Optional[float] = Field(
        default=None, ge=0.1, le=50.0,
        description="Override cecid gate 24-h rainfall accumulation threshold (mm). "
                    f"Default: {CECID_RAINFALL_THRESHOLD_MM}.",
    )
    cecid_base_dispersal_prob: Optional[float] = Field(
        default=None, ge=0.01, le=0.50,
        description="Override cecid per-cell base dispersal probability. "
                    f"Default: {CECID_BASE_DISPERSAL_PROB}.",
    )
    fruit_fly_temp_threshold_c: Optional[float] = Field(
        default=None, ge=15.0, le=40.0,
        description="Override fruit fly gate temperature threshold (°C). "
                    f"Default: {FRUIT_FLY_TEMP_THRESHOLD_C}.",
    )
    fruit_fly_base_dispersal_prob: Optional[float] = Field(
        default=None, ge=0.01, le=0.50,
        description="Override fruit fly per-cell base dispersal probability. "
                    f"Default: {FRUIT_FLY_BASE_DISPERSAL_PROB}.",
    )

    # ── observation-based seeding ─────────────────────────────────
    use_observations_as_seeds: bool = Field(
        default=False,
        description="When true, recent infestation observations for this orchard are "
                    "merged into tree_overrides as infected sources before the simulation "
                    "starts. Lets field data drive the initial infestation pattern.",
    )
    observations_lookback_days: int = Field(
        default=30, ge=1, le=365,
        description="How many calendar days back to look for infestation observations "
                    "when use_observations_as_seeds=True.",
    )

    debug_gates: bool = Field(
        default=False,
        description="If true, the response includes a `gate_diagnostics` array with "
                    "per-hour gate-open/closed flags and the inputs that determined "
                    "them. Useful for tuning manual weather scenarios.",
    )
    include_time_series: bool = Field(
        default=True,
        description="When false, skips detailed per-timestep GeoJSON snapshots in "
                    "`time_series` and `timesteps`. Use this for dashboards that only "
                    "need the final `risk_geojson` so simulation results return faster.",
    )

    model_config = ConfigDict(
        json_schema_extra={
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
    )


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

    # Mode selector — present in every response for explicit A/B comparison
    simulation_mode: str = "grid"
    neighbor_direction: Optional[str] = None
    initial_seed_strategy: Optional[str] = None
    initial_seed_count: int = 0
    initial_seed_cells: Optional[List[Dict[str, int]]] = None
    initial_seed_tree_ids: Optional[List[str]] = None
    treatment_summary: Optional[Dict[str, Any]] = None

    # tree_graph-specific parameters (None when mode = grid)
    tg_n_trees: Optional[int] = None
    tg_n_edges: Optional[int] = None
    tg_lambda0: Optional[float] = None
    tg_alpha: Optional[float] = None
    tg_beta: Optional[float] = None
    tg_wind_bias: Optional[float] = None
    tg_max_neighbor_dist_m: Optional[float] = None
    tg_default_crown_radius_m: Optional[float] = None

    # Per-quadrant phenology breakdown (present when quadrant_stages was supplied
    # or always as a 100%-single-stage object when it wasn't). Keys: dormant,
    # flowering, fruitlet, mature. Feeds the dashboard phenology donut.
    stage_breakdown: Optional[Dict[str, int]] = None
    quadrant_stages: Optional[Dict[str, str]] = None
    tree_stage_override_count: int = 0


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

    # Optional gate diagnostics (only present when request.debug_gates=True)
    gate_diagnostics: Optional[List[Dict[str, Any]]] = None


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
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tree_id": "tree_042",
                "observed_pest": "cecid",
                "timestamp": "2026-02-15T10:30:00Z",
                "severity": 0.7,
                "notes": "Moderate gall midge infestation on young leaves"
            }
        }
    )


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
class WeatherForecastCheckRequest(BaseModel):
    """Request body for POST /alerts/check-weather-forecast."""
    orchard_id: str = Field(default="unknown", description="Orchard identifier")
    lat: Optional[float] = Field(default=None, ge=-90, le=90, description="Latitude (defaults to server default)")
    lon: Optional[float] = Field(default=None, ge=-180, le=180, description="Longitude (defaults to server default)")
    orchard_stage: Optional[str] = Field(default=None, description="Current phenological stage of the orchard")
    monitored_pest_types: Optional[List[str]] = Field(default=None, description="Pest types to check (defaults to both)")


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
    recommended_actions: List[str] = Field(default_factory=list)
    action_status: AlertActionStatusEnum = AlertActionStatusEnum.PENDING
    action_assigned_to: Optional[str] = None
    action_notes: Optional[str] = None
    action_due_at: Optional[datetime] = None
    action_completed_at: Optional[datetime] = None
    suggested_simulation_params: Optional[Dict[str, Any]] = None


class AlertResponse(BaseModel):
    """Response schema for alert data."""
    alert_id: str
    simulation_run_id: Optional[str] = None
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
    centroid_lon: Optional[float] = None
    centroid_lat: Optional[float] = None
    acknowledged_by: Optional[str]
    acknowledged_at: Optional[str]
    resolved_at: Optional[str]
    recommended_actions: List[str] = Field(default_factory=list)
    action_status: AlertActionStatusEnum = AlertActionStatusEnum.PENDING
    action_assigned_to: Optional[str] = None
    action_notes: Optional[str] = None
    action_due_at: Optional[str] = None
    action_completed_at: Optional[str] = None
    suggested_simulation_params: Optional[Dict[str, Any]] = None


class AlertListResponse(BaseModel):
    """Response schema for GET /alerts."""
    total: int
    active_count: int
    alerts: List[AlertResponse]


class AlertAcknowledge(BaseModel):
    """Request schema for acknowledging an alert."""
    acknowledged_by: str
    notes: Optional[str] = None


class AlertActionUpdate(BaseModel):
    """Request schema for updating alert response work."""
    action_status: Optional[AlertActionStatusEnum] = None
    assigned_to: Optional[str] = Field(default=None, max_length=100)
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


# ═══════════════════════════════════════════════
#  Health Check
# ═══════════════════════════════════════════════
class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    database: str
    weather_api: str
