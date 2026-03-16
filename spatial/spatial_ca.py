"""
Tree-level spatial cellular automata.

This module is retained in the refactored ``spatial`` package so older
``spatial_ca`` imports can continue to work through a thin compatibility shim.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

BASE_SPREAD_PROB = 0.30
DISTANCE_DECAY = 0.06
CROWN_OVERLAP_BOOST = 0.20
MAX_SPREAD_DIST_M = 40.0
ELEV_DIFF_FACTOR = 0.003
_M_PER_DEG_LAT = 111_132.0


def _m_per_deg_lon(lat_deg: float) -> float:
    return 111_132.0 * math.cos(math.radians(lat_deg))


class Tree:
    """Single mango tree with spatial attributes."""

    __slots__ = (
        "tree_id",
        "fid",
        "lon",
        "lat",
        "crown_width",
        "elevation",
        "status",
        "day_infected",
    )

    def __init__(
        self,
        tree_id: int,
        fid: int,
        lon: float,
        lat: float,
        crown_width: float,
        elevation: float,
        status: str = "healthy",
    ):
        self.tree_id = tree_id
        self.fid = fid
        self.lon = lon
        self.lat = lat
        self.crown_width = crown_width
        self.elevation = elevation
        self.status = status
        self.day_infected: Optional[int] = None

    def distance_m(self, other: "Tree", m_lon: float) -> float:
        dx = (self.lon - other.lon) * m_lon
        dy = (self.lat - other.lat) * _M_PER_DEG_LAT
        return math.sqrt(dx * dx + dy * dy)

    def crowns_overlap(self, other: "Tree", dist_m: float) -> bool:
        return dist_m < (self.crown_width + other.crown_width) / 2.0

    def to_dict(self) -> dict:
        return {
            "tree_id": self.tree_id,
            "fid": self.fid,
            "lon": self.lon,
            "lat": self.lat,
            "crown_width": self.crown_width,
            "elevation": self.elevation,
            "status": self.status,
            "day_infected": self.day_infected,
        }


class SpatialCA:
    """Tree-level cellular automata for pest spread between orchard points."""

    def __init__(
        self,
        trees: List[Tree],
        base_prob: float = BASE_SPREAD_PROB,
        decay: float = DISTANCE_DECAY,
        crown_boost: float = CROWN_OVERLAP_BOOST,
        max_dist: float = MAX_SPREAD_DIST_M,
        elev_factor: float = ELEV_DIFF_FACTOR,
        seed: int = 42,
    ):
        self.trees = trees
        self.base_prob = base_prob
        self.decay = decay
        self.crown_boost = crown_boost
        self.max_dist = max_dist
        self.elev_factor = elev_factor
        self.rng = np.random.default_rng(seed)
        self.day = 0

        mean_lat = np.mean([t.lat for t in trees])
        self._m_lon = _m_per_deg_lon(float(mean_lat))

        n_trees = len(trees)
        self._dist = np.full((n_trees, n_trees), np.inf)
        self._overlap = np.zeros((n_trees, n_trees), dtype=bool)
        self._elev_diff = np.zeros((n_trees, n_trees))
        for i in range(n_trees):
            for j in range(i + 1, n_trees):
                dist = trees[i].distance_m(trees[j], self._m_lon)
                self._dist[i, j] = self._dist[j, i] = dist
                self._overlap[i, j] = self._overlap[j, i] = trees[i].crowns_overlap(trees[j], dist)
                self._elev_diff[i, j] = self._elev_diff[j, i] = abs(
                    trees[i].elevation - trees[j].elevation
                )

    @classmethod
    def from_geojson(cls, path: str | Path, **kwargs) -> "SpatialCA":
        with open(path, encoding="utf-8") as file_obj:
            feature_collection = json.load(file_obj)
        return cls.from_feature_collection(feature_collection, **kwargs)

    @classmethod
    def from_feature_collection(cls, feature_collection: dict, **kwargs) -> "SpatialCA":
        trees: List[Tree] = []
        for feature in feature_collection.get("features", []):
            props = feature.get("properties", {})
            coords = feature["geometry"]["coordinates"]
            raw_status = str(props.get("status", props.get("Status", "healthy"))).strip().lower()
            status = {
                "unbagged": "healthy",
                "healthy": "healthy",
                "infected": "infected",
                "infested": "infected",
                "bagged": "bagged",
                "dead": "dead",
            }.get(raw_status, "healthy")
            trees.append(
                Tree(
                    tree_id=int(props.get("tree_id", props.get("Tree_ID", props.get("fid", 0)))),
                    fid=int(props.get("fid", 0)),
                    lon=coords[0],
                    lat=coords[1],
                    crown_width=float(props.get("crown_size", props.get("Crown_Width", 5.0))),
                    elevation=float(props.get("elevation", props.get("Elev_1", 0.0))),
                    status=status,
                )
            )
        return cls(trees, **kwargs)

    def seed_infection(self, tree_ids: List[int]) -> None:
        id_set = set(tree_ids)
        for tree in self.trees:
            if tree.tree_id in id_set and tree.status == "healthy":
                tree.status = "infected"
                tree.day_infected = self.day

    def seed_random(self, n: int = 1) -> List[int]:
        healthy = [tree for tree in self.trees if tree.status == "healthy"]
        if not healthy:
            return []
        indices = self.rng.choice(len(healthy), size=min(n, len(healthy)), replace=False)
        selected = [healthy[i] for i in indices]
        ids = [int(tree.tree_id) for tree in selected]
        self.seed_infection(ids)
        return ids

    def step(self) -> Dict:
        self.day += 1
        infected_idx = [i for i, tree in enumerate(self.trees) if tree.status == "infected"]
        newly_infected: List[int] = []

        for i in infected_idx:
            for j, tree in enumerate(self.trees):
                if tree.status != "healthy":
                    continue
                dist = self._dist[i, j]
                if dist > self.max_dist:
                    continue

                prob = self.base_prob * math.exp(-self.decay * dist)
                if self._overlap[i, j]:
                    prob += self.crown_boost

                elev_penalty = self.elev_factor * self._elev_diff[i, j]
                prob = min(max(0.0, prob - elev_penalty), 1.0)

                if self.rng.random() < prob:
                    tree.status = "infected"
                    tree.day_infected = self.day
                    newly_infected.append(tree.tree_id)

        return self._snapshot(newly_infected)

    def run(self, days: int = 10) -> List[Dict]:
        snapshots = [self._snapshot([])]
        for _ in range(days):
            snapshots.append(self.step())
        return snapshots

    def reset(self) -> None:
        self.day = 0
        for tree in self.trees:
            tree.status = "healthy"
            tree.day_infected = None

    def _snapshot(self, newly_infected: List[int]) -> Dict:
        n_infected = sum(1 for tree in self.trees if tree.status == "infected")
        return {
            "day": self.day,
            "n_infected": n_infected,
            "n_healthy": len(self.trees) - n_infected,
            "newly_infected": newly_infected,
            "trees": [tree.to_dict() for tree in self.trees],
        }

    @staticmethod
    def snapshot_to_geojson(snapshot: Dict) -> Dict:
        features = []
        for tree_dict in snapshot["trees"]:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "tree_id": tree_dict["tree_id"],
                        "fid": tree_dict["fid"],
                        "status": tree_dict["status"],
                        "crown_width": tree_dict["crown_width"],
                        "elevation": tree_dict["elevation"],
                        "day_infected": tree_dict["day_infected"],
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [tree_dict["lon"], tree_dict["lat"]],
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}
