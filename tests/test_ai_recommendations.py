"""AI integration checks use isolated responses and never call Google or farm storage."""

import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import BackgroundTasks, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.dialects import postgresql

from api.core.database import get_db
from api.core.security import get_current_active_user
from api.models.recommendations import GuidanceContent
from api.models.schemas import SimulationRequest, SimulationResponse
from api.routes import simulation
from api.services import ai_recommendation_service as service
from db.models import PestType, SimulationRun


@pytest.fixture
def result():
    values = dict(run_id="isolated-ai-run", pest_type="cecid", hours=1, random_seed=42,
                  started_at="2026-10-29T00:00:00Z", completed_at="2026-10-29T00:00:01Z",
                  peak_risk=0.8, cells_at_risk=1, n_infested_final=0, risk_threshold=0.7)
    return SimulationResponse(**values, status="completed", time_series=[], timesteps=[],
        metadata={**values, "duration_seconds": 1, "orchard_stage": "fruitlet",
                  "days_since_flowering": 30, "sugar_index": 0.2, "neighbor_threat": 0.3,
                  "weather_provenance": {"provider": "manual", "coordinates": {"lat": 10.5}},
                  "initial_seed_tree_ids": ["PRIVATE-TREE"],
                  "uncertainty_summary": {"runs": 5, "minimum": 0, "median": 1, "maximum": 2}},
        risk_geojson={"type": "FeatureCollection", "features": [{"type": "Feature",
            "geometry": {"type": "Point", "coordinates": [122.58, 10.58]},
            "properties": {"tree_id": "PRIVATE-TREE", "risk": 0.8, "state": "unbagged", "stage": "fruitlet"}}]})


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(service.settings, "GEMINI_API_KEY", SecretStr("isolated-private-key"))
    monkeypatch.setattr(service.settings, "AI_RECOMMENDATIONS_ENABLED", True)
    monkeypatch.setattr(service, "_slots", asyncio.Semaphore(2))


def explanation(result):
    return GuidanceContent(summary="Inspect the modeled risk locations and confirm field signs.",
        explanations=[{"action_index": index, "explanation": "Field inspection checks whether modeled pressure is present."}
                      for index, _ in enumerate(result.action_plan)])


def database(monkeypatch, result, status="completed"):
    saved = result.model_dump(mode="json")
    run = SimulationRun(run_id=result.run_id, pest_type=PestType.CECID_FLY, status=status,
                        response_payload=deepcopy(saved), result_metadata={"model_version": "retained"})
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalar_one_or_none.return_value = run

    @asynccontextmanager
    async def maker():
        yield db
    monkeypatch.setattr(service, "async_session_maker", maker)
    return db, run, saved


@pytest.mark.parametrize("pest", ["cecid", "fruitfly"])
@pytest.mark.parametrize("mode", ["grid", "tree_graph"])
def test_prepared_plan_keeps_pest_scope_and_excludes_private_data(result, configured, pest, mode):
    result.pest_type = type(result.pest_type)(pest)
    result.metadata.simulation_mode = mode
    context = service.prepare_recommendations(result)
    text = json.dumps(context)
    assert result.ai_guidance.status == "pending"
    assert context["pest"] == pest and context["engine"] == mode
    assert context["repeated_runs"]["runs"] == 5
    assert context["weather"]["provider"] == "manual"
    assert context["weather"]["known_temperature_hours"] == 0
    assert "PRIVATE-TREE" not in text and "122.58" not in text
    assert "coordinates" not in text and "isolated-private-key" not in text
    assert result.action_plan[0]["tree_ids"] == ["PRIVATE-TREE"]
    assert result.ai_guidance.simulation_model_version == result.metadata.model_version


@pytest.mark.parametrize("reason", ["not_configured", "disabled", "no_actions"])
def test_unavailable_configuration_keeps_plan_without_provider_calls(result, configured, monkeypatch, reason):
    if reason == "not_configured": monkeypatch.setattr(service.settings, "GEMINI_API_KEY", None)
    if reason == "disabled": monkeypatch.setattr(service.settings, "AI_RECOMMENDATIONS_ENABLED", False)
    if reason == "no_actions": result.risk_geojson["features"] = []
    service.prepare_recommendations(result)
    assert result.ai_guidance.status == "unavailable" and result.ai_guidance.reason == reason
    assert bool(result.action_plan) == (reason != "no_actions")


@pytest.mark.asyncio
async def test_rest_request_uses_header_schema_and_validates_saved_action_references(result, configured, monkeypatch):
    context = service.prepare_recommendations(result)
    seen = []
    candidate = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
        {"text": explanation(result).model_dump_json()}]}}]}

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=candidate)

    client_type = httpx.AsyncClient
    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **kwargs: client_type(
        transport=httpx.MockTransport(handler), **kwargs))
    content = await service.request_explanation(context, result.ai_guidance)
    assert content.explanations[0].action_index == 0
    request = seen[0]
    assert request.headers["x-goog-api-key"] == "isolated-private-key"
    assert "key" not in str(request.url)
    body = json.loads(request.content)
    assert "responseJsonSchema" in body["generationConfig"] and "tools" not in body
    assert "PRIVATE-TREE" not in str(body)
    candidate["candidates"][0]["content"]["parts"][0]["text"] = json.dumps({
        "summary": "Unsupported action reference.",
        "explanations": [{"action_index": 3, "explanation": "A different action was invented."}],
    })
    with pytest.raises(ValueError): await service.request_explanation(context, result.ai_guidance)
    candidate["candidates"][0]["finishReason"] = "MAX_TOKENS"
    with pytest.raises(ValueError): await service.request_explanation(context, result.ai_guidance)


@pytest.mark.asyncio
async def test_background_saves_only_guidance_and_preserves_forecast_and_metadata(result, configured, monkeypatch):
    context = service.prepare_recommendations(result)
    db, run, original = database(monkeypatch, result)
    monkeypatch.setattr(service, "request_explanation", AsyncMock(return_value=explanation(result)))
    await service.generate_and_save_guidance(result.run_id, context, result.ai_guidance)
    assert run.response_payload["ai_guidance"]["status"] == "ready"
    assert run.response_payload["ai_guidance"]["generated_at"]
    assert {k: v for k, v in run.response_payload.items() if k != "ai_guidance"} == {
        k: v for k, v in original.items() if k != "ai_guidance"}
    assert run.status == "completed" and run.result_metadata == {"model_version": "retained"}
    assert result.ai_guidance.status == "pending", "response snapshot remains independent of background mutation"
    db.commit.assert_awaited_once()
    await service.generate_and_save_guidance(result.run_id, context, result.ai_guidance)
    assert db.commit.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("error,reason", [(ValueError("invalid"), "invalid_response"),
    (httpx.ReadTimeout("secret-response"), "request_failed"), (RuntimeError("secret-response"), "request_failed")])
async def test_provider_failures_are_saved_as_fallback_without_exposing_errors(result, configured, monkeypatch, caplog, error, reason):
    context = service.prepare_recommendations(result)
    db, run, _ = database(monkeypatch, result)
    request = AsyncMock(side_effect=error)
    monkeypatch.setattr(service, "request_explanation", request)
    await service.generate_and_save_guidance(result.run_id, context, result.ai_guidance)
    assert run.response_payload["ai_guidance"]["reason"] == reason
    assert run.response_payload["action_plan"] == result.action_plan
    assert "secret-response" not in caplog.text
    request.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["deleted", "ready", "busy", "expired"])
async def test_deleted_completed_busy_and_abandoned_jobs_are_bounded(result, configured, monkeypatch, state):
    context = service.prepare_recommendations(result)
    if state == "expired": result.ai_guidance.expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    db, run, _ = database(monkeypatch, result, status="deleted" if state == "deleted" else "completed")
    if state == "ready": run.response_payload["ai_guidance"]["status"] = "ready"
    if state == "busy": monkeypatch.setattr(service, "_slots", asyncio.Semaphore(0))
    request = AsyncMock(return_value=explanation(result))
    monkeypatch.setattr(service, "request_explanation", request)
    await service.generate_and_save_guidance(result.run_id, context, result.ai_guidance)
    if state in {"deleted", "ready"}: db.commit.assert_not_awaited()
    else:
        request.assert_not_awaited()
        assert run.response_payload["ai_guidance"]["reason"] == state


@pytest.mark.asyncio
async def test_successful_simulation_saves_pending_then_queues_generation_after_response(result, configured, monkeypatch):
    request = SimulationRequest(pest_type="cecid", hours=1, orchard_stage="fruitlet",
        orchard_geojson=result.risk_geojson, manual_weather={"temperature_c": 28,
            "wind_speed_ms": 1, "wind_direction_deg": 90, "rainfall_mm": 0, "humidity": 75})
    for name in ("_resolve_cecid_weed_zones", "_resolve_management_zones"):
        monkeypatch.setattr(simulation, name, AsyncMock(return_value=request))
    monkeypatch.setattr(simulation.simulation_service, "run_simulation", AsyncMock(return_value=result))
    save, alerts, generate = AsyncMock(), AsyncMock(), AsyncMock()
    monkeypatch.setattr(simulation, "save_simulation_run", save)
    monkeypatch.setattr(simulation, "check_alerts", alerts)
    monkeypatch.setattr(simulation, "generate_and_save_guidance", generate)
    tasks = BackgroundTasks()
    returned = await simulation.run_simulation(request, tasks, db=AsyncMock())
    assert returned.ai_guidance.status == "pending"
    save.assert_awaited_once()
    assert save.call_args.kwargs["result"].action_plan
    alerts.assert_awaited_once()
    generate.assert_not_awaited()
    await tasks()
    generate.assert_awaited_once()


def test_status_endpoint_requires_auth_and_reads_only_the_requested_visible_run(result, configured):
    service.prepare_recommendations(result)
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.first.return_value = SimpleNamespace(ai_guidance=result.ai_guidance.model_dump())
    app = FastAPI()
    app.include_router(simulation.router, dependencies=[Depends(get_current_active_user)])
    async def connection(): yield db
    app.dependency_overrides[get_db] = connection
    client = TestClient(app)
    path = f"/simulation/runs/{result.run_id}/recommendations"
    assert client.get(path).status_code == 401
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(user_id=7)
    assert client.get(path).json()["ai_guidance"]["run_id"] == result.run_id
    query = db.execute.call_args.args[0].compile(dialect=postgresql.dialect())
    assert "status IS DISTINCT FROM" in str(query) and result.run_id in query.params.values()
    assert "output_geojson" not in str(query) and "time_series" not in str(query)
    db.commit.assert_not_awaited()
    db.execute.return_value.first.return_value = None
    assert client.get(path).status_code == 404


def test_expired_saved_job_has_fallback_without_mutating_the_record(result, configured):
    service.prepare_recommendations(result)
    result.ai_guidance.expires_at = "2020-01-01T00:00:00Z"
    saved = result.ai_guidance.model_dump()
    assert service.guidance_for_display(saved).reason == "expired"
    assert saved["status"] == "pending"
