from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, case, desc, exists, extract, func, literal, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import get_table
from app.schemas import PredictionRequest, TrafficScenarioRequest, to_database_datetime
from app.security import get_current_user
from app.services.prediction_service import InsufficientTrainingData, what_if_scenarios

router = APIRouter(prefix="/analytics", tags=["Analytics"])
CONGESTION_LEVELS = ("low", "moderate", "high", "severe")
HIGH_CONGESTION = ("high", "severe")


def _time_filters(
    table: Any,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[Any]:
    normalized_start = to_database_datetime(start_time) if start_time is not None else None
    normalized_end = to_database_datetime(end_time) if end_time is not None else None
    if normalized_start is not None and normalized_end is not None and normalized_start > normalized_end:
        raise HTTPException(status_code=422, detail="start_time must be on or before end_time.")
    filters = []
    if normalized_start is not None:
        filters.append(table.c.recorded_at >= normalized_start)
    if normalized_end is not None:
        filters.append(table.c.recorded_at <= normalized_end)
    return filters


def _weather_traffic_patterns(
    db: Session,
    readings: Any,
    start_time: datetime | None,
    end_time: datetime | None,
    segment_id: int | None = None,
) -> dict[str, Any]:
    weather = get_table("weather_data")
    required = {"recorded_at"}
    if not required.issubset(readings.c.keys()) or not required.issubset(weather.c.keys()):
        return {
            "available": False,
            "detail": "Traffic and weather timestamps are required to compare time-aligned observations.",
            "patterns": [],
        }
    if not {"speed_kmh", "congestion_level"}.issubset(readings.c.keys()):
        return {
            "available": False,
            "detail": "Traffic speed and congestion columns are required for this comparison.",
            "patterns": [],
        }
    if "condition" in weather.c:
        weather_group = weather.c.condition
        weather_label = "condition"
    elif "rainfall_mm" in weather.c:
        weather_group = case(
            (weather.c.rainfall_mm.is_(None), "unknown"),
            (weather.c.rainfall_mm > 0, "rainy"),
            else_="no recorded rain",
        )
        weather_label = "rainfall category"
    else:
        return {
            "available": False,
            "detail": "The weather table has neither a condition nor rainfall column.",
            "patterns": [],
        }

    traffic_hour = extract("hour", readings.c.recorded_at)
    weather_hour = extract("hour", weather.c.recorded_at)
    same_hour = and_(
        func.date(readings.c.recorded_at) == func.date(weather.c.recorded_at),
        traffic_hour == weather_hour,
    )
    statement = (
        select(
            weather_group.label("weather_category"),
            func.count(readings.c.segment_id if "segment_id" in readings.c else readings.c.recorded_at).label("matched_readings"),
            func.count(func.distinct(weather.c.recorded_at)).label("weather_observations"),
            func.avg(readings.c.speed_kmh).label("average_speed_kmh"),
            func.avg(
                case((readings.c.congestion_level.in_(HIGH_CONGESTION), 1.0), else_=0.0)
            ).label("high_or_severe_reading_share"),
        )
        .select_from(readings.join(weather, same_hour))
        .group_by(weather_group)
        .order_by(weather_group)
    )
    if start_time is not None:
        statement = statement.where(readings.c.recorded_at >= to_database_datetime(start_time))
    if end_time is not None:
        statement = statement.where(readings.c.recorded_at <= to_database_datetime(end_time))
    if segment_id is not None:
        statement = statement.where(readings.c.segment_id == segment_id)
    rows = [dict(row) for row in db.execute(statement).mappings().all()]
    return {
        "available": True,
        "weather_dimension": weather_label,
        "matching_method": "same calendar date and hour; weather is not linked to a road segment",
        "interpretation": "Descriptive temporal association only; it does not establish that weather caused traffic changes.",
        "patterns": rows,
    }


@router.get("/summary")
def analytics_summary(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    segment_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    readings = get_table("traffic_readings")
    roads = get_table("road_segments")
    required = {"segment_id", "recorded_at", "speed_kmh", "travel_time_minutes", "congestion_level"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"traffic_readings is missing analytics columns: {', '.join(sorted(missing))}.",
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
    latest_rows = ranked.subquery()
    latest_per_segment = select(
        *(latest_rows.c[name] for name in readings.c.keys())
    ).where(latest_rows.c._row_number == 1)
    latest_congestion = db.execute(
        select(latest_rows.c.congestion_level, func.count().label("segment_count"))
        .where(latest_rows.c._row_number == 1)
        .group_by(latest_rows.c.congestion_level)
    ).mappings().all()
    distribution = {level: 0 for level in CONGESTION_LEVELS}
    for row in latest_congestion:
        if row["congestion_level"] in distribution:
            distribution[row["congestion_level"]] = int(row["segment_count"])

    latest_rows_data = [dict(row) for row in db.execute(latest_per_segment).mappings().all()]
    total_segments = int(db.scalar(select(func.count()).select_from(roads)) or 0)
    total_readings = int(
        db.scalar(select(func.count()).select_from(readings).where(*filters)) or 0
    )
    average_speed = db.scalar(
        select(func.avg(readings.c.speed_kmh)).where(*filters)
    )
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
    volume_total = func.sum(readings.c.vehicle_count) if "vehicle_count" in readings.c else None
    date_expression = func.date(readings.c.recorded_at)
    hour_expression = extract("hour", readings.c.recorded_at)
    busiest_statement = (
        select(
            date_expression.label("date"),
            hour_expression.label("hour"),
            func.count().label("reading_count"),
            volume_total.label("total_vehicle_count")
            if volume_total is not None
            else literal(None).label("total_vehicle_count"),
        )
        .group_by(date_expression, hour_expression)
        .order_by(date_expression, hour_expression)
    )
    congestion_statement = (
        select(readings.c.congestion_level, func.count().label("reading_count"))
        .group_by(readings.c.congestion_level)
        .order_by(desc(func.count()))
    )
    if filters:
        segment_statement = segment_statement.where(*filters)
        busiest_statement = busiest_statement.where(*filters)
        congestion_statement = congestion_statement.where(*filters)

    segment_rows = [dict(row) for row in db.execute(segment_statement).mappings().all()]
    hourly_rows = [dict(row) for row in db.execute(busiest_statement).mappings().all()]
    congestion_rows = [dict(row) for row in db.execute(congestion_statement).mappings().all()]
    return {
        "total_road_segments": total_segments,
        "total_traffic_readings": total_readings,
        "high_congestion_roads": distribution["high"] + distribution["severe"],
        "average_traffic_speed_kmh": None if average_speed is None else float(average_speed),
        "latest_per_segment": latest_rows_data,
        "latest_congestion_distribution": distribution,
        "segment_comparison": segment_rows,
        "road_wise_average_speed": segment_rows,
        "busiest_hours": hourly_rows,
        "traffic_volume_by_time": hourly_rows,
        "traffic_volume_supported": volume_total is not None,
        "congestion_distribution": congestion_rows,
        "weather_vs_traffic_patterns": _weather_traffic_patterns(
            db, readings, start_time, end_time, segment_id
        ),
        "selected_segment_id": segment_id,
        "data_window": {"start_time": start_time, "end_time": end_time},
    }


def _period_filter(recorded_at: Any, period: str) -> Any | None:
    hour = extract("hour", recorded_at)
    if period == "morning_peak":
        return and_(hour >= 7, hour < 10)
    if period == "evening_peak":
        return and_(hour >= 16, hour < 19)
    if period == "peak":
        return or_(and_(hour >= 7, hour < 10), and_(hour >= 16, hour < 19))
    if period == "off_peak":
        return or_(hour < 7, and_(hour >= 10, hour < 16), hour >= 19)
    if period == "daytime":
        return and_(hour >= 6, hour < 22)
    if period == "overnight":
        return or_(hour < 6, hour >= 22)
    return None


@router.get("/historical")
def historical_analysis(
    segment_id: int | None = Query(default=None, gt=0),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    time_period: Literal[
        "all", "peak", "morning_peak", "evening_peak", "off_peak", "daytime", "overnight"
    ] = "all",
    congestion_level: Literal["low", "moderate", "high", "severe"] | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    readings = get_table("traffic_readings")
    required = {"segment_id", "recorded_at", "speed_kmh", "travel_time_minutes", "congestion_level"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"traffic_readings is missing historical-analysis columns: {', '.join(sorted(missing))}.",
        )
    filters = _time_filters(readings, start_time, end_time)
    if segment_id is not None:
        filters.append(readings.c.segment_id == segment_id)
    if congestion_level is not None:
        filters.append(readings.c.congestion_level == congestion_level)
    period_filter = _period_filter(readings.c.recorded_at, time_period)
    if period_filter is not None:
        filters.append(period_filter)
    base = select(readings).where(*filters)
    aggregate_columns = [
        func.count().label("reading_count"),
        func.avg(readings.c.speed_kmh).label("average_speed_kmh"),
        func.avg(readings.c.travel_time_minutes).label("average_travel_time_minutes"),
    ]
    if "vehicle_count" in readings.c:
        aggregate_columns.append(func.avg(readings.c.vehicle_count).label("average_vehicle_count"))
    stats = db.execute(select(*aggregate_columns).where(*filters)).mappings().one()
    distribution = db.execute(
        select(readings.c.congestion_level, func.count().label("reading_count"))
        .where(*filters)
        .group_by(readings.c.congestion_level)
        .order_by(readings.c.congestion_level)
    ).mappings().all()
    records = db.execute(
        base.order_by(readings.c.recorded_at.desc()).limit(limit).offset(offset)
    ).mappings().all()
    return {
        "filters": {
            "segment_id": segment_id,
            "start_time": start_time,
            "end_time": end_time,
            "time_period": time_period,
            "congestion_level": congestion_level,
        },
        "total_matching_readings": int(stats["reading_count"] or 0),
        "returned_readings": len(records),
        "limit": limit,
        "offset": offset,
        "readings": [dict(row) for row in records],
        "statistics": {
            "average_speed_kmh": None if stats["average_speed_kmh"] is None else float(stats["average_speed_kmh"]),
            "average_travel_time_minutes": None if stats["average_travel_time_minutes"] is None else float(stats["average_travel_time_minutes"]),
            "average_vehicle_count": (
                None
                if "average_vehicle_count" not in stats or stats["average_vehicle_count"] is None
                else float(stats["average_vehicle_count"])
            ),
            "vehicle_count_supported": "vehicle_count" in readings.c,
            "congestion_distribution": [dict(row) for row in distribution],
        },
    }


@router.get("/causes")
def congestion_cause_analysis(
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    segment_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    readings = get_table("traffic_readings")
    required = {"segment_id", "recorded_at", "speed_kmh", "congestion_level"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"traffic_readings is missing cause-analysis columns: {', '.join(sorted(missing))}.",
        )
    filters = _time_filters(readings, start_time, end_time)
    if segment_id is not None:
        filters.append(readings.c.segment_id == segment_id)
    peak = _period_filter(readings.c.recorded_at, "peak")
    peak_rows = db.execute(
        select(
            case((peak, "peak"), else_="outside_peak").label("period"),
            func.count().label("reading_count"),
            func.avg(readings.c.speed_kmh).label("average_speed_kmh"),
            func.avg(case((readings.c.congestion_level.in_(HIGH_CONGESTION), 1.0), else_=0.0)).label("high_or_severe_share"),
        )
        .where(*filters)
        .group_by(case((peak, "peak"), else_="outside_peak"))
    ).mappings().all()

    incidents = get_table("incidents")
    incident_columns = {"segment_id", "start_time", "end_time"}
    incident_analysis: dict[str, Any]
    if incident_columns.issubset(incidents.c.keys()):
        incident_match = exists(
            select(1).where(
                incidents.c.segment_id == readings.c.segment_id,
                incidents.c.start_time <= readings.c.recorded_at,
                or_(incidents.c.end_time.is_(None), incidents.c.end_time >= readings.c.recorded_at),
            )
        )
        high_or_severe = readings.c.congestion_level.in_(HIGH_CONGESTION)
        incident_stats = db.execute(
            select(
                func.coalesce(
                    func.sum(case((incident_match, 1), else_=0)),
                    0,
                ).label("incident_reading_count"),
                func.coalesce(
                    func.sum(case((~incident_match, 1), else_=0)),
                    0,
                ).label("outside_incident_reading_count"),
                func.avg(
                    case((incident_match, readings.c.speed_kmh), else_=None)
                ).label("incident_average_speed_kmh"),
                func.avg(
                    case((~incident_match, readings.c.speed_kmh), else_=None)
                ).label("outside_incident_average_speed_kmh"),
                func.avg(
                    case(
                        (incident_match, case((high_or_severe, 1.0), else_=0.0)),
                        else_=None,
                    )
                ).label("incident_high_or_severe_share"),
                func.avg(
                    case(
                        (~incident_match, case((high_or_severe, 1.0), else_=0.0)),
                        else_=None,
                    )
                ).label("outside_incident_high_or_severe_share"),
            )
            .where(*filters)
        ).mappings().one()
        incident_rows = []
        for period, count_key, speed_key, share_key in (
            (
                "incident_window",
                "incident_reading_count",
                "incident_average_speed_kmh",
                "incident_high_or_severe_share",
            ),
            (
                "no_recorded_incident",
                "outside_incident_reading_count",
                "outside_incident_average_speed_kmh",
                "outside_incident_high_or_severe_share",
            ),
        ):
            reading_count = int(incident_stats[count_key] or 0)
            if reading_count:
                incident_rows.append({
                    "period": period,
                    "reading_count": reading_count,
                    "average_speed_kmh": (
                        None
                        if incident_stats[speed_key] is None
                        else float(incident_stats[speed_key])
                    ),
                    "high_or_severe_share": (
                        None
                        if incident_stats[share_key] is None
                        else float(incident_stats[share_key])
                    ),
                })
        incident_analysis = {
            "available": True,
            "comparison": incident_rows,
            "interpretation": "Readings overlap recorded incident windows on the same segment; association does not prove the incident caused congestion.",
        }
    else:
        incident_analysis = {
            "available": False,
            "detail": "Incident association requires segment_id, start_time, and end_time in incidents.",
            "comparison": [],
        }

    return {
        "peak_hour_traffic": [dict(row) for row in peak_rows],
        "weather_related_patterns": _weather_traffic_patterns(
            db, readings, start_time, end_time, segment_id
        ),
        "incident_associated_congestion": incident_analysis,
        "causality": "These are observational statistical relationships in stored records, not proven causes.",
        "data_window": {"start_time": start_time, "end_time": end_time},
        "segment_id": segment_id,
    }


def _scenario_recommendations(
    baseline: dict[str, Any],
    increased: dict[str, Any] | None,
    observed_evidence: dict[str, Any],
    predicted_for: datetime,
) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    baseline_level = baseline.get("predicted_congestion_level")
    increased_level = increased.get("predicted_congestion_level") if increased else None
    congestion_rank = {name: rank for rank, name in enumerate(CONGESTION_LEVELS)}
    road_name = baseline.get("segment_name") or f"segment #{baseline.get('segment_id', 'unknown')}"
    prediction_time = to_database_datetime(predicted_for).strftime("%Y-%m-%d %H:%M")
    observed_count = int(observed_evidence.get("classified_reading_count") or 0)
    high_count = int(observed_evidence.get("high_or_severe_count") or 0)
    observation_window = (
        f" The {observed_count} classified readings from "
        f"{observed_evidence.get('from_recorded_at')} through "
        f"{observed_evidence.get('through_recorded_at')} include "
        f"{high_count} high/severe readings."
        if observed_count
        else " No classified recent readings were available to support an observed-pattern comparison."
    )
    if increased_level in ("high", "severe"):
        recommendations.append({
            "recommendation": f"Prioritize monitoring {road_name} at {prediction_time} if the modeled 20% higher-volume scenario is relevant.",
            "basis": (
                f"The trained congestion model estimates {increased_level} for {road_name} "
                f"at {prediction_time} under the 20% volume-increase scenario; the baseline estimate "
                f"is {baseline_level or 'unavailable'}.{observation_window}"
            ),
        })
    elif baseline_level in ("high", "severe"):
        recommendations.append({
            "recommendation": f"Monitor {road_name} around {prediction_time} and review the next stored reading.",
            "basis": (
                f"The trained congestion model estimates {baseline_level} for {road_name} "
                f"at {prediction_time} at baseline.{observation_window}"
            ),
        })
    if (
        increased_level in congestion_rank
        and baseline_level in congestion_rank
        and congestion_rank[increased_level] > congestion_rank[baseline_level]
    ):
        recommendations.append({
            "recommendation": f"Review monitoring plans for {road_name} at {prediction_time} if volume increases.",
            "basis": (
                f"For {road_name} at {prediction_time}, the classifier estimate shifts from "
                f"{baseline_level} at baseline to {increased_level} with 20% more vehicle-count input."
                f"{observation_window}"
            ),
        })
    baseline_time = baseline.get("predicted_travel_time_minutes")
    increased_time = increased.get("predicted_travel_time_minutes") if increased else None
    if baseline_time is not None and increased_time is not None and increased_time > baseline_time:
        recommendations.append({
            "recommendation": f"Allow a travel-time margin on {road_name} at {prediction_time} if the higher-volume scenario occurs.",
            "basis": (
                f"For {road_name} at {prediction_time}, the trained model estimates "
                f"{increased_time:.2f} minutes under the scenario versus {baseline_time:.2f} minutes at baseline."
                f"{observation_window}"
            ),
        })
    if observed_count and high_count:
        observed_high_share = high_count / observed_count
        recommendations.append({
            "recommendation": f"Continue monitoring {road_name} near {prediction_time} against new readings.",
            "basis": (
                f"For {road_name} at {prediction_time}, {high_count} of {observed_count} classified readings "
                f"({observed_high_share:.1%}) in the stated recent observation window were high or severe."
            ),
        })
    if not recommendations:
        if observed_count:
            recommendations.append({
                "recommendation": f"No elevated-congestion recommendation is supported for {road_name} at {prediction_time} by the available evidence.",
                "basis": (
                    f"The model returned no high/severe baseline or scenario classification, and "
                    f"{high_count} of {observed_count} classified recent readings were high or severe."
                ),
            })
        else:
            recommendations.append({
                "recommendation": f"Insufficient observed evidence for a congestion recommendation for {road_name} at {prediction_time}.",
                "basis": "No classified recent readings or elevated supported model output were available.",
            })
    return recommendations


@router.post("/what-if")
def what_if_scenario(
    request: TrafficScenarioRequest,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    prediction_inputs = PredictionRequest(
        segment_id=request.segment_id,
        predicted_for=request.predicted_for,
        speed_kmh=request.speed_kmh,
        vehicle_count=request.vehicle_count,
        current_congestion_level=request.current_congestion_level,
        weather_condition=request.weather_condition,
        rainfall_mm=request.rainfall_mm,
        save=False,
    )
    try:
        scenario_result = what_if_scenarios(db, prediction_inputs)
        baseline = scenario_result["baseline"]
        volume_scenario = scenario_result["scenarios"][0]
        increased = (
            {
                key: output.get("scenario")
                for key, output in volume_scenario["predictions"].items()
            }
            if volume_scenario["supported"]
            else None
        )
        observed_evidence = baseline.get("observed_evidence", {})
    except InsufficientTrainingData as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Scenario inputs could not be loaded from the traffic database.") from None

    return {
        "segment_id": request.segment_id,
        "predicted_for": to_database_datetime(request.predicted_for),
        "baseline": baseline,
        "traffic_volume_increase_20_percent": {
            "available": volume_scenario["supported"],
            "input_vehicle_count": volume_scenario.get("input_vehicle_count"),
            "prediction": increased,
            "detail": volume_scenario.get("detail"),
        },
        "rainy_weather_scenario": {
            "available": False,
            "requested_weather_condition": request.weather_condition,
            "requested_rainfall_mm": request.rainfall_mm,
            "detail": "The existing model has no weather features, and weather observations are not mapped to road segments; a rainy-weather prediction cannot be supported.",
        },
        "recommendations": _scenario_recommendations(
            baseline, increased, observed_evidence, request.predicted_for
        ),
        "observed_recent_reading_count": observed_evidence.get("reading_count", 0),
        "observed_evidence": observed_evidence,
        "recommendation_basis": "Recommendations are conditional interpretations of the selected road's timestamped stored readings and trained model outputs, not evidence that an intervention will cause a particular outcome.",
    }
