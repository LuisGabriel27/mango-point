"""
MangoPoint — Visualisation Module
===================================
Renders the simulation output as:

    1. Static matplotlib heatmaps (risk, state, time-series)
    2. Animated time-series of the infection wavefront
    3. Interactive Folium maps for the web dashboard

All plotting functions accept a SimulationResult or raw numpy arrays
so they can be used stand-alone.
"""

from __future__ import annotations

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from matplotlib.axes import Axes
from matplotlib.animation import FuncAnimation
from typing import Optional, List

from core.config import (
    CellState,
    STATE_COLORS,
    RISK_CMAP,
    CELL_SIZE_M,
)


# ─────────────────────────────────────────────
#  Colour maps
# ─────────────────────────────────────────────
STATE_CMAP = mcolors.ListedColormap([
    STATE_COLORS[CellState.EMPTY],
    STATE_COLORS[CellState.UNBAGGED],
    STATE_COLORS[CellState.BAGGED],
    STATE_COLORS[CellState.INFESTED],
])
STATE_NORM = mcolors.BoundaryNorm([0, 0.5, 1.5, 2.5, 3.5], STATE_CMAP.N)  # type: ignore[attr-defined]

STATE_LEGEND_HANDLES = [
    mpatches.Patch(color=STATE_COLORS[CellState.EMPTY],    label="Empty"),
    mpatches.Patch(color=STATE_COLORS[CellState.UNBAGGED], label="Unbagged"),
    mpatches.Patch(color=STATE_COLORS[CellState.BAGGED],   label="Bagged"),
    mpatches.Patch(color=STATE_COLORS[CellState.INFESTED], label="Infested"),
]


# ═══════════════════════════════════════════════
#  1. Static Plots
# ═══════════════════════════════════════════════

def plot_grid_state(
    state: np.ndarray,
    ax: Optional[Axes] = None,
    title: str = "Orchard State",
) -> Axes:
    """Show the cell-state matrix as a colour-coded image."""
    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(7, 7))
    ax.imshow(state, cmap=STATE_CMAP, norm=STATE_NORM, origin="lower")
    ax.set_title(title)
    ax.set_xlabel("Column (East →)")
    ax.set_ylabel("Row (North →)")
    ax.legend(handles=STATE_LEGEND_HANDLES, loc="upper right", fontsize=8)
    return ax


def plot_risk_heatmap(
    risk: np.ndarray,
    ax: Optional[Axes] = None,
    title: str = "Pest Risk",
    vmin: float = 0.0,
    vmax: float = 1.0,
    cmap: str = RISK_CMAP,
) -> Axes:
    """Show the risk accumulator as a heatmap."""
    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(7, 7))
    im = ax.imshow(risk, cmap=cmap, vmin=vmin, vmax=vmax, origin="lower")
    ax.set_title(title)
    ax.set_xlabel("Column (East →)")
    ax.set_ylabel("Row (North →)")
    plt.colorbar(im, ax=ax, shrink=0.7, label="Infestation probability")
    return ax


def plot_monte_carlo_risk(
    mc_risk: np.ndarray,
    state: np.ndarray,
    ax: Optional[Axes] = None,
    title: str = "48-hour Forecast — Monte Carlo Mean Risk",
    cmap: str = RISK_CMAP,
) -> Axes:
    """
    Overlay Monte Carlo mean infestation probability on the orchard layout.
    Empty cells are masked out.
    """
    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(8, 8))

    masked = np.ma.masked_where(state == CellState.EMPTY, mc_risk)
    im = ax.imshow(masked, cmap=cmap, vmin=0, vmax=1.0, origin="lower")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("Column (East →)")
    ax.set_ylabel("Row (North →)")
    plt.colorbar(im, ax=ax, shrink=0.7, label="P(infested after 48 h)")
    return ax


# ═══════════════════════════════════════════════
#  2. Time-series dashboard
# ═══════════════════════════════════════════════

def plot_simulation_dashboard(result, figsize=(16, 10)):
    """
    4-panel dashboard summarising one simulation run:
        [0] Initial state
        [1] Final state
        [2] Final risk heatmap
        [3] Infested count over time + weather overlay
    """
    fig, axs = plt.subplots(2, 2, figsize=figsize)
    fig.suptitle("MangoPoint — Simulation Dashboard", fontsize=15, fontweight="bold")

    # Panel 0 – initial state
    plot_grid_state(result.snapshots[0]["state"], ax=axs[0, 0], title="Initial State (t=0)")

    # Panel 1 – final state
    plot_grid_state(result.snapshots[-1]["state"], ax=axs[0, 1],
                    title=f"Final State (t={len(result)}h)")

    # Panel 2 – final cumulative risk
    plot_risk_heatmap(result.snapshots[-1]["risk"], ax=axs[1, 0],
                      title="Risk at Final Timestep")

    # Panel 3 – time series
    ax3 = axs[1, 1]
    steps = np.arange(len(result))
    ax3.plot(steps, result.infested_count_series, "r-o", ms=2, label="Infested cells")
    ax3.set_xlabel("Hour")
    ax3.set_ylabel("# Infested cells", color="red")
    ax3.tick_params(axis="y", labelcolor="red")
    ax3.legend(loc="upper left")

    # Weather overlay
    wind = [s["weather"]["wind_speed_ms"] for s in result.snapshots]
    temp = [s["weather"]["temperature_c"] for s in result.snapshots]
    ax3b = ax3.twinx()
    ax3b.plot(steps, temp, "b-", alpha=0.5, label="Temp (°C)")
    ax3b.plot(steps, wind, "g--", alpha=0.5, label="Wind (m/s)")
    ax3b.set_ylabel("Weather", color="blue")
    ax3b.tick_params(axis="y", labelcolor="blue")
    ax3b.legend(loc="upper right")

    ax3.set_title("Infection Progression & Weather")

    plt.tight_layout()
    return fig, axs


# ═══════════════════════════════════════════════
#  3. Multi-timestep snapshots
# ═══════════════════════════════════════════════

def plot_wavefront_snapshots(
    result,
    timesteps: Optional[List[int]] = None,
    n_panels: int = 6,
    figsize=(18, 8),
):
    """
    Show several snapshots of the risk field to visualise the
    infection wavefront advancing across the orchard.
    """
    if timesteps is None:
        total = len(result)
        timesteps = np.linspace(0, total - 1, n_panels, dtype=int).tolist()

    assert timesteps is not None
    n: int = len(timesteps)
    fig, axs = plt.subplots(1, n, figsize=figsize, sharey=True)
    fig.suptitle("Infection Wavefront — Spatiotemporal Heatmaps",
                 fontsize=14, fontweight="bold")

    im = None
    for i, t in enumerate(timesteps):  # type: ignore[arg-type]
        snap = result.snapshots[t]
        state = snap["state"]
        risk  = snap["risk"]

        masked_risk = np.ma.masked_where(state == CellState.EMPTY, risk)
        im = axs[i].imshow(masked_risk, cmap=RISK_CMAP, vmin=0, vmax=0.5,
                           origin="lower")
        dt_str = snap["datetime"].strftime("%d %b %H:%M") if hasattr(snap["datetime"], "strftime") else f"t={t}"
        axs[i].set_title(f"t={t}h\n{dt_str}", fontsize=9)
        axs[i].set_xlabel("Col")
        if i == 0:
            axs[i].set_ylabel("Row")

    if im is not None:
        cbar_ax = fig.add_axes((0.92, 0.15, 0.015, 0.7))
        fig.colorbar(im, cax=cbar_ax, label="Dispersal risk")
    plt.tight_layout(rect=(0, 0, 0.91, 0.95))
    return fig


# ═══════════════════════════════════════════════
#  4. Decision recommendation map
# ═══════════════════════════════════════════════

def plot_decision_map(
    mc_risk: np.ndarray,
    state: np.ndarray,
    monitor_thresh: float = 0.15,
    spray_thresh: float = 0.40,
    ax: Optional[Axes] = None,
    title: str = "48-hour Decision Recommendation",
):
    """
    Classify each cell into:  No action / Monitor / Bag+Spray
    based on Monte Carlo risk thresholds.
    """
    if ax is None:
        _, ax = plt.subplots(1, 1, figsize=(8, 8))

    decision = np.zeros_like(state, dtype=np.int8)
    tree_mask = state != CellState.EMPTY

    decision[tree_mask & (mc_risk < monitor_thresh)]  = 0  # no action
    decision[tree_mask & (mc_risk >= monitor_thresh) & (mc_risk < spray_thresh)] = 1  # monitor
    decision[tree_mask & (mc_risk >= spray_thresh)]    = 2  # bag + spray

    dec_cmap = mcolors.ListedColormap(["#42a5f5", "#ffa726", "#ef5350"])
    dec_norm = mcolors.BoundaryNorm([-0.5, 0.5, 1.5, 2.5], dec_cmap.N)  # type: ignore[attr-defined]

    masked = np.ma.masked_where(~tree_mask, decision)
    ax.imshow(masked, cmap=dec_cmap, norm=dec_norm, origin="lower")
    ax.set_title(title, fontsize=13, fontweight="bold")
    ax.set_xlabel("Column (East →)")
    ax.set_ylabel("Row (North →)")

    handles = [
        mpatches.Patch(color="#42a5f5", label="No action"),
        mpatches.Patch(color="#ffa726", label="Monitor"),
        mpatches.Patch(color="#ef5350", label="Bag + Spray"),
    ]
    ax.legend(handles=handles, loc="upper right")
    return ax
