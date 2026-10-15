from datetime import datetime
import hashlib
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_, case, func, inspect, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import String

from app.database import engine
from app.models import get_table
from app.schemas import to_database_datetime

router = APIRouter(prefix="/api", tags=["Traffic analytics"])
CORE_TABLES = ("road_segments", "traffic_readings", "weather_data", "incidents")
CONGESTION_LEVELS = ("low", "moderate", "high", "severe")
HIGH_CONGESTION = ("high", "severe")


def _table_exists(table_name: str) -> bool:
    return table_name in inspect(engine).get_table_names()


def _table(table_name: str) -> Any:
    if not _table_exists(table_name):
        raise HTTPException(
            status_code=503,
            detail=f"The required database table '{table_name}' is not available.",
        )
    return get_table(table_name)


def _validate_time_range(start_time: datetime | None, end_time: datetime | None) -> None:
    if start_time is not None and end_time is not None:
        if to_database_datetime(start_time) > to_database_datetime(end_time):
            raise HTTPException(
                status_code=422,
                detail="start_time must be on or before end_time.",
            )


def _time_filters(
    table: Any,
    start_time: datetime | None,
    end_time: datetime | None,
    column_name: str = "recorded_at",
) -> list[Any]:
    _validate_time_range(start_time, end_time)
    if (start_time is not None or end_time is not None) and column_name not in table.c:
        raise HTTPException(
            status_code=422,
            detail=f"The {table.name} table does not support time filtering.",
        )
    filters: list[Any] = []
    if start_time is not None:
        filters.append(table.c[column_name] >= to_database_datetime(start_time))
    if end_time is not None:
        filters.append(table.c[column_name] <= to_database_datetime(end_time))
    return filters


def _search_filter(table: Any, search: str | None) -> Any | None:
    if not search:
        return None
    searchable = [
        column
        for column in table.c
        if isinstance(column.type, String)
    ]
    if not searchable:
        return None
    return or_(*(column.ilike(f"%{search.strip()}%") for column in searchable))


def _list_records(
    table_name: str,
    *,
    segment_id: int | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    search: str | None = None,
    location: str | None = None,
    congestion_level: str | None = None,
    active_only: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[dict[str, Any]]:
    table = _table(table_name)
    statement = select(table)
    if segment_id is not None:
        if "segment_id" not in table.c:
            raise HTTPException(
                status_code=422,
                detail=f"The {table_name} table does not support a segment_id filter.",
            )
        statement = statement.where(table.c.segment_id == segment_id)
    if location is not None:
        if "location" not in table.c:
            raise HTTPException(
                status_code=422,
                detail=f"The {table_name} table does not support a location filter.",
            )
        statement = statement.where(table.c.location == location)
    if congestion_level is not None:
        if "congestion_level" not in table.c:
            raise HTTPException(
                status_code=422,
                detail=f"The {table_name} table does not support a congestion_level filter.",
            )
        if congestion_level not in CONGESTION_LEVELS:
            raise HTTPException(
                status_code=422,
                detail="congestion_level must be low, moderate, high, or severe.",
            )
        statement = statement.where(table.c.congestion_level == congestion_level)

    time_column = "recorded_at"
    if table_name == "incidents":
        time_column = "start_time"
    statement = statement.where(*_time_filters(table, start_time, end_time, time_column))
    search_condition = _search_filter(table, search)
    if search_condition is not None:
        statement = statement.where(search_condition)

    if active_only:
        if "start_time" not in table.c or "end_time" not in table.c:
            raise HTTPException(
                status_code=422,
                detail="Active incident filtering requires start_time and end_time columns.",
            )
        now = datetime.now()
        statement = statement.where(
            table.c.start_time <= now,
            or_(table.c.end_time.is_(None), table.c.end_time >= now),
        )

    order_name = next(
        (
            name
            for name in ("recorded_at", "start_time", "created_at")
            if name in table.c
        ),
        None,
    )
    if order_name:
        statement = statement.order_by(table.c[order_name].desc())
    primary_keys = list(table.primary_key.columns)
    if not order_name and primary_keys:
        statement = statement.order_by(primary_keys[0].desc())
    with Session(engine) as session:
        rows = session.execute(statement.limit(limit).offset(offset)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/road-segments")
def road_segments(
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _list_records("road_segments", search=search, limit=limit, offset=offset)


@router.get("/traffic-readings")
def traffic_readings(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    congestion_level: str | None = None,
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _list_records(
        "traffic_readings",
        segment_id=segment_id,
        start_time=start_time,
        end_time=end_time,
        congestion_level=congestion_level,
        limit=limit,
        offset=offset,
    )


@router.get("/weather")
def weather_records(
    location: str | None = Query(default=None, max_length=255),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _list_records(
        "weather_data",
        location=location,
        start_time=start_time,
        end_time=end_time,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/incidents")
def incidents(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    active_only: bool = False,
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=500, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[dict[str, Any]]:
    return _list_records(
        "incidents",
        segment_id=segment_id,
        start_time=start_time,
        end_time=end_time,
        active_only=active_only,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/recommendations")
def recommendations(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    if not _table_exists("decision_recommendations"):
        return {
            "available": False,
            "items": [],
            "detail": (
                "The decision_recommendations table is not present in the configured database. "
                "Recommendations can be generated from real records but cannot be saved."
            ),
        }
    return {
        "available": True,
        "items": _list_records(
            "decision_recommendations",
            limit=limit,
            offset=offset,
        ),
        "detail": None,
    }


@router.get("/analytics/summary")
def analytics_summary(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    roads = _table("road_segments")
    readings = _table("traffic_readings")
    incidents_table = _table("incidents")
    filters = _time_filters(readings, start_time, end_time)
    if segment_id is not None:
        if "segment_id" not in readings.c:
            raise HTTPException(status_code=503, detail="Traffic readings cannot be grouped by road segment.")
        filters.append(readings.c.segment_id == segment_id)

    with Session(engine) as session:
        road_query = select(func.count()).select_from(roads)
        if segment_id is not None:
            if "segment_id" not in roads.c:
                raise HTTPException(status_code=503, detail="Road segments are missing segment_id.")
            road_query = road_query.where(roads.c.segment_id == segment_id)
        total_roads = int(session.scalar(road_query) or 0)

        reading_query = select(func.count()).select_from(readings)
        if filters:
            reading_query = reading_query.where(*filters)
        total_readings = int(session.scalar(reading_query) or 0)

        def aggregate(column_name: str, operation: Any) -> Any:
            if column_name not in readings.c:
                return None
            query = select(operation(readings.c[column_name])).select_from(readings)
            if filters:
                query = query.where(*filters)
            return session.scalar(query)

        total_vehicles = aggregate("vehicle_count", func.sum)
        average_speed = aggregate("speed_kmh", func.avg)
        average_travel_time = aggregate("travel_time_minutes", func.avg)
        high_severe_count: int | None = None
        if "congestion_level" in readings.c:
            query = select(func.count()).select_from(readings).where(
                readings.c.congestion_level.in_(HIGH_CONGESTION)
            )
            if filters:
                query = query.where(*filters)
            high_severe_count = int(session.scalar(query) or 0)

        active_incidents: int | None = None
        if {"start_time", "end_time"}.issubset(incidents_table.c.keys()):
            now = datetime.now()
            incident_query = select(func.count()).select_from(incidents_table).where(
                incidents_table.c.start_time <= now,
                or_(incidents_table.c.end_time.is_(None), incidents_table.c.end_time >= now),
            )
            if segment_id is not None and "segment_id" in incidents_table.c:
                incident_query = incident_query.where(incidents_table.c.segment_id == segment_id)
            active_incidents = int(session.scalar(incident_query) or 0)

    return {
        "total_road_segments": total_roads,
        "total_recorded_vehicles": (
            int(total_vehicles or 0) if "vehicle_count" in readings.c else None
        ),
        "average_speed_kmh": average_speed,
        "average_travel_time_minutes": average_travel_time,
        "high_or_severe_readings": high_severe_count,
        "active_incidents": active_incidents,
        "total_traffic_readings": total_readings,
        "recommendations_storage_available": _table_exists("decision_recommendations"),
    }


@router.get("/analytics/congestion")
def congestion_analytics(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    readings = _table("traffic_readings")
    if "congestion_level" not in readings.c:
        raise HTTPException(status_code=503, detail="Traffic readings are missing congestion_level.")
    filters = _time_filters(readings, start_time, end_time)
    if segment_id is not None:
        if "segment_id" not in readings.c:
            raise HTTPException(status_code=503, detail="Traffic readings are missing segment_id.")
        filters.append(readings.c.segment_id == segment_id)
    statement = select(
        readings.c.congestion_level,
        func.count().label("reading_count"),
    ).group_by(readings.c.congestion_level)
    if filters:
        statement = statement.where(*filters)
    with Session(engine) as session:
        rows = session.execute(statement).mappings().all()
    counts = {level: 0 for level in CONGESTION_LEVELS}
    for row in rows:
        level = str(row["congestion_level"]).lower()
        counts[level] = int(row["reading_count"])
    return {
        "distribution": [
            {"congestion_level": level, "reading_count": count}
            for level, count in counts.items()
        ],
        "total_readings": sum(counts.values()),
    }


@router.get("/analytics/roads")
def road_analytics(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[dict[str, Any]]:
    roads = _table("road_segments")
    readings = _table("traffic_readings")
    if not {"segment_id"}.issubset(roads.c.keys()) or "segment_id" not in readings.c:
        raise HTTPException(status_code=503, detail="Road and traffic tables cannot be joined by segment_id.")

    conditions = [readings.c.segment_id == roads.c.segment_id]
    conditions.extend(_time_filters(readings, start_time, end_time))
    statement = select(
        roads.c.segment_id,
        *(
            [roads.c[name] for name in ("name", "start_location", "end_location", "length_km", "road_type") if name in roads.c]
        ),
    )
    group_by = [
        roads.c.segment_id,
        *(roads.c[name] for name in ("name", "start_location", "end_location", "length_km", "road_type") if name in roads.c),
    ]
    statement = statement.add_columns(func.count(readings.c.segment_id).label("reading_count"))

    def add_aggregate(column_name: str, label: str, operation: Any) -> None:
        nonlocal statement
        if column_name in readings.c:
            statement = statement.add_columns(operation(readings.c[column_name]).label(label))

    add_aggregate("vehicle_count", "total_vehicle_count", func.sum)
    add_aggregate("speed_kmh", "average_speed_kmh", func.avg)
    add_aggregate("travel_time_minutes", "average_travel_time_minutes", func.avg)
    if "congestion_level" in readings.c:
        statement = statement.add_columns(
            func.sum(case((readings.c.congestion_level.in_(HIGH_CONGESTION), 1), else_=0))
            .label("high_or_severe_readings")
        )
    statement = (
        statement.select_from(roads.outerjoin(readings, and_(*conditions)))
        .group_by(*group_by)
        .order_by(roads.c.segment_id)
    )
    if segment_id is not None:
        statement = statement.where(roads.c.segment_id == segment_id)
    with Session(engine) as session:
        return [dict(row) for row in session.execute(statement).mappings().all()]


def _recommendation_candidates(
    db: Session,
    segment_id: int | None,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[dict[str, Any]]:
    readings = _table("traffic_readings")
    required = {"segment_id", "recorded_at", "congestion_level"}
    if not required.issubset(readings.c.keys()):
        raise HTTPException(
            status_code=503,
            detail="Traffic readings are missing columns required for evidence-based recommendations.",
        )
    filters = _time_filters(readings, start_time, end_time)
    if segment_id is not None:
        filters.append(readings.c.segment_id == segment_id)
    ranked = select(
        *readings.c,
        func.row_number().over(
            partition_by=readings.c.segment_id,
            order_by=readings.c.recorded_at.desc(),
        ).label("_row_number"),
    )
    if filters:
        ranked = ranked.where(*filters)
    latest = ranked.subquery()
    latest_statement = select(
        *(latest.c[name] for name in readings.c.keys())
    ).where(latest.c._row_number == 1)
    latest_rows = db.execute(latest_statement).mappings().all()

    road_table = _table("road_segments")
    road_names: dict[Any, str] = {}
    if {"segment_id", "name"}.issubset(road_table.c.keys()):
        road_names = {
            row["segment_id"]: str(row["name"])
            for row in db.execute(select(road_table.c.segment_id, road_table.c.name)).mappings()
        }

    suggestions: list[dict[str, Any]] = []
    for row in latest_rows:
        level = str(row["congestion_level"]).lower()
        if level not in HIGH_CONGESTION:
            continue
        name = road_names.get(row["segment_id"], f"Road segment {row['segment_id']}")
        priority = "high" if level == "severe" else "medium"
        if level == "severe":
            recommendation = f"Review diversion options and temporary traffic controls on {name}."
        else:
            recommendation = f"Review signal timing and increase traffic monitoring on {name}."
        evidence_parts = [
            f"Latest recorded reading at {row['recorded_at']}: {level} congestion."
        ]
        for column_name, label, unit in (
            ("speed_kmh", "speed", " km/h"),
            ("vehicle_count", "vehicle count", ""),
            ("travel_time_minutes", "travel time", " minutes"),
        ):
            value = row.get(column_name)
            if value is not None:
                evidence_parts.append(f"{label} {value}{unit}.")
        suggestions.append({
            "segment_id": row["segment_id"],
            "priority": priority,
            "recommendation": recommendation,
            "evidence_summary": " ".join(evidence_parts),
            "status": "pending",
            "created_at": datetime.now(),
        })

    incidents_table = _table("incidents")
    if {"segment_id", "incident_type", "start_time", "end_time"}.issubset(incidents_table.c.keys()):
        now = datetime.now()
        incident_query = select(incidents_table).where(
            incidents_table.c.start_time <= now,
            or_(incidents_table.c.end_time.is_(None), incidents_table.c.end_time >= now),
        )
        if segment_id is not None:
            incident_query = incident_query.where(incidents_table.c.segment_id == segment_id)
        for incident in db.execute(incident_query).mappings():
            name = road_names.get(
                incident["segment_id"],
                f"Road segment {incident['segment_id']}",
            )
            description = incident.get("description")
            evidence = (
                f"Active {incident['incident_type']} incident on {name}, "
                f"recorded from {incident['start_time']}."
            )
            if description:
                evidence += f" Incident details: {description}"
            suggestions.append({
                "segment_id": incident["segment_id"],
                "priority": "high",
                "recommendation": f"Monitor the incident response and review diversion options for {name}.",
                "evidence_summary": evidence,
                "status": "pending",
                "created_at": datetime.now(),
            })
    return suggestions


def _insert_values(table: Any, suggestion: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    aliases: dict[str, tuple[str, ...]] = {
        "segment_id": ("segment_id", "road_segment_id"),
        "priority": ("priority", "recommendation_priority", "severity"),
        "recommendation": (
            "recommendation_text",
            "recommendation",
            "action",
            "suggestion",
            "title",
        ),
        "evidence_summary": (
            "evidence_summary",
            "evidence",
            "supporting_evidence",
            "reason",
        ),
        "created_at": ("created_at", "created_on", "recommended_at"),
        "status": ("status", "recommendation_status"),
        "deduplication_key": ("deduplication_key",),
    }
    values: dict[str, Any] = {}
    for key, names in aliases.items():
        column_name = next((name for name in names if name in table.c), None)
        if column_name is not None and suggestion.get(key) is not None:
            values[column_name] = suggestion[key]

    for column in table.c:
        if column.name == "status" and not column.nullable and column.default is None and column.server_default is None:
            enum_values = getattr(column.type, "enums", [])
            if enum_values:
                values[column.name] = enum_values[0]

    missing_evidence_fields = [
        field
        for field in (
            "segment_id",
            "priority",
            "recommendation",
            "evidence_summary",
            "created_at",
            "status",
            "deduplication_key",
        )
        if not any(name in values for name in aliases[field])
    ]
    if missing_evidence_fields:
        return {}, (
            "The decision_recommendations table needs road, priority, recommendation text, "
            "evidence, creation-time, and status columns before recommendations can be saved."
        )

    missing = [
        column.name
        for column in table.c
        if not column.nullable
        and not column.primary_key
        and column.default is None
        and column.server_default is None
        and column.autoincrement is not True
        and column.name not in values
    ]
    if missing:
        return {}, (
            "The decision_recommendations schema has required columns this application "
            f"cannot safely populate: {', '.join(missing)}."
        )
    return values, None


def _persist_suggestion(db: Session, table: Any, suggestion: dict[str, Any]) -> bool:
    suggestion = {
        **suggestion,
        "deduplication_key": hashlib.sha256(
            json.dumps(
                {
                    "segment_id": suggestion["segment_id"],
                    "priority": suggestion["priority"],
                    "recommendation": suggestion["recommendation"],
                    "evidence_summary": suggestion["evidence_summary"],
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest(),
    }
    values, schema_error = _insert_values(table, suggestion)
    if schema_error:
        raise HTTPException(status_code=503, detail=schema_error)

    deduplication_column = next(
        (name for name in ("deduplication_key",) if name in table.c),
        None,
    )
    if deduplication_column is None:
        raise HTTPException(
            status_code=503,
            detail="The decision_recommendations table needs a unique deduplication_key column.",
        )
    deduplication_key = values[deduplication_column]
    exists = db.execute(
        select(func.count())
        .select_from(table)
        .where(table.c[deduplication_column] == deduplication_key)
    ).scalar_one()
    if exists:
        return False
    try:
        with db.begin_nested():
            db.execute(table.insert().values(**values))
    except IntegrityError:
        exists = db.execute(
            select(func.count())
            .select_from(table)
            .where(table.c[deduplication_column] == deduplication_key)
        ).scalar_one()
        if exists:
            return False
        raise
    return True


@router.post("/recommendations/generate")
def generate_recommendations(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    _validate_time_range(start_time, end_time)
    with Session(engine) as session:
        suggestions = _recommendation_candidates(
            session,
            segment_id,
            start_time,
            end_time,
        )
        storage_available = _table_exists("decision_recommendations")
        saved_count = 0
        detail: str | None = None
        if storage_available:
            recommendation_table = _table("decision_recommendations")
            try:
                for suggestion in suggestions:
                    if _persist_suggestion(session, recommendation_table, suggestion):
                        saved_count += 1
                session.commit()
            except (HTTPException, SQLAlchemyError):
                session.rollback()
                raise
        else:
            detail = (
                "Recommendations are based on stored traffic readings and active incidents. "
                "The decision_recommendations table is missing, so no recommendation was saved."
            )
        return {
            "available": storage_available,
            "generated_count": len(suggestions),
            "saved_count": saved_count,
            "items": suggestions,
            "detail": detail,
        }
