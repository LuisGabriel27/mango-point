import asyncio
import math

import numpy as np
import pandas as pd
import pytest

from api.models.schemas import SimulationRequest
from pydantic import ValidationError
from api.services.simulation_service import SimulationService
from core.biological_rules import CecidFlyGate, FruitFlyGate
from core.cecid_habitat import CecidHabitatNetwork
from core.config import BAG_RESISTANCE, CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode, TreeState
from utils.weather import WeatherTimeSeries


PESTS = [('cecid', 'fruitlet', 18), ('fruitfly', 'mature', 12)]


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_per_tree_presence_overrides_defaults_without_disabling_confirmed_sources(mode, pest, stage, hour):
    request = _request(mode, pest, stage,
        ['history_infected', 'history_infected', 'suspect', 'suspect', 'infected', 'dead'],
        history=0.0, suspect=1.0,
        tree_source_probability_overrides={'0': 1.0, '1': 0.0, '2': 0.0, '3': 1.0, '4': 0.0, '5': 1.0})
    response = _run(request)
    entries = {entry['tree_id']: entry for entry in response.metadata.initial_sources}
    assert {tree_id: entry['active'] for tree_id, entry in entries.items()} == {
        '0': True, '1': False, '2': False, '3': True, '4': True}
    assert entries['4']['probability'] == 1.0 and entries['4']['assumed'] is False
    assert response.metadata.initial_infected_count == 2
    assert response.metadata.source_uncertainty_assumptions['uncertain_source_candidate_count'] == 0
    assert response.metadata.source_uncertainty_assumptions['source_probability_override_count'] == 4
    replay = SimulationRequest.model_validate(request.model_dump(mode='json'))
    assert replay.tree_source_probability_overrides == request.tree_source_probability_overrides


def test_uncertainty_count_uses_each_tree_probability_and_replays_identically():
    request = _request('tree_graph', 'fruitfly', 'mature', ['history_infected', 'suspect'],
        history=0.0, suspect=1.0, uncertainty_runs=5,
        tree_source_probability_overrides={'0': 0.7, '1': 0.3})
    first, replay = _run(request), _run(request)
    assert first.metadata.source_uncertainty_assumptions['uncertain_source_candidate_count'] == 2
    assert [entry['probability'] for entry in first.metadata.initial_sources] == [0.7, 0.3]
    assert first.metadata.initial_sources == replay.metadata.initial_sources
    assert first.metadata.uncertainty_summary == replay.metadata.uncertainty_summary
    assert first.risk_geojson == replay.risk_geojson


@pytest.mark.parametrize('invalid', [-0.1, 1.1, float('nan'), float('inf')])
def test_per_tree_presence_rejects_out_of_range_or_nonfinite_values(invalid):
    with pytest.raises(ValidationError):
        _request('tree_graph', 'fruitfly', 'mature', ['suspect'],
            tree_source_probability_overrides={'0': invalid})


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('kind', ['targeted_spray', 'sanitation'])
def test_default_targeted_treatment_reaches_active_history_reservoirs(mode, pest, stage, hour, kind):
    untreated = _run(_request(mode, pest, stage, ['history_infected', 'healthy'], history=1.0), hour)
    treated = _run(_request(mode, pest, stage, ['history_infected', 'healthy'], history=1.0,
        treatment_applications=[{'treatment_type': kind, 'coverage': 'targeted',
            'efficacy': 0.0 if kind == 'sanitation' else 0.8, 'source_reduction': 0.8}]), hour)
    properties = _properties(treated)
    assert treated.metadata.initial_infected_count == 0
    assert treated.metadata.treatment_summary['treated_tree_count'] == 1
    assert properties['0']['treated'] is True
    assert properties['1']['treated'] is False
    assert properties['0']['treatment_source_factor'] == pytest.approx(0.2)
    assert 0 < properties['1']['risk'] < _properties(untreated)['1']['risk']


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_absent_history_and_suspect_are_not_default_treatment_targets(mode):
    response = _run(_request(mode, 'fruitfly', 'mature', ['history_infected', 'suspect', 'infected'],
        history=0.0, suspect=0.0,
        treatment_applications=[{'treatment_type': 'sanitation', 'coverage': 'targeted',
            'efficacy': 0.0, 'source_reduction': 0.8}]))
    assert response.metadata.treatment_summary['treated_tree_count'] == 1
    assert response.metadata.treatment_summary['applications'][0]['target_tree_ids'] == ['2']


def _weather(hour):
    return [{'datetime': f'2026-04-01T{hour:02d}:00:00+08:00', 'hour': hour,
             'wind_speed_ms': 1.0, 'wind_dir_deg': 0.0,
             'temperature_c': 30.0, 'rainfall_mm': 0.0}]


def _request(mode, pest, stage, statuses, history=0.5, suspect=0.5, seed=42, **kwargs):
    return SimulationRequest(
        pest_type=pest, orchard_stage=stage, simulation_mode=mode, hours=1, random_seed=seed,
        history_source_probability=history, suspect_source_probability=suspect,
        manual_weather_prefix_rain=[0.0] * 68 + [2.0] * 4,
        orchard_geojson={'type': 'FeatureCollection', 'features': [
            {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [122.58 + i * 0.00005, 10.585]},
             'properties': {'Tree_ID': str(i), 'Status': status}}
            for i, status in enumerate(statuses)
        ]}, **kwargs,
    )


def _run(request, hour=0):
    weather = _weather(hour)
    if hour == 0:
        # Source-only tests use zero temperature activity, not a night cutoff.
        weather = [{**entry, 'temperature_c': 10.0} for entry in weather]
    return asyncio.run(SimulationService().run_simulation(request, weather_data=weather, weather_context=[]))


def _properties(response):
    return {feature['properties']['tree_id']: feature['properties']
            for feature in response.risk_geojson['features']}


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('status', ['history_infected', 'suspect'])
@pytest.mark.parametrize('probability', [0.0, 1.0])
def test_source_presence_endpoints_keep_history_distinct_from_possible_current_infection(mode, pest, stage, hour, status, probability):
    response = _run(_request(mode, pest, stage, [status, 'healthy'], history=probability, suspect=probability))
    properties = _properties(response)
    entry = next(source for source in response.metadata.initial_sources if source['tree_id'] == '0')
    assert entry['status'] == status
    assert entry['probability'] == probability
    assert entry['active'] is bool(probability)
    assert entry['assumed'] is True
    assert entry['origin'] == ('history_reservoir' if status == 'history_infected' else 'suspect_infection')
    assert properties['0']['initial_source'] is bool(probability)
    assert properties['0']['initial_source_assumed'] is True
    assert properties['0']['initial_source_origin'] == entry['origin']
    assert properties['1']['initial_source'] is False
    expected_initial_infections = int(status == 'suspect' and probability == 1.0)
    assert response.metadata.initial_infected_count == expected_initial_infections
    assert properties['0']['risk'] == expected_initial_infections
    assert properties['1']['risk'] == 0.0
    assert response.metadata.initial_seed_strategy == 'status_source_hypotheses'
    if pest == 'cecid':
        assert response.metadata.cecid_source_count == int(probability)
        assert response.metadata.cecid_assumed_source_count == int(probability)
        assert response.metadata.cecid_explicit_source_count == 0
        if probability:
            assert response.metadata.cecid_sources[0]['origin'] == entry['origin']
    frame_properties = next(feature['properties'] for feature in response.timesteps[0].geojson['features']
                            if feature['properties']['tree_id'] == '0')
    assert frame_properties['initial_source'] == properties['0']['initial_source']
    assert frame_properties['initial_source_origin'] == entry['origin']


@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_presence_sampling_is_reproducible_across_modes_and_independent_of_establishment_rng(pest, stage, hour):
    service = SimulationService()
    request = _request('grid', pest, stage, ['history_infected', 'suspect'])
    records = [
        {'key': i, 'tree_id': str(i), 'status': status, 'dead': False, 'infested': False}
        for i, status in enumerate(('history_infected', 'suspect'))
    ]
    np.random.seed(7)
    baseline_draw = np.random.random()
    np.random.seed(7)
    entries, assumptions = service._sample_status_sources(records, request, 42)
    assert np.random.random() == baseline_draw
    assert entries == service._sample_status_sources(records, request, 42)[0]
    assert assumptions['calibration_status'] == 'uncalibrated source-presence assumptions'
    assert assumptions['uncertain_source_candidate_count'] == 2
    activations = {
        tuple(entry['active'] for entry in service._sample_status_sources(records, request, seed)[0])
        for seed in range(20)
    }
    assert len(activations) > 1
    responses = [_run(_request(mode, pest, stage, ['history_infected', 'suspect', 'healthy']))
                 for mode in ('grid', 'tree_graph')]
    assert responses[0].metadata.initial_sources == responses[1].metadata.initial_sources
    assert responses[0].metadata.source_uncertainty_assumptions == responses[1].metadata.source_uncertainty_assumptions


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_history_and_suspect_hypotheses_are_sampled_alongside_known_infection(mode, pest, stage, hour):
    response = _run(_request(mode, pest, stage, ['infected', 'history_infected', 'suspect', 'dead'], history=1.0, suspect=1.0))
    entries = {entry['tree_id']: entry for entry in response.metadata.initial_sources}
    assert set(entries) == {'0', '1', '2'}
    assert entries['0']['origin'] == 'observed_infection'
    assert entries['0']['assumed'] is False
    assert all(entry['active'] for entry in entries.values())
    assert response.metadata.initial_infected_count == 2
    assert _properties(response)['1']['risk'] == 0.0
    assert _properties(response)['3']['initial_source'] is False
    if pest == 'cecid':
        assert response.metadata.cecid_source_count == 3
        assert response.metadata.cecid_explicit_source_count == 1
        assert response.metadata.cecid_assumed_source_count == 2


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_fruit_fly_history_reservoir_exposes_neighbors_without_self_infection(mode):
    reservoir = _run(_request(mode, 'fruitfly', 'mature', ['history_infected', 'healthy'], history=1.0), 12)
    known = _run(_request(mode, 'fruitfly', 'mature', ['infected', 'healthy']), 12)
    properties = _properties(reservoir)
    assert reservoir.metadata.initial_infected_count == 0
    assert properties['0']['state'] in ('history_infected', 'unbagged')
    assert properties['0']['risk'] == 0.0
    assert properties['1']['risk'] > 0.0
    assert properties['1']['risk'] == pytest.approx(_properties(known)['1']['risk'])
    assert reservoir.metadata.initial_sources[0]['label'] == 'Possible historical adult reservoir'


@pytest.mark.parametrize('probability,source_stage,eligible_count,reachable_count', [
    (1.0, 'mature', 4, 2), (0.0, 'mature', 4, 0), (1.0, 'fruitlet', 3, 0),
])
def test_history_only_fruit_fly_connectivity_reports_the_active_eligible_source_component(
        probability, source_stage, eligible_count, reachable_count):
    request = _request(
        'tree_graph', 'fruitfly', 'mature', ['history_infected', 'healthy', 'healthy', 'healthy'],
        history=probability, tg_max_neighbor_dist_m=20.0,
        tree_stage_overrides={'0': source_stage},
    )
    metres_lon = 111_132.0 * math.cos(math.radians(10.585))
    for feature, distance in zip(request.orchard_geojson['features'], (0.0, 10.0, 60.0, 70.0)):
        feature['geometry']['coordinates'][0] = 122.58 + distance / metres_lon
    response = _run(request, 12)
    properties = _properties(response)
    assert response.metadata.initial_infected_count == 0
    assert response.metadata.tg_eligible_tree_count == eligible_count
    assert response.metadata.tg_eligible_component_count == 2
    assert response.metadata.tg_largest_eligible_component == 2
    assert response.metadata.tg_source_reachable_tree_count == reachable_count
    assert (properties['1']['risk'] > 0.0) is bool(reachable_count)
    assert properties['2']['risk'] == properties['3']['risk'] == 0.0


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_cecid_history_soil_source_is_fixed_and_remains_assumed_after_new_establishment(mode):
    request = _request(mode, 'cecid', 'fruitlet', ['history_infected', 'healthy'], history=1.0, seed=21,
                       cecid_base_dispersal_prob=0.5)
    request.orchard_geojson['features'][1]['geometry']['coordinates'][0] = (
        122.58 + 5.0 / (111_132.0 * math.cos(math.radians(10.585))))
    response = _run(request, 18)
    assert response.metadata.initial_infected_count == 0
    assert response.metadata.cecid_source_count == 1
    assert [source['tree_id'] for source in response.metadata.cecid_sources] == ['0']
    assert response.metadata.cecid_sources[0]['origin'] == 'history_reservoir'
    assert response.metadata.cecid_sources[0]['assumed'] is True
    assert _properties(response)['1']['risk'] > 0.0
    assert _properties(response)['1']['state'] == 'infested'
    assert _properties(response)['1']['cecid_source'] is False
    assert _properties(response)['1']['initial_source'] is False


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_explicit_manual_source_overrides_probability_zero_without_reviving_dead_trees(mode, pest, stage, hour):
    request = _request(mode, pest, stage, ['history_infected', 'dead', 'suspect'], history=0.0, suspect=0.0)
    if mode == 'tree_graph':
        request.initial_infestation_tree_ids = ['0', '1']
    else:
        service = SimulationService(); service._load_modules()
        grid, _ = service._create_grid_from_geojson(request.orchard_geojson)
        request.initial_infestation = [
            {'row': int(row), 'col': int(col)}
            for row, col in np.argwhere(np.isin(grid.tree_ids, ['0', '1']))
        ]
    response = _run(request)
    entries = {entry['tree_id']: entry for entry in response.metadata.initial_sources}
    assert entries['0']['origin'] == 'manual_initial_source'
    assert entries['0']['active'] is True
    assert entries['0']['assumed'] is False
    assert entries['0']['probability'] == 1.0
    assert '1' not in entries
    assert entries['2']['active'] is False
    assert response.metadata.initial_infected_count == 1
    assert _properties(response)['1']['state'] == 'dead'
    if pest == 'cecid':
        assert response.metadata.cecid_explicit_source_count == 1
        assert response.metadata.cecid_assumed_source_count == 0


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_explicit_soil_zone_stays_active_when_overlapping_history_hypothesis_is_absent(mode):
    lon, lat = 122.58, 10.585
    zone = {'id': 'known-ground', 'label': 'Selected ground evidence', 'pressure': 'medium',
            'coordinates': [[lon - 0.00002, lat - 0.00002], [lon + 0.00002, lat - 0.00002],
                            [lon + 0.00002, lat + 0.00002], [lon - 0.00002, lat + 0.00002]]}
    response = _run(_request(mode, 'cecid', 'fruitlet', ['history_infected', 'healthy'], history=0.0,
                             cecid_emergence_zones=[zone]))
    history = next(entry for entry in response.metadata.initial_sources if entry['status'] == 'history_infected')
    soil = next(entry for entry in response.metadata.initial_sources if entry['origin'] == 'emergence_zone')
    assert history['active'] is False
    assert soil['active'] is True and soil['assumed'] is False
    assert response.metadata.cecid_source_count == response.metadata.cecid_explicit_source_count == 1
    assert _properties(response)['0']['initial_source'] is True
    assert _properties(response)['0']['initial_source_assumed'] is False
    assert _properties(response)['0']['initial_source_origin'] == 'emergence_zone'


@pytest.mark.parametrize('per_cell', [False, True])
@pytest.mark.parametrize('target_sweep', [False, True])
def test_fruit_fly_grid_reservoir_matches_neighbor_pressure_of_an_infected_source_in_all_spread_paths(per_cell, target_sweep):
    grids = []
    for reservoir in (True, False):
        grid = OrchardGrid(1, 5)
        grid.state[:] = [[CellState.INFESTED if target_sweep else CellState.EMPTY] * 3
                        + [CellState.HISTORY_INFECTED if reservoir else CellState.INFESTED, CellState.UNBAGGED]]
        if reservoir:
            grid.fruitfly_reservoir_pressure[0, 3] = 1.0
        gate = FruitFlyGate()
        weather = dict(hour=12, wind_speed_ms=1.0, wind_dir_deg=0.0, temperature_c=30.0)
        if per_cell:
            gate.compute_dispersal_per_cell(grid, np.full((1, 5), OrchardStage.MATURE), **weather)
        else:
            gate.compute_dispersal(grid, orchard_stage=OrchardStage.MATURE, **weather)
        grids.append(grid)
    assert grids[0].risk[0, 4] > 0.0
    assert grids[0].risk[0, 4] == pytest.approx(grids[1].risk[0, 4])


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_bagging_keeps_thirty_percent_of_equal_incoming_pressure(mode, pest, stage, hour):
    assert BAG_RESISTANCE == 0.70
    probabilities = []
    for bagged in (False, True):
        weather_frame = pd.DataFrame(_weather(hour))
        weather_frame['datetime'] = pd.to_datetime(weather_frame['datetime'])
        weather = WeatherTimeSeries(weather_frame, source='test')
        is_cecid = pest == 'cecid'
        phenology = OrchardStage.FRUITLET if is_cecid else OrchardStage.MATURE
        gate = CecidFlyGate() if is_cecid else FruitFlyGate()
        lon_step = 5.0 / (111_132.0 * math.cos(math.radians(10.585)))
        positions = {0: (122.58, 10.585), 1: (122.58 + lon_step, 10.585)}
        common = dict(gates=[gate], orchard_stage=phenology, transition_mode='threshold', threshold=2.0,
                      initial_rainfall_history=[0.0] * 68 + [2.0] * 4)
        if mode == 'grid':
            grid = OrchardGrid(1, 2)
            grid.state[:] = [[CellState.INFESTED, CellState.BAGGED if bagged else CellState.UNBAGGED]]
            grid_positions = {(0, i): position for i, position in positions.items()}
            engine = SimulationEngine(grid, weather, **common,
                cecid_source_pressures={(0, 0): 1.0} if is_cecid else None,
                cecid_habitat_network=CecidHabitatNetwork.from_lonlat(
                    {(0, 0): positions[0]}, grid_positions, []) if is_cecid else None)
            snapshot = engine.run(1, progress=False).snapshots[0]
            probabilities.append(snapshot['risk'][0, 1])
        else:
            graph = TreeGraph([
                TreeNode(i, str(i), *positions[i], i * 5.0, 0.0, 2.5,
                         state=TreeState.INFESTED if i == 0 else (TreeState.BAGGED if bagged else TreeState.SUSCEPTIBLE))
                for i in range(2)
            ], max_dist=20.0)
            engine = TreeGraphEngine(graph, weather, **common,
                cecid_source_pressures={0: 1.0} if is_cecid else None,
                cecid_habitat_network=CecidHabitatNetwork.from_lonlat(
                    {0: positions[0]}, positions, []) if is_cecid else None)
            probabilities.append(engine.run(1, progress=False).snapshots[0]['risks'][1])
    assert probabilities[0] > 0.0
    assert probabilities[1] == pytest.approx(probabilities[0] * 0.30)


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_bagging_preserves_historical_reservoir_evidence_without_forcing_infection(mode, pest, stage, hour):
    response = _run(_request(mode, pest, stage, ['history_infected', 'healthy'], history=1.0, bagged_tree_ids=['0']))
    assert _properties(response)['0']['state'] == 'bagged'
    assert _properties(response)['0']['initial_source'] is True
    assert _properties(response)['0']['initial_source_origin'] == 'history_reservoir'
    assert response.metadata.initial_infected_count == 0


def test_grid_copies_and_graph_clones_preserve_reservoir_and_interpretation_fields():
    grid = OrchardGrid(1, 1)
    grid.state[:] = CellState.HISTORY_INFECTED
    grid.fruitfly_reservoir_pressure[:] = 1.0
    grid.initial_source[:] = grid.initial_source_assumed[:] = True
    grid.initial_source_origin[:] = 'history_reservoir'
    grid.initial_source_label[:] = 'Possible historical adult reservoir'
    copied = grid.copy()
    assert copied.fruitfly_reservoir_pressure[0, 0] == 1.0
    assert copied.initial_source[0, 0]
    assert copied.initial_source_origin[0, 0] == 'history_reservoir'
    graph = TreeGraph([TreeNode(0, 'H', 122.58, 10.585, 0.0, 0.0, 2.5,
                               fruitfly_reservoir_pressure=1.0, initial_source=True,
                               initial_source_assumed=True, initial_source_origin='history_reservoir')], max_dist=20.0)
    frame = pd.DataFrame(_weather(0)); frame['datetime'] = pd.to_datetime(frame['datetime'])
    engine = TreeGraphEngine(graph, WeatherTimeSeries(frame, source='test'))
    assert engine.graph.nodes[0].fruitfly_reservoir_pressure == 1.0
    assert engine.graph.nodes[0].initial_source_origin == 'history_reservoir'
