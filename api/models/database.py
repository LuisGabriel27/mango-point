"""
MangoPoint API — Database Models (Backward-Compatibility Shim)
================================================================
This module re-exports all models from the consolidated db.models module.

All ORM models now live in db/models.py. This file exists solely to
preserve existing import paths like:
    from ..models.database import SimulationRun, Alert, PestType

DO NOT ADD NEW MODELS HERE — add them to db/models.py instead.
"""

# Re-export everything from the consolidated models module
from db.models import (
    # Enums
    TreeStatusEnum,
    TreeStageEnum,
    PestAttackStageEnum,
    MangoStageStatusEnum,
    PestType,
    AlertSeverity,
    AlertStatus,
    UserRoleEnum,
    # Models
    UserAccount,
    Orchard,
    Tree,
    Pest,
    SimulationRun,
    InfestationRecord,
    EnvironmentalCondition,
    MangoStage,
    Alert,
    WeatherCache,
)

# Legacy aliases for old code that used different names
TreeRegistry = Tree              # old name → new name
PestObservation = InfestationRecord  # old name → new name

# Backward-compatible enum aliases
CellStateDB = TreeStatusEnum

__all__ = [
    # Enums
    "TreeStatusEnum",
    "TreeStageEnum",
    "PestAttackStageEnum",
    "MangoStageStatusEnum",
    "PestType",
    "AlertSeverity",
    "AlertStatus",
    "UserRoleEnum",
    "CellStateDB",
    # Models
    "UserAccount",
    "Orchard",
    "Tree",
    "Pest",
    "SimulationRun",
    "InfestationRecord",
    "EnvironmentalCondition",
    "MangoStage",
    "Alert",
    "WeatherCache",
    # Legacy aliases
    "TreeRegistry",
    "PestObservation",
]
