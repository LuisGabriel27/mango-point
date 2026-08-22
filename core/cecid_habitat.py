"""Shared adult-only Weed Habitat network for Cecid Fly simulations.

Weed polygons are provisional shelter/relay assumptions. They never arm soil
sources, emit cohorts, become hosts, or create a second generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, cos, exp, floor, hypot, pi
from typing import Any, Dict, Hashable, Iterable, Mapping, Optional, Tuple

from core.config import (
    CECID_DISTANCE_DECAY,
    CECID_GENTLE_WIND_MAX_KMH,
    CECID_GENTLE_WIND_MIN_KMH,
    CECID_HIGH_WIND_DECAY_KMH,
    CECID_MAX_RANGE_M,
    CECID_WEED_RELAY_EFFICIENCY,
    CECID_WEED_RELAY_SPACING_M,
    CECID_WIND_DIRECTION_MAX_ASSIST,
)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


def cecid_wind_survival(wind_speed_ms: float) -> float:
    """Return the soft survival score for the selected wind-speed curve."""
    speed_kmh = max(0.0, float(wind_speed_ms)) * 3.6
    if speed_kmh <= CECID_GENTLE_WIND_MAX_KMH:
        return 1.0
    excess = speed_kmh - CECID_GENTLE_WIND_MAX_KMH
    return exp(-((excess / CECID_HIGH_WIND_DECAY_KMH) ** 2))


def cecid_wind_assist_strength(wind_speed_ms: float) -> float:
    """Ramp directional assistance from zero at 1 km/h to 35% at 5 km/h."""
    speed_kmh = max(0.0, float(wind_speed_ms)) * 3.6
    span = CECID_GENTLE_WIND_MAX_KMH - CECID_GENTLE_WIND_MIN_KMH
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
    """Static source/weed/target graph shared by grid and tree modes."""

    def __init__(self) -> None:
        self.nodes: Dict[str, CecidHabitatNode] = {}
        self.adjacency: Dict[str, list[CecidHabitatEdge]] = {}
        self.source_nodes: Dict[Hashable, str] = {}
        self.target_nodes: Dict[Hashable, str] = {}
        self.zone_count = 0
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

        network._add_relay_nodes(zones, local)
        network._connect_nodes()
        return network

    def _add_relay_nodes(self, zones: list[Any], local) -> None:
        if not zones:
            return
        from shapely.geometry import Point, Polygon

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

        spacing = float(CECID_WEED_RELAY_SPACING_M)
        samples: Dict[Tuple[int, int], Tuple[float, float]] = {}

        def add_sample(x: float, y: float) -> None:
            samples.setdefault((round(x * 10), round(y * 10)), (float(x), float(y)))

        for polygon, _density in zone_geometries:
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

            boundary = polygon.boundary
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

        for origin in [*sources, *relays]:
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
            "active_relay_density_counts": {
                "sparse": 0, "moderate": 0, "dense": 0,
            },
            "reachable_tree_count": 0,
            "max_path_efficiency": 0.0,
            "directional_factor_min": 1.0,
            "directional_factor_max": 1.0,
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

        if eligible:
            for cohort_id, cohort in active_cohorts.items():
                source_key = cohort.get("source")
                source_node_id = self.network.source_nodes.get(source_key)
                if source_node_id is None:
                    continue
                current_relays = self.relay_state.setdefault(cohort_id, {})
                snapshot = {source_node_id: 1.0, **current_relays}
                next_relays = dict(current_relays)
                cohort_targets: Dict[Hashable, Dict[str, Any]] = {}

                for node_id, path_efficiency in snapshot.items():
                    for edge in self.network.adjacency.get(node_id, []):
                        destination = self.network.nodes[edge.destination]
                        directional_factor = cecid_wind_direction_factor(
                            wind_speed_ms, wind_from_deg, edge.bearing_deg,
                        )
                        directional_factors.append(directional_factor)
                        transfer = cecid_distance_factor(edge.distance_m)
                        transfer *= directional_factor
                        if destination.kind == "relay":
                            transfer *= destination.relay_efficiency
                        next_efficiency = path_efficiency * transfer
                        if next_efficiency <= 0.0:
                            continue
                        if destination.kind == "relay":
                            next_relays[destination.node_id] = max(
                                next_relays.get(destination.node_id, 0.0),
                                next_efficiency,
                            )
                        elif destination.kind == "target" and destination.key is not None:
                            candidate = {
                                "cohort_id": cohort_id,
                                "source": source_key,
                                "cohort_pressure": float(cohort.get("pressure", 0.0)),
                                "path_efficiency": next_efficiency,
                                "edge_distance_m": edge.distance_m,
                                "edge_bearing_deg": edge.bearing_deg,
                                "wind_direction_factor": directional_factor,
                            }
                            existing = cohort_targets.get(destination.key)
                            if (
                                existing is None
                                or candidate["path_efficiency"] > existing["path_efficiency"]
                            ):
                                cohort_targets[destination.key] = candidate
                self.relay_state[cohort_id] = next_relays
                for target_key, contribution in cohort_targets.items():
                    target_contributions.setdefault(target_key, []).append(contribution)

        diagnostics = self._empty_diagnostics()
        active_relay_ids = {
            relay_id
            for state in self.relay_state.values()
            for relay_id, pressure in state.items()
            if pressure > 0.0
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
                "adult pressure is retained at weed relays until another eligible hour"
                if active_relay_ids
                else "no fruitlet tree or weed relay is reachable within the current 15 m habitat hop"
            )
        diagnostics.update({
            "active_source_count": len({
                cohort.get("source") for cohort in active_cohorts.values()
            }),
            "active_cohort_count": len(active_cohorts),
            "active_relay_count": len(active_relay_ids),
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
