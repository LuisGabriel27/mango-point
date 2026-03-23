"""
MangoPoint Dashboard — Pure-Python (Dash + Plotly + Bootstrap Icons)
=====================================================================
A single-file, self-contained dashboard for the MangoPoint system.

Start:
    cd mangopoint
    python -m dashboard.app            # → http://localhost:8050

Make sure the FastAPI backend is already running on http://localhost:8000
"""

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests
import numpy as np
import pandas as pd

import dash
from dash import html, dcc, callback_context, no_update, Patch
from dash.dependencies import Input, Output, State, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import plotly.express as px

# Ensure the parent package is importable so raster_utils resolve
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from spatial.raster_utils import load_raster_as_png_b64  # drone raster → base64
from spatial.orchard_location import ORCHARD_LAT, ORCHARD_LON

# Decision Support Layer — post-processing for management recommendations
from utils.decision_support import (
    compute_decision_metrics,
    classify_risk_zone,
    format_metrics_summary,
    DecisionZone,
    ZoneThresholds,
    get_zone_color,
    get_zone_label,
)
from core.config import (
    DECISION_ZONE_LOW_THRESHOLD,
    DECISION_ZONE_HIGH_THRESHOLD,
    DECISION_ZONE_COLORS,
    PESTICIDE_COST_PER_HECTARE,
    CELL_AREA_HECTARES,
)



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Configuration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _read_env_setting(name: str, default: str) -> str:
    """Read settings from process env first, then fall back to the project .env file."""
    value = os.getenv(name)
    if value:
        return value

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, raw_value = stripped.split("=", 1)
                if key.strip() == name:
                    return raw_value.strip().strip('"').strip("'")
        except OSError:
            pass

    return default


API_BASE = _read_env_setting("MANGOPOINT_API_BASE", "http://localhost:8000").rstrip("/")
DEFAULT_LAT = ORCHARD_LAT
DEFAULT_LON = ORCHARD_LON
MAP_STYLE = "white-bg"
SATELLITE_TILE_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

# Default orchard data
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _resolve_data_path(*names: str) -> Path:
    for name in names:
        candidate = _DATA_DIR / name
        if candidate.exists():
            return candidate
    return _DATA_DIR / names[0]


_ORCHARD_PATH = _resolve_data_path("trees.geojson", "Dummy_Mango_Data.geojson")
try:
    with open(_ORCHARD_PATH, encoding="utf-8") as _f:
        DEFAULT_ORCHARD = json.load(_f)
except FileNotFoundError:
    DEFAULT_ORCHARD = {"type": "FeatureCollection", "features": []}

SEVERITY_BADGE = {
    "critical": "danger",
    "high": "warning",
    "medium": "info",
    "low": "secondary",
}

STATE_COLORS = {
    "empty": "#cccccc",
    "unbagged": "#4caf50",
    "bagged": "#2196f3",
    "infested": "#f44336",
}

VALIDATION_PEST_LABELS = {
    "cecid": "Cecid Fly",
    "fruitfly": "Fruit Fly",
}

VALIDATION_PEST_OPTIONS = [
    {"label": "Cecid Fly (Gall Midge)", "value": "cecid"},
    {"label": "Fruit Fly (Bactrocera)", "value": "fruitfly"},
]

VALIDATION_YEAR_OPTIONS = [
    {"label": str(year), "value": year}
    for year in [2022, 2023, 2024, 2025]
]

VALIDATION_LEVEL_BADGES = {
    "Low": "success",
    "Medium": "warning",
    "High": "danger",
}

AUTH_STATE_DEFAULT = {
    "checked": False,
    "authenticated": False,
    "message": None,
    "message_color": "warning",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Drone raster overlay (loaded once at startup)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_ORTHO_PATH = _resolve_data_path("bpi_map.tif", "Map.tif")
_DTM_PATH   = _resolve_data_path("bpi_dtm.tif", "dtm.tif")

ORTHO_OVERLAY: dict | None = None
DTM_OVERLAY:   dict | None = None

try:
    ORTHO_OVERLAY = load_raster_as_png_b64(_ORTHO_PATH, max_pixels=2048)
    print(f"[GIS] Loaded orthophoto overlay ({ORTHO_OVERLAY['width']}×{ORTHO_OVERLAY['height']})")
except Exception as exc:
    print(f"[GIS] Could not load {_ORTHO_PATH}: {exc}")

try:
    DTM_OVERLAY = load_raster_as_png_b64(_DTM_PATH, max_pixels=1024)
    print(f"[GIS] Loaded DTM overlay ({DTM_OVERLAY['width']}×{DTM_OVERLAY['height']})")
except Exception as exc:
    print(f"[GIS] Could not load {_DTM_PATH}: {exc}")

# GIS tree-status colour map
GIS_STATUS_COLORS = {
    "healthy":          "#22c55e",   # green
    "infected":         "#ef4444",   # red
    "bagged":           "#3b82f6",   # blue
    # Advanced Tree Management states
    "dead":             "#424242",   # dark grey - permanently removed
    "history_infected": "#ff9800",   # orange - previously infected
    "suspect":          "#9c27b0",   # purple - flagged for monitoring
}

# All valid tree statuses for the management dropdown
TREE_STATUS_OPTIONS = [
    {"label": "Healthy", "value": "healthy"},
    {"label": "Infected", "value": "infected"},
    {"label": "Bagged (reduced risk)", "value": "bagged"},
    {"label": "Dead (removed)", "value": "dead"},
    {"label": "History Infected", "value": "history_infected"},
    {"label": "Suspect (monitoring)", "value": "suspect"},
]

# Icons for each tree status (Bootstrap icons)
TREE_STATUS_ICONS = {
    "healthy": "heart-pulse-fill",
    "infected": "virus",
    "bagged": "bag-fill",
    "dead": "x-octagon-fill",
    "history_infected": "clock-history",
    "suspect": "exclamation-triangle-fill",
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helper: Bootstrap icon shortcut
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def icon(name, extra_class=""):
    """Return a <i> element using Bootstrap Icons.  Usage: icon('thermometer-half')"""
    return html.I(className=f"bi bi-{name} {extra_class}".strip())


def _build_compass_svg_data_uri():
    """Build a polished, true-north compass SVG as a data URI."""
    svg = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 140 140">
  <defs>
    <radialGradient id="face" cx="50%" cy="45%" r="60%">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#edf2f7"/>
    </radialGradient>
    <linearGradient id="needleN" x1="0" y1="1" x2="0" y2="0">
      <stop offset="0%" stop-color="#d33131"/>
      <stop offset="100%" stop-color="#ff7b7b"/>
    </linearGradient>
    <linearGradient id="needleS" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#2f3b46"/>
      <stop offset="100%" stop-color="#5b6a78"/>
    </linearGradient>
    <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="2" stdDeviation="2" flood-color="#000000" flood-opacity="0.28"/>
    </filter>
  </defs>

  <g filter="url(#shadow)">
    <circle cx="70" cy="70" r="64" fill="url(#face)" stroke="#334155" stroke-width="1.8"/>
  </g>
  <circle cx="70" cy="70" r="55" fill="#f8fafc" stroke="#94a3b8" stroke-width="1.2"/>

  <g stroke="#64748b" stroke-width="1.2" stroke-linecap="round">
    <line x1="70" y1="18" x2="70" y2="28"/>
    <line x1="70" y1="112" x2="70" y2="122"/>
    <line x1="18" y1="70" x2="28" y2="70"/>
    <line x1="112" y1="70" x2="122" y2="70"/>
    <line x1="32" y1="32" x2="38" y2="38"/>
    <line x1="102" y1="102" x2="108" y2="108"/>
    <line x1="32" y1="108" x2="38" y2="102"/>
    <line x1="102" y1="38" x2="108" y2="32"/>
  </g>

  <g font-family="Segoe UI, Tahoma, sans-serif" font-weight="700" text-anchor="middle">
    <text x="70" y="14" font-size="11" fill="#b91c1c">N</text>
    <text x="70" y="134" font-size="10" fill="#334155">S</text>
    <text x="131" y="74" font-size="10" fill="#334155">E</text>
    <text x="9" y="74" font-size="10" fill="#334155">W</text>
  </g>

  <g>
    <polygon points="70,24 78,68 70,78 62,68" fill="url(#needleN)" stroke="#991b1b" stroke-width="1"/>
    <polygon points="70,116 78,72 70,62 62,72" fill="url(#needleS)" stroke="#1f2937" stroke-width="1"/>
    <circle cx="70" cy="70" r="7.5" fill="#ffffff" stroke="#334155" stroke-width="1.3"/>
    <circle cx="70" cy="70" r="2.6" fill="#0f172a"/>
  </g>

  <text x="70" y="88" font-family="Segoe UI, Tahoma, sans-serif" font-size="7.5" fill="#475569" text-anchor="middle" letter-spacing="0.8">TRUE NORTH</text>
</svg>
"""
    return "data:image/svg+xml;utf8," + quote(svg)


COMPASS_SVG_DATA_URI = _build_compass_svg_data_uri()


def get_cardinal_direction(degree):
    """Converts degrees to human-readable cardinal directions."""
    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = round(degree / 45) % 8
    return directions[index]


def ensure_list(value):
    """Normalize dropdown values to a list."""
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if item not in (None, "")]
    return [value]


LOSS_ESTIMATE_ASSUMPTIONS = {
    "yield_per_tree_kg": 45.0,
    "farmgate_price_php_per_kg": 60.0,
    "damage_low": 0.15,
    "damage_base": 0.30,
    "damage_high": 0.45,
}
PHENO_STAGE_COLORS = {
    "dormant": "#9e9e9e",
    "flowering": "#e91e63",
    "fruitlet": "#4caf50",
    "mature": "#ff9800",
}
PHENO_STAGE_ORDER = ["dormant", "flowering", "fruitlet", "mature"]


def _loss_assumptions_text():
    return (
        "Planning estimate only: "
        f"{LOSS_ESTIMATE_ASSUMPTIONS['yield_per_tree_kg']:.0f} kg/tree, "
        f"PHP {LOSS_ESTIMATE_ASSUMPTIONS['farmgate_price_php_per_kg']:.0f}/kg, "
        "damage: 15% / 30% / 45%"
    )


def _loss_scenario_values(infested_trees):
    """Compute low/base/high loss-at-risk scenarios in PHP."""
    try:
        infested = max(float(infested_trees), 0.0)
    except (TypeError, ValueError):
        infested = 0.0

    unit_value = (
        LOSS_ESTIMATE_ASSUMPTIONS["yield_per_tree_kg"]
        * LOSS_ESTIMATE_ASSUMPTIONS["farmgate_price_php_per_kg"]
    )
    low = infested * unit_value * LOSS_ESTIMATE_ASSUMPTIONS["damage_low"]
    base = infested * unit_value * LOSS_ESTIMATE_ASSUMPTIONS["damage_base"]
    high = infested * unit_value * LOSS_ESTIMATE_ASSUMPTIONS["damage_high"]
    return low, base, high


def _build_loss_at_risk_chart(rows, x_title):
    """Build scenario-based estimated loss-at-risk chart."""
    if not rows:
        return go.Figure()

    x_vals, infested_vals, low_vals, base_vals, high_vals = [], [], [], [], []
    for row in rows:
        x_value = row.get("x")
        infested = row.get("infested_trees", 0)
        low, base, high = _loss_scenario_values(infested)
        x_vals.append(x_value)
        infested_vals.append(int(max(float(infested or 0), 0)))
        low_vals.append(low)
        base_vals.append(base)
        high_vals.append(high)

    if not x_vals:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=low_vals,
        mode="lines",
        name="Low Scenario (15%)",
        line=dict(color="#16a34a", width=1.8),
        customdata=infested_vals,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Loss at Risk: PHP %{y:,.0f}<br>"
            "Infested Trees: %{customdata}"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=high_vals,
        mode="lines",
        name="High Scenario (45%)",
        line=dict(color="#dc2626", width=1.8),
        fill="tonexty",
        fillcolor="rgba(220, 38, 38, 0.10)",
        customdata=infested_vals,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Loss at Risk: PHP %{y:,.0f}<br>"
            "Infested Trees: %{customdata}"
            "<extra></extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=x_vals,
        y=base_vals,
        mode="lines+markers",
        name="Base Scenario (30%)",
        line=dict(color="#f59e0b", width=2.4),
        marker=dict(size=5),
        customdata=infested_vals,
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Loss at Risk: PHP %{y:,.0f}<br>"
            "Infested Trees: %{customdata}"
            "<extra></extra>"
        ),
    ))

    fig.update_layout(
        margin=dict(l=20, r=20, t=34, b=42),
        height=260,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(title=x_title, title_standoff=8, gridcolor="#eee"),
        yaxis=dict(title="Estimated Loss at Risk (PHP)", gridcolor="#eee", tickprefix="PHP "),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0),
    )
    return fig


def _build_phenology_figure(pheno_rows):
    """
    Build phenology donut chart.
    - Keeps all stages in legend for consistency.
    - Avoids overlapping labels by hiding text on zero-count slices.
    - Uses center annotation for single-stage 100% cases.
    """
    if not pheno_rows:
        return go.Figure()

    df_pheno = pd.DataFrame(pheno_rows)
    if df_pheno.empty or "stage" not in df_pheno.columns or "count" not in df_pheno.columns:
        return go.Figure()

    df_pheno["stage"] = df_pheno["stage"].astype(str).str.lower()
    df_pheno["count"] = pd.to_numeric(df_pheno["count"], errors="coerce").fillna(0.0)

    # Keep all canonical stages even when count is zero (legend remains stable).
    df_pheno = (
        df_pheno.groupby("stage", as_index=False)["count"].sum()
        .set_index("stage")
        .reindex(PHENO_STAGE_ORDER, fill_value=0.0)
        .reset_index()
    )

    total_count = float(df_pheno["count"].sum())
    if total_count <= 0:
        return go.Figure()

    df_pheno["stage"] = pd.Categorical(
        df_pheno["stage"],
        categories=PHENO_STAGE_ORDER,
        ordered=True,
    )
    df_pheno = df_pheno.sort_values("stage")

    fig_pheno = px.pie(
        df_pheno,
        values="count",
        names="stage",
        color="stage",
        color_discrete_map=PHENO_STAGE_COLORS,
        hole=0.4,
    )
    fig_pheno.update_layout(
        margin=dict(l=10, r=10, t=10, b=18),
        height=240,
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=-0.12, xanchor="center", x=0.5),
    )

    positive = df_pheno[df_pheno["count"] > 0]
    if len(positive) == 1:
        only_stage = str(positive.iloc[0]["stage"]).strip()
        fig_pheno.update_traces(textinfo="none", textposition="none")
        fig_pheno.add_annotation(
            text=f"{only_stage}<br>100%",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font=dict(size=16, color="#1f2937"),
            align="center",
        )
    else:
        labels = []
        for _, row in df_pheno.iterrows():
            count = float(row["count"])
            if count <= 0:
                labels.append("")
            else:
                pct = (count / total_count) * 100.0
                labels.append(f"{row['stage']}<br>{pct:.0f}%")
        fig_pheno.update_traces(
            text=labels,
            textinfo="text",
            textposition="outside",
        )

    return fig_pheno


_TREE_ID_DIGITS_RE = re.compile(r"^(?:tree[_\-\s]*)?t?0*(\d+)$", re.IGNORECASE)


def normalize_tree_id_input(value):
    """Accept common dashboard tree ID formats and normalize them for API requests."""
    if value is None:
        return None
    text = str(value).strip().replace("#", "")
    if not text:
        return None
    match = _TREE_ID_DIGITS_RE.fullmatch(text)
    if match:
        return str(int(match.group(1)))
    return text


def _get_tree_property(props, *names, default=None):
    for name in names:
        value = props.get(name)
        if value not in (None, ""):
            return value
    return default


def _normalize_tree_status(value, default="healthy"):
    normalized = str(value or default).strip().lower()
    status_map = {
        "healthy": "healthy",
        "unbagged": "healthy",
        "infected": "infected",
        "infested": "infected",
        "bagged": "bagged",
        "dead": "dead",
        "history_infected": "history_infected",
        "suspect": "suspect",
        "empty": default,
    }
    return status_map.get(normalized, default)


def _get_tree_id(props):
    value = _get_tree_property(props, "tree_id", "Tree_ID", "fid", default=0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _get_tree_crown_width(props):
    value = _get_tree_property(props, "crown_size", "Crown_Width", default=5.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 5.0


def _get_tree_elevation(props):
    value = _get_tree_property(props, "elevation", "Elev_1", default=0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_tree_status(props):
    return _normalize_tree_status(_get_tree_property(props, "status", "Status", default="healthy"))


def _mercator_lat(lat):
    clamped = max(min(float(lat), 89.9), -89.9)
    return np.log(np.tan(np.pi / 4.0 + np.radians(clamped) / 2.0))


def _compute_map_view(lons=None, lats=None, bounds=None, width_px=1200, height_px=720, padding=1.08, fallback_zoom=17.6):
    if bounds is None:
        if not lons or not lats:
            return DEFAULT_LAT, DEFAULT_LON, fallback_zoom
        bounds = (min(lons), min(lats), max(lons), max(lats))

    west, south, east, north = [float(value) for value in bounds]
    center_lat = (south + north) / 2.0
    center_lon = (west + east) / 2.0

    lon_span = max(abs(east - west) * padding, 1e-6)
    lat_fraction = abs(_mercator_lat(north) - _mercator_lat(south)) / (2.0 * np.pi)
    lat_fraction = max(lat_fraction * padding, 1e-6)

    zoom_lon = np.log2(width_px * 360.0 / (lon_span * 512.0))
    zoom_lat = np.log2(height_px / (lat_fraction * 512.0))
    zoom = float(np.clip(min(zoom_lon, zoom_lat), 0.0, 20.0))
    return center_lat, center_lon, zoom


def validation_pest_label(pest_type):
    """Return a presentation-friendly pest label."""
    return VALIDATION_PEST_LABELS.get(pest_type, str(pest_type).replace("_", " ").title())


def validation_level_badge(level):
    """Return a colored risk-level badge."""
    return dbc.Badge(
        str(level or "Unknown"),
        color=VALIDATION_LEVEL_BADGES.get(level, "secondary"),
        pill=True,
    )


def validation_match_badge(match):
    """Return a match / mismatch badge."""
    return dbc.Badge(
        "Match" if match else "Mismatch",
        color="success" if match else "danger",
        pill=True,
    )


def format_validation_rate(value, digits=1):
    """Format a 0-1 metric value as a percentage string."""
    if value is None:
        return "-"
    return f"{float(value) * 100:.{digits}f}%"


def format_validation_scalar(value, digits=3):
    """Format a scalar metric for dashboard display."""
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


def make_validation_metric_card(title, value_text, note, color="success"):
    """Small KPI card used in the historical validation section."""
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Small(title, className=f"text-{color} text-uppercase fw-semibold d-block mb-1"),
                    html.H4(value_text, className="mb-1 fw-bold"),
                    html.P(note, className="text-muted small mb-0"),
                ],
                className="py-3",
            ),
            className="shadow-sm border-0 h-100",
        ),
        xs=12,
        sm=6,
        lg=4,
        xl=3,
        className="mb-2",
    )


def make_validation_empty_figure(message):
    """Create a consistent empty-state chart for validation panels."""
    fig = go.Figure()
    fig.update_layout(
        margin=dict(l=20, r=20, t=40, b=40),
        height=300,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        annotations=[
            dict(
                text=message,
                x=0.5,
                y=0.5,
                xref="paper",
                yref="paper",
                showarrow=False,
                font=dict(size=14, color="#7c7c7c"),
            )
        ],
    )
    return fig


def format_actual_value(actual_value, pest_type):
    """Format the historical value with a pest-specific unit."""
    if actual_value is None:
        return "-"
    unit = "%" if pest_type == "cecid" else "CPTD"
    return f"{float(actual_value):.2f} {unit}"


def build_case_preview_table(cases, table_id=None, limit=6):
    """Build a compact preview table for historical validation cases."""
    if not cases:
        return dbc.Alert(
            [icon("info-circle", "me-2"), "No historical validation cases match the current filters."],
            color="light",
            className="mb-0 py-2",
        )

    ordered_cases = sorted(
        cases,
        key=lambda item: (item.get("date", ""), item.get("case_id", "")),
        reverse=True,
    )[:limit]

    table_kwargs = {
        "bordered": True,
        "hover": True,
        "responsive": True,
        "size": "sm",
        "className": "mb-0 align-middle",
    }
    if table_id:
        table_kwargs["id"] = table_id

    table = dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Case ID"),
                        html.Th("Date"),
                        html.Th("Pest"),
                        html.Th("Stage"),
                        html.Th("Actual Level"),
                    ]
                ),
                className="table-light",
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(item.get("case_id", "-"), className="fw-semibold"),
                            html.Td(item.get("date", "-")),
                            html.Td(validation_pest_label(item.get("pest_type"))),
                            html.Td(str(item.get("orchard_stage", "-")).title()),
                            html.Td(validation_level_badge(item.get("actual_level"))),
                        ]
                    )
                    for item in ordered_cases
                ]
            ),
        ],
        **table_kwargs,
    )
    return html.Div(table, style={"maxHeight": "260px", "overflowY": "auto"})


def build_validation_results_table(results):
    """Build the historical validation results table."""
    if not results:
        return dbc.Alert(
            [icon("info-circle", "me-2"), "Run historical validation to populate the results table."],
            color="light",
            className="mb-0 py-2",
        )

    ordered_results = sorted(
        results,
        key=lambda item: (item.get("date", ""), item.get("case_id", "")),
        reverse=True,
    )

    table = dbc.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Case ID"),
                        html.Th("Date"),
                        html.Th("Pest Type"),
                        html.Th("Actual Level"),
                        html.Th("Predicted Level"),
                        html.Th("Actual Value"),
                        html.Th("Predicted Risk"),
                        html.Th("Outcome"),
                    ]
                ),
                className="table-light",
            ),
            html.Tbody(
                [
                    html.Tr(
                        [
                            html.Td(item.get("case_id", "-"), className="fw-semibold"),
                            html.Td(item.get("date", "-")),
                            html.Td(validation_pest_label(item.get("pest_type"))),
                            html.Td(validation_level_badge(item.get("actual_level"))),
                            html.Td(validation_level_badge(item.get("predicted_level"))),
                            html.Td(format_actual_value(item.get("actual_value"), item.get("pest_type"))),
                            html.Td(format_validation_rate(item.get("predicted_risk"), digits=1)),
                            html.Td(validation_match_badge(bool(item.get("match")))),
                        ]
                    )
                    for item in ordered_results
                ]
            ),
        ],
        bordered=True,
        hover=True,
        responsive=True,
        size="sm",
        className="mb-0 align-middle",
    )

    return html.Div(table, style={"maxHeight": "420px", "overflowY": "auto"})


def build_validation_metric_chart(validation_data):
    """Bar chart summarizing historical validation score metrics."""
    if not validation_data:
        return make_validation_empty_figure("Historical validation metrics will appear here after a run.")

    summary = validation_data.get("summary", {})
    cls_metrics = validation_data.get("classification_metrics", {})
    reg_metrics = validation_data.get("regression_metrics", {})

    chart_rows = [
        ("Overall Accuracy", summary.get("overall_accuracy_pct", 0.0)),
        ("Precision", float(cls_metrics.get("precision", 0.0)) * 100),
        ("Recall", float(cls_metrics.get("recall", 0.0)) * 100),
        ("F1-Score", float(cls_metrics.get("f1_score", 0.0)) * 100),
        ("Specificity", float(cls_metrics.get("specificity", 0.0)) * 100),
        ("R-squared", float(reg_metrics.get("r_squared", 0.0)) * 100),
    ]

    df_metrics = pd.DataFrame(chart_rows, columns=["Metric", "Value"])
    fig = px.bar(
        df_metrics,
        x="Metric",
        y="Value",
        text="Value",
        color="Metric",
        color_discrete_sequence=["#2e7d32", "#558b2f", "#ef6c00", "#1565c0", "#6a1b9a", "#455a64"],
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside", hovertemplate="%{x}: %{y:.1f}%<extra></extra>")
    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        yaxis_title="Score (%)",
        xaxis_title=None,
        yaxis=dict(gridcolor="#ececec"),
    )
    return fig


def build_validation_match_chart(results):
    """Stacked bar chart showing match and mismatch counts by pest type."""
    if not results:
        return make_validation_empty_figure("Match and mismatch counts will appear after historical validation runs.")

    df_results = pd.DataFrame(results)
    if df_results.empty:
        return make_validation_empty_figure("No historical validation results are available for charting.")

    df_results["Outcome"] = np.where(df_results["match"], "Match", "Mismatch")
    df_results["Pest Label"] = df_results["pest_type"].map(validation_pest_label)
    grouped = (
        df_results.groupby(["Pest Label", "Outcome"])
        .size()
        .reset_index(name="Cases")
    )

    fig = px.bar(
        grouped,
        x="Pest Label",
        y="Cases",
        color="Outcome",
        barmode="stack",
        text="Cases",
        color_discrete_map={"Match": "#2e7d32", "Mismatch": "#c62828"},
    )
    fig.update_traces(textposition="inside", hovertemplate="%{x}<br>%{fullData.name}: %{y}<extra></extra>")
    fig.update_layout(
        height=320,
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title=None,
        xaxis_title=None,
        yaxis_title="Historical Cases",
        yaxis=dict(gridcolor="#ececec"),
    )
    return fig


def build_validation_comparison_chart(results):
    """Scatter chart comparing normalized historical values and predicted risk."""
    if not results:
        return make_validation_empty_figure("Normalized historical vs predicted comparison will appear after validation.")

    df_results = pd.DataFrame(results)
    if df_results.empty or "actual_normalized" not in df_results.columns:
        return make_validation_empty_figure("Normalized comparison data is unavailable for the selected validation run.")

    fig = px.scatter(
        df_results,
        x="actual_normalized",
        y="predicted_risk",
        color="pest_type",
        symbol="match",
        hover_name="case_id",
        hover_data={
            "date": True,
            "actual_level": True,
            "predicted_level": True,
            "actual_normalized": ":.3f",
            "predicted_risk": ":.3f",
            "pest_type": False,
            "match": False,
        },
        color_discrete_map={"cecid": "#ef6c00", "fruitfly": "#1565c0"},
        labels={
            "actual_normalized": "Actual Historical Value (normalized)",
            "predicted_risk": "Predicted Risk",
            "pest_type": "Pest Type",
        },
    )
    fig.add_trace(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            name="Ideal Alignment",
            line=dict(color="#546e7a", width=2, dash="dash"),
            hoverinfo="skip",
        )
    )
    fig.for_each_trace(
        lambda trace: trace.update(name=validation_pest_label(trace.name))
        if trace.name in VALIDATION_PEST_LABELS else None
    )
    fig.update_layout(
        height=340,
        margin=dict(l=20, r=20, t=40, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title=None,
        xaxis=dict(range=[0, 1], gridcolor="#ececec"),
        yaxis=dict(range=[0, 1], gridcolor="#ececec"),
    )
    return fig


def build_validation_dataset_summary(summary_data, cases_data):
    """Build the historical dataset summary card body."""
    if not summary_data:
        return dbc.Alert(
            [icon("wifi-off", "me-2"), "Historical validation metadata is unavailable. Check whether the API is running."],
            color="warning",
            className="mb-0 py-2",
        )

    preview_cases = []
    preview_total = 0
    preview_error = None
    if isinstance(cases_data, dict):
        preview_cases = cases_data.get("cases", []) or []
        preview_total = cases_data.get("total_cases", 0) or 0
        preview_error = cases_data.get("error")

    year_badges = [
        dbc.Badge(str(year), color="secondary", pill=True, className="me-1")
        for year in summary_data.get("years", [])
    ]
    fruit_distribution = summary_data.get("fruit_fly_risk_distribution", {})
    cecid_distribution = summary_data.get("cecid_fly_risk_distribution", {})

    overview_cards = dbc.Row(
        [
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Historical Records", className="text-muted d-block"),
                            html.H5(str(summary_data.get("n_records", 0)), className="mb-0 fw-bold"),
                        ],
                        className="py-2",
                    ),
                    className="border-0 bg-light h-100",
                ),
                sm=6,
                xl=3,
                className="mb-2",
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Data Period", className="text-muted d-block"),
                            html.H5(summary_data.get("year_range", "-"), className="mb-0 fw-bold"),
                        ],
                        className="py-2",
                    ),
                    className="border-0 bg-light h-100",
                ),
                sm=6,
                xl=3,
                className="mb-2",
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Fruit Fly Cases", className="text-muted d-block"),
                            html.H5(str(summary_data.get("fruit_fly_relevant_records", 0)), className="mb-0 fw-bold"),
                        ],
                        className="py-2",
                    ),
                    className="border-0 bg-light h-100",
                ),
                sm=6,
                xl=3,
                className="mb-2",
            ),
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        [
                            html.Small("Cecid Fly Cases", className="text-muted d-block"),
                            html.H5(str(summary_data.get("cecid_fly_relevant_records", 0)), className="mb-0 fw-bold"),
                        ],
                        className="py-2",
                    ),
                    className="border-0 bg-light h-100",
                ),
                sm=6,
                xl=3,
                className="mb-2",
            ),
        ],
        className="g-2 mb-2",
    )

    preview_note = (
        dbc.Alert(
            [icon("info-circle", "me-2"), preview_error],
            color="warning",
            className="py-2 mb-2",
        )
        if preview_error else
        html.Small(
            f"Previewing {preview_total} eligible historical validation case(s) under the current filters.",
            className="text-muted d-block mb-2",
        )
    )

    return html.Div(
        [
            html.P(
                "Source: BPI Guimaras pest monitoring records. The preview below shows real historical cases that can be "
                "used for validation and presentation.",
                className="text-muted small mb-3",
            ),
            overview_cards,
            html.Div(
                [
                    html.Small("Years covered:", className="text-muted me-2"),
                    *year_badges,
                ],
                className="mb-2",
            ),
            html.Div(
                [
                    html.Small("Fruit Fly risk distribution:", className="text-muted me-2"),
                    dbc.Badge(f"Low {fruit_distribution.get('Low', 0)}", color="success", className="me-1"),
                    dbc.Badge(f"Medium {fruit_distribution.get('Medium', 0)}", color="warning", className="me-1"),
                    dbc.Badge(f"High {fruit_distribution.get('High', 0)}", color="danger"),
                ],
                className="mb-2",
            ),
            html.Div(
                [
                    html.Small("Cecid Fly risk distribution:", className="text-muted me-2"),
                    dbc.Badge(f"Low {cecid_distribution.get('Low', 0)}", color="success", className="me-1"),
                    dbc.Badge(f"Medium {cecid_distribution.get('Medium', 0)}", color="warning", className="me-1"),
                    dbc.Badge(f"High {cecid_distribution.get('High', 0)}", color="danger"),
                ],
                className="mb-3",
            ),
            html.Div(
                [
                    html.Div(
                        [
                            icon("table", "me-2"),
                            html.Span("Eligible Historical Case Preview", className="fw-semibold"),
                        ],
                        className="d-flex align-items-center mb-2",
                    ),
                    preview_note,
                    build_case_preview_table(preview_cases, limit=6),
                ]
            ),
        ]
    )


def build_pest_metric_card(title, metrics_data, accent):
    """Build a pest-specific validation metric card."""
    if not metrics_data:
        return dbc.Card(
            dbc.CardBody(
                [
                    html.H6(title, className="fw-semibold"),
                    html.P("No historical cases are available for this pest under the current filters.", className="text-muted small mb-0"),
                ],
                className="py-3",
            ),
            className="shadow-sm border-0 h-100",
        )

    rows = [
        ("Sample Count", str(metrics_data.get("n_samples", 0))),
        ("Accuracy", format_validation_rate(metrics_data.get("accuracy"))),
        ("Precision", format_validation_rate(metrics_data.get("precision"))),
        ("Recall", format_validation_rate(metrics_data.get("recall"))),
        ("F1-Score", format_validation_rate(metrics_data.get("f1_score"))),
        ("Specificity", format_validation_rate(metrics_data.get("specificity"))),
    ]

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Span(title, className="fw-semibold"),
                        dbc.Badge(f"{metrics_data.get('n_samples', 0)} cases", color=accent, pill=True),
                    ],
                    className="d-flex justify-content-between align-items-center",
                ),
                className="py-2",
            ),
            dbc.CardBody(
                dbc.Table(
                    [
                        html.Tbody(
                            [
                                html.Tr([html.Td(label, className="text-muted"), html.Td(value, className="fw-semibold text-end")])
                                for label, value in rows
                            ]
                        )
                    ],
                    borderless=True,
                    size="sm",
                    className="mb-2",
                ),
                className="py-2",
            ),
            dbc.CardFooter(
                html.Small(
                    "Use these pest-specific metrics to discuss where historical agreement is stronger or weaker across pest types.",
                    className="text-muted",
                ),
                className="bg-white border-0 pt-0",
            ),
        ],
        className="shadow-sm border-0 h-100",
    )


def build_confusion_matrix_panel(confusion_matrix):
    """Build the confusion-matrix summary panel."""
    confusion_matrix = confusion_matrix or {}
    tn = confusion_matrix.get("true_negatives", 0)
    fp = confusion_matrix.get("false_positives", 0)
    fn = confusion_matrix.get("false_negatives", 0)
    tp = confusion_matrix.get("true_positives", 0)

    def _mini_matrix_card(title, value, note, color):
        return dbc.Col(
            dbc.Card(
                dbc.CardBody(
                    [
                        html.Small(title, className=f"text-{color} text-uppercase fw-semibold d-block mb-1"),
                        html.H5(str(value), className="mb-1 fw-bold"),
                        html.P(note, className="text-muted small mb-0"),
                    ],
                    className="py-2",
                ),
                className="border-0 bg-light h-100",
            ),
            md=6,
            className="mb-2",
        )

    mini_cards = dbc.Row(
        [
            _mini_matrix_card("True Positives", tp, "Detected historical high-risk periods.", "success"),
            _mini_matrix_card("False Positives", fp, "Alerts raised when historical records were not high risk.", "warning"),
            _mini_matrix_card("False Negatives", fn, "Missed outbreaks; these are the most critical errors for early warning.", "danger"),
            _mini_matrix_card("True Negatives", tn, "Lower-risk periods correctly recognized as non-outbreak cases.", "secondary"),
        ],
        className="g-2",
    )

    matrix_table = dbc.Table(
        [
            html.Thead(
                html.Tr([html.Th("Historical"), html.Th("Predicted Low/Medium"), html.Th("Predicted High")]),
                className="table-light",
            ),
            html.Tbody(
                [
                    html.Tr([html.Th("Actual Low/Medium"), html.Td(str(tn)), html.Td(str(fp))]),
                    html.Tr([html.Th("Actual High"), html.Td(str(fn)), html.Td(str(tp))]),
                ]
            ),
        ],
        bordered=True,
        size="sm",
        className="mb-2",
    )

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [icon("grid-3x3-gap", "me-2"), html.Span("Confusion Matrix", className="fw-semibold")],
                    className="d-flex align-items-center",
                ),
                className="py-2",
            ),
            dbc.CardBody(
                [
                    mini_cards,
                    matrix_table,
                    html.Small(
                        "False negatives are especially critical because they represent missed outbreaks that could delay intervention decisions.",
                        className="text-danger",
                    ),
                ],
                className="py-2",
            ),
        ],
        className="shadow-sm border-0 h-100",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers — API calls
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def default_auth_state():
    """Return a fresh default auth state payload."""
    return dict(AUTH_STATE_DEFAULT)


def build_auth_state(checked=False, authenticated=False, message=None, message_color="warning"):
    """Create a serializable auth state payload for Dash stores."""
    return {
        "checked": checked,
        "authenticated": authenticated,
        "message": message,
        "message_color": message_color,
    }


def extract_access_token(auth_session):
    """Safely read the bearer token from the session store."""
    if not isinstance(auth_session, dict):
        return None
    token = auth_session.get("access_token")
    return token if isinstance(token, str) and token.strip() else None


def is_authenticated_session(auth_session, auth_state):
    """Return True when both the auth state and session token are valid."""
    return bool(
        isinstance(auth_state, dict)
        and auth_state.get("authenticated")
        and extract_access_token(auth_session)
    )


def api_request(method, path, *, token=None, params=None, json_body=None, timeout=60):
    """Call the FastAPI backend and return a structured response."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.request(
            method=method.upper(),
            url=f"{API_BASE}{path}",
            params=params,
            json=json_body,
            headers=headers,
            timeout=timeout,
        )
    except requests.RequestException as exc:
        print(f"[API {method.upper()} {path}] {exc}")
        return {
            "ok": False,
            "status_code": None,
            "data": None,
            "error": f"Unable to reach the API at {API_BASE}.",
        }

    payload = None
    if response.content:
        try:
            payload = response.json()
        except ValueError:
            payload = None

    if response.ok:
        return {
            "ok": True,
            "status_code": response.status_code,
            "data": payload,
            "error": None,
        }

    error_message = None
    if isinstance(payload, dict):
        error_message = payload.get("detail") or payload.get("message")
    if not error_message:
        error_message = f"Request failed with status {response.status_code}."

    print(f"[API {method.upper()} {path}] {response.status_code}: {error_message}")
    return {
        "ok": False,
        "status_code": response.status_code,
        "data": payload,
        "error": error_message,
    }


def api_get(path, *, token=None, params=None, timeout=60):
    """Structured GET wrapper for the backend API."""
    return api_request("GET", path, token=token, params=params, timeout=timeout)


def api_post(path, json_body=None, *, token=None, timeout=120):
    """Structured POST wrapper for the backend API."""
    return api_request("POST", path, token=token, json_body=json_body, timeout=timeout)


def auth_error_message(response, fallback_message):
    """Map API failures to concise auth-aware dashboard messages."""
    if not isinstance(response, dict):
        return fallback_message
    if response.get("status_code") == 404:
        return "Authentication endpoint not found. Restart the FastAPI backend after installing the new auth dependencies."
    if response.get("status_code") == 401:
        return "Session expired. Sign in again."
    return response.get("error") or fallback_message


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Map figure builder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def build_risk_map(geojson=None, alerts=None, title="Pest Risk Heatmap", show_heatmap_layer=False, tree_overrides=None):
    """Build a Plotly Mapbox scatter plot coloured by risk, with optional density heatmap layer.
    
    Parameters
    ----------
    tree_overrides : dict, optional
        Dict mapping tree_id (str) -> status (str) for manual status overrides.
        These affect the marker colors on the map.
    """
    fig = go.Figure()
    tree_overrides = tree_overrides or {}

    lons, lats, risks = [], [], []
    texts = []
    customdata = []  # For tree management modal
    
    if geojson and "features" in geojson and len(geojson["features"]) > 0:
        for feat in geojson["features"]:
            props = feat.get("properties", {})
            geom_type = feat["geometry"]["type"]
            if geom_type == "Point":
                clon, clat = feat["geometry"]["coordinates"][:2]
            else:
                coords = feat["geometry"]["coordinates"][0]
                clon = np.mean([c[0] for c in coords])
                clat = np.mean([c[1] for c in coords])
            risk = props.get("risk", 0)
            state = props.get("state", "empty")
            normalized_state = _normalize_tree_status(state)
            lons.append(clon)
            lats.append(clat)
            risks.append(risk)
            texts.append(
                f"<b>({props.get('row')}, {props.get('col')})</b><br>"
                f"State: {state}<br>"
                f"Risk: {risk:.0%}<br>"
                f"Risk: {risk:.0%}<br>"
                f"Tree: {props.get('tree_id') or '—'}"
            )
            # Add custom data for tree management modal
            customdata.append({
                "tree_id": props.get("tree_id", props.get("row", 0) * 1000 + props.get("col", 0)),
                "row": props.get("row", 0),
                "col": props.get("col", 0),
                "status": normalized_state,
                "risk": risk,
                "lon": clon,
                "lat": clat,
            })

        # Add density heatmap layer (thermal spread visualization)
        if show_heatmap_layer and len(lons) >= 3:
            fig.add_trace(
                go.Densitymap(
                    lon=lons,
                    lat=lats,
                    z=risks,
                    radius=50,
                    colorscale=[
                        [0.0, "rgba(34,197,94,0.0)"],      # Transparent - No risk
                        [0.15, "rgba(34,197,94,0.4)"],     # Green - Healthy/Low
                        [0.3, "rgba(250,204,21,0.5)"],     # Yellow - Low-Moderate
                        [0.5, "rgba(251,146,60,0.6)"],     # Orange - Moderate
                        [0.7, "rgba(239,68,68,0.7)"],      # Red - High
                        [0.85, "rgba(220,38,38,0.8)"],     # Dark red - Severe
                        [1.0, "rgba(127,29,29,0.9)"],      # Deep red - Critical
                    ],
                    zmin=0,
                    zmax=1,
                    showscale=True,
                    colorbar=dict(
                        title=dict(text="Risk Level", font=dict(size=12)),
                        tickvals=[0, 0.25, 0.5, 0.75, 1.0],
                        ticktext=["Low", "Moderate", "High", "Severe", "Critical"],
                        tickformat=".0%",
                        thickness=15,
                        len=0.4,
                        x=0.99,
                        bgcolor="rgba(255,255,255,0.8)",
                        bordercolor="#ccc",
                        borderwidth=1,
                    ),
                    hoverinfo="skip",
                    name="Risk Heatmap",
                )
            )

        # Add scatter markers on top
        fig.add_trace(
            go.Scattermap(
                lon=lons,
                lat=lats,
                mode="markers",
                marker=dict(
                    size=10 if show_heatmap_layer else 14,
                    color=risks,
                    colorscale="YlOrRd",
                    cmin=0,
                    cmax=1,
                    colorbar=dict(
                        title="Risk",
                        tickformat=".0%",
                        thickness=12,
                        len=0.6,
                    ) if not show_heatmap_layer else None,
                    showscale=not show_heatmap_layer,
                    opacity=0.9 if show_heatmap_layer else 0.85,
                ),
                text=texts,
                hoverinfo="text",
                customdata=customdata,  # For tree management modal
                name="Trees",
            )
        )
        if ORTHO_OVERLAY and ORTHO_OVERLAY.get("bounds"):
            center_lat, center_lon, zoom = _compute_map_view(bounds=ORTHO_OVERLAY["bounds"])
        else:
            center_lat, center_lon, zoom = _compute_map_view(lons=lons, lats=lats)
    else:
        if ORTHO_OVERLAY and ORTHO_OVERLAY.get("bounds"):
            center_lat, center_lon, zoom = _compute_map_view(bounds=ORTHO_OVERLAY["bounds"])
        else:
            center_lat, center_lon, zoom = DEFAULT_LAT, DEFAULT_LON, 17.6

        # Load tree locations from default orchard so the map always shows
        # real tree markers (and, critically, forces Plotly to render a
        # Mapbox map instead of a blank cartesian figure).
        tree_lons, tree_lats, tree_texts, tree_customdata, tree_colors = [], [], [], [], []
        for feat in DEFAULT_ORCHARD.get("features", []):
            p = feat.get("properties", {})
            c = feat["geometry"]["coordinates"]
            tree_id = _get_tree_id(p)
            crown_width = _get_tree_crown_width(p)
            elevation = _get_tree_elevation(p)
            
            # Check for status override, otherwise use original status
            original_status = _get_tree_status(p)
            status = tree_overrides.get(str(tree_id), original_status)
            
            tree_lons.append(c[0])
            tree_lats.append(c[1])
            tree_texts.append(
                f"<b>Tree {tree_id}</b><br>"
                f"Status: {status.replace('_', ' ').title()}<br>"
                f"Crown: {crown_width:.1f} m"
            )
            # Add custom data for tree management modal
            tree_customdata.append({
                "tree_id": tree_id,
                "status": status,
                "crown_width": crown_width,
                "elevation": elevation,
                "lon": c[0],
                "lat": c[1],
            })
            # Color based on current status
            tree_colors.append(GIS_STATUS_COLORS.get(status, "#4caf50"))
            
        if tree_lons:
            if not (ORTHO_OVERLAY and ORTHO_OVERLAY.get("bounds")):
                center_lat, center_lon, zoom = _compute_map_view(lons=tree_lons, lats=tree_lats)
            fig.add_trace(
                go.Scattermap(
                    lon=tree_lons, lat=tree_lats, mode="markers",
                    marker=dict(size=14, color=tree_colors, opacity=0.9),
                    text=tree_texts, hoverinfo="text",
                    name="Trees",
                    customdata=tree_customdata,  # For tree management modal
                )
            )
        else:
            # Fallback: add an invisible anchor point so mapbox renders
            fig.add_trace(
                go.Scattermap(
                    lon=[center_lon], lat=[center_lat], mode="markers",
                    marker=dict(size=1, opacity=0),
                    hoverinfo="skip", showlegend=False,
                )
            )

    # Alert markers
    if alerts:
        for a in alerts:
            clat = a.get("centroid_lat")
            clon = a.get("centroid_lon")
            if clat and clon:
                sev = a.get("severity", "medium")
                cmap = {"critical": "red", "high": "orange", "medium": "gold", "low": "grey"}
                fig.add_trace(
                    go.Scattermap(
                        lon=[clon], lat=[clat], mode="markers",
                        marker=dict(size=22, color=cmap.get(sev, "gold"), symbol="circle"),
                        text=f"Alert: {a.get('message', '')}", hoverinfo="text",
                        name="Alert", showlegend=False,
                    )
                )

    # --- satellite basemap under the orchard overlay and simulation traces ---
    mapbox_layers = [{
        "sourcetype": "raster",
        "source": [SATELLITE_TILE_URL],
        "below": "traces",
        "opacity": 1.0,
    }]
    if ORTHO_OVERLAY:
        mapbox_layers.append({
            "sourcetype": "image",
            "source": ORTHO_OVERLAY["b64"],
            "coordinates": ORTHO_OVERLAY["coordinates"],
            "below": "traces",
            "opacity": 0.92,
        })

    fig.update_layout(
        map=dict(
            style=MAP_STYLE,
            center=dict(lat=center_lat, lon=center_lon),
            zoom=zoom,
            bearing=0,
            layers=mapbox_layers,
        ),
        margin=dict(l=0, r=0, t=32, b=0),
        title=dict(text=title, x=0.5, font=dict(size=14)),
        height=720,
        paper_bgcolor="rgba(0,0,0,0)",
        dragmode="pan",  # Allow pan for click interaction
        clickmode="event+select",  # Enable click events on markers
    )
    return fig





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layout — component builders
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _sidebar_panel_toggle_title(is_open):
    return "Collapse panel" if is_open else "Expand panel"


def _sidebar_panel_toggle_children(is_open):
    label = _sidebar_panel_toggle_title(is_open)
    return [icon("chevron-up" if is_open else "chevron-down"), html.Span(label, className="visually-hidden")]


def _card(
    header_icon,
    header_text,
    body,
    card_cls="mb-3 shadow-sm panel-card",
    *,
    header_extra=None,
    collapsible=False,
    panel_id=None,
    collapsed=False,
    header_class_name="py-2",
    card_style=None,
):
    """Standard card wrapper with optional collapsible body for sidebar panels."""
    header_children = [icon(header_icon, "me-2"), html.Span(header_text, className="fw-semibold")]
    if header_extra is not None:
        if isinstance(header_extra, (list, tuple)):
            header_children.extend(header_extra)
        else:
            header_children.append(header_extra)

    body_component = dbc.CardBody(body, className="py-2 px-3")
    header_controls = []

    if collapsible:
        if not panel_id:
            raise ValueError("A panel_id is required when collapsible=True.")

        is_open = not collapsed
        body_component = dbc.Collapse(
            body_component,
            id={"type": "sidebar-panel-collapse", "panel": panel_id},
            is_open=is_open,
        )
        header_controls.append(
            dbc.Button(
                _sidebar_panel_toggle_children(is_open),
                id={"type": "sidebar-panel-toggle", "panel": panel_id},
                color="link",
                className="sidebar-panel-toggle",
                title=_sidebar_panel_toggle_title(is_open),
                n_clicks=0,
            )
        )
        card_cls = f"{card_cls} sidebar-panel-card".strip()

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Div(header_children, className="d-flex align-items-center flex-wrap gap-2"),
                        *header_controls,
                    ],
                    className="d-flex align-items-center justify-content-between gap-2 w-100",
                ),
                className=header_class_name,
            ),
            body_component,
        ],
        className=card_cls,
        style=card_style,
    )


def make_weather_card():
    body = [
        dbc.Spinner(html.Div(id="weather-content", children="Waiting for data…"), size="sm"),
        html.Small(
            [icon("arrow-repeat", "me-1"), "Auto-refreshes every 60 s"],
            className="text-muted mt-2 d-block",
        ),
    ]
    return _card("cloud-sun", "Live Weather", body, collapsible=True, panel_id="weather")


def make_sim_controls():
    body = [
        # Pest type selector
        dbc.Label([icon("bug", "me-1"), " Pest type"], className="fw-medium mb-1"),
        dbc.Select(
            id="pest-type",
            options=[
                {"label": "Cecid Fly (Gall Midge)", "value": "cecid"},
                {"label": "Fruit Fly (Bactrocera)", "value": "fruitfly"},
            ],
            value="fruitfly",
            className="mb-2",
        ),
        
        # Orchard phenology stage selector (NEW - from 2022-2025 data calibration)
        dbc.Label([icon("flower1", "me-1"), " Orchard Stage"], className="fw-medium mb-1"),
        dbc.Select(
            id="orchard-stage",
            options=[
                {"label": "🌿 Dormant — No fruit activity", "value": "dormant"},
                {"label": "🌸 Flowering — Blossoms present", "value": "flowering"},
                {"label": "🫛 Fruitlet — Young fruit forming (Cecid Fly risk)", "value": "fruitlet"},
                {"label": "🥭 Mature — Ripe fruit (Fruit Fly risk)", "value": "mature"},
            ],
            value="mature",
            className="mb-2",
        ),
        html.Small(
            "Stage determines which pests can activate based on biological triggers.",
            className="text-muted d-block mb-2",
        ),
        
        # Days since flowering (for sugar index calculation)
        dbc.Label([icon("calendar-event", "me-1"), " Days Since Flowering"], className="fw-medium mb-1"),
        dcc.Slider(
            id="days-flowering",
            min=0,
            max=120,
            step=5,
            value=60,
            marks={0: "0", 30: "30", 60: "60", 90: "90", 120: "120"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        html.Small(
            "Controls fruit ripeness (sugar index). Higher = riper fruit, more attractive to Fruit Fly.",
            className="text-muted d-block mb-2",
        ),
        
        # Neighbor threat slider (external orchard pressure)
        dbc.Label([icon("exclamation-triangle", "me-1"), " Neighbor Threat Level"], className="fw-medium mb-1"),
        dcc.Slider(
            id="neighbor-threat",
            min=0,
            max=1,
            step=0.1,
            value=0.0,
            marks={0: "None", 0.3: "Low", 0.5: "Med", 0.7: "High", 1: "Max"},
            tooltip={"placement": "bottom", "always_visible": False},
        ),
        html.Small(
            "External pressure from adjacent unmanaged orchards (historical data shows ~2× higher CPTD).",
            className="text-muted d-block mb-2",
        ),
        
        html.Hr(className="my-2"),
        
        # Forecast duration
        dbc.Label([icon("clock-history", "me-1"), " Forecast duration"], className="fw-medium mb-1"),
        dbc.Select(
            id="sim-hours",
            options=[
                {"label": "24 h", "value": "24"},
                {"label": "48 h (recommended)", "value": "48"},
                {"label": "72 h", "value": "72"},
                {"label": "168 h (7 days)", "value": "168"},
            ],
            value="48",
            className="mb-3",
        ),
        dbc.Button(
            [icon("play-circle", "me-2"), "Run Simulation"],
            id="run-sim-btn",
            color="success",
            className="w-100 fw-semibold",
            n_clicks=0,
        ),
        html.Div(id="sim-status", className="mt-2"),
    ]
    return _card("cpu", "Simulation", body, collapsible=True, panel_id="simulation")


def make_playback_controls():
    body = [
        dcc.Slider(id="playback-slider", min=0, max=1, step=1, value=0, marks={0: "0 h"}, disabled=True),
        html.Div(
            dbc.ButtonGroup(
                [
                    dbc.Button([icon("skip-backward")], id="pb-prev", size="sm", outline=True, color="primary"),
                    dbc.Button([icon("play-fill"), " Play"], id="pb-play", size="sm", color="primary"),
                    dbc.Button([icon("skip-forward")], id="pb-next", size="sm", outline=True, color="primary"),
                ],
                className="mt-2",
            ),
            className="d-flex justify-content-center",
        ),
        html.Div(id="playback-info", className="mt-2 text-center small text-muted"),
        dcc.Interval(id="play-interval", interval=1000, disabled=True),
    ]
    return _card("film", "Playback", body, collapsible=True, panel_id="playback")


def make_observation_form():
    body = [
        dbc.Label([icon("tree", "me-1"), " Tree ID"], className="fw-medium mb-1"),
        dbc.Input(id="obs-tree-id", placeholder="e.g. 5 or T05", size="sm", className="mb-2"),
        dbc.Label([icon("bug", "me-1"), " Pest observed"], className="fw-medium mb-1"),
        dbc.Select(
            id="obs-pest",
            options=[
                {"label": "Cecid Fly", "value": "cecid"},
                {"label": "Fruit Fly", "value": "fruitfly"},
            ],
            value="cecid",
            className="mb-2",
        ),
        dbc.Label([icon("speedometer2", "me-1"), " Severity (0–1)"], className="fw-medium mb-1"),
        dcc.Slider(id="obs-severity", min=0, max=1, step=0.1, value=0.5, marks={0: "0", 0.5: "0.5", 1: "1"}),
        dbc.Label([icon("person", "me-1"), " Observer ID"], className="fw-medium mb-1 mt-1"),
        dbc.Input(id="obs-observer", placeholder="Your name / ID", size="sm", className="mb-2"),
        dbc.Label([icon("journal-text", "me-1"), " Notes"], className="fw-medium mb-1"),
        dbc.Textarea(id="obs-notes", placeholder="Optional notes…", className="mb-2", style={"height": "60px"}),
        dbc.Button(
            [icon("send", "me-2"), "Submit Observation"],
            id="obs-submit-btn", color="primary", outline=True, className="w-100", n_clicks=0,
        ),
        html.Div(id="obs-result", className="mt-2"),
    ]
    return _card("clipboard2-data", "Field Observation", body)


def make_alert_panel():
    body = [
        dbc.Spinner(html.Div(id="alert-list", children="Loading…"), size="sm"),
        html.Small(
            [icon("arrow-repeat", "me-1"), "Auto-refreshes every 30 s"],
            className="text-muted mt-2 d-block",
        ),
    ]
    return _card(
        "exclamation-triangle",
        "Alerts",
        body,
        header_extra=dbc.Badge(id="alert-count-badge", children="0", color="danger", pill=True),
        collapsible=True,
        panel_id="alerts",
    )


def make_evaluation_panel():
    body = [
        html.P(
            "Live evaluation reviews the latest simulation run against operational observation data. "
            "It is separate from the historical validation evidence shown above.",
            className="text-muted small mb-2",
        ),
        dbc.Label([icon("sliders", "me-1"), " Risk threshold"], className="fw-medium mb-1"),
        dbc.Input(id="eval-threshold", type="number", min=0, max=1, step=0.05, value=0.5, size="sm", className="mb-2"),
        dbc.Button(
            [icon("bar-chart-line", "me-2"), "Evaluate Latest Simulation Run"],
            id="eval-btn", color="info", outline=True, className="w-100 mb-2", n_clicks=0,
        ),
        html.Div(id="eval-results"),
    ]
    return _card("graph-up", "Live Evaluation", body)


def make_historical_validation_panel():
    dataset_body = dbc.Spinner(
        html.Div(id="validation-dataset-summary", children="Loading historical validation metadata..."),
        size="sm",
    )

    controls_body = [
        html.P(
            "Historical validation compares MangoPoint simulations against archived BPI Guimaras monitoring records "
            "from 2022 to 2025 to document how closely the model aligns with observed pest activity.",
            className="text-muted small mb-3",
        ),
        dbc.Label([icon("bug", "me-1"), " Pest filter"], className="fw-medium mb-1"),
        dcc.Dropdown(
            id="validation-pest-filter",
            options=VALIDATION_PEST_OPTIONS,
            value=["cecid", "fruitfly"],
            multi=True,
            clearable=False,
            className="mb-3",
        ),
        dbc.Label([icon("calendar3", "me-1"), " Years"], className="fw-medium mb-1"),
        dcc.Dropdown(
            id="validation-year-filter",
            options=VALIDATION_YEAR_OPTIONS,
            value=[2022, 2023, 2024, 2025],
            multi=True,
            clearable=False,
            className="mb-3",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label([icon("collection", "me-1"), " Max cases"], className="fw-medium mb-1"),
                        dbc.Input(id="validation-max-cases", type="number", min=1, max=20, step=1, value=12),
                    ],
                    md=6,
                ),
                dbc.Col(
                    [
                        dbc.Label([icon("clock-history", "me-1"), " Simulation hours"], className="fw-medium mb-1"),
                        dbc.Input(id="validation-hours", type="number", min=24, max=168, step=24, value=48),
                    ],
                    md=6,
                ),
            ],
            className="g-2 mb-3",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        dbc.Label([icon("shuffle", "me-1"), " Monte Carlo runs"], className="fw-medium mb-1"),
                        dbc.Input(
                            id="validation-monte-carlo-runs",
                            type="number",
                            min=10,
                            max=100,
                            step=5,
                            value=20,
                        ),
                    ],
                    md=6,
                ),
            ],
            className="g-2 mb-3",
        ),
        dbc.Button(
            [icon("play-circle", "me-2"), "Run Historical Validation"],
            id="validation-run-btn",
            color="success",
            className="w-100 mb-2",
            n_clicks=0,
        ),
        html.Small(
            "Default settings prioritize a presentation-friendly runtime while preserving the historical validation narrative. "
            "The latest successful run is cached for this session.",
            className="text-muted d-block mb-2",
        ),
        dcc.Loading(
            html.Div(
                id="validation-run-feedback",
                children=html.Small(
                    "Ready to run historical validation against filtered BPI records.",
                    className="text-muted",
                ),
            ),
            type="circle",
            color="#2e7d32",
        ),
    ]

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Div(
                            [
                                icon("clipboard2-check", "me-2"),
                                html.Span("Model Validation", className="fw-semibold"),
                                dbc.Badge("Historical", color="success", pill=True, className="ms-2"),
                            ],
                            className="d-flex align-items-center",
                        ),
                        html.Small("BPI Guimaras 2022-2025", className="text-muted"),
                    ],
                    className="d-flex justify-content-between align-items-center flex-wrap gap-2",
                ),
                className="py-2",
            ),
            dbc.CardBody(
                [
                    html.P(
                        "Historical validation indicates the model aligns reasonably with past pest activity patterns and "
                        "provides evidence for decision-support use. Future performance still depends on environmental "
                        "variability, data quality, and continued calibration.",
                        className="text-muted small mb-3",
                    ),
                    dbc.Row(
                        [
                            dbc.Col(_card("database", "Historical Dataset", dataset_body, card_cls="shadow-sm h-100"), lg=7),
                            dbc.Col(_card("sliders2", "Validation Controls", controls_body, card_cls="shadow-sm h-100"), lg=5),
                        ],
                        className="g-2 mb-3",
                    ),
                    html.Div(id="validation-results-content"),
                ],
                className="py-3",
            ),
        ],
        className="mb-3 shadow-sm border-0",
    )


def make_validation_interpretation_panel():
    body = [
        html.P(
            "This panel explains why the historical validation metrics matter for research presentation and decision support.",
            className="text-muted small mb-3",
        ),
        html.Ul(
            [
                html.Li("Reliability: accuracy and F1-score summarize how consistently the model agrees with documented pest activity."),
                html.Li("Early warning confidence: recall highlights how often higher-risk periods are detected before they are missed."),
                html.Li("Reduced false alarms: precision and specificity indicate whether interventions are recommended selectively."),
                html.Li("Reduced missed infestations: false negatives reveal where outbreaks would have been overlooked."),
                html.Li("Evidence-based forecasting: historical agreement supports decision-support use, while future accuracy still depends on calibration and changing field conditions."),
            ],
            className="small mb-0 ps-3",
        ),
    ]
    return _card("journal-check", "Validation Interpretation", body)


def _monitoring_kpi_card(icon_name, icon_class_name, title, value_id, detail_children):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                html.Div(
                    [
                        html.Div(
                            icon(icon_name, f"{icon_class_name} fs-4"),
                            className="monitoring-kpi-icon",
                        ),
                        html.Div(
                            [
                                html.P(title, className="monitoring-kpi-label text-muted mb-1"),
                                html.H3("\u2014", id=value_id, className="monitoring-kpi-value mb-1 fw-bold"),
                                html.Div(detail_children, className="monitoring-kpi-detail"),
                            ],
                            className="flex-grow-1",
                        ),
                    ],
                    className="d-flex align-items-start gap-3",
                ),
                className="p-3",
            ),
            className="shadow-sm border-0 h-100 monitoring-kpi-card",
        ),
        xs=12,
        md=4,
    )


def make_monitoring_overview_module():
    return html.Div(
        [
            dbc.Row(
                [
                    _monitoring_kpi_card(
                        "virus",
                        "text-danger",
                        "Infestation rate",
                        "mon-infestation-rate",
                        html.Div(id="mon-infestation-bar", className="mt-2"),
                    ),
                    _monitoring_kpi_card(
                        "speedometer2",
                        "text-warning",
                        "Pest risk level",
                        "mon-risk-score",
                        dbc.Badge("\u2014", id="mon-risk-level", pill=True, className="mt-2 monitoring-risk-badge"),
                    ),
                    _monitoring_kpi_card(
                        "tree-fill",
                        "text-danger",
                        "Infested trees",
                        "mon-infested-trees",
                        html.Div(id="mon-infested-trees-detail", className="mt-2"),
                    ),
                ],
                className="g-3",
            ),
        ],
        className="monitoring-module-panel",
    )


def make_monitoring_impact_module():
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            icon("cash-coin", "me-2"),
                                            html.Span("Estimated Loss at Risk (Scenario)", className="fw-semibold"),
                                        ],
                                        className="d-flex align-items-center",
                                    ),
                                    className="py-2",
                                ),
                                dbc.CardBody(
                                    [
                                        html.Small(_loss_assumptions_text(), className="text-muted d-block px-2 pt-1"),
                                        dcc.Graph(
                                            id="mon-pest-trend-chart",
                                            config={"displayModeBar": False},
                                            style={"height": "248px"},
                                        ),
                                    ],
                                    className="py-1",
                                ),
                            ],
                            className="shadow-sm border-0 h-100 monitoring-module-chart-card",
                        ),
                        lg=8,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            icon("flower1", "me-2"),
                                            html.Span("Phenology Distribution", className="fw-semibold"),
                                        ],
                                        className="d-flex align-items-center",
                                    ),
                                    className="py-2",
                                ),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="mon-phenology-chart",
                                        config={"displayModeBar": False},
                                        style={"height": "260px"},
                                    ),
                                    className="py-1",
                                ),
                            ],
                            className="shadow-sm border-0 h-100 monitoring-module-chart-card",
                        ),
                        lg=4,
                    ),
                ],
                className="g-3",
            ),
        ],
        className="monitoring-module-panel",
    )


def make_monitoring_surveillance_module():
    return html.Div(
        [
            dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            icon("graph-up-arrow", "me-2"),
                                            html.Span("Infestation Spread Over Time", className="fw-semibold"),
                                        ],
                                        className="d-flex align-items-center",
                                    ),
                                    className="py-2",
                                ),
                                dbc.CardBody(
                                    dcc.Graph(
                                        id="mon-spread-chart",
                                        config={"displayModeBar": False},
                                        style={"height": "260px"},
                                    ),
                                    className="py-1",
                                ),
                            ],
                            className="shadow-sm border-0 h-100 monitoring-module-chart-card",
                        ),
                        lg=7,
                    ),
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(
                                    html.Div(
                                        [
                                            icon("cloud-sun", "me-2"),
                                            html.Span("Environmental Monitoring", className="fw-semibold"),
                                        ],
                                        className="d-flex align-items-center",
                                    ),
                                    className="py-2",
                                ),
                                dbc.CardBody(
                                    [
                                        html.Div(id="mon-env-current", className="mb-2"),
                                        dcc.Graph(
                                            id="mon-env-trend-chart",
                                            config={"displayModeBar": False},
                                            style={"height": "180px"},
                                        ),
                                    ],
                                    className="py-1",
                                ),
                            ],
                            className="shadow-sm border-0 h-100 monitoring-module-chart-card",
                        ),
                        lg=5,
                    ),
                ],
                className="g-3",
            ),
        ],
        className="monitoring-module-panel",
    )


def make_operations_map_page():
    return html.Div(
        [
            html.Div(
                [
                    dbc.Card(
                        dcc.Loading(
                            dcc.Graph(
                                id="risk-map",
                                figure=build_risk_map(),
                                config={"scrollZoom": True, "displayModeBar": False, "displaylogo": False, "doubleClick": False},
                                style={"borderRadius": "6px"},
                            ),
                            type="circle",
                            color="#4caf50",
                        ),
                        className="shadow-sm border-0 map-card",
                    ),
                    html.Img(
                        src=COMPASS_SVG_DATA_URI,
                        alt="Compass - True North",
                        className="map-compass",
                    ),
                ],
                style={"position": "relative"},
                className="mb-0 map-stage operations-map-stage",
            ),
        ],
        className="monitoring-module-panel operations-map-panel",
    )


def make_operations_pages_panel():
    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        html.Div(
                            [
                                icon("layout-sidebar-inset", "me-2"),
                                html.Span("Operations Pages", className="fw-semibold"),
                            ],
                            className="d-flex align-items-center",
                        ),
                    ],
                    className="d-flex flex-wrap gap-2 justify-content-between align-items-center",
                ),
                className="py-3",
            ),
            dbc.CardBody(
                [
                    dbc.Tabs(
                        [
                            dbc.Tab(make_operations_map_page(), label="Live Map", tab_id="operations-live-map"),
                            dbc.Tab(make_monitoring_overview_module(), label="Overview", tab_id="monitoring-overview"),
                            dbc.Tab(make_monitoring_impact_module(), label="Crop Impact", tab_id="monitoring-impact"),
                            dbc.Tab(make_monitoring_surveillance_module(), label="Spread and Weather", tab_id="monitoring-surveillance"),
                        ],
                        id="operations-page-tabs",
                        active_tab="operations-live-map",
                        className="monitoring-module-tabs operations-page-tabs",
                    ),
                ],
                className="pt-3",
            ),
            dbc.CardFooter(
                html.Small(
                    [
                        icon("arrow-repeat", "me-1"),
                        "Auto-refreshes every 30 seconds | ",
                        html.Span(id="mon-last-updated", children="Never"),
                    ],
                    className="text-muted",
                ),
                className="border-0 pt-0 pb-3 bg-transparent",
            ),
        ],
        className="shadow-sm border-0 monitoring-modules-card",
    )


# Retained only as a reference for the pre-module dashboard layout.
def _legacy_make_operations_dashboard_tab_old():
    """Primary operational dashboard content."""
    return html.Div(
        [
            html.Div(
                [
                    dbc.Card(
                        dcc.Loading(
                            dcc.Graph(
                                id="risk-map",
                                figure=build_risk_map(),
                                config={"scrollZoom": True, "displayModeBar": False, "displaylogo": False, "doubleClick": False},
                                style={"borderRadius": "6px"},
                            ),
                            type="circle",
                            color="#4caf50",
                        ),
                        className="shadow-sm border-0 map-card",
                    ),
                    html.Img(
                        src=COMPASS_SVG_DATA_URI,
                        alt="Compass - True North",
                        className="map-compass",
                    ),
                ],
                style={"position": "relative"},
                className="mb-3 map-stage",
            ),
            html.Hr(className="my-3"),
            html.H6([
                icon("clipboard-data", "me-2"),
                "Monitoring Dashboard",
            ], className="fw-bold text-dark mb-3"),
            dbc.Row([
                dbc.Col(dbc.Card([dbc.CardBody([html.Div([
                    html.Div(icon("virus", "text-danger fs-4"), className="me-2"),
                    html.Div([
                        html.P("Infestation Rate", className="text-muted small mb-0", style={"fontSize": "0.75rem"}),
                        html.H5("—", id="mon-infestation-rate", className="mb-0 fw-bold"),
                        html.Div(id="mon-infestation-bar", className="mt-1"),
                    ]),
                ], className="d-flex align-items-center")], className="py-2 px-2")], className="shadow-sm border-0 h-100"), xs=6, md=4),
                dbc.Col(dbc.Card([dbc.CardBody([html.Div([
                    html.Div(icon("speedometer2", "text-warning fs-4"), className="me-2"),
                    html.Div([
                        html.P("Pest Risk Level", className="text-muted small mb-0", style={"fontSize": "0.75rem"}),
                        html.H5("—", id="mon-risk-score", className="mb-0 fw-bold"),
                        dbc.Badge("—", id="mon-risk-level", pill=True, className="mt-1"),
                    ]),
                ], className="d-flex align-items-center")], className="py-2 px-2")], className="shadow-sm border-0 h-100"), xs=6, md=4),
                dbc.Col(dbc.Card([dbc.CardBody([html.Div([
                    html.Div(icon("tree-fill", "text-danger fs-4"), className="me-2"),
                    html.Div([
                        html.P("Infested Trees", className="text-muted small mb-0", style={"fontSize": "0.75rem"}),
                        html.H5("—", id="mon-infested-trees", className="mb-0 fw-bold"),
                        html.Div(id="mon-infested-trees-detail", className="mt-1"),
                    ]),
                ], className="d-flex align-items-center")], className="py-2 px-2")], className="shadow-sm border-0 h-100"), xs=6, md=4),
            ], className="mb-3 g-2"),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.Div([icon("cash-coin", "me-2"), html.Span("Estimated Loss at Risk (Scenario)", className="fw-semibold")], className="d-flex align-items-center"), className="py-2"),
                    dbc.CardBody([
                        html.Small(_loss_assumptions_text(), className="text-muted d-block px-2 pt-1"),
                        dcc.Graph(id="mon-pest-trend-chart", config={"displayModeBar": False}, style={"height": "248px"}),
                    ], className="py-1"),
                ], className="shadow-sm border-0"), md=8),
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.Div([icon("flower1", "me-2"), html.Span("Phenology Distribution", className="fw-semibold")], className="d-flex align-items-center"), className="py-2"),
                    dbc.CardBody(dcc.Graph(id="mon-phenology-chart", config={"displayModeBar": False}, style={"height": "260px"}), className="py-1"),
                ], className="shadow-sm border-0"), md=4),
            ], className="mb-3 g-2"),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.Div([icon("graph-up-arrow", "me-2"), html.Span("Infestation Spread Over Time", className="fw-semibold")], className="d-flex align-items-center"), className="py-2"),
                    dbc.CardBody(dcc.Graph(id="mon-spread-chart", config={"displayModeBar": False}, style={"height": "260px"}), className="py-1"),
                ], className="shadow-sm border-0"), md=12),
            ], className="mb-3 g-2"),
            dbc.Row([
                dbc.Col(dbc.Card([
                    dbc.CardHeader(html.Div([icon("cloud-sun", "me-2"), html.Span("Environmental Monitoring", className="fw-semibold")], className="d-flex align-items-center"), className="py-2"),
                    dbc.CardBody([
                        html.Div(id="mon-env-current", className="mb-2"),
                        dcc.Graph(id="mon-env-trend-chart", config={"displayModeBar": False}, style={"height": "180px"}),
                    ], className="py-1"),
                ], className="shadow-sm border-0"), md=12),
            ], className="mb-3 g-2"),
            html.Div(
                html.Small([icon("arrow-repeat", "me-1"), "Auto-refreshes every 30 seconds  |  ", html.Span(id="mon-last-updated", children="Never")], className="text-muted"),
                className="text-center mb-2",
            ),
        ],
    )


def make_operations_dashboard_tab():
    """Primary operational dashboard content."""
    return make_operations_pages_panel()


def make_risk_legend():
    risk_items = [
        ("< 15 %", "#ffffb2"),
        ("15-30 %", "#fecc5c"),
        ("30-50 %", "#fd8d3c"),
        ("50-70 %", "#f03b20"),
        ("70-85 %", "#e31a1c"),
        ("85-90 %", "#bd0026"),
        ("90-100 %", "#800026"),
    ]
    state_items = [
        ("Empty", STATE_COLORS["empty"]), ("Unbagged", STATE_COLORS["unbagged"]),
        ("Bagged", STATE_COLORS["bagged"]), ("Infested", STATE_COLORS["infested"]),
    ]

    def _swatch(color, label, radius="2px"):
        return html.Div(
            [
                html.Span(style={
                    "display": "inline-block", "width": "14px", "height": "14px",
                    "backgroundColor": color, "marginRight": "6px", "verticalAlign": "middle",
                    "border": "1px solid #aaa", "borderRadius": radius,
                }),
                html.Span(label, style={"fontSize": "0.8rem"}),
            ],
            className="mb-1",
        )

    body = [
        html.Small([icon("palette", "me-1"), html.Strong(" Risk Scale")], className="d-block mb-1"),
        *[_swatch(c, l) for l, c in risk_items],
        html.Hr(className="my-2"),
        html.Small([icon("tree", "me-1"), html.Strong(" Tree States")], className="d-block mb-1"),
        *[_swatch(c, l, "50%") for l, c in state_items],
    ]
    return _card("info-circle", "Legend", body, collapsible=True, panel_id="legend")


def _stat_card(title, value_id, ico, color="light"):
    return dbc.Col(
        dbc.Card(
            dbc.CardBody(
                [
                    html.Div(icon(ico, f"text-{color} fs-4"), className="mb-1"),
                    html.P(title, className="text-muted small mb-0"),
                    html.H4("—", id=value_id, className="mb-0 fw-bold"),
                ],
                className="text-center py-2",
            ),
            className="shadow-sm border-0",
        ),
        xs=6, md=3,
    )


def make_decision_support_panel():
    """
    Create the Decision Support Summary panel.
    
    Displays management recommendations and economic metrics based on
    the latest simulation results. Updates automatically when new
    simulation data is available.
    """
    # Zone indicator items with color swatches
    def zone_indicator(zone_num, label, color, value_id):
        return html.Div([
            html.Div([
                html.Span(style={
                    "display": "inline-block",
                    "width": "16px",
                    "height": "16px",
                    "backgroundColor": color,
                    "marginRight": "8px",
                    "borderRadius": "3px",
                    "border": "2px solid" + (" #7f1d1d" if zone_num == 3 else " transparent"),
                    "boxShadow": "0 0 4px " + color if zone_num == 3 else "none",
                }),
                html.Span(label, className="fw-medium"),
            ], className="d-flex align-items-center"),
            html.Span("—", id=value_id, className="fw-bold"),
        ], className="d-flex justify-content-between align-items-center py-1")
    
    body = [
        # Threshold info
        html.Div([
            html.Small([
                icon("sliders2", "me-1"),
                f"Thresholds: <{DECISION_ZONE_LOW_THRESHOLD:.0%} (Safe) | "
                f"≥{DECISION_ZONE_HIGH_THRESHOLD:.0%} (Critical)"
            ], className="text-muted"),
        ], className="mb-2"),
        
        html.Hr(className="my-2"),
        
        # Zone breakdown
        html.Div([
            html.Small([icon("layers", "me-1"), html.Strong(" Zone Classification")], className="d-block mb-2"),
            zone_indicator(1, "Zone 1: No Action", DECISION_ZONE_COLORS["zone_1"], "ds-zone1-pct"),
            zone_indicator(2, "Zone 2: Monitor", DECISION_ZONE_COLORS["zone_2"], "ds-zone2-pct"),
            zone_indicator(3, "Zone 3: Spray Now", DECISION_ZONE_COLORS["zone_3"], "ds-zone3-pct"),
        ], className="mb-3"),
        
        html.Hr(className="my-2"),
        
        # Economic metrics
        html.Div([
            html.Small([icon("piggy-bank", "me-1"), html.Strong(" Economic Impact")], className="d-block mb-2"),
            
            # Pesticide reduction badge
            html.Div([
                html.Span([icon("arrows-collapse", "me-1"), "Pesticide Reduction"], 
                         className="text-muted small"),
                html.Span("—", id="ds-pesticide-reduction", 
                         className="badge bg-success fs-6"),
            ], className="d-flex justify-content-between align-items-center py-1"),
            
            # Estimated savings
            html.Div([
                html.Span([icon("cash-coin", "me-1"), "Est. Savings"], 
                         className="text-muted small"),
                html.Span("—", id="ds-money-saved", 
                         className="fw-bold text-success"),
            ], className="d-flex justify-content-between align-items-center py-1"),
        ], className="mb-2"),
        
        # Summary message
        html.Div(id="ds-summary-message", className="mt-2"),
        
        # Metadata
        html.Small([
            icon("info-circle", "me-1"),
            "Updates automatically after each simulation"
        ], className="text-muted d-block mt-2"),
    ]
    
    return _card(
        "clipboard2-pulse",
        "Decision Support Summary",
        body,
        card_cls="mb-3 shadow-sm panel-card border-success decision-support-card",
        header_extra=dbc.Badge("NEW", color="info", pill=True),
        collapsible=True,
        panel_id="decision-support",
        header_class_name="py-2 bg-light",
    )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App init
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css",
    ],
    title="MangoPoint Dashboard",
    update_title=None, # type: ignore
    suppress_callback_exceptions=True,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
)

# Custom CSS for light theme styling
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            /* Light theme slider styling */
            .rc-slider-track {
                background-color: #2e7d32 !important;
            }
            .rc-slider-handle {
                border-color: #2e7d32 !important;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layout
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app.layout = dbc.Container(
    [
        # ── Navbar ──
        dbc.Navbar(
            dbc.Container(
                [
                    dbc.NavbarBrand(
                        [
                            html.Img(
                                src="https://img.icons8.com/color/48/mango.png",
                                height="28px", className="me-2",
                            ),
                            html.Span("MangoPoint", className="fw-bold"),
                            html.Span(" Dashboard", className="fw-light d-none d-sm-inline"),
                        ],
                        className="fs-5",
                    ),
                    html.Div(
                        [
                            dbc.Badge(
                                [icon("exclamation-triangle-fill", "me-1"), html.Span(id="navbar-alert-text", children="0 alerts")],
                                id="navbar-alert-badge", color="danger", pill=True, className="me-2 me-lg-3",
                            ),
                            html.Small(id="navbar-time", className="text-white-50 d-none d-md-inline me-3"),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Div(id="navbar-user-name", className="auth-user-name"),
                                            html.Small(id="navbar-user-role", className="auth-user-role"),
                                        ],
                                        className="auth-user-meta d-none d-lg-block",
                                    ),
                                    dbc.Button(
                                        [icon("box-arrow-right", "me-1"), "Logout"],
                                        id="logout-btn",
                                        color="light",
                                        size="sm",
                                        className="logout-btn",
                                    ),
                                ],
                                className="d-flex align-items-center gap-2",
                            ),
                        ],
                        className="d-flex align-items-center flex-wrap justify-content-end",
                    ),
                ],
                fluid=True,
                className="d-flex justify-content-between align-items-center gap-3",
            ),
            color="#2e7d32",
            dark=True,
            className="mb-3 shadow main-navbar",
        ),

        # ── Hidden stores ──
        dcc.Store(id="sim-data-store"),
        dcc.Store(id="active-alerts-store"),
        dcc.Store(id="is-playing", data=False),
        dcc.Store(id="playback-frames-store"), # Pre-computed frame data for smooth animation
        dcc.Store(id="selected-tree-store"),   # Selected tree for management modal
        dcc.Store(id="monitoring-data-store"), # Monitoring tab metrics cache
        dcc.Store(id="validation-summary-store"),
        dcc.Store(id="validation-metrics-explanation-store"),
        dcc.Store(id="validation-cases-store"),
        dcc.Store(id="validation-latest-result-store", storage_type="session"),

        # ── Tree Management Modal ──
        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle([
                        html.I(className="bi bi-tree-fill me-2", style={"color": "#22c55e"}),
                        "Tree Management"
                    ]),
                    close_button=True,
                    className="bg-light border-bottom",
                ),
                dbc.ModalBody([
                    # Tree information display (dynamically updated)
                    html.Div(id="tree-modal-info", className="mb-4"),
                    
                    # Divider with label
                    html.Div([
                        html.Hr(className="my-2"),
                        html.Div([
                            html.I(className="bi bi-pencil-square me-2 text-primary"),
                            html.Strong("Override Status", className="text-primary"),
                        ], className="d-flex align-items-center mb-2"),
                    ]),
                    
                    # Status override dropdown with custom styling
                    dbc.Select(
                        id="tree-status-dropdown",
                        options=TREE_STATUS_OPTIONS,  # type: ignore[arg-type]
                        value="healthy",
                        className="mb-3 border-primary",
                        style={"fontSize": "0.95rem"},
                    ),
                    
                    # Info callout
                    dbc.Card([
                        dbc.CardBody([
                            html.Div([
                                html.I(className="bi bi-info-circle-fill me-2 text-info"),
                                html.Span("Status changes take effect on the next simulation run.", 
                                         className="small"),
                            ], className="d-flex align-items-center"),
                            html.Div([
                                html.I(className="bi bi-shield-check me-2 text-success"),
                                html.Span([
                                    html.Strong("Bagged"), " trees have reduced infection risk; ",
                                    html.Strong("Dead"), " trees are immune to pest spread."
                                ], className="small"),
                            ], className="d-flex align-items-center mt-2"),
                        ], className="py-2 px-3"),
                    ], className="bg-light border-0"),
                ], className="px-4 py-3"),
                dbc.ModalFooter([
                    dbc.Button(
                        [html.I(className="bi bi-x-lg me-1"), "Cancel"],
                        id="tree-modal-cancel",
                        color="secondary",
                        outline=True,
                        className="px-4",
                    ),
                    dbc.Button(
                        [html.I(className="bi bi-check-lg me-1"), "Apply Changes"],
                        id="tree-modal-update",
                        color="success",
                        className="px-4 ms-2",
                    ),
                ], className="bg-light border-top"),
            ],
            id="tree-management-modal",
            is_open=False,
            centered=True,
            size="md",
            backdrop="static",  # Prevent closing by clicking outside
        ),

        # ── Timers ──
        dcc.Interval(id="weather-timer", interval=60_000, n_intervals=0),
        dcc.Interval(id="alert-timer", interval=30_000, n_intervals=0),
        dcc.Interval(id="clock-timer", interval=1_000, n_intervals=0),
        dcc.Interval(id="monitoring-timer", interval=30_000, n_intervals=0),



        # ━━━ Main Dashboard Content ━━━
                        # Main body
                        dbc.Row(
                            [
                                # Left sidebar
                                dbc.Col(
                                    html.Div(
                                        [
                                            make_weather_card(),
                                            make_sim_controls(),
                                            make_playback_controls(),
                                            make_alert_panel(),
                                            make_decision_support_panel(),
                                            make_risk_legend(),
                                            # Keep auxiliary panels mounted because callbacks still target these IDs.
                                            html.Div(
                                                [
                                                    make_observation_form(),
                                                    make_evaluation_panel(),
                                                    make_historical_validation_panel(),
                                                    make_validation_interpretation_panel(),
                                                ],
                                                style={"display": "none"},
                                            ),
                                        ],
                                        className="sidebar-scroll-frame",
                                    ),
                                    md=4, lg=3,
                                    className="pe-md-2 sidebar-col",
                                ),
                                # Right content
                                dbc.Col(
                                    [
                                        make_operations_dashboard_tab(),
                                    ],
                                    md=8, lg=9,
                                    className="content-col",
                                ),
                            ],
                            className="dashboard-grid g-3",
                        ),

        # Footer
        html.Hr(className="mt-4"),
        html.Footer(
            html.Small(
                [
                    icon("geo-alt", "me-1"),
                    "MangoPoint — GIS-Based Pest Risk Simulation for Mango Orchards  |  ",
                    icon("pin-map", "me-1"),
                    f" Guimaras, Philippines ({DEFAULT_LAT}°N, {DEFAULT_LON}°E)",
                ],
                className="text-muted",
            ),
            className="text-center pb-3",
        ),
    ],
    fluid=True,
    className="px-3 app-shell",
)

DASHBOARD_LAYOUT = app.layout


def make_login_screen(auth_state=None):
    """Render the login form shown before the dashboard shell."""
    auth_state = auth_state if isinstance(auth_state, dict) else default_auth_state()
    message = auth_state.get("message")
    message_color = auth_state.get("message_color", "warning")

    message_block = None
    if message:
        message_block = dbc.Alert(message, color=message_color, className="py-2 mb-3")

    return dbc.Container(
        [
            html.Div(
                [
                    html.Div(className="login-orb login-orb-a"),
                    html.Div(className="login-orb login-orb-b"),
                    dbc.Row(
                        [
                            dbc.Col(
                                html.Div(
                                    [
                                        dbc.Badge("Secure Access", color="warning", className="mb-3 login-badge"),
                                        html.H1("MangoPoint", className="login-hero-title"),
                                        html.P(
                                            "Sign in to unlock the existing simulation, monitoring, GIS, and validation tools.",
                                            className="login-hero-copy",
                                        ),
                                        html.Div(
                                            [
                                                html.Div([icon("shield-lock", "me-2 text-success"), html.Span("Protected FastAPI routes")], className="login-feature"),
                                                html.Div([icon("map", "me-2 text-success"), html.Span("GIS and monitoring dashboards")], className="login-feature"),
                                                html.Div([icon("cpu", "me-2 text-success"), html.Span("Simulation and validation workflows")], className="login-feature"),
                                            ],
                                            className="login-feature-list",
                                        ),
                                    ],
                                    className="login-hero-panel",
                                ),
                                lg=6,
                                className="mb-4 mb-lg-0",
                            ),
                            dbc.Col(
                                dbc.Card(
                                    dbc.CardBody(
                                        [
                                            html.Div("Dashboard Login", className="login-card-kicker"),
                                            html.H2("Welcome back", className="login-card-title"),
                                            html.P(
                                                "Use your MangoPoint username or email and password.",
                                                className="text-muted mb-4",
                                            ),
                                            message_block,
                                            dbc.Label("Username or Email", html_for="login-identifier", className="fw-semibold"),
                                            dbc.Input(
                                                id="login-identifier",
                                                type="text",
                                                placeholder="admin or admin@example.com",
                                                className="mb-3",
                                                autoComplete="username",
                                            ),
                                            dbc.Label("Password", html_for="login-password", className="fw-semibold"),
                                            dbc.Input(
                                                id="login-password",
                                                type="password",
                                                placeholder="Enter your password",
                                                className="mb-3",
                                                autoComplete="current-password",
                                            ),
                                            dcc.Loading(
                                                html.Div(id="login-processing", className="login-processing"),
                                                type="circle",
                                                color="#2e7d32",
                                            ),
                                            dbc.Button(
                                                [icon("box-arrow-in-right", "me-2"), "Login"],
                                                id="login-btn",
                                                color="success",
                                                className="w-100 login-submit-btn",
                                            ),
                                            html.Small(
                                                "Replace the default development admin password after first login.",
                                                className="text-muted d-block mt-3",
                                            ),
                                        ],
                                        className="p-4 p-lg-5",
                                    ),
                                    className="login-card border-0 shadow-lg",
                                ),
                                lg=5,
                            ),
                        ],
                        className="align-items-center justify-content-center g-4 login-grid",
                    ),
                ],
                className="login-shell",
            )
        ],
        fluid=True,
        className="px-3 auth-shell",
    )


def make_auth_loading_screen():
    """Render a neutral loading view while restoring a stored session."""
    return dbc.Container(
        [
            html.Div(
                dbc.Card(
                    dbc.CardBody(
                        [
                            dbc.Spinner(color="success", size="md", className="mb-3"),
                            html.H2("Restoring session", className="login-card-title mb-2"),
                            html.P(
                                "Validating your MangoPoint access token.",
                                className="text-muted mb-0",
                            ),
                        ],
                        className="text-center p-5",
                    ),
                    className="login-card border-0 shadow-lg",
                ),
                className="login-shell d-flex align-items-center justify-content-center",
            )
        ],
        fluid=True,
        className="px-3 auth-shell",
    )


app.layout = html.Div(
    [
        dcc.Store(id="auth-session-store", storage_type="session"),
        dcc.Store(id="auth-state-store", data=default_auth_state()),
        dcc.Interval(id="auth-bootstrap", interval=100, n_intervals=0, max_intervals=1),
        dcc.Interval(id="auth-session-check-timer", interval=60_000, n_intervals=0),
        html.Div(id="app-root"),
    ]
)


@app.callback(
    Output("app-root", "children"),
    Input("auth-state-store", "data"),
    State("auth-session-store", "data"),
)
def render_app_root(auth_state, auth_session):
    """Swap between the login screen and the protected dashboard shell."""
    token = extract_access_token(auth_session)
    if token and not (auth_state or {}).get("checked"):
        return make_auth_loading_screen()
    if is_authenticated_session(auth_session, auth_state):
        return DASHBOARD_LAYOUT
    return make_login_screen(auth_state)


@app.callback(
    Output("auth-state-store", "data", allow_duplicate=True),
    Output("auth-session-store", "data", allow_duplicate=True),
    Input("auth-bootstrap", "n_intervals"),
    Input("auth-session-check-timer", "n_intervals"),
    State("auth-session-store", "data"),
    State("auth-state-store", "data"),
    prevent_initial_call="initial_duplicate",
)
def validate_auth_session(_bootstrap, _refresh, auth_session, auth_state):
    """Validate the stored bearer token on load and on a short interval."""
    token = extract_access_token(auth_session)
    current_state = auth_state if isinstance(auth_state, dict) else default_auth_state()

    if not token:
        if current_state.get("checked"):
            return no_update, no_update
        return build_auth_state(checked=True, authenticated=False), no_update

    response = api_get("/auth/me", token=token, timeout=15)
    if response.get("ok"):
        payload = response.get("data") or {}
        session_user = payload.get("user") or (auth_session or {}).get("user")
        updated_session = dict(auth_session or {})
        updated_session["user"] = session_user
        updated_state = build_auth_state(checked=True, authenticated=True)

        next_session = no_update if updated_session == auth_session else updated_session
        next_state = no_update if updated_state == current_state else updated_state
        return next_state, next_session

    if response.get("status_code") == 401:
        return (
            build_auth_state(
                checked=True,
                authenticated=False,
                message="Your session expired. Sign in again.",
                message_color="warning",
            ),
            None,
        )

    updated_state = build_auth_state(
        checked=True,
        authenticated=False,
        message=response.get("error") or "Unable to validate the current session.",
        message_color="danger",
    )
    if updated_state == current_state:
        return no_update, no_update
    return updated_state, no_update


@app.callback(
    Output("auth-session-store", "data", allow_duplicate=True),
    Output("auth-state-store", "data", allow_duplicate=True),
    Output("login-processing", "children"),
    Input("login-btn", "n_clicks"),
    State("login-identifier", "value"),
    State("login-password", "value"),
    prevent_initial_call=True,
)
def handle_login(n_clicks, username_or_email, password):
    """Authenticate the user against the FastAPI auth endpoint."""
    if not n_clicks:
        return no_update, no_update, no_update

    identifier = str(username_or_email or "").strip()
    if not identifier:
        return (
            no_update,
            build_auth_state(
                checked=True,
                authenticated=False,
                message="Username or email is required.",
                message_color="warning",
            ),
            "",
        )

    if not password:
        return (
            no_update,
            build_auth_state(
                checked=True,
                authenticated=False,
                message="Password is required.",
                message_color="warning",
            ),
            "",
        )

    response = api_post(
        "/auth/login",
        json_body={"username_or_email": identifier, "password": password},
        timeout=30,
    )
    if response.get("ok"):
        payload = response.get("data") or {}
        session_data = {
            "access_token": payload.get("access_token"),
            "token_type": payload.get("token_type", "bearer"),
            "expires_at": payload.get("expires_at"),
            "user": payload.get("user"),
        }
        return session_data, build_auth_state(checked=True, authenticated=True), f"login-{n_clicks}"

    status_code = response.get("status_code")
    return (
        no_update,
        build_auth_state(
            checked=True,
            authenticated=False,
            message=response.get("error") or "Login failed. Check your credentials and API connection.",
            message_color="warning" if status_code == 401 else "danger",
        ),
        "",
    )


@app.callback(
    Output("auth-session-store", "data", allow_duplicate=True),
    Output("auth-state-store", "data", allow_duplicate=True),
    Input("logout-btn", "n_clicks"),
    prevent_initial_call=True,
)
def handle_logout(n_clicks):
    """Clear the current browser session and return to the login screen."""
    if not n_clicks:
        return no_update, no_update
    return None, build_auth_state(
        checked=True,
        authenticated=False,
        message="You have been signed out.",
        message_color="info",
    )


@app.callback(
    Output("navbar-user-name", "children"),
    Output("navbar-user-role", "children"),
    Input("auth-session-store", "data"),
)
def update_navbar_user(auth_session):
    """Show the current authenticated user's name and role in the navbar."""
    user = auth_session.get("user") if isinstance(auth_session, dict) else {}
    if not isinstance(user, dict):
        return "Authenticated User", "Authenticated"

    display_name = user.get("full_name") or user.get("username") or "Authenticated User"
    display_role = str(user.get("role") or "authenticated").replace("_", " ").title()
    return display_name, display_role


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Callbacks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── 1) Live clock ──
@app.callback(
    Output({"type": "sidebar-panel-collapse", "panel": MATCH}, "is_open"),
    Output({"type": "sidebar-panel-toggle", "panel": MATCH}, "children"),
    Output({"type": "sidebar-panel-toggle", "panel": MATCH}, "title"),
    Input({"type": "sidebar-panel-toggle", "panel": MATCH}, "n_clicks"),
    State({"type": "sidebar-panel-collapse", "panel": MATCH}, "is_open"),
    prevent_initial_call=True,
)
def toggle_sidebar_panel(_n_clicks, is_open):
    next_state = not is_open
    return (
        next_state,
        _sidebar_panel_toggle_children(next_state),
        _sidebar_panel_toggle_title(next_state),
    )


app.clientside_callback(
    """
    function(_) {
        return new Date().toLocaleString("en-US", {
            month: "short",
            day: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
            hour12: false
        }).replace(",", "");
    }
    """,
    Output("navbar-time", "children"),
    Input("clock-timer", "n_intervals"),
)


# ── 2) Weather polling — reads data["current"] (matches API response) ──
@app.callback(
    Output("weather-content", "children"),
    Input("weather-timer", "n_intervals"),
    State("auth-session-store", "data"),
)
def update_weather(_, auth_session):
    response = api_get(
        "/weather/live",
        token=extract_access_token(auth_session),
        params={"lat": DEFAULT_LAT, "lon": DEFAULT_LON},
    )
    if not response.get("ok"):
        return dbc.Alert(
            [icon("wifi-off", "me-2"), "Weather unavailable — is the API running?"],
            color="warning", className="mb-0 py-2",
        )

    # API returns { "current": { ... }, "cached": ..., "location": ... }
    data = response.get("data") or {}
    w = data.get("current") or data
    temp = w.get("temperature_c", "—")
    hum = w.get("humidity", "—")
    ws = w.get("wind_speed_ms", "—")
    wd = w.get("wind_direction_deg", "—")
    src = w.get("source", "")
    cached = data.get("cached", False)

    def _metric(ico, label, value, unit):
        return dbc.Col(
            html.Div(
                [
                    icon(ico, "text-muted fs-5"),
                    html.Div(
                        [
                            html.Small(label, className="text-muted d-block", style={"lineHeight": "1"}),
                            html.Span(
                                f"{value} {unit}" if value != "—" else "—",
                                className="fw-bold",
                            ),
                        ],
                        className="ms-2",
                    ),
                ],
                className="d-flex align-items-center",
            ),
            xs=6,
            className="mb-2",
        )

    # Convert wind direction to cardinal
    if isinstance(wd, (int, float)):
        cardinal = get_cardinal_direction(wd)
        wind_dir_display = f"{cardinal} ({wd:.0f}°)"
    else:
        wind_dir_display = "—"

    return html.Div(
        [
            dbc.Row(
                [
                    _metric("thermometer-half", "Temperature", f"{temp:.1f}" if isinstance(temp, (int, float)) else temp, "°C"),
                    _metric("droplet-half", "Humidity", f"{hum:.0f}" if isinstance(hum, (int, float)) else hum, "%"),
                    _metric("wind", "Wind Speed", f"{ws:.1f}" if isinstance(ws, (int, float)) else ws, "m/s"),
                    _metric("compass", "Direction", wind_dir_display, ""),
                ],
            ),
            html.Div(
                [
                    dbc.Badge([icon("cloud-arrow-down", "me-1"), src], color="primary", pill=True, className="me-1") if src else None,
                    dbc.Badge([icon("database", "me-1"), "cached"], color="secondary", pill=True) if cached else None,
                ],
                className="mt-1",
            ),
        ]
    )


# ── 3) Alert polling ──
@app.callback(
    [
        Output("alert-list", "children"),
        Output("alert-count-badge", "children"),
        Output("navbar-alert-text", "children"),
        Output("active-alerts-store", "data"),
    ],
    Input("alert-timer", "n_intervals"),
    State("auth-session-store", "data"),
)
def update_alerts(_, auth_session):
    response = api_get("/alerts", token=extract_access_token(auth_session), params={"limit": 50})
    if not response.get("ok"):
        return (
            html.P([icon("check-circle", "me-1"), "No alerts available."], className="text-muted mb-0"),
            "0",
            "0 alerts",
            [],
        )

    data = response.get("data") or {}
    alerts = data.get("alerts", [])
    active_count = data.get("active_count", 0)
    badge_text = f"{active_count} alert{'s' if active_count != 1 else ''}"

    if not alerts:
        return (
            html.P([icon("check-circle", "me-1 text-success"), " All clear."], className="text-muted mb-0"),
            "0",
            badge_text,
            [],
        )

    items = []
    for a in alerts:
        sev = a.get("severity", "medium")
        status = a.get("status", "active")
        risk_val = a.get("risk_value", 0)
        affected_trees = a.get("affected_cells", [])
        items.append(
            dbc.ListGroupItem(
                [
                    html.Div(
                        [
                            dbc.Badge(sev.upper(), color=SEVERITY_BADGE.get(sev, "secondary"), className="me-1"),
                            dbc.Badge(
                                status.title(),
                                color="success" if status == "active" else "dark",
                                className="me-2",
                            ),
                            html.Span(f"Risk: {risk_val:.0%}" if isinstance(risk_val, (int, float)) else "", className="fw-medium"),
                        ],
                        className="d-flex align-items-center",
                    ),
                    html.Small(a.get("message", ""), className="text-muted d-block mt-1"),
                    html.Small(
                        [icon("tree-fill", "me-1"), f"{len(affected_trees)} trees affected"],
                        className="text-muted",
                    ),
                ],
                className="py-2",
            )
        )
    return dbc.ListGroup(items, flush=True), str(active_count), badge_text, alerts


# ── 4) Submit observation ──
@app.callback(
    Output("obs-result", "children"),
    Input("obs-submit-btn", "n_clicks"),
    [
        State("obs-tree-id", "value"),
        State("obs-pest", "value"),
        State("obs-severity", "value"),
        State("obs-observer", "value"),
        State("obs-notes", "value"),
        State("auth-session-store", "data"),
    ],
    prevent_initial_call=True,
)
def submit_observation(n, tree_id, pest, severity, observer, notes, auth_session):
    normalized_tree_id = normalize_tree_id_input(tree_id)
    if not normalized_tree_id:
        return dbc.Alert(
            [icon("exclamation-circle", "me-2"), "Tree ID is required."],
            color="warning", duration=4000, className="py-2 mb-0",
        )
    if pest not in {"cecid", "fruitfly"}:
        return dbc.Alert(
            [icon("exclamation-circle", "me-2"), "Choose a supported pest type before submitting."],
            color="warning", duration=4000, className="py-2 mb-0",
        )
    body = {
        "tree_id": normalized_tree_id,
        "observed_pest": pest,
        "severity": severity or 0.5,
        "observer_id": observer or "dashboard_user",
        "notes": notes or "",
        "timestamp": dt.datetime.utcnow().isoformat(),
    }
    response = api_post(
        "/observations/submit-observation",
        json_body=body,
        token=extract_access_token(auth_session),
    )
    if response.get("ok"):
        return dbc.Alert(
            [icon("check-circle", "me-2"), "Observation submitted successfully."],
            color="success", duration=4000, className="py-2 mb-0",
        )
    return dbc.Alert(
        [icon("x-circle", "me-2"), "Submission failed — check API."],
        color="danger", duration=4000, className="py-2 mb-0",
    )


# ── 4b) Auto-suggest pest type based on orchard stage ──
@app.callback(
    [
        Output("pest-type", "value"),
        Output("sim-status", "children", allow_duplicate=True),
    ],
    Input("orchard-stage", "value"),
    State("pest-type", "value"),
    prevent_initial_call=True,
)
def auto_suggest_pest_type(stage, current_pest):
    """
    Automatically suggest the appropriate pest type based on orchard phenological stage.
    Based on 2022-2025 historical data calibration:
    - FRUITLET stage: Cecid Fly emerges to infest young fruitlets
    - MATURE stage: Fruit Fly attracted to ripe fruit
    """
    if stage == "fruitlet":
        suggested = "cecid"
        msg = dbc.Alert(
            [icon("info-circle", "me-2"), 
             html.Strong("Stage: Fruitlet"), " — Cecid Fly (Gall Midge) is active during this stage. "
             "Larvae emerge from soil after rainfall to infest young fruitlets."],
            color="info", className="py-2 mb-0 small", dismissable=True,
        )
    elif stage == "mature":
        suggested = "fruitfly"
        msg = dbc.Alert(
            [icon("info-circle", "me-2"),
             html.Strong("Stage: Mature"), " — Fruit Fly is active during this stage. "
             "Attracted to ripe fruit (sugar index increases with days since flowering)."],
            color="info", className="py-2 mb-0 small", dismissable=True,
        )
    elif stage in ("dormant", "flowering"):
        # Keep current pest but warn that neither will be active
        suggested = current_pest
        msg = dbc.Alert(
            [icon("exclamation-triangle", "me-2"),
             html.Strong(f"Stage: {stage.title()}"), " — Neither pest is active in this stage. "
             "No dispersal will occur during simulation."],
            color="warning", className="py-2 mb-0 small", dismissable=True,
        )
    else:
        suggested = current_pest
        msg = no_update
    
    return suggested, msg


# ── 5) Run simulation → store + map + stats + playback ──
@app.callback(
    [
        Output("sim-data-store", "data"),
        Output("sim-status", "children"),
        Output("risk-map", "figure"),
        Output("playback-slider", "max"),
        Output("playback-slider", "marks"),
        Output("playback-slider", "disabled"),
        Output("playback-slider", "value"),
        Output("playback-frames-store", "data"),  # Pre-computed frame data for smooth animation
    ],
    Input("run-sim-btn", "n_clicks"),
    [
        State("pest-type", "value"),
        State("sim-hours", "value"),
        State("orchard-stage", "value"),
        State("days-flowering", "value"),
        State("neighbor-threat", "value"),
        State("sim-data-store", "data"),  # For tree status overrides
        State("auth-session-store", "data"),
    ],
    prevent_initial_call=True,
)
def run_simulation(n, pest_type, hours_str, orchard_stage, days_flowering, neighbor_threat, sim_data, auth_session):
    hours = int(hours_str)
    # Bagging is now applied via Tree Management status overrides.
    bagged_tree_ids = []
    
    # Get tree overrides from sim_data (set via Tree Management modal)
    tree_overrides = None
    if sim_data and isinstance(sim_data, dict):
        tree_overrides = sim_data.get("tree_overrides")

    # Build request body with phenology parameters
    body = {
        "pest_type": pest_type,
        "orchard_geojson": DEFAULT_ORCHARD,
        "hours": hours,
        "bagged_tree_ids": bagged_tree_ids,
        "risk_threshold": 0.7,
        "orchard_stage": orchard_stage,
        "days_since_flowering": int(days_flowering) if days_flowering else 60,
        "neighbor_threat": float(neighbor_threat) if neighbor_threat else 0.0,
    }
    
    # Add tree overrides if present
    if tree_overrides:
        body["tree_overrides"] = tree_overrides

    response = api_post(
        "/simulation/run-simulation",
        json_body=body,
        token=extract_access_token(auth_session),
    )
    if not response.get("ok"):
        err = dbc.Alert(
            [icon("x-octagon", "me-2"), "Simulation failed — is the API server running?"],
            color="danger", className="py-2",
        )
        return (no_update, err, no_update, no_update, no_update, no_update,
                no_update, no_update)

    resp = response.get("data") or {}
    # Extract response fields
    risk_geojson = resp.get("risk_geojson")
    peak = resp.get("peak_risk", 0)
    trees_at_risk = resp.get("cells_at_risk", 0)
    infested = resp.get("n_infested_final", 0)
    ts = resp.get("time_series", [])

    pest_label = "Cecid Fly" if pest_type == "cecid" else "Fruit Fly"
    # Build map with heatmap layer to show thermal spread
    fig_map = build_risk_map(risk_geojson, title=f"{pest_label} — {hours}h Risk Forecast", show_heatmap_layer=True)

    # Playback marks — use timestep (elapsed hours), NOT hour-of-day
    n_steps = len(ts)
    if n_steps > 0:
        step_interval = max(1, n_steps // 6)
        marks = {}
        for i in range(0, n_steps, step_interval):
            elapsed = ts[i].get("timestep", i)
            marks[i] = f"{elapsed} h"
        last_elapsed = ts[-1].get("timestep", n_steps - 1)
        marks[n_steps - 1] = f"{last_elapsed} h"
    else:
        marks = {0: "0 h"}
        n_steps = 1

    # Pre-compute all frame data for smooth clientside playback
    # State-to-color mapping for special states (others use risk-based coloring)
    STATE_COLOR_MAP = {
        "dead": "#424242",
        "bagged": "#3b82f6",
        "history_infected": "#ff9800",
        "suspect": "#9c27b0",
        "infested": "#ef4444",
    }
    
    playback_frames = []
    for i, snap in enumerate(ts):
        gj = snap.get("risk_geojson")
        lons, lats, risks, texts, states = [], [], [], [], []
        if gj and "features" in gj:
            for feat in gj["features"]:
                props = feat.get("properties", {})
                geom_type = feat["geometry"]["type"]
                if geom_type == "Point":
                    clon, clat = feat["geometry"]["coordinates"][:2]
                else:
                    coords = feat["geometry"]["coordinates"][0]
                    clon = float(np.mean([c[0] for c in coords]))
                    clat = float(np.mean([c[1] for c in coords]))
                risk = props.get("risk", 0)
                state = props.get("state", "empty")
                lons.append(clon)
                lats.append(clat)
                risks.append(risk)
                states.append(state)
                texts.append(
                    f"<b>({props.get('row')}, {props.get('col')})</b><br>"
                    f"State: {state.replace('_', ' ').title()}<br>"
                    f"Risk: {risk:.0%}<br>"
                    f"Tree: {props.get('tree_id') or '—'}"
                )
        weather = snap.get("weather", {})
        playback_frames.append({
            "lon": lons,
            "lat": lats,
            "z": risks,
            "states": states,  # Include states for color mapping
            "state_colors": STATE_COLOR_MAP,  # Include color map for clientside
            "text": texts,
            "timestep": snap.get("timestep", i),
            "n_infested": snap.get("n_infested", 0),
            "n_new": snap.get("n_new", 0),
            "temp": weather.get("temperature_c"),
            "wind": weather.get("wind_speed_ms"),
        })

    # Get phenology info from metadata for display
    metadata = resp.get("metadata", {})
    stage_display = metadata.get("orchard_stage", orchard_stage).title()
    sugar_idx = metadata.get("sugar_index", 0)
    
    done_msg = dbc.Alert(
        [
            icon("check-circle-fill", "me-2"), 
            html.Span([
                html.Strong("Simulation complete"), f" — ID: {resp.get('run_id', '?')}",
                html.Br(),
                html.Small([
                    f"Stage: {stage_display} | ",
                    f"Sugar Index: {sugar_idx:.2f} | " if sugar_idx else "",
                    f"Neighbor Threat: {neighbor_threat:.0%}" if neighbor_threat else "Neighbor Threat: None"
                ], className="text-muted"),
            ]),
        ],
        color="success", duration=8000, className="py-2",
    )

    return (
        resp,                       # store
        done_msg,                   # status
        fig_map,                    # map
        max(n_steps - 1, 0),        # slider max
        marks,                      # slider marks
        n_steps <= 1,               # slider disabled
        0,                          # slider reset
        playback_frames,            # pre-computed frame data for clientside playback
    )


def _extract_heatmap_data(geojson):
    """Extract lon, lat, risk arrays from a risk geojson for trace updates."""
    lons, lats, risks, texts = [], [], [], []
    if geojson and "features" in geojson:
        for feat in geojson["features"]:
            props = feat.get("properties", {})
            geom_type = feat["geometry"]["type"]
            if geom_type == "Point":
                clon, clat = feat["geometry"]["coordinates"][:2]
            else:
                coords = feat["geometry"]["coordinates"][0]
                clon = np.mean([c[0] for c in coords])
                clat = np.mean([c[1] for c in coords])
            risk = props.get("risk", 0)
            state = props.get("state", "empty")
            lons.append(clon)
            lats.append(clat)
            risks.append(risk)
            texts.append(
                f"<b>({props.get('row')}, {props.get('col')})</b><br>"
                f"State: {state}<br>"
                f"Risk: {risk:.0%}<br>"
                f"Tree: {props.get('tree_id') or '—'}"
            )
    return lons, lats, risks, texts


# ── 6) Playback: CLIENTSIDE callback for smooth map updates (no server round-trip) ──
app.clientside_callback(
    """
    function(step, frames, currentFig) {
        // Return no_update if no data
        if (!frames || frames.length === 0 || step >= frames.length) {
            return window.dash_clientside.no_update;
        }
        
        const frame = frames[step];
        const stateColors = frame.state_colors || {};
        
        // Compute marker colors based on state (special states get fixed colors, others use risk)
        const colors = [];
        for (let i = 0; i < frame.z.length; i++) {
            const state = frame.states ? frame.states[i] : '';
            if (stateColors[state]) {
                // Use fixed color for special states (dead, bagged, etc.)
                colors.push(stateColors[state]);
            } else {
                // Use risk value for colorscale (will be interpreted by Plotly)
                colors.push(frame.z[i]);
            }
        }
        
        // Deep clone the current figure to avoid mutation issues
        const fig = JSON.parse(JSON.stringify(currentFig));
        
        // Update Densitymapbox trace (index 0) if it exists
        if (fig.data && fig.data[0]) {
            fig.data[0].lon = frame.lon;
            fig.data[0].lat = frame.lat;
            fig.data[0].z = frame.z;
        }
        
        // Update Scattermapbox trace (index 1) if it exists
        if (fig.data && fig.data[1]) {
            fig.data[1].lon = frame.lon;
            fig.data[1].lat = frame.lat;
            fig.data[1].marker.color = colors;
            fig.data[1].text = frame.text;
        }
        
        // Update title
        if (fig.layout && fig.layout.title) {
            fig.layout.title.text = "Hour " + frame.timestep + " — Spread Animation";
        }
        
        // Preserve map state (viewport, zoom) with uirevision
        if (fig.layout) {
            fig.layout.uirevision = 'constant';
        }
        
        return fig;
    }
    """,
    Output("risk-map", "figure", allow_duplicate=True),
    Input("playback-slider", "value"),
    [State("playback-frames-store", "data"), State("risk-map", "figure")],
    prevent_initial_call=True,
)

# ── 6b) Playback info panel (server-side, only updates text) ──
@app.callback(
    Output("playback-info", "children"),
    Input("playback-slider", "value"),
    State("playback-frames-store", "data"),
    prevent_initial_call=True,
)
def update_playback_info(step, frames):
    if not frames or step >= len(frames):
        return ""
    frame = frames[step]
    elapsed = frame.get("timestep", step)
    n_infested = frame.get("n_infested", 0)
    n_new = frame.get("n_new", 0)
    temp = frame.get("temp")
    wind = frame.get("wind")
    
    info_parts = [
        html.Span([icon("clock", "me-1"), f"Hour {elapsed}"]),
        html.Span([icon("virus", "me-1"), f"Infested: {n_infested}"]),
        html.Span([icon("plus-circle", "me-1"), f"New: {n_new}"]),
    ]
    if temp is not None:
        info_parts.append(html.Span([icon("thermometer-half", "me-1"), f"{temp:.1f}°C"]))
    if wind is not None:
        info_parts.append(html.Span([icon("wind", "me-1"), f"{wind:.1f} m/s"]))

    return html.Div(
        [html.Span(p, className="me-3") for p in info_parts],
        className="d-flex flex-wrap justify-content-center gap-1",
    )


# ── 6c) Decision Support Summary — updates when sim data changes ──
@app.callback(
    [
        Output("ds-zone1-pct", "children"),
        Output("ds-zone2-pct", "children"),
        Output("ds-zone3-pct", "children"),
        Output("ds-pesticide-reduction", "children"),
        Output("ds-money-saved", "children"),
        Output("ds-summary-message", "children"),
    ],
    Input("sim-data-store", "data"),
    prevent_initial_call=True,
)
def update_decision_support_summary(sim_data):
    """
    Compute and display Decision Support metrics.
    
    This is a pure interpretation layer — it reads the final risk values
    and produces management recommendations without modifying simulation data.
    """
    if not sim_data:
        return "—", "—", "—", "—", "—", ""
    
    # Extract risk GeoJSON from simulation response
    risk_geojson = sim_data.get("risk_geojson")
    if not risk_geojson:
        return "—", "—", "—", "—", "—", dbc.Alert(
            "No risk data available", color="secondary", className="py-1 small"
        )
    
    try:
        # Compute metrics using the decision support module
        metrics = compute_decision_metrics(risk_geojson)
        formatted = format_metrics_summary(metrics)
        
        # Zone percentages with tree counts
        zone1_text = f"{formatted['safe_percentage']} ({formatted['safe_cells']} trees)"
        zone2_text = f"{formatted['monitor_percentage']} ({formatted['monitor_cells']} trees)"
        zone3_text = f"{formatted['spray_percentage']} ({formatted['spray_cells']} trees)"
        
        # Generate summary message based on risk levels
        if metrics.spray_percentage >= 0.5:
            summary_msg = dbc.Alert([
                icon("exclamation-triangle-fill", "me-2"),
                html.Strong("High Alert: "),
                f"{metrics.spray_percentage:.0%} of farm requires immediate action. "
                "Deploy spray teams to critical zones."
            ], color="danger", className="py-2 mb-0 small")
        elif metrics.spray_percentage >= 0.2:
            summary_msg = dbc.Alert([
                icon("shield-exclamation", "me-2"),
                html.Strong("Moderate Risk: "),
                f"Only {metrics.spray_percentage:.0%} requires spraying. "
                f"Precision targeting saves {formatted['pesticide_reduction']} pesticide."
            ], color="warning", className="py-2 mb-0 small")
        elif metrics.spray_percentage > 0:
            summary_msg = dbc.Alert([
                icon("shield-check", "me-2"),
                html.Strong("Low Risk: "),
                f"Only {metrics.spray_percentage:.0%} at critical level. "
                f"Targeted intervention recommended."
            ], color="info", className="py-2 mb-0 small")
        else:
            summary_msg = dbc.Alert([
                icon("check-circle-fill", "me-2"),
                html.Strong("All Clear: "),
                "No critical zones detected. Continue routine monitoring."
            ], color="success", className="py-2 mb-0 small")
        
        return (
            zone1_text,
            zone2_text,
            zone3_text,
            formatted["pesticide_reduction"],
            formatted["estimated_savings"],
            summary_msg,
        )
        
    except Exception as e:
        # Decision Support Layer failure should not affect simulation
        print(f"[Decision Support] Error computing metrics: {e}")
        return "—", "—", "—", "—", "—", dbc.Alert(
            f"Metrics unavailable: {str(e)}", color="secondary", className="py-1 small"
        )


# ── 7) Play / pause toggle ──
@app.callback(
    [Output("is-playing", "data"), Output("pb-play", "children"), Output("play-interval", "disabled")],
    Input("pb-play", "n_clicks"),
    State("is-playing", "data"),
    prevent_initial_call=True,
)
def toggle_play(_, playing):
    new_state = not playing
    if new_state:
        label = [icon("pause-fill"), " Pause"]
    else:
        label = [icon("play-fill"), " Play"]
    return new_state, label, not new_state


# ── 8) Auto-advance on play interval ──
@app.callback(
    Output("playback-slider", "value", allow_duplicate=True),
    Input("play-interval", "n_intervals"),
    [State("playback-slider", "value"), State("playback-slider", "max"), State("is-playing", "data")],
    prevent_initial_call=True,
)
def auto_advance(_, current, max_val, playing):
    if not playing:
        return no_update
    nxt = current + 1
    return 0 if nxt > max_val else nxt


# ── 9) Prev / Next buttons ──
@app.callback(
    Output("playback-slider", "value", allow_duplicate=True),
    [Input("pb-prev", "n_clicks"), Input("pb-next", "n_clicks")],
    [State("playback-slider", "value"), State("playback-slider", "max")],
    prevent_initial_call=True,
)
def step_buttons(prev_n, next_n, current, max_val):
    trigger = callback_context.triggered_id
    if trigger == "pb-prev":
        return max(current - 1, 0)
    elif trigger == "pb-next":
        return min(current + 1, max_val)
    return no_update


# ── 10) Evaluate — uses correct confusion matrix keys ──
@app.callback(
    Output("eval-results", "children"),
    Input("eval-btn", "n_clicks"),
    State("eval-threshold", "value"),
    State("auth-session-store", "data"),
    prevent_initial_call=True,
)
def run_evaluation(_, threshold, auth_session):
    response = api_get(
        "/evaluation/evaluate",
        token=extract_access_token(auth_session),
        params={"risk_threshold": threshold or 0.5},
    )
    if not response.get("ok"):
        return dbc.Alert(
            [icon("info-circle", "me-2"), "Evaluation unavailable — need observations + a simulation run."],
            color="warning", className="py-2 mb-0",
        )

    data = response.get("data") or {}
    cm = data.get("confusion_matrix", {})
    metrics = [
        ("Precision", data.get("precision"), "bullseye"),
        ("Recall", data.get("recall"), "search"),
        ("F1 Score", data.get("f1_score"), "trophy"),
        ("Accuracy", data.get("accuracy"), "check2-circle"),
        ("Spatial IoU", data.get("spatial_overlap_percentage"), "bounding-box"),
    ]
    return html.Div(
        [
            dbc.Table(
                [
                    html.Thead(html.Tr([html.Th("Metric"), html.Th("Value")]), className="table-light"),
                    html.Tbody(
                        [
                            html.Tr([
                                html.Td([icon(ico, "me-2 text-muted"), name]),
                                html.Td(f"{val:.2%}" if isinstance(val, (int, float)) else "—"),
                            ])
                            for name, val, ico in metrics
                        ]
                    ),
                ],
                bordered=True,
                hover=True,
                size="sm",
                className="mb-2",
            ),
            html.Small(
                [
                    icon("grid", "me-1"),
                    f"TP={cm.get('true_positives', 0)}  "
                    f"FP={cm.get('false_positives', 0)}  "
                    f"FN={cm.get('false_negatives', 0)}  "
                    f"TN={cm.get('true_negatives', 0)}",
                ],
                className="text-muted font-monospace",
            ),
        ]
    )



# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Historical Validation - Data Loading + Rendering
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.callback(
    [
        Output("validation-summary-store", "data"),
        Output("validation-metrics-explanation-store", "data"),
    ],
    Input("validation-run-btn", "id"),
    State("auth-session-store", "data"),
    prevent_initial_call=False,
)
def load_validation_reference_data(_, auth_session):
    """Load validation metadata used by the presentation panel."""
    token = extract_access_token(auth_session)
    historical_response = api_get("/validation/historical-data", token=token, timeout=30)
    metrics_response = api_get("/validation/metrics-explanation", token=token, timeout=30)
    return (
        historical_response.get("data"),
        metrics_response.get("data"),
    )


@app.callback(
    Output("validation-cases-store", "data"),
    [
        Input("validation-pest-filter", "value"),
        Input("validation-year-filter", "value"),
        Input("validation-max-cases", "value"),
    ],
    State("auth-session-store", "data"),
    prevent_initial_call=False,
)
def load_validation_case_preview(pest_types, years, max_cases, auth_session):
    """Preview eligible historical cases for the current validation filters."""
    selected_pests = ensure_list(pest_types)
    selected_years = sorted(int(year) for year in ensure_list(years))
    safe_max_cases = max(1, min(int(max_cases or 12), 100))

    query_params: dict[str, str | int] = {"max_cases": safe_max_cases}
    if selected_pests:
        query_params["pest_types"] = ",".join(selected_pests)
    if selected_years:
        query_params["years"] = ",".join(str(year) for year in selected_years)

    response = api_get(
        "/validation/cases",
        token=extract_access_token(auth_session),
        params=query_params,
        timeout=60,
    )
    if not response.get("ok"):
        return {
            "error": auth_error_message(response, "Unable to load filtered historical validation cases from the API."),
            "total_cases": 0,
            "cases": [],
        }
    return response.get("data")


@app.callback(
    [
        Output("validation-latest-result-store", "data"),
        Output("validation-run-feedback", "children"),
    ],
    Input("validation-run-btn", "n_clicks"),
    [
        State("validation-pest-filter", "value"),
        State("validation-year-filter", "value"),
        State("validation-max-cases", "value"),
        State("validation-hours", "value"),
        State("validation-monte-carlo-runs", "value"),
        State("auth-session-store", "data"),
    ],
    prevent_initial_call=True,
)
def run_historical_validation(n_clicks, pest_types, years, max_cases, hours, monte_carlo_runs, auth_session):
    """Run historical validation and cache the latest successful response."""
    if not n_clicks:
        return no_update, no_update

    selected_pests = ensure_list(pest_types)
    selected_years = sorted(int(year) for year in ensure_list(years))
    payload = {
        "max_cases": max(1, min(int(max_cases or 12), 100)),
        "pest_types": selected_pests or None,
        "years": selected_years or None,
        "hours": max(24, min(int(hours or 48), 168)),
        "monte_carlo_runs": max(10, min(int(monte_carlo_runs or 20), 100)),
    }

    response = api_post(
        "/validation/run",
        json_body=payload,
        token=extract_access_token(auth_session),
        timeout=600,
    )
    if not response.get("ok"):
        return (
            no_update,
            dbc.Alert(
                [
                    icon("x-octagon", "me-2"),
                    auth_error_message(response, "Historical validation failed. The latest successful result remains cached."),
                ],
                color="danger",
                className="py-2 mb-0",
            ),
        )

    response = response.get("data") or {}
    response["request"] = {
        "max_cases": payload["max_cases"],
        "pest_types": selected_pests,
        "years": selected_years,
        "hours": payload["hours"],
        "monte_carlo_runs": payload["monte_carlo_runs"],
    }

    summary = response.get("summary", {})
    duration_seconds = float(response.get("duration_seconds", 0.0) or 0.0)
    completed_at = response.get("completed_at", "")
    completed_label = completed_at.replace("T", " ")[:19] if completed_at else "N/A"

    feedback = dbc.Alert(
        [
            html.Div(
                [
                    icon("check-circle-fill", "me-2"),
                    html.Strong("Historical validation completed."),
                    html.Span(
                        f" {summary.get('total_tests', 0)} case(s) processed in {duration_seconds:.1f} seconds."
                    ),
                ],
                className="d-flex align-items-center flex-wrap gap-1",
            ),
            html.Small(
                f"Completed at {completed_label}. Overall accuracy: {summary.get('overall_accuracy_pct', 0):.1f}%. "
                "These results summarize agreement with historical records and should not be treated as a guarantee of future field performance.",
                className="d-block mt-1",
            ),
        ],
        color="success",
        className="py-2 mb-0",
    )
    return response, feedback


@app.callback(
    Output("validation-dataset-summary", "children"),
    [
        Input("validation-summary-store", "data"),
        Input("validation-cases-store", "data"),
    ],
)
def render_validation_dataset_summary(summary_data, cases_data):
    """Render dataset context and filtered case preview."""
    return build_validation_dataset_summary(summary_data, cases_data)


@app.callback(
    Output("validation-results-content", "children"),
    [
        Input("validation-latest-result-store", "data"),
        Input("validation-metrics-explanation-store", "data"),
        Input("validation-cases-store", "data"),
    ],
)
def render_validation_results(validation_data, explanation_data, cases_data):
    """Render KPI cards, charts, confusion matrix, and the historical results table."""
    classification_notes = (explanation_data or {}).get("classification_metrics", {})
    regression_notes = (explanation_data or {}).get("regression_metrics", {})

    accuracy_note = classification_notes.get("accuracy", {}).get(
        "interpretation",
        "Higher values indicate stronger historical agreement.",
    )
    precision_note = classification_notes.get("precision", {}).get(
        "interpretation",
        "High precision means fewer false alarms.",
    )
    recall_note = classification_notes.get("recall", {}).get(
        "interpretation",
        "High recall means fewer missed outbreaks.",
    )
    f1_note = classification_notes.get("f1_score", {}).get(
        "interpretation",
        "Balanced measure of precision and recall.",
    )
    specificity_note = classification_notes.get("specificity", {}).get(
        "interpretation",
        "High specificity means safe periods are identified correctly.",
    )
    mae_note = regression_notes.get("mae", {}).get(
        "interpretation",
        "Lower MAE indicates smaller average prediction error.",
    )
    rmse_note = regression_notes.get("rmse", {}).get(
        "interpretation",
        "RMSE closer to 0 means smaller prediction error.",
    )
    r_squared_note = regression_notes.get("r_squared", {}).get(
        "interpretation",
        "Higher values indicate the model explains more historical variation.",
    )

    if not validation_data:
        preview_cases = (cases_data or {}).get("cases", []) if isinstance(cases_data, dict) else []
        preview_total = (cases_data or {}).get("total_cases", 0) if isinstance(cases_data, dict) else 0
        return html.Div(
            [
                dbc.Alert(
                    [
                        icon("info-circle", "me-2"),
                        html.Strong("Historical validation has not been run yet."),
                        html.Span(
                            f" The current filters expose {preview_total} eligible historical case(s) from BPI records."
                        ),
                    ],
                    color="info",
                    className="py-2",
                ),
                dbc.Card(
                    [
                        dbc.CardHeader(
                            html.Div(
                                [icon("table", "me-2"), html.Span("Historical Case Preview", className="fw-semibold")],
                                className="d-flex align-items-center",
                            ),
                            className="py-2",
                        ),
                        dbc.CardBody(
                            [
                                html.Small(
                                    "These are real historical cases selected by the current filters. Run validation to compute the formal metrics, confusion matrix, and charts.",
                                    className="text-muted d-block mb-2",
                                ),
                                build_case_preview_table(preview_cases, limit=8),
                            ],
                            className="py-2",
                        ),
                    ],
                    className="shadow-sm border-0",
                ),
            ]
        )

    summary = validation_data.get("summary", {})
    classification_metrics = validation_data.get("classification_metrics", {})
    regression_metrics = validation_data.get("regression_metrics", {})
    confusion_matrix = validation_data.get("confusion_matrix", {})
    results = validation_data.get("results", [])
    request_details = validation_data.get("request", {})

    selected_pests = request_details.get("pest_types") or []
    selected_years = request_details.get("years") or []
    pest_text = ", ".join(validation_pest_label(pest) for pest in selected_pests) if selected_pests else "All supported pests"
    year_text = ", ".join(str(year) for year in selected_years) if selected_years else "All available years"
    completed_at = validation_data.get("completed_at", "")
    completed_label = completed_at.replace("T", " ")[:19] if completed_at else "N/A"

    kpi_cards = dbc.Row(
        [
            make_validation_metric_card(
                "Total Validation Cases",
                str(summary.get("total_tests", 0)),
                "Historical BPI records included in this validation run.",
                color="secondary",
            ),
            make_validation_metric_card(
                "Correct Predictions",
                str(summary.get("correct_predictions", 0)),
                "Cases where predicted and historical risk levels agreed.",
                color="success",
            ),
            make_validation_metric_card(
                "Incorrect Predictions",
                str(summary.get("incorrect_predictions", 0)),
                "Cases where the model and historical label differed.",
                color="danger",
            ),
            make_validation_metric_card(
                "Overall Accuracy",
                f"{float(summary.get('overall_accuracy_pct', 0.0)):.1f}%",
                accuracy_note,
                color="primary",
            ),
            make_validation_metric_card(
                "Precision",
                format_validation_rate(classification_metrics.get("precision")),
                precision_note,
                color="info",
            ),
            make_validation_metric_card(
                "Recall",
                format_validation_rate(classification_metrics.get("recall")),
                recall_note,
                color="warning",
            ),
            make_validation_metric_card(
                "F1-Score",
                format_validation_rate(classification_metrics.get("f1_score")),
                f1_note,
                color="primary",
            ),
            make_validation_metric_card(
                "Specificity",
                format_validation_rate(classification_metrics.get("specificity")),
                specificity_note,
                color="secondary",
            ),
            make_validation_metric_card(
                "MAE",
                format_validation_scalar(regression_metrics.get("mae")),
                mae_note,
                color="dark",
            ),
            make_validation_metric_card(
                "RMSE",
                format_validation_scalar(regression_metrics.get("rmse")),
                rmse_note,
                color="dark",
            ),
            make_validation_metric_card(
                "R-squared",
                format_validation_scalar(regression_metrics.get("r_squared")),
                r_squared_note,
                color="dark",
            ),
        ],
        className="g-2 mb-2",
    )

    confusion_and_pests = dbc.Row(
        [
            dbc.Col(build_confusion_matrix_panel(confusion_matrix), lg=5),
            dbc.Col(
                dbc.Row(
                    [
                        dbc.Col(
                            build_pest_metric_card(
                                "Fruit Fly (Bactrocera)",
                                validation_data.get("fruit_fly_metrics"),
                                "primary",
                            ),
                            md=6,
                        ),
                        dbc.Col(
                            build_pest_metric_card(
                                "Cecid Fly (Gall Midge)",
                                validation_data.get("cecid_fly_metrics"),
                                "warning",
                            ),
                            md=6,
                        ),
                    ],
                    className="g-2",
                ),
                lg=7,
            ),
        ],
        className="mb-3 g-2",
    )

    chart_row = dbc.Row(
        [
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            html.Div(
                                [icon("bar-chart", "me-2"), html.Span("Validation Metric Summary", className="fw-semibold")],
                                className="d-flex align-items-center",
                            ),
                            className="py-2",
                        ),
                        dbc.CardBody(
                            dcc.Graph(
                                id="validation-metric-chart",
                                figure=build_validation_metric_chart(validation_data),
                                config={"displayModeBar": False},
                            ),
                            className="py-2",
                        ),
                    ],
                    className="shadow-sm border-0 h-100",
                ),
                lg=6,
            ),
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardHeader(
                            html.Div(
                                [icon("bar-chart-line", "me-2"), html.Span("Match vs Mismatch by Pest", className="fw-semibold")],
                                className="d-flex align-items-center",
                            ),
                            className="py-2",
                        ),
                        dbc.CardBody(
                            dcc.Graph(
                                id="validation-match-chart",
                                figure=build_validation_match_chart(results),
                                config={"displayModeBar": False},
                            ),
                            className="py-2",
                        ),
                    ],
                    className="shadow-sm border-0 h-100",
                ),
                lg=6,
            ),
        ],
        className="mb-3 g-2",
    )

    comparison_chart = dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [icon("diagram-3", "me-2"), html.Span("Normalized Historical vs Predicted Risk", className="fw-semibold")],
                    className="d-flex align-items-center",
                ),
                className="py-2",
            ),
            dbc.CardBody(
                [
                    html.Small(
                        "This comparison normalizes the historical pest value to a 0-1 scale so it can be compared directly with predicted risk.",
                        className="text-muted d-block mb-2",
                    ),
                    dcc.Graph(
                        id="validation-comparison-chart",
                        figure=build_validation_comparison_chart(results),
                        config={"displayModeBar": False},
                    ),
                ],
                className="py-2",
            ),
        ],
        className="shadow-sm border-0 mb-3",
    )

    results_table_card = dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [icon("table", "me-2"), html.Span("Latest Historical Validation Cases", className="fw-semibold")],
                    className="d-flex align-items-center",
                ),
                className="py-2",
            ),
            dbc.CardBody(
                [
                    html.Small(
                        "These rows come from historical BPI records used in the latest validation run; they are not fabricated sample outputs.",
                        className="text-muted d-block mb-2",
                    ),
                    build_validation_results_table(results),
                ],
                className="py-2",
            ),
        ],
        className="shadow-sm border-0",
    )

    return html.Div(
        [
            dbc.Alert(
                [
                    html.Div(
                        [
                            icon("journal-check", "me-2"),
                            html.Strong("Historical validation summary"),
                            html.Span(f" for {pest_text} across {year_text}."),
                        ],
                        className="d-flex align-items-center flex-wrap gap-1",
                    ),
                    html.Small(
                        f"Completed at {completed_label}. Historical validation indicates the model aligns reasonably with past pest activity patterns and provides evidence for decision-support use. Future accuracy still depends on environmental variability, data quality, and continued calibration.",
                        className="d-block mt-1",
                    ),
                ],
                color="light",
                className="border mb-3",
            ),
            kpi_cards,
            confusion_and_pests,
            chart_row,
            comparison_chart,
            results_table_card,
        ]
    )





# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Monitoring Tab - Callback
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.callback(
    [
        # KPI cards
        Output("mon-infestation-rate", "children"),
        Output("mon-infestation-bar", "children"),
        Output("mon-risk-score", "children"),
        Output("mon-risk-level", "children"),
        Output("mon-risk-level", "color"),
        Output("mon-infested-trees", "children"),
        Output("mon-infested-trees-detail", "children"),
        # Charts
        Output("mon-pest-trend-chart", "figure"),
        Output("mon-phenology-chart", "figure"),
        Output("mon-spread-chart", "figure"),
        # Environment
        Output("mon-env-current", "children"),
        Output("mon-env-trend-chart", "figure"),
        # Metadata
        Output("mon-last-updated", "children"),
        Output("monitoring-data-store", "data"),
    ],
    Input("monitoring-timer", "n_intervals"),
    Input("sim-data-store", "data"),
    State("auth-session-store", "data"),
    prevent_initial_call=False,
)
def update_monitoring_tab(_, sim_data, auth_session):
    """
    Compute monitoring metrics.
    When simulation data (sim_data) is available, extract metrics directly
    from the in-memory simulation results. Otherwise fall back to the
    monitoring API (database queries).
    """

    # ----- Defaults for all outputs -----
    EMPTY_FIG = go.Figure().update_layout(
        margin=dict(l=20, r=20, t=10, b=20), height=240,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#eee"), yaxis=dict(gridcolor="#eee"),
        annotations=[dict(text="No data available", xref="paper", yref="paper",
                          x=0.5, y=0.5, showarrow=False,
                          font=dict(size=14, color="#aaa"))],
    )

    # =====================================================
    #  Path A — Use SIMULATION DATA when available
    # =====================================================
    has_sim = (
        sim_data
        and isinstance(sim_data, dict)
        and sim_data.get("time_series")
        and sim_data.get("risk_geojson")
    )

    if has_sim:
        ts = sim_data.get("time_series", [])
        meta = sim_data.get("metadata", {})
        risk_gj = sim_data.get("risk_geojson", {})
        features = risk_gj.get("features", [])

        # Count trees & infested from final GeoJSON
        total_trees = len(features)
        infested_trees_from_geojson = sum(1 for f in features if f.get("properties", {}).get("state") == "infested")
        n_infested = sim_data.get("n_infested_final", infested_trees_from_geojson)
        rate = n_infested / max(total_trees, 1)

        # 1) Infestation Rate KPI
        rate_pct = f"{rate * 100:.1f}%"
        rate_bar = dbc.Progress(
            value=rate * 100, max=100,
            color="danger" if rate > 0.5 else "warning" if rate > 0.2 else "success",
            style={"height": "6px"}, className="w-100",
        )
        rate_content = html.Div([rate_bar, html.Small(f"{n_infested} / {total_trees} trees", className="text-muted")])

        # 2) Pest Risk Index KPI (from peak_risk)
        peak = sim_data.get("peak_risk", 0)
        risk_score = min(peak * 100, 100)
        if risk_score >= 75:
            risk_level = "critical"
        elif risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "moderate"
        else:
            risk_level = "low"
        risk_color_map = {"low": "success", "moderate": "info", "high": "warning", "critical": "danger"}
        risk_color = risk_color_map.get(risk_level, "secondary")
        risk_score_text = f"{risk_score:.0f} / 100"

        # 3) Active Alerts (derive from risk)
        active_alerts = 0
        by_sev = {}
        if risk_score >= 75:
            active_alerts = 2
            by_sev = {"critical": 1, "high": 1}
        elif risk_score >= 50:
            active_alerts = 1
            by_sev = {"high": 1}
        elif risk_score >= 25:
            active_alerts = 1
            by_sev = {"medium": 1}
        severity_badges = html.Div([
            dbc.Badge(f"{sev.title()}: {cnt}", color=SEVERITY_BADGE.get(sev, "secondary"),
                      pill=True, className="me-1", style={"fontSize": "0.7rem"})
            for sev, cnt in by_sev.items() if cnt > 0
        ]) if by_sev else ""

        # 4) Total Trees
        total_trees_text = str(total_trees)

        # 5) Estimated Loss at Risk (scenario-based planning estimate)
        if ts:
            loss_rows = []
            for i, s in enumerate(ts):
                loss_rows.append({
                    "x": s.get("timestep", i),
                    "infested_trees": s.get("n_infested", 0),
                })
            fig_trend = _build_loss_at_risk_chart(loss_rows, x_title="Elapsed Hours")
            if not fig_trend.data:
                fig_trend = EMPTY_FIG
        else:
            fig_trend = EMPTY_FIG

        # 6) Phenology Distribution
        stage = meta.get("orchard_stage", "mature")
        all_stages = ["dormant", "flowering", "fruitlet", "mature"]
        pheno_data = [{"stage": s, "count": (total_trees if s == stage else 0)} for s in all_stages]
        fig_pheno = _build_phenology_figure(pheno_data)
        if not fig_pheno.data:
            fig_pheno = EMPTY_FIG

        # 7) Infestation Spread (from time_series)
        if ts:
            spread_rows = [{"hour": s.get("timestep", i), "n_infested": s.get("n_infested", 0), "n_new": s.get("n_new", 0)} for i, s in enumerate(ts)]
            df_spread = pd.DataFrame(spread_rows)
            fig_spread = go.Figure()
            fig_spread.add_trace(go.Scatter(
                x=df_spread["hour"], y=df_spread["n_infested"], mode="lines", fill="tozeroy",
                fillcolor="rgba(244,67,54,0.15)", line=dict(color="#f44336", width=2), name="Total Infested",
            ))
            fig_spread.add_trace(go.Bar(
                x=df_spread["hour"], y=df_spread["n_new"], marker_color="rgba(255,152,0,0.6)", name="New / Hour",
            ))
            fig_spread.update_layout(
                margin=dict(l=20, r=20, t=10, b=30), height=240,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(title="Elapsed Hours", gridcolor="#eee"),
                yaxis=dict(title="Infested Trees", gridcolor="#eee"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                barmode="overlay",
            )
        else:
            fig_spread = EMPTY_FIG

        # 8) Infestation Hotspot Map (from risk_geojson)
        hs_lons, hs_lats, hs_sizes, hs_colors, hs_texts = [], [], [], [], []
        for feat in features:
            props = feat.get("properties", {})
            state = props.get("state", "")
            risk_val = props.get("risk", 0)
            geom = feat.get("geometry", {})
            if geom.get("type") == "Polygon":
                coords = geom["coordinates"][0]
                clon = sum(c[0] for c in coords) / len(coords)
                clat = sum(c[1] for c in coords) / len(coords)
            elif geom.get("type") == "Point":
                clon, clat = geom["coordinates"][:2]
            else:
                continue
            hs_lons.append(clon)
            hs_lats.append(clat)
            sz = max(6, min(risk_val * 20, 24))
            hs_sizes.append(sz)
            hs_colors.append(risk_val * 100)
            tid = props.get("tree_id") or "—"
            hs_texts.append(f"<b>{tid}</b><br>State: {state}<br>Risk: {risk_val:.0%}")

        if hs_lons:
            fig_hotspot = go.Figure()
            fig_hotspot.add_trace(go.Scattermap(
                lon=hs_lons, lat=hs_lats, mode="markers",
                marker=dict(size=hs_sizes, color=hs_colors, colorscale="YlOrRd", cmin=0, cmax=100,
                            colorbar=dict(title="Risk%", thickness=8, len=0.5), opacity=0.85),
                text=hs_texts, hoverinfo="text", name="Risk Hotspots",
            ))
            fig_hotspot.update_layout(
                map=dict(style=MAP_STYLE, center=dict(lat=np.mean(hs_lats), lon=np.mean(hs_lons)), zoom=18),
                margin=dict(l=0, r=0, t=0, b=0), height=240, paper_bgcolor="rgba(0,0,0,0)",
            )
        else:
            fig_hotspot = EMPTY_FIG

        # 9) Environmental (from time_series weather)
        env_temps, env_winds = [], []
        for s in ts:
            w = s.get("weather", {})
            if w.get("temperature_c") is not None:
                env_temps.append(w["temperature_c"])
            if w.get("wind_speed_ms") is not None:
                env_winds.append(w["wind_speed_ms"])

        def _env_metric(ico, label, value, unit):
            return dbc.Col(
                html.Div([
                    icon(ico, "text-muted fs-5"),
                    html.Div([
                        html.Small(label, className="text-muted d-block", style={"lineHeight": "1"}),
                        html.Span(f"{value:.1f} {unit}" if isinstance(value, (int, float)) else "—", className="fw-bold"),
                    ], className="ms-2"),
                ], className="d-flex align-items-center"),
                xs=6, md=3, className="mb-2",
            )

        last_temp = env_temps[-1] if env_temps else None
        last_wind = env_winds[-1] if env_winds else None
        env_content = dbc.Row([
            _env_metric("thermometer-half", "Temperature", last_temp, "°C"),
            _env_metric("wind", "Wind Speed", last_wind, "m/s"),
        ])

        if env_temps:
            fig_env = go.Figure()
            fig_env.add_trace(go.Scatter(
                x=list(range(len(env_temps))), y=env_temps, mode="lines",
                line=dict(color="#ef4444", width=2), name="Temp (°C)",
            ))
            if env_winds:
                fig_env.add_trace(go.Scatter(
                    x=list(range(len(env_winds))), y=env_winds, mode="lines",
                    line=dict(color="#3b82f6", width=2), name="Wind (m/s)", yaxis="y2",
                ))
            fig_env.update_layout(
                margin=dict(l=20, r=40, t=10, b=20), height=160,
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(title="Hour", gridcolor="#eee"),
                yaxis=dict(title="°C", gridcolor="#eee"),
                yaxis2=dict(title="m/s", overlaying="y", side="right", gridcolor="#eee"),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
        else:
            fig_env = EMPTY_FIG

        # Infested Trees KPI
        infested_trees_text = str(n_infested)
        infested_trees_detail = html.Small(f"{n_infested} / {total_trees} trees ({rate:.1%})", className="text-muted")

        now = dt.datetime.now().strftime("%H:%M:%S")
        return (
            rate_pct, rate_content, risk_score_text, risk_level.title(), risk_color,
            infested_trees_text, infested_trees_detail,
            fig_trend, fig_pheno, fig_spread,
            env_content, fig_env,
            f"Last updated: {now} (from simulation)",
            sim_data,
        )

    # =====================================================
    #  Path B — Fallback to API (database queries)
    # =====================================================
    response = api_get("/monitoring/metrics", token=extract_access_token(auth_session))

    if not response.get("ok"):
        now = dt.datetime.now().strftime("%H:%M:%S")
        return (
            "—", "", "—", "—", "secondary", "—", "",
            EMPTY_FIG, EMPTY_FIG, EMPTY_FIG,
            html.Small("No data — run a simulation", className="text-muted"),
            EMPTY_FIG,
            f"Waiting at {now}",
            None,
        )

    # ── Parse DB metrics ──
    data = response.get("data") or {}
    ir = data.get("infestation_rate", {})
    rate = ir.get("rate", 0)
    inf_trees = ir.get("infested_trees", 0)
    total_trees = ir.get("total_trees", 0)
    rate_pct = f"{rate * 100:.1f}%"
    rate_bar = dbc.Progress(
        value=rate * 100, max=100,
        color="danger" if rate > 0.5 else "warning" if rate > 0.2 else "success",
        style={"height": "6px"}, className="w-100",
    )
    rate_content = html.Div([rate_bar, html.Small(f"{inf_trees} / {total_trees} trees", className="text-muted")])

    ri = data.get("risk_index", {})
    risk_score = ri.get("score", 0)
    risk_level = ri.get("level", "low")
    risk_color_map = {"low": "success", "moderate": "info", "high": "warning", "critical": "danger"}
    risk_color = risk_color_map.get(risk_level, "secondary")
    risk_score_text = f"{risk_score:.0f} / 100"

    al = data.get("alert_summary", {})
    active_alerts = al.get("active", 0)
    by_sev = al.get("by_severity", {})
    severity_badges = html.Div([
        dbc.Badge(f"{sev.title()}: {cnt}", color=SEVERITY_BADGE.get(sev, "secondary"),
                  pill=True, className="me-1", style={"fontSize": "0.7rem"})
        for sev, cnt in by_sev.items() if cnt > 0
    ]) if by_sev else ""

    total_trees_text = str(total_trees)

    # Estimated Loss at Risk (scenario-based planning estimate)
    spread_for_loss = data.get("infestation_spread", [])
    if spread_for_loss:
        loss_rows = [
            {
                "x": row.get("date"),
                "infested_trees": row.get("cumulative", 0),
            }
            for row in spread_for_loss
        ]
        fig_trend = _build_loss_at_risk_chart(loss_rows, x_title="Date")
        if not fig_trend.data:
            fig_trend = EMPTY_FIG
    elif inf_trees:
        fig_trend = _build_loss_at_risk_chart(
            [{"x": "Current", "infested_trees": inf_trees}],
            x_title="Date",
        )
    else:
        fig_trend = EMPTY_FIG

    # Phenology
    pheno = data.get("phenology", [])
    if pheno:
        fig_pheno = _build_phenology_figure(pheno)
        if not fig_pheno.data:
            fig_pheno = EMPTY_FIG
    else:
        fig_pheno = EMPTY_FIG

    # Spread
    spread = data.get("infestation_spread", [])
    if spread:
        df_spread = pd.DataFrame(spread)
        fig_spread = go.Figure()
        fig_spread.add_trace(go.Scatter(x=df_spread["date"], y=df_spread["cumulative"], mode="lines", fill="tozeroy",
                                        fillcolor="rgba(244,67,54,0.15)", line=dict(color="#f44336", width=2), name="Cumulative"))
        fig_spread.add_trace(go.Bar(x=df_spread["date"], y=df_spread["new_count"], marker_color="rgba(255,152,0,0.6)", name="New / Day"))
        fig_spread.update_layout(margin=dict(l=20, r=20, t=10, b=30), height=240,
                                 paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                 xaxis=dict(title="Date", gridcolor="#eee"), yaxis=dict(title="Count", gridcolor="#eee"),
                                 legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), barmode="overlay")
    else:
        fig_spread = EMPTY_FIG

    # Hotspots
    hotspots = data.get("hotspots", [])
    if hotspots:
        h_lons, h_lats, h_sz, h_col, h_txt = [], [], [], [], []
        for hs in hotspots:
            x, y = hs.get("x"), hs.get("y")
            if x is not None and y is not None:
                h_lons.append(x); h_lats.append(y)
                lv = hs.get("avg_level", 0)
                h_sz.append(max(8, min(lv * 20, 30))); h_col.append(lv)
                h_txt.append(f"<b>Tree {hs.get('tree_id')}</b><br>Pest: {hs.get('pest_name', '—')}<br>Level: {lv:.1f}")
        if h_lons:
            fig_hotspot = go.Figure()
            fig_hotspot.add_trace(go.Scattermap(lon=h_lons, lat=h_lats, mode="markers",
                                                marker=dict(size=h_sz, color=h_col, colorscale="YlOrRd", cmin=0, cmax=100,
                                                            colorbar=dict(title="Level", thickness=10, len=0.6), opacity=0.85),
                                                text=h_txt, hoverinfo="text", name="Hotspots"))
            fig_hotspot.update_layout(map=dict(style=MAP_STYLE, center=dict(lat=np.mean(h_lats), lon=np.mean(h_lons)), zoom=18),
                                      margin=dict(l=0, r=0, t=0, b=0), height=240, paper_bgcolor="rgba(0,0,0,0)")
        else:
            fig_hotspot = EMPTY_FIG
    else:
        fig_hotspot = go.Figure()
        t_lons, t_lats = [], []
        for feat in DEFAULT_ORCHARD.get("features", []):
            c = feat["geometry"]["coordinates"]
            t_lons.append(c[0]); t_lats.append(c[1])
        if t_lons:
            fig_hotspot.add_trace(go.Scattermap(lon=t_lons, lat=t_lats, mode="markers",
                                                marker=dict(size=8, color="#22c55e", opacity=0.6), hoverinfo="skip", name="Trees"))
            fig_hotspot.update_layout(map=dict(style=MAP_STYLE, center=dict(lat=np.mean(t_lats), lon=np.mean(t_lons)), zoom=18),
                                      margin=dict(l=0, r=0, t=0, b=0), height=240, paper_bgcolor="rgba(0,0,0,0)")
            fig_hotspot.add_annotation(text="No infestation data — showing orchard trees", xref="paper", yref="paper",
                                       x=0.5, y=0.02, showarrow=False, font=dict(size=11, color="#888"),
                                       bgcolor="rgba(255,255,255,0.8)", borderpad=4)
        else:
            fig_hotspot = EMPTY_FIG

    # Environment
    env = data.get("environment", {})
    env_current = env.get("current", {})
    def _env_metric(ico, label, value, unit):
        return dbc.Col(html.Div([icon(ico, "text-muted fs-5"), html.Div([
            html.Small(label, className="text-muted d-block", style={"lineHeight": "1"}),
            html.Span(f"{value:.1f} {unit}" if isinstance(value, (int, float)) else "—", className="fw-bold"),
        ], className="ms-2")], className="d-flex align-items-center"), xs=6, md=3, className="mb-2")
    env_content = dbc.Row([
        _env_metric("thermometer-half", "Temperature", env_current.get("temperature"), "°C"),
        _env_metric("droplet-half", "Humidity", env_current.get("humidity"), "%"),
        _env_metric("cloud-rain", "Rainfall", env_current.get("rainfall"), "mm"),
        _env_metric("wind", "Wind Speed", env_current.get("wind_speed"), "m/s"),
    ]) if env_current else html.Small("No environmental data", className="text-muted")

    trends = env.get("trends", [])
    if trends:
        df_env = pd.DataFrame(trends)
        fig_env = go.Figure()
        if "temperature" in df_env.columns:
            fig_env.add_trace(go.Scatter(x=df_env.get("date", range(len(df_env))), y=df_env["temperature"],
                                         mode="lines", line=dict(color="#ef4444", width=2), name="Temp (°C)"))
        if "humidity" in df_env.columns:
            fig_env.add_trace(go.Scatter(x=df_env.get("date", range(len(df_env))), y=df_env["humidity"],
                                         mode="lines", line=dict(color="#3b82f6", width=2), name="Humidity (%)", yaxis="y2"))
        fig_env.update_layout(margin=dict(l=20, r=40, t=10, b=20), height=160,
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              xaxis=dict(gridcolor="#eee"), yaxis=dict(title="°C", gridcolor="#eee"),
                              yaxis2=dict(title="%", overlaying="y", side="right", gridcolor="#eee"),
                              legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    else:
        fig_env = EMPTY_FIG

    # Infested Trees KPI from DB data
    infested_trees_text = str(inf_trees)
    infested_trees_detail = html.Small(f"{inf_trees} / {total_trees} trees ({rate:.1%})", className="text-muted")

    now = dt.datetime.now().strftime("%H:%M:%S")
    return (
        rate_pct, rate_content, risk_score_text, risk_level.title(), risk_color,
        infested_trees_text, infested_trees_detail,
        fig_trend, fig_pheno, fig_spread,
        env_content, fig_env,
        f"Last updated: {now}",
        data,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tree Management Modal — Callbacks (Risk Forecast Tab)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── TM1) Open modal on tree click in Risk Forecast map ──
@app.callback(
    [
        Output("tree-management-modal", "is_open"),
        Output("tree-modal-info", "children"),
        Output("tree-status-dropdown", "value"),
        Output("selected-tree-store", "data"),
    ],
    [
        Input("risk-map", "clickData"),
        Input("tree-modal-cancel", "n_clicks"),
        Input("tree-modal-update", "n_clicks"),
    ],
    [
        State("sim-data-store", "data"),
        State("tree-management-modal", "is_open"),
        State("selected-tree-store", "data"),
        State("tree-status-dropdown", "value"),
    ],
    prevent_initial_call=True,
)
def handle_tree_modal(
    click_data, cancel_clicks, update_clicks,
    sim_data, is_open, selected_tree, new_status
):
    """Handle opening/closing the tree management modal and display tree info."""
    trigger = callback_context.triggered_id
    print(f"[Tree Modal] Callback triggered by: {trigger}, click_data: {click_data is not None}")
    
    # Cancel button closes modal
    if trigger == "tree-modal-cancel":
        return False, no_update, no_update, None
    
    # Update button - keep modal open, TM2 handles the update and refresh
    if trigger == "tree-modal-update":
        return no_update, no_update, no_update, no_update
    
    # Handle map click from risk-map
    if trigger == "risk-map" and click_data:
        print(f"[Tree Modal] Click data received: {click_data}")
        try:
            # Extract clicked point info from customdata
            point = click_data.get("points", [{}])[0]
            custom = point.get("customdata")
            
            # Use customdata if available (preferred)
            if custom and isinstance(custom, dict):
                tree_data = {
                    "tree_id": custom.get("tree_id"),
                    "status": custom.get("status", "healthy"),
                    "crown_width": custom.get("crown_width"),
                    "elevation": custom.get("elevation"),
                    "lon": custom.get("lon", 0),
                    "lat": custom.get("lat", 0),
                    "row": custom.get("row"),
                    "col": custom.get("col"),
                    "risk": custom.get("risk"),
                }
                tree_id = tree_data["tree_id"]
            else:
                # Fallback: parse tree ID from hover text (format: "<b>Tree X</b>...")
                hover_text = point.get("text", "")
                tree_id = None
                if "<b>Tree " in hover_text:
                    start = hover_text.find("<b>Tree ") + 8
                    end = hover_text.find("</b>", start)
                    tree_id_str = hover_text[start:end].strip()
                    if tree_id_str.isdigit():
                        tree_id = int(tree_id_str)
                
                if tree_id is None:
                    return no_update, no_update, no_update, no_update
                
                # Fallback to default orchard data
                tree_data = None
                for feat in DEFAULT_ORCHARD.get("features", []):
                    props = feat.get("properties", {})
                    if _get_tree_id(props) == tree_id:
                        coords = feat["geometry"]["coordinates"]
                        tree_data = {
                            "tree_id": tree_id,
                            "lon": coords[0],
                            "lat": coords[1],
                            "crown_width": _get_tree_crown_width(props),
                            "elevation": _get_tree_elevation(props),
                            "status": _get_tree_status(props),
                        }
                        break
            
            if tree_data is None or tree_id is None:
                return no_update, no_update, no_update, no_update
            
            # Build info display
            status = tree_data.get("status", "healthy")
            status_color = GIS_STATUS_COLORS.get(status, "#888")
            status_icon = TREE_STATUS_ICONS.get(status, "circle-fill")
            
            # Build professional info card with sections
            info_content = dbc.Card([
                # Header with tree ID
                dbc.CardHeader([
                    html.Div([
                        html.I(className=f"bi bi-{status_icon} me-2", style={"color": status_color, "fontSize": "1.2rem"}),
                        html.Span(f"Tree #{tree_data['tree_id']}", className="fw-bold fs-5"),
                    ], className="d-flex align-items-center"),
                ], className="bg-white py-2"),
                
                dbc.CardBody([
                    # Status row with badge
                    html.Div([
                        html.I(className="bi bi-tag-fill me-2 text-muted"),
                        html.Span("Status", className="text-muted me-2"),
                        dbc.Badge(
                            status.replace("_", " ").title(),
                            style={"backgroundColor": status_color, "color": "white"},
                            className="px-3 py-1",
                            pill=True,
                        ),
                    ], className="d-flex align-items-center mb-3"),
                    
                    # Grid of info items
                    dbc.Row([
                        # Left column
                        dbc.Col([
                            # Grid position if available
                            html.Div([
                                html.I(className="bi bi-grid-3x3 me-2 text-primary"),
                                html.Span("Grid: ", className="text-muted"),
                                html.Span(
                                    f"({tree_data.get('row', '—')}, {tree_data.get('col', '—')})",
                                    className="fw-medium"
                                ) if tree_data.get("row") is not None else html.Span("—", className="text-muted"),
                            ], className="mb-2") if tree_data.get("row") is not None else None,
                            
                            # Risk level if available
                            html.Div([
                                html.I(className="bi bi-speedometer2 me-2 text-warning"),
                                html.Span("Risk: ", className="text-muted"),
                                html.Span(
                                    f"{tree_data.get('risk', 0):.0%}",
                                    className="fw-bold",
                                    style={"color": "#ef4444" if tree_data.get("risk", 0) > 0.7 else "#f97316" if tree_data.get("risk", 0) > 0.4 else "#22c55e"}
                                ),
                            ], className="mb-2") if tree_data.get("risk") is not None else None,
                            
                            # Crown width if available
                            html.Div([
                                html.I(className="bi bi-rulers me-2 text-success"),
                                html.Span("Crown: ", className="text-muted"),
                                html.Span(f"{tree_data.get('crown_width', 0):.1f} m", className="fw-medium"),
                            ], className="mb-2") if tree_data.get("crown_width") is not None else None,
                        ], md=6),
                        
                        # Right column
                        dbc.Col([
                            # Elevation if available
                            html.Div([
                                html.I(className="bi bi-arrow-up-circle me-2 text-info"),
                                html.Span("Elevation: ", className="text-muted"),
                                html.Span(f"{tree_data.get('elevation', 0):.1f} m", className="fw-medium"),
                            ], className="mb-2") if tree_data.get("elevation") is not None else None,
                            
                            # Coordinates
                            html.Div([
                                html.I(className="bi bi-geo-alt-fill me-2 text-danger"),
                                html.Span("Location: ", className="text-muted"),
                                html.Br(),
                                html.Span(
                                    f"{tree_data.get('lat', 0):.5f}°N",
                                    className="font-monospace small d-block",
                                ),
                                html.Span(
                                    f"{tree_data.get('lon', 0):.5f}°E",
                                    className="font-monospace small",
                                ),
                            ], className="mb-2"),
                        ], md=6),
                    ]),
                ], className="py-2"),
            ], className="border-0 shadow-sm")
            
            return True, info_content, status, tree_data
            
        except Exception as e:
            print(f"[Tree Modal] Error handling click: {e}")
            return no_update, no_update, no_update, no_update
    
    return no_update, no_update, no_update, no_update


# ── TM2) Update tree status in sim-data-store ──
@app.callback(
    [
        Output("sim-data-store", "data", allow_duplicate=True),
        Output("sim-status", "children", allow_duplicate=True),
        Output("tree-modal-info", "children", allow_duplicate=True),
        Output("selected-tree-store", "data", allow_duplicate=True),
        Output("risk-map", "figure", allow_duplicate=True),
    ],
    Input("tree-modal-update", "n_clicks"),
    [
        State("selected-tree-store", "data"),
        State("tree-status-dropdown", "value"),
        State("sim-data-store", "data"),
    ],
    prevent_initial_call=True,
)
def update_tree_status(n_clicks, selected_tree, new_status, sim_data):
    """Update tree status in the sim-data-store and refresh modal display."""
    if not n_clicks or not selected_tree or not new_status:
        return no_update, no_update, no_update, no_update, no_update
    
    tree_id = selected_tree.get("tree_id")
    old_status = selected_tree.get("status", "unknown")
    
    if tree_id is None:
        return no_update, no_update, no_update, no_update, no_update
    
    # Store tree status overrides in sim_data for use in next simulation
    if sim_data is None:
        sim_data = {}
    
    # Create or update tree_overrides dict
    if "tree_overrides" not in sim_data:
        sim_data["tree_overrides"] = {}
    
    sim_data["tree_overrides"][str(tree_id)] = new_status
    
    # Update selected_tree with new status for modal display
    updated_tree = selected_tree.copy()
    updated_tree["status"] = new_status
    
    # Build updated info display with new status
    status_color = GIS_STATUS_COLORS.get(new_status, "#888")
    status_icon = TREE_STATUS_ICONS.get(new_status, "circle-fill")
    
    info_content = dbc.Card([
        # Header with tree ID
        dbc.CardHeader([
            html.Div([
                html.I(className=f"bi bi-{status_icon} me-2", style={"color": status_color, "fontSize": "1.2rem"}),
                html.Span(f"Tree #{updated_tree['tree_id']}", className="fw-bold fs-5"),
            ], className="d-flex align-items-center"),
        ], className="bg-white py-2"),
        
        dbc.CardBody([
            # Status row with badge - show updated status
            html.Div([
                html.I(className="bi bi-tag-fill me-2 text-muted"),
                html.Span("Status", className="text-muted me-2"),
                dbc.Badge(
                    new_status.replace("_", " ").title(),
                    style={"backgroundColor": status_color, "color": "white"},
                    className="px-3 py-1",
                    pill=True,
                ),
                dbc.Badge(
                    "Updated",
                    color="success",
                    className="ms-2 px-2 py-1",
                    pill=True,
                ),
            ], className="d-flex align-items-center mb-3"),
            
            # Grid of info items
            dbc.Row([
                # Left column
                dbc.Col([
                    # Grid position if available
                    html.Div([
                        html.I(className="bi bi-grid-3x3 me-2 text-primary"),
                        html.Span("Grid: ", className="text-muted"),
                        html.Span(
                            f"({updated_tree.get('row', '—')}, {updated_tree.get('col', '—')})",
                            className="fw-medium"
                        ) if updated_tree.get("row") is not None else html.Span("—", className="text-muted"),
                    ], className="mb-2") if updated_tree.get("row") is not None else None,
                    
                    # Risk level if available
                    html.Div([
                        html.I(className="bi bi-speedometer2 me-2 text-warning"),
                        html.Span("Risk: ", className="text-muted"),
                        html.Span(
                            f"{updated_tree.get('risk', 0):.0%}",
                            className="fw-bold",
                            style={"color": "#ef4444" if updated_tree.get("risk", 0) > 0.7 else "#f97316" if updated_tree.get("risk", 0) > 0.4 else "#22c55e"}
                        ),
                    ], className="mb-2") if updated_tree.get("risk") is not None else None,
                    
                    # Crown width if available
                    html.Div([
                        html.I(className="bi bi-rulers me-2 text-success"),
                        html.Span("Crown: ", className="text-muted"),
                        html.Span(f"{updated_tree.get('crown_width', 0):.1f} m", className="fw-medium"),
                    ], className="mb-2") if updated_tree.get("crown_width") is not None else None,
                ], md=6),
                
                # Right column
                dbc.Col([
                    # Elevation if available
                    html.Div([
                        html.I(className="bi bi-arrow-up-circle me-2 text-info"),
                        html.Span("Elevation: ", className="text-muted"),
                        html.Span(f"{updated_tree.get('elevation', 0):.1f} m", className="fw-medium"),
                    ], className="mb-2") if updated_tree.get("elevation") is not None else None,
                    
                    # Coordinates
                    html.Div([
                        html.I(className="bi bi-geo-alt-fill me-2 text-danger"),
                        html.Span("Location: ", className="text-muted"),
                        html.Br(),
                        html.Span(
                            f"{updated_tree.get('lat', 0):.5f}°N",
                            className="font-monospace small d-block",
                        ),
                        html.Span(
                            f"{updated_tree.get('lon', 0):.5f}°E",
                            className="font-monospace small",
                        ),
                    ], className="mb-2"),
                ], md=6),
            ]),
        ], className="py-2"),
    ], className="border-0 shadow-sm")
    
    status_msg = dbc.Alert(
        [
            html.I(className="bi bi-check-circle-fill me-2"),
            f"Tree #{tree_id}: ",
            html.Span(old_status.replace("_", " ").title(), className="text-muted"),
            " → ",
            html.Strong(new_status.replace("_", " ").title()),
            ". Run simulation to apply.",
        ],
        color="success", duration=6000, className="py-2",
    )
    
    # Build updated map with new tree colors
    updated_map = build_risk_map(tree_overrides=sim_data.get("tree_overrides", {}))
    
    return sim_data, status_msg, info_content, updated_tree, updated_map







# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entry point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if __name__ == "__main__":
    print("=" * 50)
    print("  MangoPoint Dashboard (Python / Dash)")
    print("=" * 50)
    print(f"  Backend API : {API_BASE}")
    print(f"  Dashboard   : http://localhost:8050")
    print("=" * 50)
    app.run(debug=False, host="0.0.0.0", port=8050)
