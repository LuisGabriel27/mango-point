"""
MangoPoint — Consolidated Database ORM Models
================================================
All SQLAlchemy ORM models for the MangoPoint PostgreSQL + PostGIS database.

This is the SINGLE SOURCE OF TRUTH for database models.

Tables:
    - user_account:             Dashboard users and authentication metadata
    - orchard:                  Orchard metadata
    - tree:                     Tree spatial + biological data (PostGIS)
    - pest:                     Pest species
    - simulation_run:           Simulation run history + results
    - infestation_record:       Per-tree pest events per simulation
    - environmental_condition:  Weather data per simulation
    - mango_stage:              Phenological stage tracking
    - alert:                    Risk alert log
    - weather_cache:            Weather API response cache
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from sqlalchemy import (
    Integer, Float, String, Text, DateTime, Numeric,
    Boolean, ForeignKey, Enum as SQLEnum, JSON, Index,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.pool import Pool
from geoalchemy2 import Geometry
import enum

from api.core.database import Base
from utils.datetime_utils import utcnow_naive


# ─────────────────────────────────────────────
#  ENUM Definitions
# ─────────────────────────────────────────────

class TreeStatusEnum(str, enum.Enum):
    """Tree health status."""
    HEALTHY = "healthy"
    INFECTED = "infected"
    BAGGED = "bagged"
    DEAD = "dead"


class TreeStageEnum(str, enum.Enum):
    """Phenological stage of a tree."""
    DORMANT = "dormant"
    FLOWERING = "flowering"
    FRUITLET = "fruitlet"
    MATURE = "mature"


class PestAttackStageEnum(str, enum.Enum):
    """Stage at which a pest attacks."""
    FRUITLET = "fruitlet"
    MATURE = "mature"


class MangoStageStatusEnum(str, enum.Enum):
    """Developmental stage status for mango trees."""
    DORMANT = "dormant"
    FLOWERING = "flowering"
    FRUITLET = "fruitlet"
    MATURE = "mature"


class PestType(str, enum.Enum):
    """Pest type enumeration (used by simulation routes)."""
    CECID_FLY = "cecid"
    FRUIT_FLY = "fruitfly"


class AlertSeverity(str, enum.Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, enum.Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class UserRoleEnum(str, enum.Enum):
    """Roles supported by the dashboard authentication layer."""
    ADMIN = "admin"
    ANALYST = "analyst"
    OPERATOR = "operator"


# ═══════════════════════════════════════════════
#  1. Orchard
# ═══════════════════════════════════════════════

class UserAccount(Base):
    """Dashboard user accounts for FastAPI and Dash authentication."""
    __tablename__ = "user_account"

    user_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRoleEnum] = mapped_column(
        SQLEnum(UserRoleEnum, name="user_role_enum", create_type=False),
        nullable=False,
        default=UserRoleEnum.ADMIN,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    __table_args__ = (
        Index("idx_user_account_username", "username", unique=True),
        Index("idx_user_account_email", "email", unique=True),
    )


class Orchard(Base):
    """General information about a mango orchard."""
    __tablename__ = "orchard"

    orchard_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    orchard_uid: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    owner_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    area_size: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    tree_count: Mapped[int] = mapped_column(Integer, default=0)
    geojson: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    orchard_stage: Mapped[str] = mapped_column(String(50), nullable=False, default="mature")
    days_since_flowering: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    monitored_pest_types: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    last_monitoring_scan_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=utcnow_naive,
        onupdate=utcnow_naive,
    )

    # Relationships
    trees: Mapped[List["Tree"]] = relationship("Tree", back_populates="orchard")

    __table_args__ = (
        Index("idx_orchard_uid", "orchard_uid", unique=True),
        Index("idx_orchard_active", "is_active"),
        Index("idx_orchard_monitoring_enabled", "monitoring_enabled"),
    )


# ═══════════════════════════════════════════════
#  2. Tree
# ═══════════════════════════════════════════════

class Tree(Base):
    """Spatial and biological data for each mango tree."""
    __tablename__ = "tree"

    tree_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    orchard_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("orchard.orchard_id", ondelete="CASCADE"),
        nullable=False,
    )

    # Coordinates kept for simulation-engine compatibility
    x_coordinate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    y_coordinate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # PostGIS geometry point (populated from GeoJSON)
    geom: Mapped[Optional[Any]] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=True,
    )

    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[TreeStatusEnum] = mapped_column(
        SQLEnum(TreeStatusEnum, name="tree_status_enum", create_type=False),
        nullable=False,
        default=TreeStatusEnum.HEALTHY,
    )
    current_stage: Mapped[TreeStageEnum] = mapped_column(
        SQLEnum(TreeStageEnum, name="tree_stage_enum", create_type=False),
        nullable=False,
        default=TreeStageEnum.DORMANT,
    )

    # Relationships
    orchard: Mapped["Orchard"] = relationship("Orchard", back_populates="trees")
    infestation_records: Mapped[List["InfestationRecord"]] = relationship(
        "InfestationRecord", back_populates="tree",
    )

    __table_args__ = (
        Index("idx_tree_orchard_id", "orchard_id"),
        Index("idx_tree_geom", "geom", postgresql_using="gist"),
    )


# ═══════════════════════════════════════════════
#  3. Pest
# ═══════════════════════════════════════════════

class Pest(Base):
    """Pest species modeled in the simulation."""
    __tablename__ = "pest"

    pest_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scientific_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    attack_stage: Mapped[PestAttackStageEnum] = mapped_column(
        SQLEnum(PestAttackStageEnum, name="pest_attack_stage_enum", create_type=False),
        nullable=False,
    )

    # Relationships
    infestation_records: Mapped[List["InfestationRecord"]] = relationship(
        "InfestationRecord", back_populates="pest",
    )


# ═══════════════════════════════════════════════
#  4. SimulationRun
# ═══════════════════════════════════════════════

class SimulationRun(Base):
    """Logs parameters, execution details, and results of each simulation."""
    __tablename__ = "simulation_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    simulation_id: Mapped[int] = mapped_column(
        Integer, autoincrement=True, unique=True, nullable=False,
    )
    run_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
    )

    # Input parameters
    pest_type: Mapped[PestType] = mapped_column(
        SQLEnum(PestType), nullable=False,
    )
    orchard_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True,
    )
    orchard_geojson: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    bagged_tree_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True,
    )
    treatment_applications: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True,
    )
    hours: Mapped[int] = mapped_column(Integer, default=48)

    # Reproducibility
    random_seed: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    risk_threshold: Mapped[float] = mapped_column(Float, default=0.7)

    # Weather source
    weather_source: Mapped[str] = mapped_column(String(50), default="synthetic")
    weather_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )

    # Results
    output_geojson: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )
    peak_risk: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cells_at_risk: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    n_infested_final: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ERD fields
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=utcnow_naive,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Status
    status: Mapped[str] = mapped_column(String(50), default="running")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    alerts: Mapped[List["Alert"]] = relationship("Alert", back_populates="simulation_run")
    infestation_records: Mapped[List["InfestationRecord"]] = relationship(
        "InfestationRecord", back_populates="simulation_run",
    )
    environmental_conditions: Mapped[List["EnvironmentalCondition"]] = relationship(
        "EnvironmentalCondition", back_populates="simulation_run",
    )
    mango_stages: Mapped[List["MangoStage"]] = relationship(
        "MangoStage", back_populates="simulation_run",
    )


# ═══════════════════════════════════════════════
#  5. InfestationRecord
# ═══════════════════════════════════════════════

class InfestationRecord(Base):
    """Pest infestation events.

    ``simulation_id`` is nullable so field observations can be stored as
    ground-truth records independently from simulation output.
    """
    __tablename__ = "infestation_record"

    infestation_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    tree_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tree.tree_id", ondelete="CASCADE"),
        nullable=False,
    )
    pest_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pest.pest_id", ondelete="CASCADE"),
        nullable=False,
    )
    simulation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("simulation_run.simulation_id", ondelete="CASCADE"),
        nullable=True,
    )
    record_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    infected_status: Mapped[bool] = mapped_column(Boolean, default=False)
    infestation_level: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 2), nullable=True,
    )

    # Relationships
    tree: Mapped["Tree"] = relationship("Tree", back_populates="infestation_records")
    pest: Mapped["Pest"] = relationship("Pest", back_populates="infestation_records")
    simulation_run: Mapped["SimulationRun"] = relationship(
        "SimulationRun", back_populates="infestation_records",
    )

    __table_args__ = (
        Index("idx_infestation_tree_id", "tree_id"),
        Index("idx_infestation_pest_id", "pest_id"),
        Index("idx_infestation_simulation_id", "simulation_id"),
    )


# ═══════════════════════════════════════════════
#  6. EnvironmentalCondition
# ═══════════════════════════════════════════════

class EnvironmentalCondition(Base):
    """Environmental variables used during a simulation run."""
    __tablename__ = "environmental_condition"

    condition_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    simulation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("simulation_run.simulation_id", ondelete="CASCADE"),
        nullable=False,
    )
    condition_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    temperature: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    humidity: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)
    rainfall: Mapped[Optional[float]] = mapped_column(Numeric(7, 2), nullable=True)
    wind_speed: Mapped[Optional[float]] = mapped_column(Numeric(5, 2), nullable=True)

    # Relationships
    simulation_run: Mapped["SimulationRun"] = relationship(
        "SimulationRun", back_populates="environmental_conditions",
    )

    __table_args__ = (
        Index("idx_envcond_simulation_id", "simulation_id"),
    )


# ═══════════════════════════════════════════════
#  7. MangoStage
# ═══════════════════════════════════════════════

class MangoStage(Base):
    """Developmental stages of mango trees during a simulation period."""
    __tablename__ = "mango_stage"

    stage_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True,
    )
    simulation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("simulation_run.simulation_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    stage_status: Mapped[MangoStageStatusEnum] = mapped_column(
        SQLEnum(MangoStageStatusEnum, name="mango_stage_status_enum", create_type=False),
        nullable=False,
        default=MangoStageStatusEnum.DORMANT,
    )

    # Relationships
    simulation_run: Mapped["SimulationRun"] = relationship(
        "SimulationRun", back_populates="mango_stages",
    )

    __table_args__ = (
        Index("idx_mangostage_simulation_id", "simulation_id"),
    )


# ═══════════════════════════════════════════════
#  8. Alert
# ═══════════════════════════════════════════════

class Alert(Base):
    """Alert log for high-risk conditions."""
    __tablename__ = "alert"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True,
    )

    # Trigger information
    simulation_run_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        ForeignKey("simulation_run.run_id"),
        nullable=True,
    )
    triggered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=utcnow_naive,
    )

    # Alert details
    severity: Mapped[AlertSeverity] = mapped_column(
        SQLEnum(AlertSeverity), default=AlertSeverity.HIGH,
    )
    status: Mapped[AlertStatus] = mapped_column(
        SQLEnum(AlertStatus), default=AlertStatus.ACTIVE,
    )

    # Risk information
    risk_value: Mapped[float] = mapped_column(Float, nullable=False)
    affected_cells: Mapped[Optional[List[Dict[str, int]]]] = mapped_column(
        JSON, nullable=True,
    )
    affected_tree_ids: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True,
    )

    # Location context
    orchard_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    zone_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    centroid_lon: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    centroid_lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Message
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_actions: Mapped[Optional[List[str]]] = mapped_column(
        JSON, nullable=True,
    )

    # Notification tracking
    email_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sms_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sms_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Resolution
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    action_assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    action_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    simulation_run: Mapped[Optional["SimulationRun"]] = relationship(
        "SimulationRun", back_populates="alerts",
    )

    __table_args__ = (
        Index("idx_alert_status", "status"),
        Index("idx_alert_severity", "severity"),
    )


# ═══════════════════════════════════════════════
#  9. WeatherCache
# ═══════════════════════════════════════════════

class WeatherCache(Base):
    """Cache for weather API responses."""
    __tablename__ = "weather_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(
        String(200), unique=True, nullable=False, index=True,
    )

    # Location
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)

    # Weather data
    wind_speed_ms: Mapped[float] = mapped_column(Float, nullable=False)
    wind_direction_deg: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Raw response
    raw_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
    )

    # Cache management
    fetched_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=utcnow_naive,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source: Mapped[str] = mapped_column(String(50), default="openweathermap")
