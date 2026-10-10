import asyncio

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from api.models.schemas import NeighborSource, SimulationRequest, PestTypeEnum
from api.services.simulation_service import SimulationService
from core.config import DIRECTION_BEARING_MAP, WIND_NEIGHBOR_BOOST
from core.config import CellState, OrchardStage
from core.biological_rules import CecidFlyGate
from core.cecid_habitat import CecidHabitatNetwork
from core.grid import OrchardGrid
from core.simulation_engine import SimulationEngine
from core.neighbor_pressure import combine_neighbor_pressure, resolve_neighbor_sources
from core.tree_graph_model import TreeGraph, TreeGraphEngine, TreeNode
from utils.weather import WeatherTimeSeries


SOURCES = [
    {"direction": "N", "threat": 0.4, "label": "North farm"},
    {"direction": "E", "threat": 0.6, "label": "East farm"},
]


def orchard():
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [122 + col * 0.00009, 10 + row * 0.00009]},
         "properties": {"Tree_ID": f"T{row}{col}"}}
        for row in range(3) for col in range(3)
    ]}


def test_source_validation_and_explicit_empty_list_precedence():
    assert NeighborSource(direction=" ne ", threat=0.5).direction == "NE"
    for data in [{"direction": "up", "threat": 0.5}, {"direction": "N", "threat": 1.1}, {"threat": float('nan')}]:
        with pytest.raises(ValidationError):
            NeighborSource(**data)
    assert resolve_neighbor_sources([], 1, "N") == []
    assert resolve_neighbor_sources(None, 0.3, "E")[0]['direction'] == 'E'


def test_legacy_neighbor_direction_uses_the_same_validation_as_multiple_sources():
    request = dict(pest_type='fruitfly', orchard_geojson=orchard(), neighbor_threat=0.5)
    assert SimulationRequest(**request, neighbor_direction=' ne ').neighbor_direction == 'NE'
    for direction in ('up', 'east', '', 90):
        with pytest.raises(ValidationError):
            SimulationRequest(**request, neighbor_direction=direction)


def test_pressure_is_bounded_order_independent_and_uses_each_wind_bearing():
    components = [(SOURCES[0], np.array([0.4])), (SOURCES[1], np.array([0.6]))]
    pressure = combine_neighbor_pressure(components, 0)[0]
    assert pressure == pytest.approx(0.4 * (1 + WIND_NEIGHBOR_BOOST) + 0.6)
    assert combine_neighbor_pressure(list(reversed(components)), 0)[0] == pressure
    overlapping = [(SOURCES[0], np.array([1.])), (SOURCES[1], np.array([1.]))]
    assert combine_neighbor_pressure(overlapping)[0] == 1
    assert 0 <= combine_neighbor_pressure(overlapping, 0)[0] <= 2


@pytest.mark.parametrize('direction', DIRECTION_BEARING_MAP)
def test_grid_single_source_matches_legacy_and_copy_keeps_sources(direction):
    legacy = OrchardGrid(3, 3)
    legacy.set_neighbor_threat_directional(direction, 0.4)
    legacy.neighbor_bearing = DIRECTION_BEARING_MAP[direction]
    multiple = OrchardGrid(3, 3)
    multiple.set_neighbor_sources([{'direction': direction, 'threat': 0.4}])
    copied = multiple.copy()
    for row in range(3):
        for col in range(3):
            for wind in (0, 90, 180, 270):
                assert copied.get_effective_neighbor_threat(row, col, wind) == pytest.approx(legacy.get_effective_neighbor_threat(row, col, wind))
    multiple.set_neighbor_sources([])
    assert not multiple.neighbor_threat.any()
    assert copied.neighbor_threat.any()
    copied.set_neighbor_threat_uniform(0)
    assert copied.get_effective_neighbor_threat(2, 2, 0) == 0


def test_grid_north_and_east_pressure_reach_the_correct_geographic_edges():
    grid = OrchardGrid(3, 3)
    grid.set_neighbor_sources(SOURCES)
    # API georeferencing increases latitude with row.
    assert grid.get_neighbor_threat(2, 1) == pytest.approx(0.4)
    assert grid.get_neighbor_threat(1, 2) == pytest.approx(0.6)
    assert grid.get_neighbor_threat(0, 0) == 0
    assert grid.get_effective_neighbor_threat(2, 1, 0) > grid.get_effective_neighbor_threat(2, 1, 180)
    assert grid.get_effective_neighbor_threat(1, 2, 90) > grid.get_effective_neighbor_threat(1, 2, 270)


@pytest.mark.parametrize('direction,bearing,row,col', [
    ('N', 0, 2, 1), ('NE', 45, 2, 2), ('E', 90, 1, 2), ('SE', 135, 0, 2),
    ('S', 180, 0, 1), ('SW', 225, 0, 0), ('W', 270, 1, 0), ('NW', 315, 2, 0),
])
def test_every_neighbor_gradient_faces_its_geographic_edge(direction, bearing, row, col):
    grid = OrchardGrid(3, 3)
    grid.set_neighbor_sources([{'direction': direction, 'threat': 0.6}])
    assert grid.get_neighbor_threat(row, col) == pytest.approx(0.6)
    assert grid.get_neighbor_threat(2 - row, 2 - col) == pytest.approx(0.0)
    assert grid.get_effective_neighbor_threat(row, col, bearing) == pytest.approx(0.6 * (1 + WIND_NEIGHBOR_BOOST))
    assert grid.get_effective_neighbor_threat(row, col, (bearing + 180) % 360) == pytest.approx(0.6 * (1 - WIND_NEIGHBOR_BOOST))


@pytest.mark.parametrize('sources', [SOURCES] + [
    [{'direction': direction, 'threat': 0.6}] for direction in DIRECTION_BEARING_MAP
])
def test_grid_and_tree_graph_pressure_agree_at_the_same_locations(sources):
    # Use a rectangular orchard to catch direction errors hidden by symmetry.
    grid = OrchardGrid(3, 5)
    grid.set_neighbor_sources(sources)
    nodes = [TreeNode(i, str(i), 0, 0, col, row, 2.5)
             for i, (row, col) in enumerate((row, col) for row in range(3) for col in range(5))]
    graph = TreeGraph(nodes, max_dist=50)
    engine = TreeGraphEngine(graph=graph, weather=[{'wind_speed_ms': 1, 'wind_dir_deg': 0, 'temperature_c': 30, 'rainfall_mm': 0}], neighbor_sources=sources)
    for wind in range(0, 360, 45):
        expected = [grid.get_effective_neighbor_threat(row, col, wind) for row in range(3) for col in range(5)]
        assert engine._effective_neighbor_threats(wind) == pytest.approx(expected)


@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('pest,stage', [('fruitfly', 'mature'), ('cecid', 'fruitlet')])
def test_simulation_preserves_every_source_and_replays_deterministically(mode, pest, stage):
    request = SimulationRequest(pest_type=pest, orchard_stage=stage, orchard_geojson=orchard(),
                                simulation_mode=mode, hours=2, random_seed=42, neighbor_sources=SOURCES)
    service = SimulationService()
    response = asyncio.run(service.run_simulation(request, weather_data=None))
    replay = asyncio.run(service.run_simulation(SimulationRequest.model_validate(request.model_dump(mode='json')), weather_data=None))
    assert [source.model_dump() for source in response.metadata.neighbor_sources] == SOURCES
    assert response.metadata.neighbor_threat == 1
    assert response.metadata.neighbor_direction is None
    assert response.risk_geojson == replay.risk_geojson
    if pest == 'fruitfly':
        assert response.metadata.initial_seed_strategy == 'neighbor_edges_N_E'
        assert response.metadata.initial_seed_count >= 2
    else:
        assert response.metadata.initial_seed_strategy.startswith('assumed_soil_')


@pytest.mark.parametrize('direction,row,col', [
    ('N', 2, None), ('NE', 2, 2), ('E', None, 2), ('SE', 0, 2),
    ('S', 0, None), ('SW', 0, 0), ('W', None, 0), ('NW', 2, 0),
])
@pytest.mark.parametrize('mode', ['grid', 'tree_graph'])
@pytest.mark.parametrize('source_form', ['legacy', 'multiple'])
def test_neighbor_auto_seeds_the_correct_geographic_edge(direction, row, col, mode, source_form):
    service = SimulationService()
    service._load_modules()
    geojson = orchard()
    pressure = dict(neighbor_threat=0.3, neighbor_direction=direction) if source_form == 'legacy' else dict(
        neighbor_sources=[{'direction': direction, 'threat': 0.3}])
    if mode == 'grid':
        grid, _origin = service._create_grid_from_geojson(geojson)
        result = service._seed_default_infestation(grid, PestTypeEnum.FRUITFLY, 'mature', 42, **pressure)
        selected = result['cells'][0]
        tree_id = grid.tree_ids[selected['row'], selected['col']]
    else:
        nodes = [TreeNode(index, feature['properties']['Tree_ID'], *feature['geometry']['coordinates'],
                          (index % 3) * 10, (index // 3) * 10, 2.5)
                 for index, feature in enumerate(geojson['features'])]
        graph = TreeGraph(nodes, max_dist=50)
        result = service._seed_tree_graph_infestation(graph, PestTypeEnum.FRUITFLY, 'mature', 42,
                                                    tree_overrides=None, **pressure)
        tree_id = result['tree_ids'][0]

    assert result['count'] == 1
    if row is not None:
        assert tree_id[1] == str(row)
    if col is not None:
        assert tree_id[2] == str(col)


@pytest.mark.parametrize('hour,stage,active', [(18, OrchardStage.FRUITLET, True), (12, OrchardStage.FRUITLET, False), (18, OrchardStage.MATURE, False)])
def test_multiple_cecid_neighbors_are_external_and_obey_gates_in_both_modes(hour, stage, active):
    weather = WeatherTimeSeries(pd.DataFrame([{
        'datetime': pd.Timestamp(f'2026-04-01T{hour}:00:00+08:00'),
        'wind_speed_ms': 1, 'wind_dir_deg': 0, 'temperature_c': 28, 'rainfall_mm': 0,
    }]), source='test')
    cells = [(0, 0), (0, 2), (2, 0), (2, 2)]
    positions = [(122.58 + col * 0.00005, 10.585 + row * 0.00005) for row, col in cells]
    shared = dict(weather=weather, transition_mode='threshold', threshold=2,
                  gates=[CecidFlyGate(latitude=10.585, longitude=122.58)],
                  orchard_stage=stage, initial_rainfall_history=[0.] * 68 + [2.] * 4,
                  cecid_source_pressures={})
    grid = OrchardGrid(3, 3)
    for cell in cells:
        grid.set_state(*cell, CellState.UNBAGGED)
    grid.set_neighbor_sources(SOURCES)
    grid_engine = SimulationEngine(grid=grid, stage_grid=np.full((3, 3), int(stage)),
        cecid_habitat_network=CecidHabitatNetwork.from_lonlat({}, dict(zip(cells, positions)), []), **shared)
    grid_result = grid_engine.run(n_steps=1, progress=False)
    graph = TreeGraph([TreeNode(i, str(i), *positions[i], col * 5, row * 5, 2.5)
                       for i, (row, col) in enumerate(cells)], max_dist=50)
    graph_engine = TreeGraphEngine(graph=graph, pest_type='cecid', neighbor_sources=SOURCES,
        stage_per_tree=[stage] * 4,
        cecid_habitat_network=CecidHabitatNetwork.from_lonlat({}, dict(enumerate(positions)), []), **shared)
    graph_result = graph_engine.run(n_steps=1, progress=False)
    grid_risks = [grid_result.snapshots[0]['risk'][row, col] for row, col in cells]
    assert graph_result.snapshots[0]['risks'] == pytest.approx(grid_risks)
    assert grid_risks[0] == 0
    if active:
        assert all(risk > 0 for risk in grid_risks[1:])
        assert grid_engine.cecid_habitat_diagnostics[0]['external_neighbor_exposed_tree_count'] == 3
        assert graph_engine.cecid_habitat_diagnostics[0]['external_neighbor_exposed_tree_count'] == 3
    else:
        assert not any(grid_risks)
