"""Shared adult-only Weed Habitat network for Cecid Fly simulations.

Weed polygons are provisional shelter/relay assumptions. They never arm soil
sources, emit cohorts, become hosts, or create a second generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, floor, hypot, pi
from typing import Any, Dict, Hashable, Iterable, Mapping, Optional, Tuple

from core.config import (
    CECID_DISTANCE_DECAY,
    CECID_GENTLE_WIND_MAX_KMH,
    CECID_GENTLE_WIND_MIN_KMH,
    CECID_MAX_RANGE_M,
    CECID_TREE_RESTING_EFFICIENCY,
    CECID_WEED_RELAY_EFFICIENCY,
    CECID_WEED_RELAY_SPACING_M,
    CECID_WIND_ACTIVITY_SCALE_KMH,
    CECID_WIND_DIRECTION_FULL_KMH,
    CECID_WIND_DIRECTION_MAX_ASSIST,
)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def cecid_wind_activity(wind_speed_ms: float) -> float:
    """Return Cecid's provisional controlled-movement activity score.

    Wind up to 5 km/h receives no activity penalty. Above that point a
    long-tailed inverse-square curve reduces controlled movement without
    treating a common orchard breeze as near-total adult mortality::

        activity = 1 / (1 + ((speed_kmh - 5) / 6) ** 2)

    This is a transparent research assumption pending target-species field
    calibration. Directional downwind assistance is applied separately per
    habitat edge, and the 15 m hourly movement cap is never expanded.
    """
    speed_kmh = max(0.0, float(wind_speed_ms)) * 3.6
    if speed_kmh <= CECID_GENTLE_WIND_MAX_KMH:
        return 1.0
    excess = speed_kmh - CECID_GENTLE_WIND_MAX_KMH
    scaled_excess = excess / CECID_WIND_ACTIVITY_SCALE_KMH
    return 1.0 / (1.0 + scaled_excess ** 2)


def cecid_wind_survival(wind_speed_ms: float) -> float:
    """Backward-compatible alias for the activity score.

    Existing API/history fields retain ``wind_survival_score`` so older
    clients continue to work, but new code and diagnostics call this an
    activity score because the model does not estimate adult mortality.
    """
    return cecid_wind_activity(wind_speed_ms)


def cecid_wind_assist_strength(wind_speed_ms: float) -> float:
    """Ramp downwind assistance from the flight-control reference to 35%."""
    speed_kmh = max(0.0, float(wind_speed_ms)) * 3.6
    span = CECID_WIND_DIRECTION_FULL_KMH - CECID_GENTLE_WIND_MIN_KMH
    progress = _clamp((speed_kmh - CECID_GENTLE_WIND_MIN_KMH) / span, 0.0, 1.0)
    return CECID_WIND_DIRECTION_MAX_ASSIST * progress


def cecid_wind_direction_factor(
    wind_speed_ms: float,
    wind_from_deg: float,
    movement_bearing_deg: float,
) -> float:
    """Bias an edge toward the meteorological downwind direction."""
    assist = cecid_wind_assist_strength(wind_speed_ms)
    if assist <= 0.0:
        return 1.0
    wind_toward = (float(wind_from_deg) + 180.0) % 360.0
    difference = (float(movement_bearing_deg) - wind_toward + 180.0) % 360.0 - 180.0
    return _clamp(1.0 + assist * cos(difference * pi / 180.0), 0.65, 1.35)


def cecid_distance_factor(distance_m: float) -> float:
    """Use the same 5 m reference distance in both spatial engines."""
    exponent = max(float(distance_m) / 5.0 - 1.0, 0.0)
    return float(CECID_DISTANCE_DECAY) ** exponent


@dataclass(frozen=True)
class CecidHabitatNode:
    node_id: str
    kind: str
    key: Optional[Hashable]
    x: float
    y: float
    density: Optional[str] = None
    relay_efficiency: float = 1.0


@dataclass(frozen=True)
class CecidHabitatEdge:
    destination: str
    distance_m: float
    bearing_deg: float


class CecidHabitatNetwork:
    """Static source/weed/tree graph shared by grid and tree modes.

    ``target`` nodes are fruitlet trees that can receive risk and temporarily
    retain an existing adult cohort. They are movement locations, never new
    reproductive or soil-emergence sources.
    """

    def __init__(self) -> None:
        self.nodes: Dict[str, CecidHabitatNode] = {}
        self.adjacency: Dict[str, list[CecidHabitatEdge]] = {}
        self.source_nodes: Dict[Hashable, str] = {}
        self.target_nodes: Dict[Hashable, str] = {}
        self.zone_count = 0
        self.resolved_habitat_component_count = 0
        self.zone_density_counts = {"sparse": 0, "moderate": 0, "dense": 0}

    @staticmethod
    def _zone_value(zone: Any, name: str, default: Any = None) -> Any:
        if isinstance(zone, dict):
            value = zone.get(name, default)
        else:
            value = getattr(zone, name, default)
        return getattr(value, "value", value)

    @classmethod
    def from_lonlat(
        cls,
        source_positions: Mapping[Hashable, Tuple[float, float]],
        target_positions: Mapping[Hashable, Tuple[float, float]],
        weed_zones: Optional[Iterable[Any]] = None,
    ) -> "CecidHabitatNetwork":
        network = cls()
        all_positions = list(source_positions.values()) + list(target_positions.values())
        zones = list(weed_zones or [])
        for zone in zones:
            all_positions.extend(
                (float(point[0]), float(point[1]))
                for point in (cls._zone_value(zone, "coordinates", []) or [])
                if isinstance(point, (list, tuple)) and len(point) >= 2
            )
        if not all_positions:
            return network

        origin_lon = min(position[0] for position in all_positions)
        origin_lat = min(position[1] for position in all_positions)
        mean_lat = sum(position[1] for position in all_positions) / len(all_positions)
        metres_lat = 111_132.0
        metres_lon = 111_132.0 * cos(mean_lat * pi / 180.0)

        def local(position: Tuple[float, float]) -> Tuple[float, float]:
            return (
                (float(position[0]) - origin_lon) * metres_lon,
                (float(position[1]) - origin_lat) * metres_lat,
            )

        for index, key in enumerate(sorted(source_positions, key=repr)):
            x, y = local(source_positions[key])
            node_id = f"source:{index}"
            network.nodes[node_id] = CecidHabitatNode(node_id, "source", key, x, y)
            network.source_nodes[key] = node_id
            network.adjacency[node_id] = []

        for index, key in enumerate(sorted(target_positions, key=repr)):
            x, y = local(target_positions[key])
            node_id = f"target:{index}"
            network.nodes[node_id] = CecidHabitatNode(node_id, "target", key, x, y)
            network.target_nodes[key] = node_id
            network.adjacency[node_id] = []

        network._add_relay_nodes(zones, local)
        network._connect_nodes()
        return network

    def _add_relay_nodes(self, zones: list[Any], local) -> None:
        if not zones:
            return
        from shapely.geometry import Point, Polygon
        from shapely.ops import unary_union

        zone_geometries = []
        for zone in zones:
            coordinates = self._zone_value(zone, "coordinates", []) or []
            if len(coordinates) < 3:
                continue
            polygon = Polygon([local((point[0], point[1])) for point in coordinates])
            if not polygon.is_valid:
                polygon = polygon.buffer(0)
            if polygon.is_empty:
                continue
            density = str(self._zone_value(zone, "density", "moderate")).lower()
            if density not in CECID_WEED_RELAY_EFFICIENCY:
                density = "moderate"
            zone_geometries.append((polygon, density))
            self.zone_density_counts[density] += 1

        self.zone_count = len(zone_geometries)
        if not zone_geometries:
            return

        # Treat weed habitat as one physical landscape, not as independent
        # stacked layers.  Sampling each submitted polygon separately leaves
        # internal overlap boundaries behind and can create extra relay paths
        # when a user accidentally draws the same habitat twice.  Dissolving
        # the geometry first makes duplicate/overlapping polygons spatially
        # idempotent; density at each sample is still the highest covering
        # zone, matching the documented overlap rule.
        dissolved = unary_union([polygon for polygon, _density in zone_geometries])
        if dissolved.is_empty:
            return
        dissolved_polygons = (
            list(dissolved.geoms)
            if dissolved.geom_type == "MultiPolygon"
            else [dissolved]
        )
        self.resolved_habitat_component_count = len(dissolved_polygons)

        spacing = float(CECID_WEED_RELAY_SPACING_M)
        samples: Dict[Tuple[int, int], Tuple[float, float]] = {}

        def add_sample(x: float, y: float) -> None:
            samples.setdefault((round(x * 10), round(y * 10)), (float(x), float(y)))

        for polygon in dissolved_polygons:
            min_x, min_y, max_x, max_y = polygon.bounds
            start_x = floor(min_x / spacing) * spacing
            start_y = floor(min_y / spacing) * spacing
            x = start_x
            while x <= max_x + 1e-9:
                y = start_y
                while y <= max_y + 1e-9:
                    if polygon.covers(Point(x, y)):
                        add_sample(x, y)
                    y += spacing
                x += spacing

            boundary_parts = (
                list(polygon.boundary.geoms)
                if hasattr(polygon.boundary, "geoms")
                else [polygon.boundary]
            )
            for boundary in boundary_parts:
                distance = 0.0
                while distance <= boundary.length + 1e-9:
                    point = boundary.interpolate(distance)
                    add_sample(point.x, point.y)
                    distance += spacing
            representative = polygon.representative_point()
            add_sample(representative.x, representative.y)

        for index, (_sample_key, (x, y)) in enumerate(sorted(samples.items())):
            densities = [
                density for polygon, density in zone_geometries
                if polygon.buffer(0.05).covers(Point(x, y))
            ]
            if not densities:
                continue
            density = max(densities, key=lambda value: CECID_WEED_RELAY_EFFICIENCY[value])
            node_id = f"relay:{index}"
            self.nodes[node_id] = CecidHabitatNode(
                node_id=node_id,
                kind="relay",
                key=None,
                x=x,
                y=y,
                density=density,
                relay_efficiency=CECID_WEED_RELAY_EFFICIENCY[density],
            )
            self.adjacency[node_id] = []

    @staticmethod
    def _edge(source: CecidHabitatNode, target: CecidHabitatNode) -> CecidHabitatEdge:
        dx = target.x - source.x
        dy = target.y - source.y
        return CecidHabitatEdge(
            destination=target.node_id,
            distance_m=hypot(dx, dy),
            bearing_deg=(atan2(dx, dy) * 180.0 / pi) % 360.0,
        )

    def _connect_nodes(self) -> None:
        sources = [node for node in self.nodes.values() if node.kind == "source"]
        relays = [node for node in self.nodes.values() if node.kind == "relay"]
        targets = [node for node in self.nodes.values() if node.kind == "target"]

        # A 15 m spatial hash avoids an all-pairs relay comparison for large
        # orchard polygons while producing the same deterministic edge set.
        destinations = [*relays, *targets]
        bucket_size = float(CECID_MAX_RANGE_M)
        buckets: Dict[Tuple[int, int], list[CecidHabitatNode]] = {}
        for destination in destinations:
            bucket = (
                floor(destination.x / bucket_size),
                floor(destination.y / bucket_size),
            )
            buckets.setdefault(bucket, []).append(destination)

        # Tree targets are valid resting/movement locations for the same adult
        # cohort. Keeping sources out of ``destinations`` prevents a path from
        # turning another source into a relay or generating a new cohort.
        for origin in [*sources, *relays, *targets]:
            bucket_x = floor(origin.x / bucket_size)
            bucket_y = floor(origin.y / bucket_size)
            for offset_x in (-1, 0, 1):
                for offset_y in (-1, 0, 1):
                    for destination in buckets.get(
                        (bucket_x + offset_x, bucket_y + offset_y), []
                    ):
                        if origin.node_id == destination.node_id:
                            continue
                        edge = self._edge(origin, destination)
                        if edge.distance_m <= CECID_MAX_RANGE_M + 1e-9:
                            self.adjacency[origin.node_id].append(edge)

        for edges in self.adjacency.values():
            edges.sort(key=lambda edge: (edge.destination, edge.distance_m))

    @property
    def relay_count(self) -> int:
        return sum(node.kind == "relay" for node in self.nodes.values())

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self.adjacency.values())


class CecidHabitatTracker:
    """Propagate each adult cohort through at most one habitat edge per hour."""

    def __init__(self, network: CecidHabitatNetwork) -> None:
        self.network = network
        self.relay_state: Dict[str, Dict[str, float]] = {}
        self.last_diagnostics: Dict[str, Any] = self._empty_diagnostics()

    def _empty_diagnostics(self) -> Dict[str, Any]:
        return {
            "weed_zone_count": self.network.zone_count,
            "weed_relay_count": self.network.relay_count,
            "weed_density_counts": dict(self.network.zone_density_counts),
            "habitat_edge_count": self.network.edge_count,
            "active_source_count": 0,
            "active_cohort_count": 0,
            "active_relay_count": 0,
            "active_tree_rest_count": 0,
            "active_mobility_node_count": 0,
            "active_relay_density_counts": {
                "sparse": 0, "moderate": 0, "dense": 0,
            },
            "reachable_tree_count": 0,
            "max_path_efficiency": 0.0,
            "directional_factor_min": 1.0,
            "directional_factor_max": 1.0,
            "tree_resting_efficiency": CECID_TREE_RESTING_EFFICIENCY,
            "habitat_limiting_reasons": [],
            "weed_effect_assumption": (
                "Provisional adult shelter, humidity retention, and short-hop relay coefficients; "
                "weeds are not Cecid sources, hosts, or pupal-survival multipliers."
            ),
        }

    def step(
        self,
        active_cohorts: Mapping[str, Mapping[str, Any]],
        eligible: bool,
        wind_speed_ms: float,
        wind_from_deg: float,
    ) -> Dict[Hashable, list[Dict[str, Any]]]:
        active_ids = set(active_cohorts)
        self.relay_state = {
            cohort_id: state
            for cohort_id, state in self.relay_state.items()
            if cohort_id in active_ids
        }
        target_contributions: Dict[Hashable, list[Dict[str, Any]]] = {}
        directional_factors: list[float] = []

        # Seed each cohort's mobility state exactly once. Source pressure may
        # remain available while that cohort is alive, but it is never copied
        # into another reproductive source.
        for cohort_id, cohort in active_cohorts.items():
            source_node_id = self.network.source_nodes.get(cohort.get("source"))
            if source_node_id is None:
                continue
            locations = self.relay_state.setdefault(cohort_id, {})
            locations[source_node_id] = max(locations.get(source_node_id, 0.0), 1.0)

        if eligible:
            for cohort_id, cohort in active_cohorts.items():
                source_key = cohort.get("source")
                source_node_id = self.network.source_nodes.get(source_key)
                if source_node_id is None:
                    continue
                current_locations = self.relay_state.setdefault(
                    cohort_id, {source_node_id: 1.0},
                )
                snapshot = dict(current_locations)
                next_locations = dict(current_locations)
                cohort_targets: Dict[Hashable, Dict[str, Any]] = {}

                def retain_best_target(target_key: Hashable, candidate: Dict[str, Any]) -> None:
                    previous = cohort_targets.get(target_key)
                    if (
                        previous is None
                        or candidate["path_efficiency"] > previous["path_efficiency"]
                    ):
                        cohort_targets[target_key] = candidate

                for node_id, path_efficiency in snapshot.items():
                    origin = self.network.nodes.get(node_id)
                    if origin is None:
                        continue

                    # Adults already resting on a fruitlet tree can continue to
                    # expose that tree during a later eligible window.
                    if origin.kind == "target" and origin.key is not None:
                        retain_best_target(origin.key, {
                            "cohort_id": cohort_id,
                            "source": source_key,
                            "cohort_pressure": float(cohort.get("pressure", 0.0)),
                            "path_efficiency": float(path_efficiency),
                            "edge_distance_m": 0.0,
                            "edge_bearing_deg": 0.0,
                            "wind_direction_factor": 1.0,
                            "resident_tree_pressure": True,
                        })

                    for edge in self.network.adjacency.get(node_id, []):
                        destination = self.network.nodes[edge.destination]
                        directional_factor = (
                            1.0
                            if edge.distance_m <= 1e-9
                            else cecid_wind_direction_factor(
                                wind_speed_ms, wind_from_deg, edge.bearing_deg,
                            )
                        )
                        directional_factors.append(directional_factor)
                        transfer = cecid_distance_factor(edge.distance_m)
                        transfer *= directional_factor
                        if destination.kind == "relay":
                            transfer *= destination.relay_efficiency
                        arrival_efficiency = float(path_efficiency) * transfer
                        if arrival_efficiency <= 0.0:
                            continue

                        # Keep the path state bounded so cycles and duplicate
                        # branches cannot manufacture pressure. Directional
                        # assistance still affects this hour's target exposure.
                        retained_efficiency = min(
                            float(path_efficiency), arrival_efficiency, 1.0,
                        )
                        if destination.kind == "target":
                            retained_efficiency *= CECID_TREE_RESTING_EFFICIENCY
                        next_locations[destination.node_id] = max(
                            next_locations.get(destination.node_id, 0.0),
                            retained_efficiency,
                        )

                        if destination.kind == "target" and destination.key is not None:
                            candidate = {
                                "cohort_id": cohort_id,
                                "source": source_key,
                                "cohort_pressure": float(cohort.get("pressure", 0.0)),
                                "path_efficiency": arrival_efficiency,
                                "edge_distance_m": edge.distance_m,
                                "edge_bearing_deg": edge.bearing_deg,
                                "wind_direction_factor": directional_factor,
                                "resident_tree_pressure": False,
                            }
                            retain_best_target(destination.key, candidate)
                self.relay_state[cohort_id] = next_locations
                for target_key, contribution in cohort_targets.items():
                    target_contributions.setdefault(target_key, []).append(contribution)

        diagnostics = self._empty_diagnostics()
        active_location_ids = {
            node_id
            for state in self.relay_state.values()
            for node_id, pressure in state.items()
            if pressure > 0.0
        }
        active_relay_ids = {
            node_id for node_id in active_location_ids
            if self.network.nodes[node_id].kind == "relay"
        }
        active_tree_ids = {
            node_id for node_id in active_location_ids
            if self.network.nodes[node_id].kind == "target"
        }
        active_density_counts = {"sparse": 0, "moderate": 0, "dense": 0}
        for relay_id in active_relay_ids:
            density = self.network.nodes[relay_id].density or "moderate"
            active_density_counts[density] = active_density_counts.get(density, 0) + 1
        limiting_reasons = []
        if not active_cohorts:
            limiting_reasons.append("no active adult cohort from a wetted soil source")
        elif eligible and not target_contributions:
            limiting_reasons.append(
                "adult pressure is retained at reachable tree or weed resting nodes until another eligible hour"
                if active_relay_ids or active_tree_ids
                else "no fruitlet tree or weed relay is reachable within the current 15 m habitat hop"
            )
        diagnostics.update({
            "active_source_count": len({
                cohort.get("source") for cohort in active_cohorts.values()
            }),
            "active_cohort_count": len(active_cohorts),
            "active_relay_count": len(active_relay_ids),
            "active_tree_rest_count": len(active_tree_ids),
            "active_mobility_node_count": len(active_location_ids),
            "active_relay_density_counts": active_density_counts,
            "reachable_tree_count": len(target_contributions),
            "max_path_efficiency": max(
                (
                    contribution["path_efficiency"]
                    for values in target_contributions.values()
                    for contribution in values
                ),
                default=0.0,
            ),
            "directional_factor_min": min(directional_factors, default=1.0),
            "directional_factor_max": max(directional_factors, default=1.0),
            "habitat_limiting_reasons": limiting_reasons,
        })
        self.last_diagnostics = diagnostics
        return target_contributions
