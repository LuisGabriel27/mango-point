"""
MangoPoint — Grid Environment
==============================
Defines the 2-D orchard grid that underpins the Cellular Automata.

Each cell holds:
    • state    – CellState enum (EMPTY / UNBAGGED / BAGGED / INFESTED)
    • risk     – cumulative infestation probability [0, 1]
    • tree_id  – optional identifier linking back to the GIS registry

The grid can be initialised from:
    1. Fixed dimensions (rows × cols)
    2. A GIS-derived spatial registry (see gis_utils.py)
"""

from __future__ import annotations
import numpy as np
from typing import Optional, Tuple, List

import math
from typing import Optional

from core.config import (
    CellState,
    DEFAULT_GRID_ROWS,
    DEFAULT_GRID_COLS,
    CELL_SIZE_M,
    BAG_RESISTANCE,
    NEIGHBOUR_OFFSETS,
    WIND_NEIGHBOR_BOOST,
    DIRECTION_BEARING_MAP,
)


class OrchardGrid:
    """2-D cellular automata grid for a mango orchard."""

    # ── construction ────────────────────────────────────────────
    def __init__(
        self,
        rows: int = DEFAULT_GRID_ROWS,
        cols: int = DEFAULT_GRID_COLS,
        cell_size_m: float = CELL_SIZE_M,
    ):
        self.rows = rows
        self.cols = cols
        self.cell_size_m = cell_size_m

        # State matrix  (int8 for memory efficiency)
        self.state: np.ndarray = np.full(
            (rows, cols), CellState.EMPTY, dtype=np.int8
        )

        # Risk accumulator  [0.0 … 1.0]
        self.risk: np.ndarray = np.zeros((rows, cols), dtype=np.float64)

        # Neighbor threat layer  [0.0 … 1.0]
        # Represents external orchard pressure from adjacent unmanaged areas
        # Historical data shows unmanaged orchards have significantly higher pest pressure
        self.neighbor_threat: np.ndarray = np.zeros((rows, cols), dtype=np.float64)

        # Optional tree-ID registry (string labels from GIS)
        self.tree_ids: np.ndarray = np.full((rows, cols), "", dtype=object)

        # Geo-reference origin (set by GIS loader)
        self.origin_lon: float = 0.0
        self.origin_lat: float = 0.0

        # Bearing toward the neighbouring orchard (degrees, 0=N CW).
        # Set by the service layer when neighbor_direction is provided.
        # Used by get_wind_neighbor_factor() to amplify threat when wind
        # blows FROM that direction.
        self.neighbor_bearing: Optional[float] = None

    # ── factory helpers ─────────────────────────────────────────
    @classmethod
    def from_shape(cls, rows: int, cols: int, **kw) -> "OrchardGrid":
        return cls(rows, cols, **kw)

    # ── state mutators ──────────────────────────────────────────
    def plant_trees(
        self,
        mask: np.ndarray,
        state: CellState = CellState.UNBAGGED,
    ) -> None:
        """Set cells where *mask* is True to the given state."""
        self.state[mask] = state

    def set_state(self, row: int, col: int, state: CellState) -> None:
        self.state[row, col] = state

    def bag_trees(self, mask: np.ndarray) -> None:
        """Bag all UNBAGGED trees where mask is True."""
        can_bag = (self.state == CellState.UNBAGGED) & mask
        self.state[can_bag] = CellState.BAGGED

    def infest(self, row: int, col: int) -> None:
        """Mark a single cell as infested (initial infection seed)."""
        if self.state[row, col] in (CellState.UNBAGGED, CellState.BAGGED):
            self.state[row, col] = CellState.INFESTED

    def seed_infestation(self, positions: List[Tuple[int, int]]) -> None:
        """Seed initial infestation at multiple grid positions."""
        for r, c in positions:
            self.infest(r, c)

    # ── queries ─────────────────────────────────────────────────
    @property
    def infested_mask(self) -> np.ndarray:
        return self.state == CellState.INFESTED

    @property
    def susceptible_mask(self) -> np.ndarray:
        """Trees that can be infected (excludes DEAD, EMPTY, INFESTED).

        BAGGED trees are included here because bagging lowers infestation
        probability but does not make infection impossible.
        """
        return (self.state == CellState.UNBAGGED) | (self.state == CellState.BAGGED)

    @property
    def unbagged_mask(self) -> np.ndarray:
        return self.state == CellState.UNBAGGED

    @property
    def bagged_mask(self) -> np.ndarray:
        return self.state == CellState.BAGGED

    @property
    def dead_mask(self) -> np.ndarray:
        """Trees permanently removed from simulation."""
        return self.state == CellState.DEAD

    @property
    def history_infected_mask(self) -> np.ndarray:
        """Trees previously infected (stored for future biology)."""
        return self.state == CellState.HISTORY_INFECTED

    @property
    def suspect_mask(self) -> np.ndarray:
        """Trees flagged for monitoring (near external infected areas)."""
        return self.state == CellState.SUSPECT

    def get_neighbours(self, row: int, col: int) -> np.ndarray:
        """Return valid (row, col) pairs for 8-connected neighbours."""
        nbrs = NEIGHBOUR_OFFSETS + np.array([row, col])
        valid = (
            (nbrs[:, 0] >= 0) & (nbrs[:, 0] < self.rows) &
            (nbrs[:, 1] >= 0) & (nbrs[:, 1] < self.cols)
        )
        return nbrs[valid]

    # ── neighbor threat helpers ─────────────────────────────────
    def set_neighbor_threat(
        self,
        row: int,
        col: int,
        threat: float,
    ) -> None:
        """Set neighbor threat level for a cell (0.0 to 1.0)."""
        self.neighbor_threat[row, col] = np.clip(threat, 0.0, 1.0)

    def set_neighbor_threat_uniform(self, threat: float) -> None:
        """Set uniform neighbor threat across all cells."""
        self.neighbor_threat[:] = np.clip(threat, 0.0, 1.0)

    def set_neighbor_threat_from_mask(
        self,
        mask: np.ndarray,
        threat_value: float = 0.8,
    ) -> None:
        """
        Set neighbor threat for cells adjacent to a mask (e.g., unmanaged areas).
        
        Parameters
        ----------
        mask : np.ndarray
            Boolean mask indicating external threat source cells
        threat_value : float
            Threat level to assign to adjacent cells (default 0.8)
        """
        # Dilate mask to find neighbors, then apply threat
        from scipy.ndimage import binary_dilation
        dilated = binary_dilation(mask, iterations=1)
        boundary = dilated & ~mask
        self.neighbor_threat[boundary] = threat_value

    def set_neighbor_threat_directional(
        self,
        direction: str,
        threat: float,
    ) -> None:
        """
        Apply a directional neighbor threat gradient.

        Cells near the edge facing *direction* receive a threat proportional
        to *threat*, decaying linearly toward the opposite edge.  Cells on
        the far side of the grid from the neighbour receive zero threat.

        The gradient is computed by projecting each cell's position (relative
        to the grid centre) onto the unit vector pointing toward the neighbour.

        Parameters
        ----------
        direction : str
            One of 'N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'.
        threat : float
            Maximum threat level [0, 1] applied to cells on the nearest edge.
        """
        bearing_deg = DIRECTION_BEARING_MAP.get(direction.upper(), 0.0)
        bearing_rad = math.radians(bearing_deg)

        # Grid-coordinate unit vector toward the neighbour.
        # Rows increase southward, cols increase eastward.
        # North bearing → u_row = -1 (row decreases); East → u_col = +1.
        u_row = -math.cos(bearing_rad)
        u_col = math.sin(bearing_rad)

        center_r = (self.rows - 1) / 2.0
        center_c = (self.cols - 1) / 2.0

        rows_arr = np.arange(self.rows, dtype=np.float64) - center_r
        cols_arr = np.arange(self.cols, dtype=np.float64) - center_c
        R, C = np.meshgrid(rows_arr, cols_arr, indexing="ij")

        proj = R * u_row + C * u_col          # signed projection, range [-max, +max]
        max_proj = float(proj.max())
        if max_proj > 1e-9:
            self.neighbor_threat = np.clip(
                threat * proj / max_proj, 0.0, 1.0
            )
        else:
            self.neighbor_threat = np.full_like(self.risk, float(threat))

    def get_wind_neighbor_factor(self, wind_dir_deg: float) -> float:
        """
        Return a wind-amplification factor for the neighbour threat.

        When wind blows FROM the same direction as the neighbour (i.e.
        ``wind_dir_deg ≈ neighbor_bearing``), pests are carried inward and
        the factor is ``1 + WIND_NEIGHBOR_BOOST``.  When wind blows toward
        the neighbour the factor is ``1 - WIND_NEIGHBOR_BOOST``.

        Returns 1.0 when no neighbour bearing has been set (uniform threat,
        no directional wind interaction).
        """
        if self.neighbor_bearing is None:
            return 1.0
        bearing_rad = math.radians(self.neighbor_bearing)
        wind_rad = math.radians(wind_dir_deg)
        factor = 1.0 + WIND_NEIGHBOR_BOOST * math.cos(wind_rad - bearing_rad)
        return max(0.0, min(2.0, factor))

    def get_neighbor_threat(self, row: int, col: int) -> float:
        """Get neighbor threat level for a cell."""
        return float(self.neighbor_threat[row, col])

    # ── risk helpers ────────────────────────────────────────────
    def apply_dispersal_probability(
        self,
        target_row: int,
        target_col: int,
        prob: float,
    ) -> None:
        """
        Accumulate dispersal probability onto a target cell.
        If the cell is BAGGED, reduce probability by BAG_RESISTANCE.
        Skips DEAD cells entirely (permanently removed from simulation).
        """
        cell_state = self.state[target_row, target_col]
        if cell_state == CellState.EMPTY:
            return
        if cell_state == CellState.INFESTED:
            return  # already infested
        if cell_state == CellState.DEAD:
            return  # permanently removed from simulation logic
        if cell_state == CellState.BAGGED:
            # Bagging strongly reduces risk but does not guarantee immunity.
            effective_prob = prob * (1.0 - BAG_RESISTANCE)
        else:
            effective_prob = prob

        # Union of independent probabilities: P = 1 - (1-P_old)(1-P_new)
        old = self.risk[target_row, target_col]
        self.risk[target_row, target_col] = 1.0 - (1.0 - old) * (1.0 - effective_prob)

    def transition_infested(self, threshold: float = 0.5) -> int:
        """
        Cells whose accumulated risk exceeds *threshold* transition to INFESTED.
        Returns the number of newly infested cells.
        """
        candidates = self.susceptible_mask & (self.risk >= threshold)
        n_new = int(candidates.sum())
        self.state[candidates] = CellState.INFESTED
        return n_new

    def stochastic_transition(self) -> int:
        """
        Each susceptible cell transitions to INFESTED with probability
        equal to its accumulated risk (Monte-Carlo step).
        Returns the number of newly infested cells.
        """
        susceptible = self.susceptible_mask
        rolls = np.random.random(self.state.shape)
        newly = susceptible & (rolls < self.risk)
        n_new = int(newly.sum())
        self.state[newly] = CellState.INFESTED
        return n_new

    def reset_risk(self) -> None:
        """Zero-out the risk accumulator (called after each timestep transition)."""
        self.risk[:] = 0.0

    # ── snapshot / clone ────────────────────────────────────────
    def snapshot(self) -> dict:
        """Return a lightweight dict snapshot (for time-series recording)."""
        return {
            "state": self.state.copy(),
            "risk": self.risk.copy(),
        }

    def copy(self) -> "OrchardGrid":
        g = OrchardGrid(self.rows, self.cols, self.cell_size_m)
        g.state = self.state.copy()
        g.risk = self.risk.copy()
        g.neighbor_threat = self.neighbor_threat.copy()
        g.tree_ids = self.tree_ids.copy()
        g.origin_lon = self.origin_lon
        g.origin_lat = self.origin_lat
        g.neighbor_bearing = self.neighbor_bearing
        return g

    # ── repr ────────────────────────────────────────────────────
    def __repr__(self) -> str:
        n_trees = int((self.state != CellState.EMPTY).sum())
        n_inf   = int(self.infested_mask.sum())
        return (
            f"OrchardGrid({self.rows}×{self.cols}, "
            f"trees={n_trees}, infested={n_inf})"
        )
