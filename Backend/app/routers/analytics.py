from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, extract, func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import get_table
from app.schemas import to_database_datetime
from app.security import get_current_user

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/summary")
def analytics_summary(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    readings = get_table("traffic_readings")
    roads = get_table("road_segments")
    required = {"segment_id", "recorded_at", "speed_kmh", "travel_time_minutes", "congestion_level"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise HTTPException(status_code=503, detail=f"traffic_readings is missing analytics columns: {', '.join(sorted(missing))}.")

    filters = []
    if start_time is not None:
        filters.append(readings.c.recorded_at >= to_database_datetime(start_time))
    if end_time is not None:
        filters.append(readings.c.recorded_at <= to_database_datetime(end_time))
    ranked = select(
        *readings.c,
        func.row_number().over(
            partition_by=readings.c.segment_id,
            order_by=readings.c.recorded_at.desc(),
        ).label("_row_number"),
    )
    if filters:
        ranked = ranked.where(*filters)
    latest_rows = ranked.subquery()
    latest_per_segment = select(*(latest_rows.c[name] for name in readings.c.keys())).where(latest_rows.c._row_number == 1)
    latest_congestion = db.execute(
        select(latest_rows.c.congestion_level, func.count().label("segment_count"))
        .where(latest_rows.c._row_number == 1)
        .group_by(latest_rows.c.congestion_level)
    ).mappings().all()
    distribution = {level: 0 for level in ("low", "moderate", "high", "severe")}
    for row in latest_congestion:
        if row["congestion_level"] in distribution:
            distribution[row["congestion_level"]] = int(row["segment_count"])
    latest_rows_data = [dict(row) for row in db.execute(latest_per_segment).mappings().all()]
    total_segments = db.scalar(select(func.count()).select_from(roads)) or 0
    road_name = roads.c.name if "name" in roads.c else roads.c.segment_id
    segment_statement = (
        select(
            readings.c.segment_id,
            road_name.label("name"),
            func.count().label("reading_count"),
            func.avg(readings.c.speed_kmh).label("average_speed_kmh"),
            func.avg(readings.c.travel_time_minutes).label("average_travel_time_minutes"),
        )
        .select_from(readings.join(roads, readings.c.segment_id == roads.c.segment_id))
        .group_by(readings.c.segment_id, road_name)
        .order_by(func.avg(readings.c.travel_time_minutes).desc())
        .limit(100)
    )
    hour_value = extract("hour", readings.c.recorded_at)
    busiest_statement = (
        select(hour_value.label("hour"), func.count().label("reading_count"))
        .group_by(hour_value)
        .order_by(desc(func.count()))
        .limit(5)
    )
    congestion_statement = (
        select(readings.c.congestion_level, func.count().label("reading_count"))
        .group_by(readings.c.congestion_level)
        .order_by(desc(func.count()))
    )
    for statement_name, statement in (
        ("segments", segment_statement),
        ("busiest", busiest_statement),
        ("congestion", congestion_statement),
    ):
        if filters:
            statement = statement.where(*filters)
        if statement_name == "segments":
            segment_statement = statement
        elif statement_name == "busiest":
            busiest_statement = statement
        else:
            congestion_statement = statement

    return {
        "total_road_segments": int(total_segments),
        "latest_per_segment": latest_rows_data,
        "latest_congestion_distribution": distribution,
        "segment_comparison": [dict(row) for row in db.execute(segment_statement).mappings().all()],
        "busiest_hours": [dict(row) for row in db.execute(busiest_statement).mappings().all()],
        "congestion_distribution": [dict(row) for row in db.execute(congestion_statement).mappings().all()],
        "data_window": {"start_time": start_time, "end_time": end_time},
    }