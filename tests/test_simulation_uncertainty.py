"""Across-run summaries condition on one orchard, rather than changing stages."""

from copy import deepcopy
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from api.models.schemas import SimulationRequest
from api.routes.simulation import (
    _attach_uncertainty_summary,
    _requested_uncertainty_runs,
    _summarize_uncertainty_samples,
    _uncertainty_sample,
    _uncertainty_seed,
    export_simulation_run,
)
from api.services.simulation_service import simulation_service
from db.models import PestType, SimulationRun


COORDINATES = {"lat": 10.585, "lon": 122.58}
WEATHER = [{
    "datetime": "2026-04-01T12:00:00+08:00",
    "hour": 12,
    "wind_speed_ms": 20.0,
    "wind_dir_deg": 90.0,
    "temperature_c": 10.0,
    "rainfall_mm": 0.0,
}]


def _orchard():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [
                COORDINATES["lon"] + col * 0.00009,
                COORDINATES["lat"] + row * 0.00009,
            ]},
            "properties": {"Tree_ID": f"T{row * 4 + col}", "Status": "healthy"},
        } for row in range(4) for col in range(4)],
    }


def _request(pest, mode="tree_graph", **kwargs):
    return SimulationRequest(
        pest_type=pest,
        orchard_geojson=_orchard(),
        orchard_stage="fruitlet" if pest == "cecid" else "mature",
        simulation_mode=mode,
        hours=1,
        random_seed=42,
        **kwargs,
    )


async def _run(request):
    return await simulation_service.run_simulation(
        request=request, weather_data=WEATHER, weather_context=[],
        orchard_coordinates=COORDINATES,
    )


async def _attach(response, request):
    await _attach_uncertainty_summary(
        result=response, request=request, weather_data=WEATHER,
        weather_context=[], weather_provenance={"provider": "test"},
        orchard_coordinates=COORDINATES,
    )


def _stage_map(response):
    return {
        feature["properties"]["tree_id"]: feature["properties"]["stage"]
        for feature in response.risk_geojson["features"]
    }


@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
def test_generic_run_count_overrides_legacy_setting(pest):
    assert _requested_uncertainty_runs(_request(
        pest, uncertainty_runs=1, cecid_uncertainty_runs=9,
    )) == 1
    assert _requested_uncertainty_runs(_request(
        pest, uncertainty_runs=5, cecid_uncertainty_runs=3,
    )) == 5
    assert _requested_uncertainty_runs(_request(
        pest, cecid_uncertainty_runs=5,
    )) == (5 if pest == "cecid" else 1)


@pytest.mark.parametrize("setting", ["uncertainty_runs", "cecid_uncertainty_runs"])
@pytest.mark.parametrize("value", [0, 10])
def test_run_count_schema_rejects_out_of_range_values(setting, value):
    with pytest.raises(ValidationError):
        _request("fruitfly", **{setting: value})


@pytest.mark.parametrize("setting", ["history_source_probability", "suspect_source_probability"])
@pytest.mark.parametrize("value", [-0.01, 1.01])
def test_uncertain_source_probability_rejects_out_of_range(setting, value):
    with pytest.raises(ValidationError):
        _request("cecid", **{setting: value})


def test_source_presence_assumptions_are_explicitly_uncalibrated():
    request = _request("fruitfly")
    assert request.history_source_probability == request.suspect_source_probability == 0.5
    schema = SimulationRequest.model_json_schema()["properties"]
    for key in ["history_source_probability", "suspect_source_probability"]:
        assert "not a calibrated field probability" in schema[key]["description"]


@pytest.mark.asyncio
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
async def test_known_source_stays_fixed_and_playback_remains_representative(pest, mode):
    request = _request(pest, mode, uncertainty_runs=3, tree_overrides={"T0": "infected"})
    primary = await _run(request)
    original_final = deepcopy(primary.risk_geojson)
    original_frames = deepcopy(primary.time_series)
    original_timesteps = deepcopy(primary.timesteps)
    await _attach(primary, request)

    summary = primary.metadata.uncertainty_summary
    assert summary["runs"] == 3
    assert summary["pest_type"] == pest
    assert summary["map_seed"] == 42
    assert summary["uncertainty_type"] == "stochastic_establishment"
    assert summary["representative_playback_only"] is True
    assert summary["source_locations_varied"] is False
    assert all(sample["source_tree_ids"] == ["T0"] for sample in summary["samples"])
    assert summary["tree_infestation_frequencies"]["T0"] == 1.0
    assert summary["tree_infestation_frequencies"]["T15"] == 0.0
    assert "not a calibrated confidence interval or field probability" in summary["interpretation"]
    if pest == "cecid":
        assert primary.metadata.cecid_uncertainty_summary == summary
    else:
        assert primary.metadata.cecid_uncertainty_summary is None

    # The ensemble is a final-outcome frequency. Adding it never replaces the
    # representative hourly states/scores with fabricated ensemble animation.
    for before, after in zip(original_final["features"], primary.risk_geojson["features"]):
        assert after["properties"]["state"] == before["properties"]["state"]
        assert after["properties"]["risk"] == before["properties"]["risk"]
    for before, after in zip(original_frames, primary.time_series):
        assert before.hour == after.hour
        assert before.n_infested == after.n_infested
        for old, new in zip(before.risk_geojson["features"], after.risk_geojson["features"]):
            assert old["properties"]["risk"] == new["properties"]["risk"]
            assert old["properties"]["state"] == new["properties"]["state"]
            assert new["properties"]["ensemble_runs"] == 3
    for before, after in zip(original_timesteps, primary.timesteps):
        assert before.hour == after.hour
        assert all(feature["properties"]["ensemble_runs"] == 3 for feature in after.geojson["features"])


@pytest.mark.asyncio
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
async def test_unknown_sources_vary_but_repeated_master_seed_replays_summary(pest, mode):
    request = _request(pest, mode, uncertainty_runs=3)
    first, second = await _run(request), await _run(request)
    await _attach(first, request)
    await _attach(second, request)
    summary = first.metadata.uncertainty_summary
    assert summary == second.metadata.uncertainty_summary
    assert summary["uncertainty_type"] == "assumed_source_placement_and_stochastic_establishment"
    assert summary["assumed_source_count_min"] >= 1
    assert [sample["seed"] for sample in summary["samples"]] == [
        _uncertainty_seed(42, index) for index in range(3)
    ]
    assert len({tuple(sample["source_tree_ids"]) for sample in summary["samples"]}) > 1
    assert summary["source_locations_varied"] is True
    assert summary["source_placement_modes"] == ["random_fallback_locations"]
    for feature in first.risk_geojson["features"]:
        properties = feature["properties"]
        count = properties["ensemble_infestation_count"]
        assert properties["ensemble_infestation_frequency"] == count / 3
    if pest == "fruitfly":
        assert any(0 < frequency < 1 for frequency in summary["tree_infestation_frequencies"].values())
    else:
        # Ineligible weather cannot create observed infestation simply because
        # there is an assumed soil anchor.
        assert all(frequency == 0 for frequency in summary["tree_infestation_frequencies"].values())


@pytest.mark.asyncio
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
async def test_quadrant_stage_mix_is_pinned_while_only_seeds_change(monkeypatch, pest, mode):
    stage = "fruitlet" if pest == "cecid" else "mature"
    request = _request(
        pest, mode, uncertainty_runs=3,
        quadrant_stages={"nw": stage, "ne": "flowering", "sw": stage, "se": "dormant"},
        tree_stage_overrides={"T0": stage},
        tree_overrides={"T0": "infected"},
    )
    primary = await _run(request)
    expected_stages = _stage_map(primary)
    assert len(set(expected_stages.values())) > 1
    calls = []
    original_run = simulation_service.run_simulation

    async def capture_replica(**kwargs):
        replica = await original_run(**kwargs)
        calls.append((kwargs, replica))
        return replica

    monkeypatch.setattr(simulation_service, "run_simulation", capture_replica)
    await _attach(primary, request)
    assert len(calls) == 2
    for kwargs, replica in calls:
        replica_request = kwargs["request"]
        assert _stage_map(replica) == expected_stages
        assert replica_request.tree_overrides == {"T0": "infected"}
        assert replica_request.include_time_series is False
        assert replica_request.uncertainty_runs == 1
        assert replica_request.cecid_uncertainty_runs == 1
        assert kwargs["weather_data"] is WEATHER
        assert kwargs["orchard_coordinates"] is COORDINATES
    assert primary.metadata.uncertainty_summary["fixed_tree_stage_count"] == 16


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
async def test_fruitfly_neighbor_edge_heuristic_is_fixed_across_replicas(mode):
    request = _request(
        "fruitfly", mode, uncertainty_runs=3,
        neighbor_sources=[{"direction": "N", "threat": 0.6}],
    )
    primary = await _run(request)
    await _attach(primary, request)
    summary = primary.metadata.uncertainty_summary
    assert summary["assumed_source_count_min"] > 0
    assert summary["uncertainty_type"] == "stochastic_establishment"
    assert summary["source_locations_varied"] is False
    assert summary["source_placement_modes"] == ["fixed_assumed_neighbor_edge_locations"]
    assert len({tuple(sample["source_tree_ids"]) for sample in summary["samples"]}) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
async def test_inactive_source_candidates_still_report_presence_uncertainty(pest):
    primary = await _run(_request(pest, tree_overrides={"T0": "infected"}))
    primary.metadata.initial_sources = [{
        "tree_id": "T0", "status": "infected", "origin": "observed_infection",
        "active": True, "assumed": False, "probability": 1.0,
    }, {
        "tree_id": "T1", "status": "history_infected", "origin": "history_reservoir",
        "active": False, "assumed": True, "probability": 0.5,
    }, {
        "tree_id": "T2", "status": "suspect", "origin": "suspect_infection",
        "active": False, "assumed": True, "probability": 0.5,
    }]
    sample = _uncertainty_sample(primary)
    assert sample["source_count"] == sample["active_source_count"] == 1
    assert sample["known_source_count"] == 1
    assert sample["assumed_source_count"] == 0
    assert sample["source_tree_ids"] == ["T0"]
    summary = _summarize_uncertainty_samples([sample, sample], 42)
    assert summary["uncertainty_type"] == "source_presence_and_stochastic_establishment"
    assert summary["uncertain_source_candidate_count"] == 2
    assert summary["uncertainty_components"] == ["uncertain_source_presence", "stochastic_establishment"]


@pytest.mark.asyncio
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
async def test_history_anchor_is_not_counted_as_established_infestation(pest, mode):
    request = _request(
        pest, mode, uncertainty_runs=3, tree_overrides={"T1": "history_infected"},
        history_source_probability=1.0,
    )
    primary = await _run(request)
    await _attach(primary, request)
    summary = primary.metadata.uncertainty_summary
    assert all(sample["source_tree_ids"] == ["T1"] for sample in summary["samples"])
    assert summary["assumed_source_count_min"] == summary["assumed_source_count_max"] == 1
    assert summary["tree_infestation_frequencies"]["T1"] == 0.0
    assert summary["minimum"] == summary["maximum"] == 0
    assert summary["uncertainty_type"] == "stochastic_establishment"


@pytest.mark.asyncio
@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
async def test_suspect_presence_can_vary_alongside_a_fixed_known_source(pest, mode):
    request = _request(
        pest, mode, uncertainty_runs=9,
        tree_overrides={"T0": "infected", "T1": "suspect"},
        suspect_source_probability=0.5,
    )
    primary = await _run(request)
    await _attach(primary, request)
    summary = primary.metadata.uncertainty_summary
    assert summary["uncertainty_type"] == "source_presence_and_stochastic_establishment"
    assert summary["uncertain_source_candidate_count"] == 1
    assert all("T0" in sample["source_tree_ids"] for sample in summary["samples"])
    assert any("T1" in sample["source_tree_ids"] for sample in summary["samples"])
    assert any("T1" not in sample["source_tree_ids"] for sample in summary["samples"])
    assert summary["tree_infestation_frequencies"]["T0"] == 1.0
    assert 0.0 < summary["tree_infestation_frequencies"]["T1"] < 1.0


@pytest.mark.asyncio
async def test_one_run_leaves_ensemble_fields_absent():
    request = _request("fruitfly", uncertainty_runs=1)
    primary = await _run(request)
    await _attach(primary, request)
    assert primary.metadata.uncertainty_summary is None
    assert all("ensemble_runs" not in feature["properties"] for feature in primary.risk_geojson["features"])


@pytest.mark.asyncio
async def test_saved_fruitfly_xlsx_preserves_frequency_separately_from_one_run_score():
    run = SimulationRun(
        run_id="ensemble-export-test", pest_type=PestType.FRUIT_FLY,
        orchard_id="test", simulation_mode="tree_graph", hours=1,
        random_seed=42, risk_threshold=0.7, status="completed",
        peak_risk=1.0, cells_at_risk=1, n_infested_final=1,
        request_payload={"history_source_probability": 0.5, "suspect_source_probability": 0.5},
        result_metadata={"uncertainty_summary": {
            "runs": 5, "minimum": 1, "median": 2, "maximum": 4,
            "uncertainty_type": "source_presence_and_stochastic_establishment",
        }},
        output_geojson={"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [122.58, 10.585]},
            "properties": {
                "tree_id": "T1", "risk": 1.0, "state": "infested", "stage": "mature",
                "ensemble_infestation_frequency": 0.4, "ensemble_infestation_count": 2,
                "ensemble_runs": 5, "initial_source": True, "initial_source_assumed": True,
                "initial_source_origin": "suspect_infection", "initial_source_label": "Possible current source",
            },
        }]},
    )

    class Result:
        def scalar_one_or_none(self):
            return run

    class Database:
        async def execute(self, _query):
            return Result()

    response = await export_simulation_run(run.run_id, db=Database())
    payload = b"".join([chunk async for chunk in response.body_iterator])
    ns = {"sheet": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with ZipFile(BytesIO(payload)) as workbook:
        sheet = ElementTree.fromstring(workbook.read("xl/worksheets/sheet6.xml"))
    rows = sheet.findall("sheet:sheetData/sheet:row", ns)

    def values(row):
        result = []
        for cell in row.findall("sheet:c", ns):
            value = cell.find("sheet:is/sheet:t", ns) if cell.get("t") == "inlineStr" else cell.find("sheet:v", ns)
            result.append(value.text if value is not None else None)
        return result

    exported = dict(zip(values(rows[0]), values(rows[1])))
    assert float(exported["risk"]) == 1.0
    assert float(exported["ensemble_infestation_frequency"]) == 0.4
    assert int(exported["ensemble_infestation_count"]) == 2
    assert int(exported["ensemble_runs"]) == 5
    assert exported["initial_source_origin"] == "suspect_infection"
