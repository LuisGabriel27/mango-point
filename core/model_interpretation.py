"""Versioned explanations saved with simulation results, not fitted claims."""


def model_interpretation(pest_type: str) -> dict[str, str]:
    common = {
        "output_measure": (
            "Infestation frequency is the share of repeated runs with modeled infestation "
            "at a location, conditional on the supplied inputs and assumptions. It is "
            "not measured fruit damage, adult trap catches, or field-calibrated probability."
        ),
        "validation_status": (
            "A simulation scenario for monitoring support. Prospective field forecast "
            "accuracy has not been established. Historical metrics apply to their tested model version."
        ),
    }
    if pest_type == "cecid":
        return {
            **common,
            "source_rule": (
                "Fruit-attacking Cecid only. Local soil sources release finite adult "
                "cohorts under suitable emergence conditions; new fruit infestation "
                "does not become another soil source during the forecast."
            ),
            "movement_rule": (
                "Local adults can relay through configured habitat during suitable "
                "movement windows. Tree shade alone does not enable emergence or movement."
            ),
            "outside_pressure": (
                "Outside Cecid pressure is an uncalibrated directional exposure proxy. "
                "It requires suitable fruitlets, light, rain and wind conditions, but "
                "does not track boundary crossings, individual adults, arrival distance, "
                "travel time, age or egg capacity. Remote targets may receive exposure "
                "in the first eligible hour; the local movement cap does not constrain this proxy."
            ),
        }
    return {
        **common,
        "source_rule": (
            "Fruit Fly adult pressure is fixed from the initial source and reservoir "
            "scenario. New fruit infestation neither creates adult sources nor increases "
            "reservoir strength. Recorded damage is a source assumption, not a measurement of adults."
        ),
        "movement_rule": (
            "Exposure is applied around initial source locations within the model's "
            "local grid or graph links. Individual adult relocation and immature "
            "development are not simulated; links are not maximum flight distances."
        ),
        "outside_pressure": (
            "Fruit Fly neighbor pressure boosts exposure around local sources. "
            "Fallback edge sources may be assumed when no source evidence is supplied. "
            "These are scenario assumptions, not observed immigration paths."
        ),
    }
