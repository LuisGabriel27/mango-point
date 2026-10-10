import asyncio
import math

import numpy as np
import pandas as pd
import pytest

from api.models.schemas import PestTypeEnum, SimulationRequest
from api.services.simulation_service import SimulationService
from core.biological_rules import CecidFlyGate, FruitFlyGate
from core.cecid_habitat import CecidHabitatNetwork, CecidHabitatTracker
from core.config import CellState, OrchardStage
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.tree_graph_model import TreeGraph, TreeNode, TreeState
from utils.weather import WeatherTimeSeries


FLAGS = [('history_infected', CellState.HISTORY_INFECTED), ('suspect', CellState.SUSPECT)]
PESTS = [('cecid', 'fruitlet', 18), ('fruitfly', 'mature', 12)]


def _weather(hour):
    return [{
        'datetime': f'2026-04-01T{hour:02d}:00:00+08:00', 'hour': hour,
        'wind_speed_ms': 1.0, 'wind_dir_deg': 270.0,
        'temperature_c': 30.0, 'rainfall_mm': 0.0,
    }]


def _grid_engine(pest, flag, transition_mode, external_only=False):
    grid = OrchardGrid(1, 2)
    grid.set_state(0, 0, CellState.UNBAGGED if external_only else CellState.INFESTED)
    grid.set_state(0, 1, flag)
    if external_only:
        grid.set_neighbor_threat_uniform(0.6)
    positions = {(0, 0): (122.58, 10.585),
                 (0, 1): (122.58 + 5.0 / (111_132.0 * math.cos(math.radians(10.585))), 10.585)}
    is_cecid = pest == 'cecid'
    stage = OrchardStage.FRUITLET if is_cecid else OrchardStage.MATURE
    weather_frame = pd.DataFrame(_weather(18 if is_cecid else 12))
    weather_frame['datetime'] = pd.to_datetime(weather_frame['datetime'])
    weather = WeatherTimeSeries(weather_frame, source='test')
    sources = {(0, 0): 1.0} if not external_only else {}
    return SimulationEngine(
        grid, weather, transition_mode=transition_mode, threshold=2.0,
        gates=[CecidFlyGate() if is_cecid else FruitFlyGate()], orchard_stage=stage,
        initial_rainfall_history=[0.0] * 68 + [2.0] * 4,
        cecid_source_pressures=sources if is_cecid else None,
        cecid_habitat_network=CecidHabitatNetwork.from_lonlat(
            {cell: positions[cell] for cell in sources}, positions, [],
        ) if is_cecid else None,
    )


@pytest.mark.parametrize('status,flag', FLAGS)
@pytest.mark.parametrize('pest,external_only', [('cecid', False), ('cecid', True), ('fruitfly', False)])
@pytest.mark.parametrize('transition_mode', ['threshold', 'stochastic'])
def test_grid_history_and_monitoring_flags_receive_ordinary_pressure_and_can_establish(status, flag, pest, external_only, transition_mode):
    flagged = _grid_engine(pest, flag, transition_mode, external_only)
    np.random.seed(11)
    flag_snapshot = flagged.run(n_steps=1, progress=False).snapshots[0]
    flag_next_draw = np.random.random()
    healthy = _grid_engine(pest, CellState.UNBAGGED, transition_mode, external_only)
    np.random.seed(11)
    healthy_snapshot = healthy.run(n_steps=1, progress=False).snapshots[0]
    healthy_next_draw = np.random.random()
    target = (0, 1)

    assert flag_snapshot['risk'][target] > 0.0
    assert flag_snapshot['risk'][target] == pytest.approx(healthy_snapshot['risk'][target])
    assert flag_next_draw == healthy_next_draw
    if transition_mode == 'stochastic':
        assert flag_snapshot['state'][target] == CellState.INFESTED
        assert healthy_snapshot['state'][target] == CellState.INFESTED
    else:
        assert flag_snapshot['state'][target] == flag
        assert healthy_snapshot['state'][target] == CellState.UNBAGGED
    if pest == 'cecid':
        assert flag_snapshot['cecid_cumulative_probability'][target] == pytest.approx(
            healthy_snapshot['cecid_cumulative_probability'][target])
        assert flag_snapshot['cecid_exposure_hours'][target] == 1
        assert flag_snapshot['cecid_external_exposure_hours'][target] == int(external_only)
        assert flag_snapshot['cecid_local_exposure_hours'][target] == int(not external_only)


@pytest.mark.parametrize('status,flag', FLAGS)
@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('original_target_status', ['dead', 'infected'])
def test_status_overrides_restore_targets_without_making_them_initial_sources(status, flag, pest, stage, hour, original_target_status):
    orchard = {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': coordinates},
         'properties': {'Tree_ID': tree_id, 'Status': original_status}}
        for tree_id, coordinates, original_status in [
            ('S', [122.58, 10.585], 'infected'), ('T', [122.5801, 10.585], original_target_status),
        ]
    ]}
    for mode in ('grid', 'tree_graph'):
        responses = []
        for target_status in (status, 'healthy'):
            request = SimulationRequest(
                pest_type=pest, orchard_stage=stage, orchard_geojson=orchard,
                simulation_mode=mode, hours=1, random_seed=11,
                tree_overrides={'S': 'infected', 'T': target_status},
                manual_weather_prefix_rain=[0.0] * 68 + [2.0] * 4,
                history_source_probability=0.0, suspect_source_probability=0.0,
            )
            responses.append(asyncio.run(SimulationService().run_simulation(
                request, weather_data=_weather(hour), weather_context=[],
            )))
        flagged, healthy = responses
        flag_target = next(feature['properties'] for feature in flagged.risk_geojson['features']
                           if feature['properties'].get('tree_id') == 'T')
        healthy_target = next(feature['properties'] for feature in healthy.risk_geojson['features']
                              if feature['properties'].get('tree_id') == 'T')
        assert flag_target['state'] != 'dead'
        assert flag_target['risk'] > 0.0
        assert flag_target['risk'] == pytest.approx(healthy_target['risk'])
        assert flagged.metadata.initial_infected_count == 1
        assert flagged.metadata.initial_seed_strategy == 'manual_tree_overrides'
        if pest == 'cecid':
            assert flagged.metadata.cecid_explicit_source_count == 1
            assert [source['tree_id'] for source in flagged.metadata.cecid_sources] == ['S']
            assert flag_target['cecid_source'] is False


@pytest.mark.parametrize('status,flag', FLAGS)
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_status_evidence_is_not_observed_infection_and_suppresses_arbitrary_fallback(status, flag, pest, stage, hour):
    service = SimulationService()
    service._load_modules()
    grid = OrchardGrid(1, 2)
    grid.state[:] = flag
    grid.tree_ids[:] = [['T0', 'T1']]
    graph = TreeGraph([TreeNode(i, f'T{i}', 122.58 + i * 0.0001, 10.585, i * 10.0, 0.0, 2.5)
                       for i in range(2)], max_dist=20.0)
    overrides = {'T0': status, 'T1': status}

    assert service._has_manual_infestation_source(overrides) is False
    assert service._grid_cecid_sources(grid, [], [])[0] == {}
    assert service._tree_cecid_sources(graph, [], [])[0] == {}
    grid_seed = service._seed_default_infestation(
        grid, PestTypeEnum(pest), stage, 42, tree_overrides=overrides)
    graph_seed = service._seed_tree_graph_infestation(
        graph, PestTypeEnum(pest), stage, 42, tree_overrides=overrides)
    assert grid_seed['count'] == graph_seed['count'] == 0
    assert grid_seed['strategy'] == graph_seed['strategy'] == 'status_source_hypotheses'
    assert not grid.infested_mask.any()
    assert graph.n_infested() == 0


@pytest.mark.parametrize('status,flag', FLAGS)
def test_bagging_can_protect_unbagged_history_and_monitoring_trees(status, flag):
    grid = OrchardGrid(1, 3)
    grid.state[:] = [[flag, CellState.INFESTED, CellState.DEAD]]
    grid.bag_trees(np.ones((1, 3), dtype=bool))
    np.testing.assert_array_equal(grid.state, [[CellState.BAGGED, CellState.INFESTED, CellState.DEAD]])


def _status_orchard(statuses, property_name='Status'):
    return {'type': 'FeatureCollection', 'features': [
        {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [122.58 + i * 0.0001, 10.585]},
         'properties': {'Tree_ID': str(i), property_name: status}}
        for i, status in enumerate(statuses)
    ]}


def _run_imported_statuses(mode, pest, stage, statuses, property_name='Status', overrides=None, bagged_ids=None):
    request = SimulationRequest(
        pest_type=pest, orchard_stage=stage, orchard_geojson=_status_orchard(statuses, property_name),
        simulation_mode=mode, hours=1, random_seed=42, tree_overrides=overrides,
        bagged_tree_ids=bagged_ids or [],
        history_source_probability=0.0, suspect_source_probability=0.0,
    )
    # Isolate source selection using a zero-temperature-activity scenario.
    # Darkness alone no longer implies zero Fruit Fly movement.
    weather = [{**entry, 'temperature_c': 10.0} for entry in _weather(0)]
    return asyncio.run(SimulationService().run_simulation(
        request, weather_data=weather, weather_context=[],
    ))


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('status', ['healthy', 'infected', 'bagged', 'dead', 'history_infected', 'suspect'])
def test_imported_statuses_are_honored_and_known_sources_prevent_unknown_fallback(mode, pest, stage, hour, status):
    response = _run_imported_statuses(mode, pest, stage, ['infected', status, 'healthy'])
    targets = {f['properties']['tree_id']: f['properties'] for f in response.risk_geojson['features']}
    expected_status = {'healthy': 'unbagged', 'infected': 'infested'}.get(status, status)
    if mode == 'tree_graph' and status in ('history_infected', 'suspect'):
        expected_status = 'unbagged'
    assert targets['1']['state'] == expected_status
    assert targets['1']['risk'] == float(status == 'infected')
    assert response.metadata.initial_infected_count == 1 + int(status == 'infected')
    assert response.metadata.initial_seed_strategy == 'existing_infestation'
    assert response.metadata.initial_seed_count == response.metadata.initial_infected_count
    if pest == 'cecid':
        assert response.metadata.cecid_assumed_source_count == 0
        assert {source['tree_id'] for source in response.metadata.cecid_sources} == (
            {'0', '1'} if status == 'infected' else {'0'})


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('property_name', ['Status', 'status'])
def test_imported_status_aliases_and_manual_overrides_share_normalization(mode, property_name):
    response = _run_imported_statuses(
        mode, 'fruitfly', 'mature', [' INFESTED ', ' Unbagged ', ' History Infected ', ' DEAD '],
        property_name, overrides={'3': ' Suspect '},
    )
    targets = {f['properties']['tree_id']: f['properties'] for f in response.risk_geojson['features']}
    assert [targets[str(i)]['state'] for i in range(4)] == (
        ['infested', 'unbagged', 'history_infected', 'suspect'] if mode == 'grid'
        else ['infested', 'unbagged', 'unbagged', 'unbagged'])
    assert response.metadata.initial_infected_count == 1
    assert response.metadata.initial_seed_strategy == 'existing_infestation'


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
def test_bagging_list_preserves_known_infection_and_dead_states_with_manual_overrides_last(mode, pest, stage, hour):
    response = _run_imported_statuses(
        mode, pest, stage, ['infected', 'dead', 'healthy', 'history_infected', 'suspect', 'healthy'],
        bagged_ids=[str(i) for i in range(6)], overrides={'5': 'healthy'},
    )
    targets = {f['properties']['tree_id']: f['properties'] for f in response.risk_geojson['features']}
    assert [targets[str(i)]['state'] for i in range(6)] == [
        'infested', 'dead', 'bagged', 'bagged', 'bagged', 'unbagged']
    assert response.metadata.initial_infected_count == 1
    assert response.metadata.initial_seed_strategy == 'existing_infestation'
    if pest == 'cecid':
        assert [source['tree_id'] for source in response.metadata.cecid_sources] == ['0']


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('status', ['bagged', 'dead'])
def test_imported_protected_or_removed_trees_are_not_automatically_seeded(mode, pest, stage, hour, status):
    response = _run_imported_statuses(mode, pest, stage, [status, status])
    assert response.metadata.initial_infected_count == response.metadata.initial_seed_count == 0
    assert response.metadata.initial_seed_strategy == 'none_no_active_stage_trees'
    assert all(f['properties']['state'] == status and f['properties']['risk'] == 0.0
               for f in response.risk_geojson['features'])
    if pest == 'cecid':
        assert response.metadata.cecid_source_count == 0


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('status', ['healthy', 'history_infected', 'suspect'])
def test_unknown_fallback_only_selects_ordinary_unbagged_candidates(mode, pest, stage, hour, status):
    response = _run_imported_statuses(mode, pest, stage, ['bagged', 'dead', status])
    targets = {f['properties']['tree_id']: f['properties'] for f in response.risk_geojson['features']}
    assert targets['0']['state'] == 'bagged'
    assert targets['1']['state'] == 'dead'
    if status != 'healthy':
        assert response.metadata.initial_seed_strategy == 'status_source_hypotheses'
        assert response.metadata.initial_infected_count == 0
        assert all(not source['active'] for source in response.metadata.initial_sources)
        if pest == 'cecid':
            assert response.metadata.cecid_source_count == 0
        return
    if pest == 'cecid':
        assert response.metadata.initial_infected_count == 0
        assert [source['tree_id'] for source in response.metadata.cecid_sources] == ['2']
        assert response.metadata.cecid_sources[0]['assumed'] is True
    else:
        assert response.metadata.initial_infected_count == 1
        assert targets['2']['state'] == 'infested'


@pytest.mark.parametrize('pest,stage,hour', PESTS)
@pytest.mark.parametrize('state', [CellState.BAGGED, CellState.DEAD, CellState.EMPTY])
def test_direct_fallback_without_eligible_trees_leaves_states_and_counts_unchanged(pest, stage, hour, state):
    service = SimulationService()
    grid = OrchardGrid(1, 2)
    grid.state[:] = state
    graph = TreeGraph([] if state == CellState.EMPTY else [
        TreeNode(i, str(i), 122.58 + i * 0.0001, 10.585, i * 10.0, 0.0, 2.5, state=int(state))
        for i in range(2)
    ], max_dist=20.0)
    grid_seed = service._seed_default_infestation(grid, PestTypeEnum(pest), stage, 42)
    graph_seed = service._seed_tree_graph_infestation(graph, PestTypeEnum(pest), stage, 42, None)
    assert grid_seed['count'] == graph_seed['count'] == 0
    np.testing.assert_array_equal(grid.state, [[state, state]])
    assert all(node.state == state for node in graph.nodes)


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_dead_fruitlet_tree_cannot_relay_cecid_adults_to_a_distant_tree(mode):
    service = SimulationService()
    service._load_modules()
    networks = []
    dead_key = target_key = None
    for middle_state in (CellState.DEAD, CellState.UNBAGGED):
        if mode == 'grid':
            grid = OrchardGrid(1, 5)
            grid.origin_lon, grid.origin_lat = 122.58, 10.585
            grid.state[:] = [[CellState.INFESTED, CellState.EMPTY, middle_state, CellState.EMPTY, CellState.UNBAGGED]]
            source_key, dead_key, target_key = (0, 0), (0, 2), (0, 4)
            network = service._grid_cecid_habitat_network(
                grid, {source_key: 1.0}, [], np.full((1, 5), OrchardStage.FRUITLET))
        else:
            lon_per_m = 1.0 / (111_132.0 * math.cos(math.radians(10.585)))
            graph = TreeGraph([
                TreeNode(i, str(i), 122.58 + i * 10.0 * lon_per_m, 10.585, i * 10.0, 0.0, 2.5,
                         state=int(state))
                for i, state in enumerate((CellState.INFESTED, middle_state, CellState.UNBAGGED))
            ], max_dist=20.0)
            source_key, dead_key, target_key = 0, 1, 2
            network = service._tree_cecid_habitat_network(
                graph, {source_key: 1.0}, [], [OrchardStage.FRUITLET] * 3)
        tracker = CecidHabitatTracker(network)
        cohort = {'test': {'source': source_key, 'pressure': 1.0}}
        first_hour = tracker.step(cohort, True, 0.0, 0.0)
        second_hour = tracker.step(cohort, True, 0.0, 0.0)
        assert target_key not in first_hour
        networks.append((network, second_hour))
    assert dead_key not in networks[0][0].target_nodes
    assert target_key not in networks[0][1]
    assert dead_key in networks[1][0].target_nodes
    assert target_key in networks[1][1]


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_dead_tree_receives_no_cecid_risk_during_real_local_and_external_pressure(mode):
    orchard = _status_orchard(['infected', 'dead', 'healthy'])
    for index, feature in enumerate(orchard['features']):
        feature['geometry']['coordinates'][0] = 122.58 + index * 0.00005
    request = SimulationRequest(
        pest_type='cecid', orchard_stage='fruitlet',
        orchard_geojson=orchard,
        simulation_mode=mode, hours=1, random_seed=42, neighbor_threat=0.6,
        manual_weather_prefix_rain=[0.0] * 68 + [2.0] * 4,
    )
    response = asyncio.run(SimulationService().run_simulation(
        request, weather_data=_weather(18), weather_context=[],
    ))
    targets = {f['properties']['tree_id']: f['properties'] for f in response.risk_geojson['features']}
    assert targets['2']['risk'] > 0.0
    assert targets['2']['local_exposure_hours'] == 1
    assert targets['2']['external_exposure_hours'] == 1
    assert targets['1']['state'] == 'dead'
    assert targets['1']['risk'] == targets['1']['cumulative_establishment_probability'] == 0.0
    assert targets['1']['exposure_hours'] == 0
    assert targets['1']['cecid_source'] is False


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
def test_explicit_cecid_soil_zone_can_keep_a_dead_location_anchor_without_reviving_the_tree(mode):
    service = SimulationService()
    service._load_modules()
    if mode == 'grid':
        grid = OrchardGrid(1, 3)
        grid.origin_lon, grid.origin_lat = 122.58, 10.585
        grid.state[:] = [[CellState.DEAD, CellState.EMPTY, CellState.UNBAGGED]]
        anchor_key, target_key = (0, 0), (0, 2)
        lon = grid.origin_lon + 2.5 / (111_132.0 * math.cos(math.radians(10.585)))
        lat = grid.origin_lat + 2.5 / 111_132.0
    else:
        graph = TreeGraph([
            TreeNode(0, 'dead', 122.58, 10.585, 0.0, 0.0, 2.5, state=TreeState.DEAD),
            TreeNode(1, 'healthy', 122.5801, 10.585, 10.0, 0.0, 2.5),
        ], max_dist=20.0)
        anchor_key, target_key = 0, 1
        lon, lat = graph.nodes[0].lon, graph.nodes[0].lat
    margin = 0.00001
    zone = {'id': 'ground', 'label': 'Explicit soil evidence', 'pressure': 'medium', 'coordinates': [
        [lon - margin, lat - margin], [lon + margin, lat - margin],
        [lon + margin, lat + margin], [lon - margin, lat + margin],
    ]}
    if mode == 'grid':
        pressures, metadata = service._grid_cecid_sources(grid, [zone], [])
        network = service._grid_cecid_habitat_network(grid, pressures, [])
        assert grid.state[anchor_key] == CellState.DEAD
    else:
        pressures, metadata = service._tree_cecid_sources(graph, [zone], [])
        network = service._tree_cecid_habitat_network(graph, pressures, [])
        assert graph.nodes[anchor_key].state == TreeState.DEAD
    assert set(pressures) == {anchor_key}
    assert metadata[0]['origin'] == 'emergence_zone'
    assert metadata[0]['assumed'] is False
    assert anchor_key not in network.target_nodes
    tracker = CecidHabitatTracker(network)
    contributions = tracker.step({'soil': {'source': anchor_key, 'pressure': 1.0}}, True, 0.0, 0.0)
    assert target_key in contributions
