from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    inspect,
    insert,
    select,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.routers import decision_support


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    roads = Table(
        "road_segments",
        metadata,
        Column("segment_id", Integer, primary_key=True),
        Column("name", String(100), nullable=False),
        Column("start_location", String(100), nullable=False),
        Column("end_location", String(100), nullable=False),
        Column("length_km", Float, nullable=False),
        Column("road_type", String(50), nullable=False),
    )
    readings = Table(
        "traffic_readings",
        metadata,
        Column("reading_id", Integer, primary_key=True),
        Column("segment_id", Integer, nullable=False),
        Column("recorded_at", DateTime, nullable=False),
        Column("speed_kmh", Float, nullable=False),
        Column("vehicle_count", Integer, nullable=False),
        Column("travel_time_minutes", Float, nullable=False),
        Column("congestion_level", String(20), nullable=False),
    )
    weather = Table(
        "weather_data",
        metadata,
        Column("weather_id", Integer, primary_key=True),
        Column("recorded_at", DateTime, nullable=False),
        Column("location", String(100), nullable=False),
        Column("temperature_c", Float),
        Column("rainfall_mm", Float),
        Column("condition", String(100)),
    )
    incidents = Table(
        "incidents",
        metadata,
        Column("incident_id", Integer, primary_key=True),
        Column("segment_id", Integer, nullable=False),
        Column("incident_type", String(100), nullable=False),
        Column("description", String(255), nullable=False),
        Column("start_time", DateTime, nullable=False),
        Column("end_time", DateTime),
    )
    metadata.create_all(engine)
    tables = {
        "road_segments": roads,
        "traffic_readings": readings,
        "weather_data": weather,
        "incidents": incidents,
    }
    now = datetime.now().replace(microsecond=0)
    with engine.begin() as connection:
        connection.execute(insert(roads), [
            {
                "segment_id": 1,
                "name": "North Road",
                "start_location": "North",
                "end_location": "Central",
                "length_km": 3.5,
                "road_type": "arterial",
            },
            {
                "segment_id": 2,
                "name": "South Road",
                "start_location": "South",
                "end_location": "Central",
                "length_km": 2.0,
                "road_type": "local",
            },
        ])
        connection.execute(insert(readings).values(
            reading_id=1,
            segment_id=1,
            recorded_at=now - timedelta(minutes=5),
            speed_kmh=8,
            vehicle_count=110,
            travel_time_minutes=24,
            congestion_level="severe",
        ))
        connection.execute(insert(incidents).values(
            incident_id=1,
            segment_id=1,
            incident_type="Road work",
            description="Lane closure",
            start_time=now - timedelta(hours=1),
            end_time=None,
        ))

    monkeypatch.setattr(decision_support, "engine", engine)
    monkeypatch.setattr(decision_support, "get_table", tables.__getitem__)
    with TestClient(main.app) as test_client:
        yield test_client
    engine.dispose()


def test_summary_and_road_analytics_apply_segment_filters(client: TestClient) -> None:
    response = client.get("/api/analytics/summary", params={"segment_id": 1})

    assert response.status_code == 200
    result = response.json()
    assert result["total_road_segments"] == 1
    assert result["total_recorded_vehicles"] == 110
    assert result["average_speed_kmh"] == 8
    assert result["high_or_severe_readings"] == 1
    assert result["active_incidents"] == 1

    roads = client.get("/api/analytics/roads", params={"segment_id": 1})
    assert roads.status_code == 200
    assert roads.json()[0]["name"] == "North Road"
    assert roads.json()[0]["reading_count"] == 1
    assert roads.json()[0]["total_vehicle_count"] == 110


def test_active_incidents_and_missing_recommendation_storage_are_reported(
    client: TestClient,
) -> None:
    incidents = client.get("/api/incidents", params={"active_only": True})
    assert incidents.status_code == 200
    assert len(incidents.json()) == 1

    saved = client.get("/api/recommendations")
    assert saved.status_code == 200
    assert saved.json()["available"] is False
    assert saved.json()["items"] == []


def test_recommendations_are_evidence_based_and_not_claimed_as_saved(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/recommendations/generate",
        params={"segment_id": 1},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["available"] is False
    assert result["generated_count"] == 2
    assert result["saved_count"] == 0
    assert all(item["evidence_summary"] for item in result["items"])
    assert any("severe congestion" in item["evidence_summary"] for item in result["items"])
    assert "is missing" in result["detail"]


def test_rejects_invalid_time_window(client: TestClient) -> None:
    response = client.get(
        "/api/analytics/congestion",
        params={
            "start_time": datetime(2026, 1, 2).isoformat(),
            "end_time": datetime(2026, 1, 1).isoformat(),
        },
    )

    assert response.status_code == 422


def test_recommendation_persistence_deduplicates_matching_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata = MetaData()
    roads = Table(
        "road_segments",
        metadata,
        Column("segment_id", Integer, primary_key=True),
    )
    table = Table(
        "decision_recommendations",
        metadata,
        Column("recommendation_id", Integer, primary_key=True),
        Column("segment_id", Integer, ForeignKey("road_segments.segment_id"), nullable=False),
        Column("priority", String(20), nullable=False),
        Column("recommendation_text", String(255), nullable=False),
        Column("evidence_summary", String(500), nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("status", String(20), nullable=False),
        Column("deduplication_key", String(64), nullable=False, unique=True),
    )
    metadata.create_all(engine)
    assert inspect(engine).get_foreign_keys("decision_recommendations")[0][
        "referred_table"
    ] == "road_segments"
    monkeypatch.setattr(decision_support, "engine", engine)
    suggestion = {
        "segment_id": 1,
        "priority": "high",
        "recommendation": "Review traffic control.",
        "evidence_summary": "Latest recorded reading shows severe congestion.",
        "created_at": datetime.now(),
        "status": "pending",
    }

    with Session(engine) as session:
        assert decision_support._persist_suggestion(session, table, suggestion) is True
        assert decision_support._persist_suggestion(session, table, suggestion) is False
        session.commit()
        count = session.scalar(select(func.count()).select_from(table))

    assert count == 1
    engine.dispose()


def test_empty_traffic_tables_return_zero_counts_and_no_chart_rows(
    client: TestClient,
) -> None:
    with decision_support.engine.begin() as connection:
        connection.execute(
            decision_support.get_table("traffic_readings").delete()
        )
        connection.execute(
            decision_support.get_table("incidents").delete()
        )

    summary = client.get("/api/analytics/summary")
    assert summary.status_code == 200
    assert summary.json()["total_recorded_vehicles"] == 0
    assert summary.json()["average_speed_kmh"] is None
    assert summary.json()["average_travel_time_minutes"] is None
    assert summary.json()["high_or_severe_readings"] == 0
    assert summary.json()["active_incidents"] == 0

    congestion = client.get("/api/analytics/congestion")
    assert congestion.status_code == 200
    assert congestion.json()["total_readings"] == 0
    assert all(row["reading_count"] == 0 for row in congestion.json()["distribution"])

    roads = client.get("/api/analytics/roads")
    assert roads.status_code == 200
    assert len(roads.json()) == 2
    assert all(row["reading_count"] == 0 for row in roads.json())
    assert all(row["total_vehicle_count"] is None for row in roads.json())

    generated = client.post("/api/recommendations/generate")
    assert generated.status_code == 200
    assert generated.json()["generated_count"] == 0
    assert generated.json()["saved_count"] == 0
