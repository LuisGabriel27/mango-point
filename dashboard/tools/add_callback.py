"""Script to add the Decision Support callback"""

from pathlib import Path


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
content = APP_PATH.read_text(encoding="utf-8")

# Find the pattern and insert after playback_info callback
old_pattern = """    return html.Div(
        [html.Span(p, className="me-3") for p in info_parts],
        className="d-flex flex-wrap justify-content-center gap-1",
    )


# ── 7) Play / pause toggle ──"""

new_code = """    return html.Div(
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
    \"\"\"
    Compute and display Decision Support metrics.
    
    This is a pure interpretation layer — it reads the final risk values
    and produces management recommendations without modifying simulation data.
    \"\"\"
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
        
        # Zone percentages with cell counts
        zone1_text = f"{formatted['safe_percentage']} ({formatted['safe_cells']} cells)"
        zone2_text = f"{formatted['monitor_percentage']} ({formatted['monitor_cells']} cells)"
        zone3_text = f"{formatted['spray_percentage']} ({formatted['spray_cells']} cells)"
        
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


# ── 7) Play / pause toggle ──"""

if old_pattern in content:
    new_content = content.replace(old_pattern, new_code, 1)
    APP_PATH.write_text(new_content, encoding="utf-8")
    print('Callback added successfully!')
else:
    print('Pattern not found')
    # Try to find the actual pattern
    idx = content.find('# ── 7) Play / pause toggle')
    if idx == -1:
        idx = content.find('# ─')
        if idx != -1:
            print('Found ─ at:', idx)
            print('Context:', repr(content[max(0,idx-100):idx+50]))
