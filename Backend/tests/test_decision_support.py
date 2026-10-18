from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import (
    CHAR,
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
from app.database import get_db
from app.models import auth_metadata, traffic_app_users
from app.routers import crud
from app.routers import decision_support
from app.routers import recommendations as recommendation_router
from app.security import get_current_user, hash_password
from scripts.add_recommendation_context_columns import (
    ADDITIVE_COLUMNS,
    ensure_context_columns,
)


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
    auth_metadata.create_all(engine, tables=[traffic_app_users])
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
        connection.execute(
            traffic_app_users.insert().values(
                username="test-admin",
                password_hash=hash_password("a-test-password-long-enough"),
                is_active=True,
                token_version=0,
            )
        )

    monkeypatch.setattr(decision_support, "engine", engine)
    monkeypatch.setattr(decision_support, "get_table", tables.__getitem__)
    monkeypatch.setattr(crud, "get_table", tables.__getitem__)
    main.app.state.test_engine = engine
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-key-with-more-than-32-bytes")
    def override_db() -> Any:
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": 1,
        "username": "test",
        "token_version": 0,
    }
    main.app.dependency_overrides[get_db] = override_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()
    engine.dispose()


def test_analytics_api_rejects_unauthenticated_requests() -> None:
    with TestClient(main.app) as test_client:
        response = test_client.get("/api/analytics/summary")

    assert response.status_code == 401


def test_login_me_and_logout_use_persistent_user_state(
    client: TestClient,
) -> None:
    main.app.dependency_overrides.pop(get_current_user, None)
    response = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "a-test-password-long-enough"},
    )

    assert response.status_code == 200
    token = response.json()["access_token"]
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200
    assert client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 204
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    ).status_code == 401


def test_login_rejects_invalid_password(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "test-admin", "password": "incorrect-password"},
    )

    assert response.status_code == 401


def test_road_and_incident_crud_persist_and_preserve_references(
    client: TestClient,
) -> None:
    created_road = client.post(
        "/api/road-segments",
        json={
            "name": "East Road",
            "start_location": "East",
            "end_location": "Central",
            "length_km": 4.2,
            "road_type": "arterial",
        },
    )
    assert created_road.status_code == 201
    road_id = created_road.json()["segment_id"]
    updated_road = client.patch(
        f"/api/road-segments/{road_id}",
        json={"name": "East Avenue"},
    )
    assert updated_road.status_code == 200
    assert updated_road.json()["name"] == "East Avenue"
    assert client.delete("/api/road-segments/1").status_code == 409
    assert client.delete(f"/api/road-segments/{road_id}").status_code == 200
    assert client.get(f"/api/road-segments/{road_id}").status_code == 404

    created_incident = client.post(
        "/api/incidents",
        json={
            "segment_id": 2,
            "incident_type": "Collision",
            "description": "Two-lane obstruction",
            "start_time": "2026-01-01T10:00:00",
            "end_time": None,
        },
    )
    assert created_incident.status_code == 201
    incident_id = created_incident.json()["incident_id"]
    invalid_update = client.patch(
        f"/api/incidents/{incident_id}",
        json={"end_time": "2025-12-31T10:00:00"},
    )
    assert invalid_update.status_code == 422
    assert client.patch(
        f"/api/incidents/{incident_id}",
        json={"incident_type": "Road work"},
    ).json()["incident_type"] == "Road work"
    assert client.delete(f"/api/incidents/{incident_id}").status_code == 200


def test_generated_recommendations_can_be_filtered_updated_and_deleted(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = main.app.state.test_engine
    metadata = MetaData()
    table = Table(
        "decision_recommendations",
        metadata,
        Column("recommendation_id", Integer, primary_key=True, autoincrement=True),
        Column("segment_id", Integer, nullable=False),
        Column("priority", String(20), nullable=False),
        Column("recommendation_text", String(500), nullable=False),
        Column("evidence_summary", String, nullable=False),
        Column("created_at", DateTime, nullable=False),
        Column("status", String(30), nullable=False, default="pending"),
        Column("deduplication_key", CHAR(64), nullable=False, unique=True),
    )
    table.create(engine)
    original_get_table = decision_support.get_table

    def resolve_table(name: str) -> Table:
        return table if name == "decision_recommendations" else original_get_table(name)

    monkeypatch.setattr(decision_support, "get_table", resolve_table)
    monkeypatch.setattr(recommendation_router, "get_table", lambda _name: table)
    generated = client.post(
        "/api/recommendations/generate",
        params={"segment_id": 1},
    )
    assert generated.status_code == 200
    assert generated.json()["saved_count"] == 2
    repeated_generation = client.post(
        "/api/recommendations/generate",
        params={"segment_id": 1},
    )
    assert repeated_generation.status_code == 200
    assert repeated_generation.json()["saved_count"] == 0

    saved = client.get("/api/recommendations", params={"segment_id": 1})
    assert saved.status_code == 200
    items = saved.json()["items"]
    assert len(items) == 2
    recommendation_id = items[0]["recommendation_id"]
    updated = client.patch(
        f"/api/recommendations/{recommendation_id}",
        json={"recommendation_text": "Review traffic controls.", "status": "reviewed"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "reviewed"
    filtered = client.get(
        "/api/recommendations",
        params={"recommendation_status": "reviewed"},
    )
    assert [item["recommendation_id"] for item in filtered.json()["items"]] == [
        recommendation_id
    ]
    assert client.delete(f"/api/recommendations/{recommendation_id}").status_code == 204


def test_manual_recommendation_uses_database_evidence_and_persists_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = main.app.state.test_engine
    metadata = MetaData()
    table = Table(
        "decision_recommendations",
        metadata,
        Column("recommendation_id", Integer, primary_key=True, autoincrement=True),
        Column("segment_id", Integer, nullable=False),
        Column("priority", String(20), nullable=False),
        Column("recommendation_text", String(500), nullable=False),
        Column("evidence_summary", String(500), nullable=False),
        Column("problem_type", String(40)),
        Column("congestion_severity", String(20)),
        Column("problem_description", String(500)),
        Column("created_at", DateTime, nullable=False),
        Column("status", String(30), nullable=False),
        Column("deduplication_key", CHAR(64), nullable=False, unique=True),
    )
    table.create(engine)
    original_get_table = decision_support.get_table

    def resolve_table(name: str) -> Table:
        return table if name == "decision_recommendations" else original_get_table(name)

    monkeypatch.setattr(decision_support, "get_table", resolve_table)
    monkeypatch.setattr(recommendation_router, "get_table", resolve_table)

    created = client.post(
        "/api/recommendations",
        json={
            "segment_id": 1,
            "problem_type": "Accident",
            "congestion_severity": "Severe",
            "problem_description": "Reported collision; cause not confirmed.",
        },
    )
    assert created.status_code == 201
    result = created.json()
    assert result["saved"] is True
    assert result["road_name"] == "North Road"
    assert result["problem_type"] == "Accident"
    assert result["congestion_severity"] == "Severe"
    assert result["status"] == "Suggested"
    assert "High/severe readings: 1" in result["evidence_summary"]
    assert "Lane closure" in result["evidence_summary"]
    assert any("do not publish an unverified route" in action for action in result["recommended_actions"])

    stored = client.get("/api/recommendations", params={"segment_id": 1})
    assert stored.status_code == 200
    saved_record = stored.json()["items"][0]
    assert saved_record["problem_description"] == "Reported collision; cause not confirmed."
    assert saved_record["status"] == "suggested"

    updated = client.patch(
        f"/api/recommendations/{result['recommendation_id']}",
        json={"status": "reviewed"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "reviewed"
    refreshed = client.get(
        "/api/recommendations",
        params={"segment_id": 1, "recommendation_status": "reviewed"},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["items"][0]["status"] == "reviewed"
    implemented = client.patch(
        f"/api/recommendations/{result['recommendation_id']}",
        json={"status": "implemented"},
    )
    assert implemented.status_code == 200
    assert implemented.json()["status"] == "implemented"
    refreshed_implemented = client.get(
        "/api/recommendations",
        params={"segment_id": 1, "recommendation_status": "implemented"},
    )
    assert refreshed_implemented.status_code == 200
    assert refreshed_implemented.json()["items"][0]["status"] == "implemented"

    empty_reading_report = client.post(
        "/api/recommendations",
        json={
            "segment_id": 2,
            "problem_type": "Other",
            "congestion_severity": "Moderate",
            "problem_description": "Reported traffic issue; details need field verification.",
        },
    )
    assert empty_reading_report.status_code == 201
    assert "No traffic readings were found" in empty_reading_report.json()["evidence_summary"]
    assert "No matching incident records were found" in empty_reading_report.json()["evidence_summary"]

    invalid = client.post(
        "/api/recommendations",
        json={
            "segment_id": 1,
            "problem_type": "Invented problem",
            "congestion_severity": "Severe",
            "problem_description": "A report.",
        },
    )
    assert invalid.status_code == 422
    blank_description = client.post(
        "/api/recommendations",
        json={
            "segment_id": 1,
            "problem_type": "Traffic Congestion",
            "congestion_severity": "High",
            "problem_description": "  ",
        },
    )
    assert blank_description.status_code == 422
    unknown_road = client.post(
        "/api/recommendations",
        json={
            "segment_id": 999,
            "problem_type": "Traffic Congestion",
            "congestion_severity": "High",
            "problem_description": "Reported traffic queue.",
        },
    )
    assert unknown_road.status_code == 422


def test_manual_recommendation_reports_missing_additive_columns_without_success(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = main.app.state.test_engine
    metadata = MetaData()
    table = Table(
        "decision_recommendations",
        metadata,
        Column("recommendation_id", Integer, primary_key=True, autoincrement=True),
        Column("segment_id", Integer, nullable=False),
        Column("priority", String(20), nullable=False),
        Column("recommendation_text", String(500), nullable=False),
        Column("evidence_summary", String(500)),
        Column("created_at", DateTime),
        Column("status", String(30)),
        Column("deduplication_key", CHAR(64), nullable=False),
    )
    table.create(engine)
    monkeypatch.setattr(recommendation_router, "get_table", lambda _name: table)

    response = client.post(
        "/api/recommendations",
        json={
            "segment_id": 1,
            "problem_type": "Traffic Congestion",
            "congestion_severity": "High",
            "problem_description": "Traffic queue reported.",
        },
    )
    assert response.status_code == 503
    assert "schema update" in response.json()["detail"]
    assert "Traceback" not in response.text


def test_recommendation_context_migration_is_additive_and_rerunnable() -> None:
    engine = create_engine("sqlite://")
    metadata = MetaData()
    table = Table(
        "decision_recommendations",
        metadata,
        Column("recommendation_id", Integer, primary_key=True),
        Column("segment_id", Integer, nullable=False),
        Column("recommendation_text", String(500), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            table.insert().values(
                recommendation_id=1,
                segment_id=3,
                recommendation_text="Existing recommendation",
            )
        )

        assert ensure_context_columns(connection) == list(ADDITIVE_COLUMNS)
        assert ensure_context_columns(connection) == []
        record = connection.execute(
            select(table).where(table.c.recommendation_id == 1)
        ).mappings().one()
        assert record["recommendation_text"] == "Existing recommendation"

        columns = {
            column["name"]: column
            for column in inspect(connection).get_columns("decision_recommendations")
        }
        assert {
            name: columns[name]["type"].length
            for name in ADDITIVE_COLUMNS
        } == {
            "problem_type": 40,
            "congestion_severity": 20,
            "problem_description": 500,
        }
        assert all(columns[name]["nullable"] for name in ADDITIVE_COLUMNS)
    engine.dispose()


def test_recommendation_table_migration_includes_form_context_columns() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "002_decision_recommendations.sql"
    ).read_text(encoding="utf-8")

    for name, definition in ADDITIVE_COLUMNS.items():
        assert f"{name} {definition}" in migration


def test_traffic_recommendation_analysis_requires_evidence_and_uses_incidents(
    client: TestClient,
) -> None:
    engine = main.app.state.test_engine
    readings = decision_support.get_table("traffic_readings")
    with engine.connect() as connection:
        recorded_at = connection.execute(
            select(readings.c.recorded_at).where(readings.c.reading_id == 1)
        ).scalar_one()
    start_time = recorded_at - timedelta(minutes=10)
    params = {
        "segment_id": 1,
        "start_time": start_time.isoformat(),
    }

    no_readings = client.get(
        "/api/recommendations/analyze",
        params={
            "segment_id": 1,
            "start_time": (recorded_at + timedelta(hours=2)).isoformat(),
        },
    )
    assert no_readings.status_code == 200
    assert no_readings.json()["status"] == "Insufficient Data"
    assert no_readings.json()["reading_count"] == 0
    assert no_readings.json()["recommendation"] is None

    insufficient = client.get("/api/recommendations/analyze", params=params)
    assert insufficient.status_code == 200
    one_reading_result = insufficient.json()
    assert one_reading_result["status"] == "Analyzed"
    assert one_reading_result["congestion_level"] == "High"
    assert one_reading_result["reading_count"] == 1
    assert one_reading_result["classified_reading_count"] == 1
    assert one_reading_result["recommendation"]
    assert "not live traffic data" in one_reading_result["evidence_summary"]

    with engine.begin() as connection:
        connection.execute(
            readings.insert(),
            {
                "reading_id": 2,
                "segment_id": 1,
                "recorded_at": recorded_at + timedelta(minutes=5),
                "speed_kmh": 20,
                "vehicle_count": 50,
                "travel_time_minutes": 12,
                "congestion_level": "low",
            },
        )

    two_readings = client.get("/api/recommendations/analyze", params=params)
    assert two_readings.status_code == 200
    two_reading_result = two_readings.json()
    assert two_reading_result["status"] == "Analyzed"
    assert two_reading_result["congestion_level"] == "High"
    assert two_reading_result["reading_count"] == 2
    assert two_reading_result["classified_reading_count"] == 2
    assert two_reading_result["recommendation"]

    with engine.begin() as connection:
        connection.execute(
            readings.insert().values(
                reading_id=3,
                segment_id=1,
                recorded_at=recorded_at + timedelta(minutes=10),
                speed_kmh=15,
                vehicle_count=70,
                travel_time_minutes=15,
                congestion_level="moderate",
            )
        )

    analyzed = client.get("/api/recommendations/analyze", params=params)
    assert analyzed.status_code == 200
    result = analyzed.json()
    assert result["status"] == "Analyzed"
    assert result["road_name"] == "North Road"
    assert result["congestion_level"] == "Moderate"
    assert result["reading_count"] == 3
    assert result["classified_reading_count"] == 3
    assert result["congestion_counts"] == {
        "low": 1,
        "moderate": 1,
        "high": 0,
        "severe": 1,
    }
    assert result["incident_records"][0]["incident_type"] == "Road work"
    assert "recorded incident" in result["recommendation"]

    with engine.begin() as connection:
        connection.execute(
            readings.insert().values(
                reading_id=4,
                segment_id=2,
                recorded_at=recorded_at,
                speed_kmh=25,
                vehicle_count=35,
                travel_time_minutes=8,
                congestion_level="unrecognized",
            )
        )
    unclassified = client.get(
        "/api/recommendations/analyze",
        params={
            "segment_id": 2,
            "start_time": start_time.isoformat(),
        },
    )
    assert unclassified.status_code == 200
    unclassified_result = unclassified.json()
    assert unclassified_result["status"] == "Insufficient Data"
    assert unclassified_result["reading_count"] == 1
    assert unclassified_result["classified_reading_count"] == 0
    assert unclassified_result["congestion_level"] is None
    assert unclassified_result["recommendation"] is None


def test_recommendation_classification_thresholds() -> None:
    assert recommendation_router._classify_congestion(
        {"low": 1, "moderate": 0, "high": 1, "severe": 1},
        3,
    ) == "High"
    assert recommendation_router._classify_congestion(
        {"low": 1, "moderate": 1, "high": 1, "severe": 0},
        3,
    ) == "Moderate"
    assert recommendation_router._classify_congestion(
        {"low": 2, "moderate": 1, "high": 0, "severe": 0},
        3,
    ) == "Low"


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


def test_analytics_and_readings_apply_road_type_and_congestion_filters(
    client: TestClient,
) -> None:
    summary = client.get("/api/analytics/summary", params={"road_type": "local"})
    assert summary.status_code == 200
    assert summary.json()["total_road_segments"] == 1
    assert summary.json()["total_traffic_readings"] == 0
    assert summary.json()["total_recorded_vehicles"] is None
    assert summary.json()["high_or_severe_readings"] is None

    road_rows = client.get("/api/analytics/roads", params={"road_type": "arterial"})
    assert [row["name"] for row in road_rows.json()] == ["North Road"]
    filtered_readings = client.get(
        "/api/traffic-readings",
        params={"road_type": "local", "congestion_level": "severe"},
    )
    assert filtered_readings.status_code == 200
    assert filtered_readings.json() == []
    now = datetime.now()
    time_filtered = client.get(
        "/api/traffic-readings",
        params={
            "from_time": (now - timedelta(minutes=10)).time().replace(microsecond=0).isoformat(),
            "to_time": now.time().replace(microsecond=0).isoformat(),
        },
    )
    assert time_filtered.status_code == 200
    assert len(time_filtered.json()) == 1


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


def test_empty_traffic_tables_return_empty_metrics_and_no_chart_rows(
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
    assert summary.json()["total_recorded_vehicles"] is None
    assert summary.json()["average_speed_kmh"] is None
    assert summary.json()["average_travel_time_minutes"] is None
    assert summary.json()["high_or_severe_readings"] is None
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
