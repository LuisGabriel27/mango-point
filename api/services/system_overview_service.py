"""Read-only activity summaries for the system Overview tab."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import SIMULATION_MODEL_VERSION
from db.models import Alert, AlertStatus, InfestationRecord, Orchard, Pest, SimulationRun, Tree
from utils.datetime_utils import format_rfc3339, utcnow_aware

OverviewPeriod = Literal["day", "week", "month", "year"]
PHILIPPINE_TIME = timezone(timedelta(hours=8))


def overview_window(period: OverviewPeriod, now: datetime, selected_date: date | None = None):
    """Use the calendar period containing the chosen Philippine date."""
    local_now = now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now
    local_now = local_now.astimezone(PHILIPPINE_TIME)
    selected_date = selected_date or local_now.date()
    if selected_date > local_now.date():
        raise ValueError("Choose today or an earlier date.")
    if period == "day":
        start_date, next_date = selected_date, selected_date + timedelta(days=1)
    elif period == "week":
        start_date = selected_date - timedelta(days=selected_date.weekday())
        next_date = start_date + timedelta(days=7)
    elif period == "month":
        start_date = selected_date.replace(day=1)
        next_date = date(start_date.year + (start_date.month == 12), start_date.month % 12 + 1, 1)
    elif period == "year":
        start_date, next_date = date(selected_date.year, 1, 1), date(selected_date.year + 1, 1, 1)
    else:
        raise ValueError("Choose day, week, month or year.")
    start = datetime.combine(start_date, time.min, PHILIPPINE_TIME)
    end = datetime.combine(next_date, time.min, PHILIPPINE_TIME) - timedelta(microseconds=1)
    return start, min(end, local_now)


def _bucket(column, period):
    # Database DateTime columns store naive UTC; shift before date grouping.
    return func.date_trunc("month" if period == "year" else "day", column + timedelta(hours=8))


def overview_queries(period, local_start, local_end, orchard_id=None):
    """Aggregate all matching records without loading maps or limiting history."""
    start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    run_bucket = _bucket(SimulationRun.started_at, period)
    version = func.coalesce(SimulationRun.result_metadata["model_version"].as_string(), "Unrecorded")
    runs = select(
        run_bucket.label("bucket"), SimulationRun.orchard_id, SimulationRun.pest_type,
        SimulationRun.status, SimulationRun.simulation_mode, version.label("model_version"),
        SimulationRun.weather_source, func.count().label("count"),
    ).where(
        SimulationRun.started_at >= start, SimulationRun.started_at <= end,
    ).group_by(
        run_bucket, SimulationRun.orchard_id, SimulationRun.pest_type, SimulationRun.status,
        SimulationRun.simulation_mode, version, SimulationRun.weather_source,
    )

    observation_time = func.coalesce(InfestationRecord.record_date, InfestationRecord.created_at)
    observation_bucket = _bucket(observation_time, period)
    presence = case(
        (InfestationRecord.observation_status.in_(["present", "absent", "not_inspected"]),
         InfestationRecord.observation_status),
        else_=case(
        (InfestationRecord.infected_status.is_(True), "present"), else_="absent",
        ),
    )
    observations = select(
        observation_bucket.label("bucket"), Orchard.orchard_uid.label("orchard_id"),
        Pest.name.label("pest_name"), presence.label("presence"), func.count().label("count"),
    ).select_from(InfestationRecord).join(
        Tree, Tree.tree_id == InfestationRecord.tree_id,
    ).join(Orchard, Orchard.orchard_id == Tree.orchard_id).join(
        Pest, Pest.pest_id == InfestationRecord.pest_id,
    ).where(
        InfestationRecord.simulation_id.is_(None),
        observation_time >= start, observation_time <= end,
    ).group_by(observation_bucket, Orchard.orchard_uid, Pest.name, presence)

    alert_bucket = _bucket(Alert.triggered_at, period)
    alerts = select(
        alert_bucket.label("bucket"), Alert.orchard_id, func.count().label("count"),
    ).where(Alert.triggered_at >= start, Alert.triggered_at <= end).group_by(alert_bucket, Alert.orchard_id)
    active_alerts = select(
        Alert.orchard_id, Alert.severity, func.count().label("count"),
    ).where(Alert.status == AlertStatus.ACTIVE).group_by(Alert.orchard_id, Alert.severity)
    orchards = select(
        Orchard.orchard_uid.label("orchard_id"), Orchard.name,
        Orchard.tree_count, Orchard.is_active, Orchard.monitoring_enabled,
    ).order_by(Orchard.name)
    if orchard_id:
        runs = runs.where(SimulationRun.orchard_id == orchard_id)
        observations = observations.where(Orchard.orchard_uid == orchard_id)
        alerts = alerts.where(Alert.orchard_id == orchard_id)
        active_alerts = active_alerts.where(Alert.orchard_id == orchard_id)
    # Keep the full directory available for the independent Overview filter.
    return {"orchards": orchards, "runs": runs, "observations": observations,
            "alerts": alerts, "active_alerts": active_alerts}


def _value(value):
    return value.value if hasattr(value, "value") else value


def summarize_overview(period, local_start, local_end, rows, orchard_id=None, selected_date=None, computed_at=None):
    """Combine independent categories without multiplying joined records."""
    timeline = {}
    cursor = local_start.date()
    while cursor <= local_end.date():
        key = (cursor.replace(day=1) if period == "year" else cursor).isoformat()
        timeline.setdefault(key, {"date": key, "simulations": 0, "observations": 0, "present": 0, "alerts": 0})
        cursor += timedelta(days=1)

    def bucket_for(row):
        return timeline[row["bucket"].date().isoformat()]

    def activity_row(uid, name=None, tree_count=None):
        return {"orchard_id": uid, "name": name or uid or "Unassigned orchard",
                "tree_count": tree_count, "simulations": 0, "observations": 0,
                "present": 0, "alerts": 0, "active_alerts": 0}

    directory = [dict(row) for row in rows["orchards"]]
    inventory = [row for row in directory if not orchard_id or row["orchard_id"] == orchard_id]
    activities = {row["orchard_id"]: activity_row(row["orchard_id"], row["name"], row["tree_count"])
                  for row in inventory}

    def orchard_for(row):
        uid = row["orchard_id"]
        return activities.setdefault(uid, activity_row(uid))

    pests = {key: {"pest_type": key, "simulations": 0, "observations": 0, "present": 0}
             for key in ("cecid", "fruitfly")}
    simulations = {"total": 0, "completed": 0, "failed": 0, "other": 0}
    observations = {"total": 0, "inspected": 0, "present": 0, "absent": 0, "not_inspected": 0}
    engines, versions, weather = {}, {}, {}
    for row in rows["runs"]:
        count = row["count"]
        status = row["status"] if row["status"] in ("completed", "failed") else "other"
        simulations["total"] += count
        simulations[status] += count
        if status != "completed":
            continue
        bucket_for(row)["simulations"] += count
        orchard_for(row)["simulations"] += count
        pest = _value(row["pest_type"])
        pests.setdefault(pest, {"pest_type": pest, "simulations": 0, "observations": 0, "present": 0})["simulations"] += count
        for counts, key in ((engines, row["simulation_mode"] or "Unrecorded"),
                            (versions, row["model_version"]), (weather, row["weather_source"] or "Unrecorded")):
            counts[key] = counts.get(key, 0) + count

    names = {"Mango Cecid Fly": "cecid", "Oriental Fruit Fly": "fruitfly"}
    for row in rows["observations"]:
        count, presence = row["count"], row["presence"]
        observations["total"] += count
        observations[presence] += count
        if presence == "not_inspected":
            continue
        observations["inspected"] += count
        bucket_for(row)["observations"] += count
        orchard_for(row)["observations"] += count
        pest = names.get(row["pest_name"], row["pest_name"])
        pest_row = pests.setdefault(pest, {"pest_type": pest, "simulations": 0, "observations": 0, "present": 0})
        pest_row["observations"] += count
        if presence == "present":
            bucket_for(row)["present"] += count
            orchard_for(row)["present"] += count
            pest_row["present"] += count

    alert_summary = {"raised": 0, "active": 0, "high_critical_active": 0}
    for row in rows["alerts"]:
        count = row["count"]
        alert_summary["raised"] += count
        bucket_for(row)["alerts"] += count
        orchard_for(row)["alerts"] += count
    for row in rows["active_alerts"]:
        count = row["count"]
        alert_summary["active"] += count
        orchard_for(row)["active_alerts"] += count
        if _value(row["severity"]) in ("high", "critical"):
            alert_summary["high_critical_active"] += count

    # Include archived IDs found in activity so their rows can also be filtered.
    known_ids = {row["orchard_id"] for row in directory}
    directory.extend({"orchard_id": uid, "name": row["name"], "tree_count": None,
                      "is_active": False, "monitoring_enabled": False}
                     for uid, row in activities.items() if uid and uid not in known_ids)
    return {
        "period": period, "selected_date": (selected_date or local_end.date()).isoformat(),
        "days": (local_end.date() - local_start.date()).days + 1, "timezone": "Asia/Manila",
        "start_at": format_rfc3339(local_start), "end_at": format_rfc3339(local_end),
        "computed_at": format_rfc3339(computed_at or local_end), "orchard_id": orchard_id,
        "current_model_version": SIMULATION_MODEL_VERSION,
        "inventory": {"orchards": len(inventory), "trees": sum(row["tree_count"] or 0 for row in inventory),
                      "monitored_orchards": sum(bool(row["is_active"] and row["monitoring_enabled"]) for row in inventory)},
        "simulations": simulations, "observations": observations, "alerts": alert_summary,
        "timeline": list(timeline.values()), "pests": list(pests.values()), "engines": engines,
        "model_versions": versions, "weather_sources": weather, "orchards": directory,
        "orchard_activity": sorted(activities.values(), key=lambda row: row["name"].lower()),
    }


async def get_system_overview(db: AsyncSession, period: OverviewPeriod, orchard_id=None, selected_date=None):
    now = utcnow_aware().astimezone(PHILIPPINE_TIME)
    selected_date = selected_date or now.date()
    local_start, local_end = overview_window(period, now, selected_date)
    rows = {}
    for name, query in overview_queries(period, local_start, local_end, orchard_id).items():
        rows[name] = (await db.execute(query)).mappings().all()
    return summarize_overview(period, local_start, local_end, rows, orchard_id, selected_date, now)
