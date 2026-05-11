from decimal import Decimal
from types import SimpleNamespace

import pytest

from api.models.schemas import SimulationRequest
from api.routes.orchards import (
    count_geojson_trees,
    derive_geojson_centroid,
    geojson_crs_name,
    normalize_geojson_to_wgs84,
    normalize_orchard_uid,
    orchard_to_response,
    _centroid_from_bounds,
    _point_within_bounds,
)
from api.routes.simulation import _orchard_id_from_request


def _point_feature(lon, lat, tree_id):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"tree_id": tree_id},
    }


def test_normalize_orchard_uid_creates_stable_slug():
    assert normalize_orchard_uid(" Orchard 1 / East Block ") == "orchard-1-east-block"
    assert normalize_orchard_uid("Testing---JL") == "testing-jl"
    assert normalize_orchard_uid("") == "orchard"


def test_geojson_tree_count_and_centroid_prefer_tree_points():
    geojson = {
        "type": "FeatureCollection",
        "features": [
            _point_feature(122.0, 10.0, "T1"),
            _point_feature(124.0, 12.0, "T2"),
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [100.0, 0.0],
                        [110.0, 0.0],
                        [110.0, 10.0],
                        [100.0, 10.0],
                        [100.0, 0.0],
                    ]],
                },
                "properties": {"name": "boundary"},
            },
        ],
    }

    assert count_geojson_trees(geojson) == 2
    assert derive_geojson_centroid(geojson) == (123.0, 11.0)


def test_geojson_centroid_falls_back_to_polygon_boundary():
    geojson = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [122.0, 10.0],
                    [124.0, 10.0],
                    [124.0, 12.0],
                    [122.0, 12.0],
                    [122.0, 10.0],
                ]],
            },
            "properties": {},
        }],
    }

    assert count_geojson_trees(geojson) == 0
    assert derive_geojson_centroid(geojson) == (123.0, 11.0)


def test_geojson_crs_name_reads_legacy_epsg_urn():
    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32651"}},
        "features": [],
    }

    assert geojson_crs_name(geojson) == "urn:ogc:def:crs:EPSG::32651"


def test_normalize_geojson_to_wgs84_transforms_utm_tree_points():
    geojson = {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32651"}},
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [457485.93798172765, 1175330.2768851554],
                },
                "properties": {"tree_id": 1},
            }
        ],
    }

    normalized = normalize_geojson_to_wgs84(geojson)
    lon, lat = normalized["features"][0]["geometry"]["coordinates"]

    assert "crs" not in normalized
    assert lon == pytest.approx(122.611310, rel=1e-6)
    assert lat == pytest.approx(10.632124, rel=1e-6)


def test_orchard_response_uses_public_orchard_id_and_can_omit_geojson():
    orchard = SimpleNamespace(
        orchard_id=7,
        orchard_uid="orchard-east",
        name="Orchard East",
        owner_name="Demo Owner",
        location="Guimaras",
        area_size=Decimal("1.25"),
        tree_count=42,
        geojson={"type": "FeatureCollection", "features": []},
        centroid_lon=122.5,
        centroid_lat=10.5,
        orthophoto_png_path="data/orchards/orchard-east/orthophoto.png",
        orthophoto_bounds=[122.0, 10.0, 124.0, 12.0],
        orthophoto_coordinates=[[122.0, 12.0], [124.0, 12.0], [124.0, 10.0], [122.0, 10.0]],
        dtm_path="data/orchards/orchard-east/dtm.tif",
        dsm_path=None,
        description="Demo orchard",
        is_active=True,
        monitoring_enabled=True,
        orchard_stage="mature",
        days_since_flowering=60,
        monitored_pest_types=["cecid", "fruitfly"],
        last_monitoring_scan_at=None,
        created_at=None,
        updated_at=None,
    )

    response = orchard_to_response(orchard, include_geojson=False)

    assert response.database_id == 7
    assert response.orchard_id == "orchard-east"
    assert response.area_size == 1.25
    assert response.geojson is None
    assert response.orthophoto_url == "/orchards/orchard-east/assets/orthophoto.png"
    assert response.orthophoto_bounds == [122.0, 10.0, 124.0, 12.0]
    assert response.has_dtm is True
    assert response.has_dsm is False
    assert response.monitoring_enabled is True
    assert response.orchard_stage == "mature"


def test_centroid_from_raster_bounds():
    assert _centroid_from_bounds([122.0, 10.0, 124.0, 12.0]) == (123.0, 11.0)


def test_point_within_bounds_allows_small_tolerance():
    assert _point_within_bounds(123.0, 11.0, [122.0, 10.0, 124.0, 12.0])
    assert _point_within_bounds(124.01, 12.01, [122.0, 10.0, 124.0, 12.0])
    assert not _point_within_bounds(130.0, 11.0, [122.0, 10.0, 124.0, 12.0])


def test_simulation_request_orchard_id_overrides_geojson_name():
    request = SimulationRequest(
        pest_type="cecid",
        orchard_id="registered-orchard-2",
        orchard_geojson={
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [122.0, 10.0]},
                "properties": {"name": "geojson-name"},
            }],
        },
    )

    assert _orchard_id_from_request(request) == "registered-orchard-2"
