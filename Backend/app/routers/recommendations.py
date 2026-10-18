from datetime import datetime, timedelta
import hashlib
import json
import math
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import ValidationError
from sqlalchemy import insert, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import get_table
from app.routers import decision_support
from app.schemas import RecommendationCreate, RecommendationPatch, to_database_datetime
from app.security import get_current_user

router = APIRouter(
    prefix="/recommendations",
    tags=["Recommendation management"],
    dependencies=[Depends(get_current_user)],
)
MINIMUM_CLASSIFIED_READINGS = 1
ANALYSIS_WINDOW = timedelta(hours=1)


def _recommendation_table():
    return get_table("decision_recommendations")


def _classify_congestion(counts: dict[str, int], total: int) -> str:
    high_share = (counts["high"] + counts["severe"]) / total
    moderate_or_higher_share = (
        counts["moderate"] + counts["high"] + counts["severe"]
    ) / total
    if high_share >= 0.5:
        return "High"
    if moderate_or_higher_share >= 0.5:
        return "Moderate"
    return "Low"


def _numeric_average(rows: list[Any], column_name: str) -> float | None:
    values: list[float] = []
    for row in rows:
        value = row.get(column_name)
        if value is None:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError, OverflowError):
            continue
        if math.isfinite(numeric_value):
            values.append(numeric_value)
    return sum(values) / len(values) if values else None


@router.get("/analyze")
def analyze_traffic_for_recommendation(
    segment_id: int = Query(..., gt=0),
    start_time: datetime = Query(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    window_start = to_database_datetime(start_time)
    window_end = window_start + ANALYSIS_WINDOW
    roads = decision_support._table("road_segments")
    if not {"segment_id", "name"}.issubset(roads.c.keys()):
        raise HTTPException(
            status_code=503,
            detail="Road segments are missing the identifier or road-name column.",
        )
    road = db.execute(
        select(roads.c.segment_id, roads.c.name).where(
            roads.c.segment_id == segment_id
        )
    ).mappings().first()
    if road is None:
        raise HTTPException(status_code=404, detail="The selected road segment was not found.")

    readings = decision_support._table("traffic_readings")
    required_columns = {"segment_id", "recorded_at", "congestion_level"}
    if not required_columns.issubset(readings.c.keys()):
        raise HTTPException(
            status_code=503,
            detail="Traffic readings need segment_id, recorded_at, and congestion_level columns for this analysis.",
        )
    selected_columns = [
        readings.c[name]
        for name in (
            "recorded_at",
            "congestion_level",
            "speed_kmh",
            "vehicle_count",
            "travel_time_minutes",
            "data_source",
        )
        if name in readings.c
    ]
    reading_query = (
        select(*selected_columns)
        .where(
            readings.c.segment_id == segment_id,
            readings.c.recorded_at >= window_start,
            readings.c.recorded_at < window_end,
        )
        .order_by(readings.c.recorded_at)
    )
    reading_rows = [dict(row) for row in db.execute(reading_query).mappings()]

    counts = {"low": 0, "moderate": 0, "high": 0, "severe": 0}
    for row in reading_rows:
        level = str(row.get("congestion_level") or "").strip().lower()
        if level == "medium":
            level = "moderate"
        if level in counts:
            counts[level] += 1
    classified_count = sum(counts.values())
    classification = (
        _classify_congestion(counts, classified_count)
        if classified_count >= MINIMUM_CLASSIFIED_READINGS
        else None
    )

    incident_details: list[dict[str, Any]] = []
    incidents_table = decision_support._table("incidents")
    incident_columns = set(incidents_table.c.keys())
    incident_context_available = {
        "segment_id",
        "incident_type",
        "start_time",
    }.issubset(incident_columns)
    if incident_context_available:
        incident_filters = [
            incidents_table.c.segment_id == segment_id,
        ]
        if "end_time" in incident_columns:
            incident_filters.extend(
                [
                    incidents_table.c.start_time < window_end,
                    or_(
                        incidents_table.c.end_time.is_(None),
                        incidents_table.c.end_time >= window_start,
                    ),
                ]
            )
        else:
            incident_filters.extend(
                [
                    incidents_table.c.start_time >= window_start,
                    incidents_table.c.start_time < window_end,
                ]
            )
        incident_query = (
            select(incidents_table)
            .where(*incident_filters)
            .order_by(incidents_table.c.start_time.desc())
            .limit(5)
        )
        for incident in db.execute(incident_query).mappings():
            incident_details.append(
                {
                    "incident_type": incident.get("incident_type") or "Recorded incident",
                    "description": incident.get("description"),
                    "start_time": incident.get("start_time"),
                    "end_time": incident.get("end_time"),
                }
            )

    evidence_parts = [
        f"{len(reading_rows)} stored traffic reading(s) in the selected one-hour window; "
        f"{classified_count} have a recognized congestion category.",
        (
            "Congestion categories: "
            + ", ".join(f"{level} {count}" for level, count in counts.items())
            + "."
        ),
    ]
    average_speed = _numeric_average(reading_rows, "speed_kmh")
    average_vehicles = _numeric_average(reading_rows, "vehicle_count")
    average_travel_time = _numeric_average(reading_rows, "travel_time_minutes")
    if average_speed is not None:
        evidence_parts.append(f"Mean recorded speed: {average_speed:.1f} km/h.")
    if average_vehicles is not None:
        evidence_parts.append(f"Mean recorded vehicle count: {average_vehicles:.1f} vehicles per reading.")
    if average_travel_time is not None:
        evidence_parts.append(f"Mean recorded travel time: {average_travel_time:.1f} minutes.")
    source_labels = sorted(
        {
            str(row["data_source"]).strip()
            for row in reading_rows
            if row.get("data_source") is not None and str(row["data_source"]).strip()
        }
    )
    normalized_sources = {label.lower() for label in source_labels}
    if normalized_sources.intersection({"sample", "demo", "demonstration", "synthetic"}):
        evidence_parts.append(
            "The database source label identifies these as sample/demonstration records: "
            + ", ".join(source_labels)
            + "."
        )
    elif source_labels:
        evidence_parts.append("Database source label(s): " + ", ".join(source_labels) + ".")
    else:
        evidence_parts.append("No traffic-data source label is recorded for these readings.")
    evidence_parts.append("These are stored observations, not live traffic data.")
    if incident_context_available:
        if incident_details:
            labels = [
                f"{item['incident_type']}"
                + (f": {item['description']}" if item["description"] else "")
                for item in incident_details
            ]
            evidence_parts.append(
                "Recorded incident(s) overlapping the window: "
                + "; ".join(labels)
                + ". Incident records provide context and do not by themselves prove causation."
            )
        else:
            evidence_parts.append("No recorded incidents overlap the selected window.")
    else:
        evidence_parts.append("Incident context is unavailable in the configured schema.")

    recommendation = None
    if classification is None:
        evidence_parts.append(
            "Insufficient Data: no readings with recognized congestion categories "
            "are available to classify this window."
        )
    elif classification == "High" and incident_details:
        recommendation = (
            "Coordinate with incident-response staff and review safe diversion options "
            "using verified current closure and field information."
        )
    elif classification == "High":
        recommendation = (
            "Review traffic-management coverage and signal timing for this observed "
            "high-congestion period."
        )
    elif classification == "Moderate" and incident_details:
        recommendation = (
            "Coordinate with staff managing the recorded incident and monitor traffic "
            "conditions during the selected period."
        )
    elif classification == "Moderate":
        recommendation = (
            "Monitor traffic conditions and review signal timing if moderate congestion "
            "recurs in observed readings."
        )
    elif incident_details:
        recommendation = (
            "Continue routine monitoring and coordinate with incident-response staff "
            "as needed; recorded traffic categories are predominantly low."
        )
    else:
        recommendation = (
            "Continue routine monitoring; recorded traffic categories are predominantly low."
        )

    return {
        "segment_id": segment_id,
        "road_name": road["name"],
        "start_time": window_start,
        "end_time": window_end,
        "status": "Analyzed" if classification else "Insufficient Data",
        "congestion_level": classification,
        "reading_count": len(reading_rows),
        "classified_reading_count": classified_count,
        "congestion_counts": counts,
        "average_speed_kmh": average_speed,
        "average_vehicle_count": average_vehicles,
        "average_travel_time_minutes": average_travel_time,
        "incident_records": incident_details,
        "incident_context_available": incident_context_available,
        "evidence_summary": " ".join(evidence_parts),
        "recommendation": recommendation,
        "minimum_classified_readings": MINIMUM_CLASSIFIED_READINGS,
        "classification_thresholds": {
            "high": "At least 50% of classified readings are high or severe.",
            "moderate": "If the high threshold is not met, at least 50% are moderate, high, or severe.",
            "low": "Neither the high nor moderate threshold is met.",
        },
    }


def _recommended_actions(problem_type: str, severity: str) -> list[str]:
    specific_actions = {
        "Traffic Congestion": (
            "Review signal timing and traffic-control coverage using current on-site conditions."
            if severity != "Severe"
            else "Arrange an immediate on-site traffic assessment and review temporary traffic controls."
        ),
        "Accident": "Confirm incident status with emergency responders and coordinate safe scene traffic control.",
        "Vehicle Breakdown": "Coordinate safe vehicle recovery with authorized responders; avoid unsafe roadside assistance.",
        "Roadwork": "Verify work-zone limits and any closures with the responsible road authority before changing traffic flow.",
        "Other": "Ask the responsible team to verify the reported issue on site before applying traffic controls.",
    }
    return [
        specific_actions[problem_type],
        "Check with traffic staff and current closure records whether a safe alternative route is available; do not publish an unverified route.",
        "Assess whether traffic-police deployment is needed using verified severity, queue conditions, and field staff observations.",
        "Monitor incident updates and new traffic readings, then review the recommendation as conditions change.",
    ]


def _report_evidence(
    db: Session,
    segment_id: int,
    start_time: datetime | None,
    end_time: datetime | None,
) -> tuple[str, str]:
    analysis = decision_support._recommendation_analysis(db, segment_id, start_time, end_time)
    segment = next(
        (item for item in analysis["segments"] if item.get("segment_id") == segment_id),
        None,
    )
    if segment is None:
        raise HTTPException(status_code=404, detail="The selected road segment was not found.")
    evidence_parts: list[str] = []
    reading_count = int(segment.get("total_readings") or 0)
    if reading_count:
        counts = segment.get("congestion_counts", {})
        evidence_parts.append(f"{reading_count} traffic reading(s) are recorded for this road in the selected period.")
        evidence_parts.append(
            f"High/severe readings: {int(counts.get('high', 0)) + int(counts.get('severe', 0))}."
        )
        if segment.get("average_speed_kmh") is not None:
            evidence_parts.append(
                f"Average recorded speed: {float(segment['average_speed_kmh']):.1f} km/h."
            )
        if segment.get("average_travel_time_minutes") is not None:
            evidence_parts.append(
                f"Average recorded travel time: {float(segment['average_travel_time_minutes']):.1f} minutes."
            )
    else:
        evidence_parts.append(
            "No traffic readings were found for this road in the selected period; no measured traffic values are available."
        )

    has_incidents_table = decision_support._table_exists("incidents")
    if not has_incidents_table:
        evidence_parts.append("The database does not contain an incidents table, so incident records could not be checked.")
    else:
        incident_table = decision_support._table("incidents")
    if has_incidents_table and {"segment_id", "incident_type", "start_time"}.issubset(incident_table.c.keys()):
        incident_filters = [incident_table.c.segment_id == segment_id]
        incident_filters.extend(
            decision_support._time_filters(
                incident_table, start_time, end_time, column_name="start_time"
            )
        )
        incident_query = select(incident_table).where(*incident_filters).order_by(
            incident_table.c.start_time.desc()
        ).limit(5)
        incidents = list(db.execute(incident_query).mappings())
        if incidents:
            details = []
            for incident in incidents:
                label = str(incident.get("incident_type") or "Recorded incident")
                if incident.get("description"):
                    label += f": {str(incident['description']).strip()}"
                details.append(label)
            evidence_parts.append(
                f"Recorded incident context on this road ({len(incidents)} shown): "
                + "; ".join(details)
                + ". These records are context only and do not establish the cause of the reported problem."
            )
        else:
            evidence_parts.append("No matching incident records were found for this road in the selected period.")
    elif has_incidents_table:
        evidence_parts.append("Incident details are not available in the configured database schema.")

    evidence = " ".join(evidence_parts)
    if len(evidence) > 500:
        evidence = evidence[:497].rsplit(" ", 1)[0] + "..."
    return segment["road_name"], evidence


@router.post("", status_code=201)
def create_recommendation(
    payload: RecommendationCreate,
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        decision_support._validate_time_range(start_time, end_time)
        table = _recommendation_table()
        required_columns = {
            "recommendation_id", "segment_id", "priority", "recommendation_text",
            "evidence_summary", "created_at", "status", "deduplication_key",
            "problem_type", "congestion_severity", "problem_description",
        }
        database_columns = {
            column["name"]
            for column in inspect(db.connection()).get_columns("decision_recommendations")
        }
        missing_columns = required_columns.difference(database_columns)
        if missing_columns:
            raise HTTPException(
                status_code=503,
                detail="Recommendation storage needs a small additive schema update. "
                "Run Backend/scripts/add_recommendation_context_columns.py and retry.",
            )

        roads = decision_support._table("road_segments")
        road = db.execute(
            select(roads).where(roads.c.segment_id == payload.segment_id)
        ).mappings().first()
        if road is None:
            raise HTTPException(status_code=422, detail="Choose a road that exists in the road-segments list.")

        road_name, evidence = _report_evidence(
            db, payload.segment_id, start_time, end_time
        )
        actions = _recommended_actions(payload.problem_type, payload.congestion_severity)
        priority = "medium" if payload.congestion_severity == "Moderate" else "high"
        if payload.problem_type in {"Accident", "Vehicle Breakdown"} and payload.congestion_severity == "Severe":
            priority = "high"
        created_at = datetime.now()
        suggestion = {
            "segment_id": payload.segment_id,
            "road_name": road_name,
            "problem_type": payload.problem_type,
            "congestion_severity": payload.congestion_severity,
            "problem_description": payload.problem_description,
            "priority": priority,
            "recommendation": "\n".join(f"• {action}" for action in actions),
            "evidence_summary": evidence,
            "status": "suggested",
            "created_at": created_at,
            "deduplication_key": hashlib.sha256(uuid4().bytes).hexdigest(),
        }
        values, schema_error = decision_support._insert_values(table, suggestion)
        if schema_error:
            raise HTTPException(status_code=503, detail=schema_error)
        for field in ("problem_type", "congestion_severity", "problem_description"):
            values[field] = suggestion[field]

        if db.bind is not None and db.bind.dialect.name == "mysql":
            values["priority"] = priority.title()
            values["status"] = "Suggested"
        result = db.execute(insert(table).values(**values))
        db.commit()
        recommendation_id = result.inserted_primary_key[0]
        return {
            "recommendation_id": recommendation_id,
            "segment_id": payload.segment_id,
            "road_name": road_name,
            "problem_type": payload.problem_type,
            "congestion_severity": payload.congestion_severity,
            "problem_description": payload.problem_description,
            "priority": priority,
            "recommendation_text": suggestion["recommendation"],
            "recommended_actions": actions,
            "evidence_summary": evidence,
            "status": "Suggested",
            "created_at": created_at.isoformat(),
            "saved": True,
        }
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="The recommendation could not be saved because the database rejected the record.",
        ) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="The recommendation could not be saved. Check the database connection and try again.",
        ) from None


@router.patch("/{recommendation_id}")
def update_recommendation(
    payload: dict[str, Any],
    recommendation_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        values = RecommendationPatch.model_validate(payload).model_dump(exclude_unset=True)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from None
    if not values or any(value is None for value in values.values()):
        raise HTTPException(status_code=422, detail="Provide non-empty recommendation fields to update.")
    if db.bind is not None and db.bind.dialect.name == "mysql":
        if "priority" in values:
            values["priority"] = values["priority"].title()
        if "status" in values:
            values["status"] = {
                "pending": "Suggested",
                "suggested": "Suggested",
                "reviewed": "Reviewed",
                "implemented": "Implemented",
            }[values["status"]]
    elif values.get("status") == "suggested":
        values["status"] = "pending"

    table = _recommendation_table()
    missing = set(values).difference(table.c.keys())
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"The decision_recommendations table is missing columns: {', '.join(sorted(missing))}.",
        )
    try:
        existing = db.execute(
            select(table).where(table.c.recommendation_id == recommendation_id)
        ).mappings().first()
        if existing is None:
            raise HTTPException(status_code=404, detail="Recommendation not found.")
        db.execute(
            update(table)
            .where(table.c.recommendation_id == recommendation_id)
            .values(**values)
        )
        db.commit()
        updated = db.execute(
            select(table).where(table.c.recommendation_id == recommendation_id)
        ).mappings().one()
        return dict(updated)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The update conflicts with a database constraint.") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="The recommendation could not be updated.") from None


@router.delete("/{recommendation_id}", status_code=204)
def delete_recommendation(
    recommendation_id: int = Path(..., gt=0),
    db: Session = Depends(get_db),
) -> None:
    table = _recommendation_table()
    try:
        result = db.execute(
            table.delete().where(table.c.recommendation_id == recommendation_id)
        )
        if result.rowcount == 0:
            db.rollback()
            raise HTTPException(status_code=404, detail="Recommendation not found.")
        db.commit()
    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="The recommendation is referenced by another record.") from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="The recommendation could not be deleted.") from None
