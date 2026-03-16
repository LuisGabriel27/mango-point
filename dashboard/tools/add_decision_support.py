"""Script to add the make_decision_support_panel function to app.py"""

from pathlib import Path


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
content = APP_PATH.read_text(encoding="utf-8")

# The exact pattern to find (after _stat_card function ends)
old_pattern = '''xs=6, md=3,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App init'''

new_function_code = '''xs=6, md=3,
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
    
    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [
                        icon("clipboard2-pulse", "me-2"),
                        html.Span("Decision Support Summary", className="fw-semibold"),
                        dbc.Badge("NEW", color="info", pill=True, className="ms-2"),
                    ],
                    className="d-flex align-items-center",
                ),
                className="py-2 bg-light",
            ),
            dbc.CardBody(body, className="py-2 px-3"),
        ],
        className="mb-3 shadow-sm border-success",
        style={"borderLeftWidth": "4px"},
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# App init'''

if old_pattern in content:
    new_content = content.replace(old_pattern, new_function_code, 1)
    APP_PATH.write_text(new_content, encoding="utf-8")
    print('Function added successfully!')
else:
    print('Pattern not found')
    # Debug: show what's actually there
    idx = content.find('xs=6, md=3,')
    if idx != -1:
        print('Found xs=6, md=3, at index:', idx)
        print('Content after:', repr(content[idx:idx+100]))
