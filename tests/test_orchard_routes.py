from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.core.database import _ensure_default_orchard
from api.models.schemas import (
    CecidWeedZone,
    ManagementZone,
    OrchardStageZone,
    OrchardStatusZone,
    OrchardCreate,
    OrchardUpdate,
    SimulationRequest,
)
from api.routes import orchards as orchard_routes
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
from api.routes.simulation import (
    _orchard_id_from_request,
    _resolve_cecid_weed_zones,
    _resolve_management_zones,
)
from api.services.orchard_tree_service import update_geojson_trees


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
        stage_zones=[{
            "id": "stage-1",
            "stage": "fruitlet",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
        status_zones=[{
            "id": "status-1",
            "status": "suspect",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
        management_zones=[{
            "id": "zone-1",
            "label": "Zone 1",
            "color": "#2563eb",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
        cecid_weed_zones=[{
            "id": "north-weeds",
            "label": "North weeds",
            "density": "dense",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
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
    assert response.stage_zones[0].stage.value == "fruitlet"
    assert response.status_zones[0].status == "suspect"
    assert response.management_zones[0].label == "Zone 1"
    assert response.cecid_weed_zones[0].density.value == "dense"


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


def test_weed_zone_schema_validates_density_and_polygon():
    zone = CecidWeedZone(
        id="weeds-1",
        label="Drainage weeds",
        density="moderate",
        coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
    )
    assert zone.density.value == "moderate"

    with pytest.raises(ValidationError):
        CecidWeedZone(
            id="bad-density",
            label="Bad",
            density="high",
            coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        )

    with pytest.raises(ValidationError):
        CecidWeedZone(
            id="bad-polygon",
            label="Bad",
            density="sparse",
            coordinates=[[122.0, 10.0], [122.1, 10.0]],
        )


def test_management_zone_schema_keeps_stable_label_and_polygon():
    zone = ManagementZone(
        id="zone-north",
        label="North Block",
        color="#2563eb",
        coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
    )
    assert zone.id == "zone-north"
    assert zone.label == "North Block"

    with pytest.raises(ValidationError):
        ManagementZone(
            id="bad",
            label="Bad",
            color="blue",
            coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        )


def test_persistent_tree_zone_schemas_validate_setting_and_polygon():
    stage_zone = OrchardStageZone(
        id="stage-north",
        stage="fruitlet",
        coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
    )
    status_zone = OrchardStatusZone(
        id="status-north",
        status="suspect",
        coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
    )
    assert stage_zone.stage.value == "fruitlet"
    assert status_zone.status == "suspect"

    with pytest.raises(ValidationError):
        OrchardStatusZone(
            id="bad-status",
            status="unknown",
            coordinates=[[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        )


def test_bulk_tree_update_uses_portable_ids_without_mutating_input():
    original = {
        "type": "FeatureCollection",
        "features": [
            _point_feature(122.0, 10.0, "T1"),
            _point_feature(122.1, 10.1, "T2"),
        ],
    }
    updated, found, missing = update_geojson_trees(
        original,
        ["T2", "missing"],
        status="suspect",
        stage="fruitlet",
    )

    assert found == ["T2"]
    assert missing == ["missing"]
    assert original["features"][1]["properties"].get("status") is None
    assert updated["features"][1]["properties"]["status"] == "suspect"
    assert updated["features"][1]["properties"]["stage"] == "fruitlet"


class _FakeOrchardSession:
    def __init__(self):
        self.added = None
        self.flush_count = 0

    def add(self, value):
        self.added = value

    async def flush(self):
        self.flush_count += 1
        if self.added is not None and self.added.orchard_id is None:
            self.added.orchard_id = 91

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_orchard_create_and_update_round_trip_weed_zones(monkeypatch):
    async def allow_uid(*_args, **_kwargs):
        return None

    monkeypatch.setattr(orchard_routes, "_ensure_unique_uid", allow_uid)
    session = _FakeOrchardSession()
    payload = OrchardCreate(
        orchard_id="weed-demo",
        name="Weed Demo",
        geojson={"type": "FeatureCollection", "features": []},
        stage_zones=[{
            "id": "stage-a",
            "stage": "fruitlet",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
        status_zones=[{
            "id": "status-a",
            "status": "infected",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
        cecid_weed_zones=[{
            "id": "zone-a",
            "label": "Canal-side weeds",
            "density": "sparse",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
        management_zones=[{
            "id": "zone-a",
            "label": "Block A",
            "color": "#2563eb",
            "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
        }],
    )
    created = await orchard_routes.create_orchard(payload, db=session)
    assert created.cecid_weed_zones[0].density.value == "sparse"
    assert session.added.cecid_weed_zones[0]["density"] == "sparse"
    assert created.management_zones[0].label == "Block A"
    assert created.stage_zones[0].stage.value == "fruitlet"
    assert created.status_zones[0].status == "infected"

    orchard = session.added

    async def return_orchard(*_args, **_kwargs):
        return orchard

    monkeypatch.setattr(orchard_routes, "_get_orchard_or_404", return_orchard)
    updated = await orchard_routes.update_orchard(
        "weed-demo",
        OrchardUpdate(cecid_weed_zones=[], stage_zones=[], status_zones=[]),
        db=session,
    )
    assert updated.cecid_weed_zones == []
    assert orchard.cecid_weed_zones == []
    assert orchard.stage_zones == []
    assert orchard.status_zones == []


class _BootstrapConnection:
    def __init__(self, exists):
        self.exists = exists
        self.executions = []

    async def scalar(self, _statement):
        return self.exists

    async def execute(self, statement, params=None):
        self.executions.append((str(statement), params))


@pytest.mark.asyncio
async def test_default_orchard_bootstrap_is_idempotent_and_never_overwrites():
    existing = _BootstrapConnection(exists=1)
    await _ensure_default_orchard(existing)
    assert existing.executions == []

    missing = _BootstrapConnection(exists=None)
    await _ensure_default_orchard(missing)
    assert len(missing.executions) == 1
    sql, params = missing.executions[0]
    assert "ON CONFLICT (orchard_uid) DO NOTHING" in sql
    assert "'default-orchard'" in sql
    assert params["tree_count"] > 0
    assert '"features"' in params["geojson"]


def test_local_and_supabase_weed_migrations_are_mirrored():
    project_root = Path(__file__).resolve().parents[1]
    local_sql = (project_root / "db/migrations/0004_cecid_weed_zones.sql").read_text(encoding="utf-8")
    cloud_sql = (project_root / "supabase/migrations/202608180000_cecid_weed_zones.sql").read_text(encoding="utf-8")
    expected = "cecid_weed_zones JSONB NOT NULL DEFAULT '[]'::jsonb"
    assert expected in local_sql
    assert expected in cloud_sql


def test_release1_local_and_supabase_migrations_are_mirrored():
    project_root = Path(__file__).resolve().parents[1]
    local_sql = (project_root / "db/migrations/0008_release1_zones_and_observations.sql").read_text(encoding="utf-8")
    cloud_sql = (project_root / "supabase/migrations/202609130000_release1_zones_and_observations.sql").read_text(encoding="utf-8")
    for expected in (
        "management_zones JSONB NOT NULL DEFAULT '[]'::jsonb",
        "external_id VARCHAR(150)",
        "observation_status VARCHAR(30)",
        "forecast_risk DOUBLE PRECISION",
    ):
        assert expected in local_sql
        assert expected in cloud_sql


def test_persistent_tree_zone_migrations_are_mirrored():
    project_root = Path(__file__).resolve().parents[1]
    local_sql = (project_root / "db/migrations/0009_persistent_stage_status_zones.sql").read_text(encoding="utf-8")
    cloud_sql = (project_root / "supabase/migrations/202610020000_persistent_stage_status_zones.sql").read_text(encoding="utf-8")
    for expected in (
        "stage_zones JSONB NOT NULL DEFAULT '[]'::jsonb",
        "status_zones JSONB NOT NULL DEFAULT '[]'::jsonb",
    ):
        assert expected in local_sql
        assert expected in cloud_sql


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _ResolveSession:
    def __init__(self, orchard):
        self.orchard = orchard
        self.calls = 0

    async def execute(self, _query):
        self.calls += 1
        return _ScalarResult(self.orchard)


@pytest.mark.asyncio
async def test_simulation_omission_loads_orchard_weeds_but_explicit_list_is_authoritative():
    stored_zone = {
        "id": "stored-weeds",
        "label": "Stored weeds",
        "density": "dense",
        "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
    }
    session = _ResolveSession(SimpleNamespace(cecid_weed_zones=[stored_zone]))
    orchard_geojson = {"type": "FeatureCollection", "features": []}
    omitted = SimulationRequest(
        pest_type="cecid",
        orchard_id="orchard-a",
        orchard_geojson=orchard_geojson,
    )
    resolved = await _resolve_cecid_weed_zones(omitted, session)
    assert resolved.cecid_weed_zones[0].id == "stored-weeds"
    assert session.calls == 1

    explicit = SimulationRequest(
        pest_type="cecid",
        orchard_id="orchard-a",
        orchard_geojson=orchard_geojson,
        cecid_weed_zones=[],
    )
    untouched = await _resolve_cecid_weed_zones(explicit, session)
    assert untouched.cecid_weed_zones == []
    assert session.calls == 1


@pytest.mark.asyncio
async def test_simulation_omission_snapshots_management_zones_but_explicit_empty_is_authoritative():
    stored_zone = {
        "id": "zone-1",
        "label": "Zone 1",
        "color": "#2563eb",
        "coordinates": [[122.0, 10.0], [122.1, 10.0], [122.1, 10.1]],
    }
    session = _ResolveSession(SimpleNamespace(management_zones=[stored_zone]))
    orchard_geojson = {"type": "FeatureCollection", "features": []}
    omitted = SimulationRequest(
        pest_type="cecid",
        orchard_id="orchard-a",
        orchard_geojson=orchard_geojson,
    )
    resolved = await _resolve_management_zones(omitted, session)
    assert resolved.management_zones[0].id == "zone-1"
    assert session.calls == 1

    explicit = SimulationRequest(
        pest_type="cecid",
        orchard_id="orchard-a",
        orchard_geojson=orchard_geojson,
        management_zones=[],
    )
    untouched = await _resolve_management_zones(explicit, session)
    assert untouched.management_zones == []
    assert session.calls == 1
