"""Script to add the function call to the sidebar"""

from pathlib import Path


APP_PATH = Path(__file__).resolve().parent.parent / "app.py"
content = APP_PATH.read_text(encoding="utf-8")

old = """                                # Left sidebar
                                dbc.Col(
                                    [
                                        make_weather_card(),
                                        make_sim_controls(),
                                        make_playback_controls(),
                                        make_observation_form(),
                                        make_alert_panel(),
                                        make_evaluation_panel(),
                                        make_risk_legend(),
                                    ],
                                    md=4, lg=3,
                                    className="pe-md-2",
                                ),"""

new = """                                # Left sidebar
                                dbc.Col(
                                    [
                                        make_weather_card(),
                                        make_sim_controls(),
                                        make_playback_controls(),
                                        make_decision_support_panel(),  # Decision Support Summary
                                        make_observation_form(),
                                        make_alert_panel(),
                                        make_evaluation_panel(),
                                        make_risk_legend(),
                                    ],
                                    md=4, lg=3,
                                    className="pe-md-2",
                                ),"""

if old in content:
    new_content = content.replace(old, new, 1)
    APP_PATH.write_text(new_content, encoding="utf-8")
    print('Sidebar updated successfully!')
else:
    print('Pattern not found')
    # Debug
    idx = content.find('make_playback_controls(),')
    if idx != -1:
        print('Found make_playback_controls at:', idx)
        print('Context:', repr(content[idx:idx+200]))
