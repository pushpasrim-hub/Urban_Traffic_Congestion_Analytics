from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Column, DateTime, Float, Integer, MetaData, String, Table, create_engine, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import main
from app.database import get_db
from app.routers import auth as auth_router
from app.routers import analytics as analytics_router
from app.routers import ml as ml_router
from app.schemas import PredictionRequest, TrafficScenarioRequest, WhatIfRequest
from app.security import get_current_user
from app.services import prediction_service as service


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Any:
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
        Column("name", String(100)),
        Column("length_km", Float),
    )
    readings = Table(
        "traffic_readings",
        metadata,
        Column("segment_id", Integer),
        Column("recorded_at", DateTime),
        Column("speed_kmh", Float),
        Column("vehicle_count", Integer),
        Column("travel_time_minutes", Float),
        Column("congestion_level", String(20)),
    )
    incidents = Table(
        "incidents",
        metadata,
        Column("incident_id", Integer, primary_key=True),
        Column("segment_id", Integer),
        Column("start_time", DateTime),
        Column("end_time", DateTime),
    )
    weather = Table(
        "weather_data",
        metadata,
        Column("weather_id", Integer, primary_key=True),
        Column("recorded_at", DateTime),
        Column("location", String(100)),
        Column("condition", String(100)),
    )
    predictions = Table(
        "traffic_predictions",
        metadata,
        Column("prediction_id", Integer, primary_key=True),
        Column("segment_id", Integer),
        Column("predicted_for", DateTime),
        Column("predicted_speed_kmh", Float),
        Column("predicted_travel_time_minutes", Float),
        Column("predicted_congestion_level", String(20)),
    )
    metadata.create_all(engine)
    tables = {
        "road_segments": roads,
        "traffic_readings": readings,
        "incidents": incidents,
        "weather_data": weather,
        "traffic_predictions": predictions,
    }
    monkeypatch.setattr(service, "get_table", tables.__getitem__)
    with Session(engine) as session:
        session.execute(insert(roads), [
            {"segment_id": 1, "name": "North Road", "length_km": 3.0},
            {"segment_id": 2, "name": "South Road", "length_km": 5.0},
        ])
        labels = ("low", "moderate", "high")
        start = datetime(2025, 1, 1)
        for index in range(60):
            volume = 20 + (index % 25) * 8
            session.execute(insert(readings).values(
                segment_id=index % 2 + 1,
                recorded_at=start + timedelta(minutes=index * 10),
                speed_kmh=max(5, 65 - volume / 3),
                vehicle_count=volume,
                travel_time_minutes=4 + volume / 12,
                congestion_level=labels[(index // 2) % len(labels)],
            ))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def model_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "traffic-model.joblib"
    monkeypatch.setattr(service, "model_path", lambda: path)
    return path


def test_training_preprocessing_removes_duplicates_and_invalid_negative_measurements(
    database: Session,
) -> None:
    readings = service.get_table("traffic_readings")
    duplicate = database.execute(readings.select().limit(1)).mappings().one()
    database.execute(insert(readings).values(**dict(duplicate)))
    database.execute(
        readings.update()
        .where(readings.c.recorded_at == datetime(2025, 1, 1, 0, 10))
        .values(speed_kmh=-5)
    )
    database.execute(
        readings.update()
        .where(readings.c.recorded_at == datetime(2025, 1, 1, 0, 20))
        .values(vehicle_count=float("inf"))
    )
    database.commit()

    frame = service._training_frame(database)

    assert frame.attrs["preprocessing"]["duplicate_rows_removed"] == 1
    assert frame.attrs["preprocessing"]["negative_measurements_replaced_with_missing"] == 1
    assert frame.attrs["preprocessing"]["invalid_numeric_values_by_column"]["vehicle_count"] == 1
    assert frame["lag_speed_kmh"].ge(0).all() or frame["lag_speed_kmh"].isna().any()
    assert frame.loc[frame["recorded_at"] == datetime(2025, 1, 1, 0, 10), "speed_kmh"].isna().all()
    assert frame.loc[frame["recorded_at"] == datetime(2025, 1, 1, 0, 20), "vehicle_count"].isna().all()


def test_same_timestamp_records_do_not_become_each_others_lagged_features(
    database: Session,
) -> None:
    readings = service.get_table("traffic_readings")
    timestamp = datetime(2025, 1, 1)
    database.execute(insert(readings).values(
        segment_id=1,
        recorded_at=timestamp,
        speed_kmh=1,
        vehicle_count=1000,
        travel_time_minutes=100,
        congestion_level="severe",
    ))
    database.commit()

    frame = service._training_frame(database)
    same_time_rows = frame.loc[
        (frame["segment_id"] == "1") & (frame["recorded_at"] == timestamp)
    ]

    assert len(same_time_rows) == 2
    assert same_time_rows["lag_speed_kmh"].isna().all()
    assert same_time_rows["lag_vehicle_count"].isna().all()
    assert same_time_rows["lag_congestion_level"].isna().all()


def test_training_saves_models_metrics_and_baseline(database: Session, model_file: Path) -> None:
    predictions = service.get_table("traffic_predictions")
    prediction_count_before = len(database.execute(predictions.select()).all())
    result = service.train_model(database)
    status = service.model_status(database)

    assert model_file.is_file()
    assert result["total_rows"] == 60
    assert status["available"] is True
    assert result["models"]["congestion"]["available"]
    assert result["models"]["congestion"]["metrics"]["confusion_matrix"]
    assert "precision_weighted" in result["models"]["congestion"]["metrics"]
    assert "recall_weighted" in result["models"]["congestion"]["metrics"]
    assert "baseline" in result["models"]["congestion"]
    assert result["models"]["travel_time"]["metrics"]["mae"] >= 0
    assert result["models"]["travel_time"]["baseline"]["metrics"]["mae"] >= 0
    assert result["models"]["traffic_volume"]["metrics"]["rmse"] >= 0
    assert result["weather_used"] is False
    assert result["preprocessing"]["schema"]["traffic_readings"]["recorded_at"] == "DATETIME"
    assert len(database.execute(predictions.select()).all()) == prediction_count_before


def test_analytics_summary_filters_all_traffic_aggregates_by_segment(
    database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(analytics_router, "get_table", service.get_table)

    result = analytics_router.analytics_summary(
        segment_id=1,
        db=database,
        _user={"user_id": 1},
    )

    assert result["total_road_segments"] == 2
    assert result["total_traffic_readings"] == 30
    assert len(result["latest_per_segment"]) == 1
    assert result["latest_per_segment"][0]["segment_id"] == 1
    assert len(result["road_wise_average_speed"]) == 1
    assert result["road_wise_average_speed"][0]["segment_id"] == 1
    assert sum(row["reading_count"] for row in result["congestion_distribution"]) == 30
    assert all(row["total_vehicle_count"] is not None for row in result["traffic_volume_by_time"])


def test_cause_analysis_compares_incident_windows_without_grouping_correlated_exists(
    database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tables = {
        "traffic_readings": service.get_table("traffic_readings"),
        "road_segments": service.get_table("road_segments"),
        "incidents": service.get_table("incidents"),
        "weather_data": service.get_table("weather_data"),
    }
    monkeypatch.setattr(analytics_router, "get_table", tables.__getitem__)
    incidents = tables["incidents"]
    database.execute(insert(incidents).values(
        segment_id=1,
        start_time=datetime(2025, 1, 1),
        end_time=datetime(2025, 1, 1, 0, 20),
    ))
    database.commit()

    result = analytics_router.congestion_cause_analysis(
        start_time=None,
        end_time=None,
        segment_id=1,
        db=database,
        _user={"user_id": 1},
    )

    comparison = {
        row["period"]: row for row in result["incident_associated_congestion"]["comparison"]
    }
    assert comparison["incident_window"]["reading_count"] == 2
    assert comparison["no_recorded_incident"]["reading_count"] == 28
    assert comparison["incident_window"]["average_speed_kmh"] is not None


def test_prediction_collection_does_not_register_manual_write_routes() -> None:
    client = TestClient(main.app)

    assert client.post("/api/predictions", json={}).status_code == 405
    assert client.patch("/api/predictions/1", json={}).status_code == 405
    assert client.put("/api/predictions/1", json={}).status_code == 405


def test_insufficient_history_does_not_create_an_artifact(
    database: Session,
    model_file: Path,
) -> None:
    readings = service.get_table("traffic_readings")
    database.execute(readings.delete().where(readings.c.recorded_at > datetime(2025, 1, 1, 1, 30)))
    database.commit()

    with pytest.raises(service.InsufficientTrainingData, match="at least"):
        service.train_model(database)
    assert not model_file.exists()


def test_model_status_reports_missing_or_corrupt_artifact(
    database: Session,
    model_file: Path,
) -> None:
    assert service.model_status(database)["available"] is False
    model_file.write_bytes(b"not a joblib artifact")
    status = service.model_status(database)
    assert status["available"] is False
    assert "could not be loaded" in status["detail"]


def test_model_status_uses_database_aggregates_without_rebuilding_training_frame(
    database: Session,
    model_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        service,
        "_training_frame",
        lambda _db: pytest.fail("Model status must not rebuild the full training frame."),
    )

    status = service.model_status(database)

    assert status["available"] is False
    assert status["total_rows"] == 60
    assert status["eligible_rows"] == {
        "travel_time": 60,
        "traffic_volume": 60,
        "congestion": 60,
    }
    assert status["models"]["congestion"]["detail"] == (
        "Ready for chronological classification validation."
    )


def test_prediction_and_hypothetical_scenarios_use_trained_pipeline(
    database: Session,
    model_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = service.train_model(database)
    for name in ("travel_time", "traffic_volume", "congestion"):
        evaluated_model = metadata["models"][name]
        assert evaluated_model["available"] is True
        assert evaluated_model["training_rows"] > 0
        assert evaluated_model["validation_rows"] > 0
        assert evaluated_model["validation_period"]["start"] <= evaluated_model["validation_period"]["end"]
        assert evaluated_model["metrics"]
    request = PredictionRequest(
        segment_id=1,
        predicted_for=datetime.now() + timedelta(days=1),
        save=False,
    )

    prediction = service.predict_travel_time(database, request)
    original_load = service._load_artifact
    load_count = 0

    def load_artifact_once() -> dict[str, Any]:
        nonlocal load_count
        load_count += 1
        return original_load()

    monkeypatch.setattr(service, "_load_artifact", load_artifact_once)
    comparison = service.what_if_scenarios(database, WhatIfRequest(
        segment_id=1,
        predicted_for=request.predicted_for,
    ))

    assert load_count == 1
    assert prediction["predicted_travel_time_minutes"] >= 0
    assert prediction["predicted_vehicle_count"] >= 0
    assert prediction["predicted_congestion_level"] in {"low", "moderate", "high"}
    assert 1 <= comparison["baseline"]["observed_evidence"]["reading_count"] <= 10
    assert comparison["hypothetical"] is True
    assert comparison["scenarios"][0]["supported"] is True
    assert comparison["scenarios"][0]["input_vehicle_count"] == pytest.approx(
        comparison["baseline"]["model_inputs"]["vehicle_count"] * 1.2
    )
    assert comparison["scenarios"][1]["supported"] is False
    assert "no road-segment mapping" in comparison["scenarios"][1]["detail"]


def test_saving_prediction_reports_vehicle_count_as_not_persisted(
    database: Session,
    model_file: Path,
) -> None:
    service.train_model(database)
    request = PredictionRequest(
        segment_id=1,
        predicted_for=datetime.now() + timedelta(days=1),
        save=True,
    )
    prediction = service.predict_travel_time(database, request)

    row, saved_fields, unsupported_fields = service.save_prediction(
        database, request, prediction
    )

    assert row is not None
    assert "predicted_vehicle_count" not in saved_fields
    assert unsupported_fields == ["predicted_vehicle_count"]


def test_model_loading_fails_clearly_when_artifact_is_missing(
    database: Session,
    model_file: Path,
) -> None:
    request = PredictionRequest(
        segment_id=1,
        predicted_for=datetime.now() + timedelta(days=1),
        save=False,
    )
    with pytest.raises(service.InsufficientTrainingData, match="No trained model"):
        service.predict_travel_time(database, request)


def test_prediction_schema_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError):
        PredictionRequest(
            segment_id=0,
            predicted_for=datetime.now() + timedelta(days=1),
        )
    with pytest.raises(ValidationError):
        PredictionRequest(
            segment_id=1,
            predicted_for=datetime.now() + timedelta(days=1),
            vehicle_count=float("inf"),
        )
    with pytest.raises(ValidationError):
        WhatIfRequest(
            segment_id=1,
            predicted_for=datetime.now() + timedelta(days=1),
            save=True,
        )


def test_what_if_api_validation_and_success_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "username": "test"}
    main.app.dependency_overrides[get_db] = lambda: None
    monkeypatch.setattr(
        ml_router,
        "what_if_scenarios",
        lambda _db, _request: {
            "hypothetical": True,
            "scenarios": [{"name": "rainy_weather", "supported": False}],
        },
    )
    try:
        client = TestClient(main.app)
        bad_response = client.post("/api/ml/what-if", json={
            "segment_id": 0,
            "predicted_for": (datetime.now() + timedelta(days=1)).isoformat(),
        })
        extra_response = client.post("/api/ml/what-if", json={
            "segment_id": 1,
            "predicted_for": (datetime.now() + timedelta(days=1)).isoformat(),
            "save": False,
        })
        good_response = client.post("/api/ml/what-if", json={
            "segment_id": 1,
            "predicted_for": (datetime.now() + timedelta(days=1)).isoformat(),
        })
    finally:
        main.app.dependency_overrides.clear()

    assert bad_response.status_code == 422
    assert extra_response.status_code == 422
    assert any(
        error["type"] == "extra_forbidden"
        for error in extra_response.json()["detail"]
    )
    assert good_response.status_code == 200
    assert good_response.json()["hypothetical"] is True
    assert good_response.json()["scenarios"][0]["supported"] is False


def test_prediction_api_idempotency_prevents_duplicate_saves_but_allows_later_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"predict": 0, "save": 0}

    def predict(_db: Any, request: PredictionRequest) -> dict[str, Any]:
        calls["predict"] += 1
        return {
            "segment_id": request.segment_id,
            "predicted_for": request.predicted_for,
            "predicted_travel_time_minutes": 8.0,
            "predicted_vehicle_count": 42.0,
            "predicted_congestion_level": "moderate",
        }

    def save(_db: Any, _request: PredictionRequest, prediction: dict[str, Any]) -> tuple[dict[str, Any], list[str], list[str]]:
        calls["save"] += 1
        return {"prediction_id": calls["save"], **prediction}, [
            "predicted_travel_time_minutes",
        ], ["predicted_vehicle_count"]

    monkeypatch.setattr(ml_router, "_prediction_request_cache", {})
    monkeypatch.setattr(ml_router, "predict_travel_time", predict)
    monkeypatch.setattr(ml_router, "save_prediction", save)
    main.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": 1,
        "username": "test",
    }
    main.app.dependency_overrides[get_db] = lambda: None
    request_time = datetime.now() + timedelta(days=1)
    payload = {
        "segment_id": 1,
        "predicted_for": request_time.isoformat(),
        "save": True,
    }
    key = "123e4567-e89b-12d3-a456-426614174000"
    try:
        client = TestClient(main.app)
        first = client.post(
            "/api/ml/predict",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        repeated = client.post(
            "/api/ml/predict",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        conflicting = client.post(
            "/api/ml/predict",
            json={**payload, "predicted_for": (request_time + timedelta(hours=1)).isoformat()},
            headers={"Idempotency-Key": key},
        )
        later_run = client.post(
            "/api/ml/predict",
            json=payload,
            headers={"Idempotency-Key": "123e4567-e89b-12d3-a456-426614174001"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json()["idempotent_replay"] is False
    assert repeated.status_code == 200
    assert repeated.json()["idempotent_replay"] is True
    assert repeated.json()["prediction"]["prediction_id"] == first.json()["prediction"]["prediction_id"]
    assert repeated.json()["unsupported_persistence_fields"] == ["predicted_vehicle_count"]
    assert conflicting.status_code == 409
    assert later_run.status_code == 200
    assert later_run.json()["idempotent_replay"] is False
    assert calls == {"predict": 2, "save": 2}


def test_analytics_what_if_uses_paired_predictions_and_evidence(
    database: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    predicted_for = datetime.now() + timedelta(days=1)
    calls: list[PredictionRequest] = []
    baseline = {
        "segment_id": 1,
        "segment_name": "North Road",
        "predicted_congestion_level": "moderate",
        "predicted_travel_time_minutes": 4.0,
        "model_inputs": {"vehicle_count": 25.0},
        "observed_evidence": {
            "reading_count": 5,
            "classified_reading_count": 5,
            "high_or_severe_count": 2,
            "high_or_severe_share": 0.4,
            "from_recorded_at": "2025-01-01 08:00",
            "through_recorded_at": "2025-01-01 08:40",
        },
    }

    def scenarios(_db: Session, request: PredictionRequest) -> dict[str, Any]:
        calls.append(request)
        return {
            "baseline": baseline,
            "scenarios": [{
                "name": "traffic_volume_increased_20_percent",
                "supported": True,
                "input_vehicle_count": 30.0,
                "predictions": {
                    "predicted_travel_time_minutes": {
                        "baseline": 4.0,
                        "scenario": 5.0,
                        "difference": 1.0,
                    },
                    "predicted_congestion_level": {
                        "baseline": "moderate",
                        "scenario": "high",
                        "difference": None,
                    },
                },
            }],
        }

    monkeypatch.setattr(analytics_router, "what_if_scenarios", scenarios)
    response = analytics_router.what_if_scenario(
        TrafficScenarioRequest(segment_id=1, predicted_for=predicted_for),
        database,
        {"user_id": 1},
    )

    assert len(calls) == 1
    assert calls[0].save is False
    assert response["traffic_volume_increase_20_percent"]["prediction"] == {
        "predicted_travel_time_minutes": 5.0,
        "predicted_congestion_level": "high",
    }
    assert response["observed_evidence"] == baseline["observed_evidence"]
    assert any(
        "North Road" in item["recommendation"]
        and predicted_for.strftime("%Y-%m-%d") in item["recommendation"]
        and "North Road" in item["basis"]
        and "2 of 5" in item["basis"]
        for item in response["recommendations"]
    )


def test_training_endpoint_queues_one_background_job_and_status_is_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class DeferredExecutor:
        def __init__(self) -> None:
            self.submitted: list[tuple[Any, tuple[Any, ...]]] = []

        def submit(self, function: Any, *args: Any) -> None:
            self.submitted.append((function, args))

    executor = DeferredExecutor()
    monkeypatch.setattr(ml_router, "_training_executor", executor)
    monkeypatch.setattr(ml_router, "_training_jobs", {})
    main.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": 1,
        "username": "test",
    }
    try:
        client = TestClient(main.app)
        first = client.post("/api/ml/train")
        second = client.post("/api/ml/train")
        job_id = first.json()["job_id"]
        status_response = client.get(f"/api/ml/train/{job_id}")
    finally:
        main.app.dependency_overrides.clear()

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == job_id
    assert len(executor.submitted) == 1
    assert status_response.json()["status"] == "queued"


def test_background_training_worker_publishes_actual_completion_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptySession:
        def __enter__(self) -> "EmptySession":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

    job_id = "background-test"
    monkeypatch.setattr(ml_router, "_training_jobs", {
        job_id: {
            "job_id": job_id,
            "status": "queued",
            "progress": "Waiting",
            "finished_at": None,
        },
    })
    monkeypatch.setattr(ml_router, "SessionLocal", EmptySession)
    monkeypatch.setattr(ml_router, "train_model", lambda _db: {"total_rows": 60})

    ml_router._run_training_job(job_id)

    job = ml_router._training_job_snapshot(job_id)
    assert job["status"] == "completed"
    assert job["result"] == {"total_rows": 60}


def test_browser_session_uses_short_lived_ticket_and_httponly_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:8501")
    monkeypatch.setattr(auth_router, "_BROWSER_SESSION_TICKETS", {})
    main.app.dependency_overrides[get_current_user] = lambda: {
        "user_id": 1,
        "username": "test",
    }
    try:
        client = TestClient(main.app)
        ticket_response = client.post(
            "/api/auth/browser-cookie-ticket",
            headers={"Authorization": "Bearer test-session-token"},
        )
        ticket = ticket_response.json()["ticket"]
        rejected_origin_response = client.post(
            "/api/auth/browser-session",
            json={"ticket": ticket},
            headers={"Origin": "http://untrusted.example"},
        )
        session_response = client.post(
            "/api/auth/browser-session",
            json={"ticket": ticket},
            headers={"Origin": "http://localhost:8501"},
        )
        replay_response = client.post(
            "/api/auth/browser-session",
            json={"ticket": ticket},
            headers={"Origin": "http://localhost:8501"},
        )
        clear_response = client.post(
            "/api/auth/browser-logout",
            headers={"Origin": "http://localhost:8501"},
        )
    finally:
        main.app.dependency_overrides.clear()

    assert ticket_response.status_code == 200
    assert rejected_origin_response.status_code == 403
    assert session_response.status_code == 200
    assert session_response.headers["access-control-allow-origin"] == "http://localhost:8501"
    cookie = session_response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert replay_response.status_code == 401
    assert clear_response.status_code == 204
