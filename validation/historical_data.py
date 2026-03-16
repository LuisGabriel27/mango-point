"""
MangoPoint Validation — Historical Data Loader
================================================
Loads and processes historical pest monitoring data from BPI Guimaras
Research and Development Center for model validation.

Data Source: guimaras_pest_data_2022_2025.csv
Columns:
  - year: Monitoring year (2022-2025)
  - month: Monitoring month (1-12)
  - fruit_fly_managed_cptd: Catch Per Trap per Day in managed orchards
  - fruit_fly_unmanaged_cptd: Catch Per Trap per Day in unmanaged orchards
  - cecid_fly_infestation_pct: Percentage of fruits infested by Cecid Fly

Risk Classification (based on BPI guidelines):
  - Fruit Fly CPTD thresholds:
      * Low: < 8 flies/trap/day
      * Medium: 8-20 flies/trap/day
      * High: > 20 flies/trap/day
  - Cecid Fly Infestation thresholds:
      * Low: < 5% infestation
      * Medium: 5-15% infestation
      * High: > 15% infestation
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple


class PestRiskLevel(Enum):
    """Categorical risk levels for pest activity."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    
    @property
    def numeric(self) -> int:
        """Return numeric value for comparison (0=Low, 1=Medium, 2=High)."""
        mapping = {PestRiskLevel.LOW: 0, PestRiskLevel.MEDIUM: 1, PestRiskLevel.HIGH: 2}
        return mapping[self]


class PestType(Enum):
    """Types of pests monitored in the historical data."""
    FRUIT_FLY = "fruitfly"
    CECID_FLY = "cecid"


# ─────────────────────────────────────────────
# BPI Risk Classification Thresholds
# ─────────────────────────────────────────────

# Fruit Fly CPTD (Catch Per Trap per Day) thresholds
# Based on BPI-Guimaras monitoring guidelines
FRUIT_FLY_CPTD_LOW_THRESHOLD = 8.0      # Below this = Low risk
FRUIT_FLY_CPTD_HIGH_THRESHOLD = 20.0    # At or above this = High risk

# Cecid Fly infestation percentage thresholds
CECID_FLY_PCT_LOW_THRESHOLD = 5.0       # Below this = Low risk
CECID_FLY_PCT_HIGH_THRESHOLD = 15.0     # At or above this = High risk


@dataclass
class HistoricalRecord:
    """
    A single historical pest monitoring record from BPI data.
    
    Attributes
    ----------
    year : int
        Year of the record (2022-2025)
    month : int
        Month of the record (1-12)
    fruit_fly_managed_cptd : float
        Catch Per Trap per Day in managed orchards
    fruit_fly_unmanaged_cptd : float
        Catch Per Trap per Day in unmanaged orchards
    cecid_fly_infestation_pct : float
        Percentage of fruits infested by Cecid Fly
    """
    year: int
    month: int
    fruit_fly_managed_cptd: float
    fruit_fly_unmanaged_cptd: float
    cecid_fly_infestation_pct: float
    
    # Computed fields
    _date: datetime = field(init=False, repr=False)
    
    def __post_init__(self):
        """Compute derived fields after initialization."""
        # Create datetime for the middle of the month (15th)
        self._date = datetime(self.year, self.month, 15)
    
    @property
    def date(self) -> datetime:
        """Representative date for this record (15th of the month)."""
        return self._date
    
    @property
    def date_str(self) -> str:
        """Date string in YYYY-MM format."""
        return f"{self.year}-{self.month:02d}"
    
    @property
    def season(self) -> str:
        """
        Philippine season classification.
        
        - Dry Season: December - May
        - Wet Season: June - November
        """
        if self.month in [12, 1, 2, 3, 4, 5]:
            return "dry"
        return "wet"
    
    @property
    def mango_stage(self) -> str:
        """
        Typical mango phenological stage for this month.
        
        Based on Guimaras mango calendar:
        - Nov-Jan: Flowering induction (Dormant → Flowering)
        - Feb-Mar: Flowering (Flowering)
        - Apr-May: Fruit development (Fruitlet)
        - Jun-Aug: Fruit maturation (Mature)
        - Sep-Oct: Post-harvest/Vegetative (Dormant)
        """
        stage_map = {
            1: "flowering",   # Late flowering
            2: "flowering",   # Peak flowering
            3: "fruitlet",    # Early fruit development
            4: "fruitlet",    # Fruit development
            5: "mature",      # Early maturation
            6: "mature",      # Peak harvest
            7: "mature",      # Late harvest
            8: "dormant",     # Post-harvest
            9: "dormant",     # Vegetative
            10: "dormant",    # Pre-flowering
            11: "dormant",    # Flowering induction
            12: "flowering",  # Early flowering
        }
        return stage_map.get(self.month, "dormant")
    
    def get_fruit_fly_risk_level(self, use_managed: bool = True) -> PestRiskLevel:
        """
        Classify Fruit Fly risk level based on CPTD values.
        
        Parameters
        ----------
        use_managed : bool
            If True, use managed orchard CPTD (default).
            If False, use unmanaged orchard CPTD.
        
        Returns
        -------
        PestRiskLevel
            Classification (LOW, MEDIUM, or HIGH)
        """
        cptd = self.fruit_fly_managed_cptd if use_managed else self.fruit_fly_unmanaged_cptd
        return classify_fruit_fly_cptd(cptd)
    
    def get_cecid_fly_risk_level(self) -> PestRiskLevel:
        """
        Classify Cecid Fly risk level based on infestation percentage.
        
        Returns
        -------
        PestRiskLevel
            Classification (LOW, MEDIUM, or HIGH)
        """
        return classify_cecid_fly_pct(self.cecid_fly_infestation_pct)
    
    def get_risk_level(self, pest_type: PestType, use_managed: bool = True) -> PestRiskLevel:
        """
        Get risk level for specified pest type.
        
        Parameters
        ----------
        pest_type : PestType
            The pest type to classify
        use_managed : bool
            For Fruit Fly, whether to use managed orchard data
        
        Returns
        -------
        PestRiskLevel
            Classification for the specified pest
        """
        if pest_type == PestType.FRUIT_FLY:
            return self.get_fruit_fly_risk_level(use_managed)
        return self.get_cecid_fly_risk_level()
    
    def get_numeric_value(self, pest_type: PestType, use_managed: bool = True) -> float:
        """
        Get the raw numeric pest metric value.
        
        Parameters
        ----------
        pest_type : PestType
            The pest type
        use_managed : bool
            For Fruit Fly, whether to use managed orchard data
        
        Returns
        -------
        float
            CPTD for Fruit Fly, or infestation % for Cecid Fly
        """
        if pest_type == PestType.FRUIT_FLY:
            return self.fruit_fly_managed_cptd if use_managed else self.fruit_fly_unmanaged_cptd
        return self.cecid_fly_infestation_pct
    
    def to_dict(self) -> dict:
        """Convert record to dictionary."""
        return {
            "year": self.year,
            "month": self.month,
            "date": self.date_str,
            "season": self.season,
            "mango_stage": self.mango_stage,
            "fruit_fly_managed_cptd": self.fruit_fly_managed_cptd,
            "fruit_fly_unmanaged_cptd": self.fruit_fly_unmanaged_cptd,
            "cecid_fly_infestation_pct": self.cecid_fly_infestation_pct,
            "fruit_fly_risk_managed": self.get_fruit_fly_risk_level(True).value,
            "fruit_fly_risk_unmanaged": self.get_fruit_fly_risk_level(False).value,
            "cecid_fly_risk": self.get_cecid_fly_risk_level().value,
        }


def classify_fruit_fly_cptd(cptd: float) -> PestRiskLevel:
    """
    Classify Fruit Fly risk based on CPTD (Catch Per Trap per Day).
    
    Based on BPI-Guimaras monitoring guidelines.
    
    Parameters
    ----------
    cptd : float
        Catch Per Trap per Day value
    
    Returns
    -------
    PestRiskLevel
        LOW if < 8, MEDIUM if 8-20, HIGH if > 20
    """
    if cptd < FRUIT_FLY_CPTD_LOW_THRESHOLD:
        return PestRiskLevel.LOW
    elif cptd < FRUIT_FLY_CPTD_HIGH_THRESHOLD:
        return PestRiskLevel.MEDIUM
    return PestRiskLevel.HIGH


def classify_cecid_fly_pct(infestation_pct: float) -> PestRiskLevel:
    """
    Classify Cecid Fly risk based on infestation percentage.
    
    Based on BPI-Guimaras monitoring guidelines.
    
    Parameters
    ----------
    infestation_pct : float
        Percentage of fruits infested
    
    Returns
    -------
    PestRiskLevel
        LOW if < 5%, MEDIUM if 5-15%, HIGH if > 15%
    """
    if infestation_pct < CECID_FLY_PCT_LOW_THRESHOLD:
        return PestRiskLevel.LOW
    elif infestation_pct < CECID_FLY_PCT_HIGH_THRESHOLD:
        return PestRiskLevel.MEDIUM
    return PestRiskLevel.HIGH


class HistoricalDataLoader:
    """
    Loads and manages historical pest monitoring data from BPI Guimaras.
    
    Usage
    -----
        loader = HistoricalDataLoader()
        records = loader.load()
        
        # Filter by pest type relevance
        fruit_fly_records = loader.get_fruit_fly_relevant_records()
        cecid_fly_records = loader.get_cecid_fly_relevant_records()
    
    Attributes
    ----------
    data_path : Path
        Path to the CSV data file
    records : list[HistoricalRecord]
        Loaded historical records
    """
    
    DEFAULT_DATA_PATH = Path(__file__).parent.parent / "data" / "guimaras_pest_data_2022_2025.csv"
    
    def __init__(self, data_path: Optional[Path] = None):
        """
        Initialize the data loader.
        
        Parameters
        ----------
        data_path : Path, optional
            Path to CSV file. Defaults to data/guimaras_pest_data_2022_2025.csv
        """
        self.data_path = Path(data_path) if data_path else self.DEFAULT_DATA_PATH
        self.records: List[HistoricalRecord] = []
        self._loaded = False
    
    def load(self) -> List[HistoricalRecord]:
        """
        Load historical records from CSV file.
        
        Returns
        -------
        list[HistoricalRecord]
            All loaded records
        
        Raises
        ------
        FileNotFoundError
            If the data file is not found
        ValueError
            If the CSV format is invalid
        """
        if not self.data_path.exists():
            raise FileNotFoundError(
                f"Historical data file not found: {self.data_path}\n"
                "Expected BPI Guimaras pest monitoring data in CSV format."
            )
        
        self.records = []
        
        with open(self.data_path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            
            # Validate expected columns
            required_cols = {
                "year", "month", 
                "fruit_fly_managed_cptd", "fruit_fly_unmanaged_cptd",
                "cecid_fly_infestation_pct"
            }
            if not required_cols.issubset(set(reader.fieldnames or [])):
                raise ValueError(
                    f"CSV missing required columns. Expected: {required_cols}\n"
                    f"Found: {reader.fieldnames}"
                )
            
            for row in reader:
                try:
                    record = HistoricalRecord(
                        year=int(row["year"]),
                        month=int(row["month"]),
                        fruit_fly_managed_cptd=float(row["fruit_fly_managed_cptd"]),
                        fruit_fly_unmanaged_cptd=float(row["fruit_fly_unmanaged_cptd"]),
                        cecid_fly_infestation_pct=float(row["cecid_fly_infestation_pct"]),
                    )
                    self.records.append(record)
                except (ValueError, KeyError) as e:
                    raise ValueError(f"Invalid data in row: {row}. Error: {e}") from e
        
        self._loaded = True
        return self.records
    
    def ensure_loaded(self) -> None:
        """Ensure data is loaded, loading if necessary."""
        if not self._loaded:
            self.load()
    
    @property
    def n_records(self) -> int:
        """Number of loaded records."""
        self.ensure_loaded()
        return len(self.records)
    
    def get_all_records(self) -> List[HistoricalRecord]:
        """Get all historical records."""
        self.ensure_loaded()
        return self.records.copy()
    
    def get_records_by_year(self, year: int) -> List[HistoricalRecord]:
        """Get records for a specific year."""
        self.ensure_loaded()
        return [r for r in self.records if r.year == year]
    
    def get_records_by_season(self, season: str) -> List[HistoricalRecord]:
        """Get records for a specific season ('dry' or 'wet')."""
        self.ensure_loaded()
        return [r for r in self.records if r.season == season]
    
    def get_records_by_stage(self, stage: str) -> List[HistoricalRecord]:
        """Get records for a specific mango stage."""
        self.ensure_loaded()
        return [r for r in self.records if r.mango_stage == stage]
    
    def get_fruit_fly_relevant_records(self) -> List[HistoricalRecord]:
        """
        Get records relevant for Fruit Fly validation.
        
        Fruit Fly is biologically active during MATURE stage
        (typically May-July in Guimaras).
        
        Returns
        -------
        list[HistoricalRecord]
            Records where Fruit Fly activity is biologically expected
        """
        self.ensure_loaded()
        return [r for r in self.records if r.mango_stage == "mature"]
    
    def get_cecid_fly_relevant_records(self) -> List[HistoricalRecord]:
        """
        Get records relevant for Cecid Fly validation.
        
        Cecid Fly is biologically active during FRUITLET stage
        (typically March-April in Guimaras), with emergence 
        triggered by rainfall during dry-to-wet season transitions.
        
        Returns
        -------
        list[HistoricalRecord]
            Records where Cecid Fly activity is biologically expected
        """
        self.ensure_loaded()
        return [r for r in self.records if r.mango_stage == "fruitlet"]
    
    def get_records_with_activity(
        self,
        pest_type: PestType,
        min_level: PestRiskLevel = PestRiskLevel.MEDIUM,
        use_managed: bool = True,
    ) -> List[HistoricalRecord]:
        """
        Get records with at least the specified pest activity level.
        
        Parameters
        ----------
        pest_type : PestType
            The pest type to filter by
        min_level : PestRiskLevel
            Minimum risk level to include (default: MEDIUM)
        use_managed : bool
            For Fruit Fly, whether to use managed orchard data
        
        Returns
        -------
        list[HistoricalRecord]
            Records meeting the criteria
        """
        self.ensure_loaded()
        results = []
        for r in self.records:
            level = r.get_risk_level(pest_type, use_managed)
            if level.numeric >= min_level.numeric:
                results.append(r)
        return results
    
    def get_date_range(self) -> Tuple[datetime, datetime]:
        """Get the date range covered by the data."""
        self.ensure_loaded()
        dates = [r.date for r in self.records]
        return (min(dates), max(dates)) if dates else (datetime.now(), datetime.now())
    
    def summary(self) -> dict:
        """
        Generate a summary of the loaded data.
        
        Returns
        -------
        dict
            Summary statistics
        """
        self.ensure_loaded()
        
        if not self.records:
            return {"n_records": 0}
        
        years = sorted(set(r.year for r in self.records))
        
        # Count risk levels for each pest type
        ff_levels = {"Low": 0, "Medium": 0, "High": 0}
        cecid_levels = {"Low": 0, "Medium": 0, "High": 0}
        
        for r in self.records:
            ff_levels[r.get_fruit_fly_risk_level(True).value] += 1
            cecid_levels[r.get_cecid_fly_risk_level().value] += 1
        
        return {
            "n_records": len(self.records),
            "years": years,
            "year_range": f"{years[0]}-{years[-1]}",
            "fruit_fly_risk_distribution": ff_levels,
            "cecid_fly_risk_distribution": cecid_levels,
            "fruit_fly_relevant_records": len(self.get_fruit_fly_relevant_records()),
            "cecid_fly_relevant_records": len(self.get_cecid_fly_relevant_records()),
        }
    
    def __repr__(self) -> str:
        status = f"{len(self.records)} records" if self._loaded else "not loaded"
        return f"HistoricalDataLoader({self.data_path.name}, {status})"
