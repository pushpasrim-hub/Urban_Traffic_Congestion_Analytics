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
from app.routers import ml as ml_router
from app.schemas import PredictionRequest, WhatIfRequest
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


def test_prediction_and_hypothetical_scenarios_use_trained_pipeline(
    database: Session,
    model_file: Path,
) -> None:
    service.train_model(database)
    request = PredictionRequest(
        segment_id=1,
        predicted_for=datetime.now() + timedelta(days=1),
        save=False,
    )

    prediction = service.predict_travel_time(database, request)
    comparison = service.what_if_scenarios(database, WhatIfRequest(
        segment_id=1,
        predicted_for=request.predicted_for,
    ))

    assert prediction["predicted_travel_time_minutes"] >= 0
    assert prediction["predicted_vehicle_count"] >= 0
    assert prediction["predicted_congestion_level"] in {"low", "moderate", "high"}
    assert comparison["hypothetical"] is True
    assert comparison["scenarios"][0]["supported"] is True
    assert comparison["scenarios"][0]["input_vehicle_count"] == pytest.approx(
        comparison["baseline"]["model_inputs"]["vehicle_count"] * 1.2
    )
    assert comparison["scenarios"][1]["supported"] is False
    assert "no road-segment mapping" in comparison["scenarios"][1]["detail"]


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
        good_response = client.post("/api/ml/what-if", json={
            "segment_id": 1,
            "predicted_for": (datetime.now() + timedelta(days=1)).isoformat(),
        })
    finally:
        main.app.dependency_overrides.clear()

    assert bad_response.status_code == 422
    assert good_response.status_code == 200
    assert good_response.json()["hypothetical"] is True
    assert good_response.json()["scenarios"][0]["supported"] is False
