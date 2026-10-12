import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import insert, select, func, or_
from sqlalchemy.orm import Session

from app.database import BACKEND_DIR
from app.models import get_table
from app.schemas import PredictionRequest, to_database_datetime

MINIMUM_TRAINING_ROWS = 30
CONGESTION_LEVELS = {"low", "moderate", "high", "severe"}
FEATURES = {
    "travel_time": {
        "numeric": ["road_length_km", "speed_kmh", "vehicle_count", "hour", "day_of_week"],
        "categorical": ["segment_id", "congestion_level"],
    },
    "traffic_volume": {
        "numeric": ["road_length_km", "speed_kmh", "hour", "day_of_week"],
        "categorical": ["segment_id", "congestion_level"],
    },
    "congestion": {
        "numeric": ["road_length_km", "speed_kmh", "vehicle_count", "hour", "day_of_week"],
        "categorical": ["segment_id"],
    },
}


class InsufficientTrainingData(Exception):
    pass


def model_path() -> Path:
    configured = Path(os.getenv("MODEL_PATH", "artifacts/travel_time_model.joblib"))
    path = (BACKEND_DIR / configured).resolve() if not configured.is_absolute() else configured.resolve()
    if not path.is_relative_to(BACKEND_DIR.resolve()):
        raise ValueError("MODEL_PATH must resolve inside the Backend folder.")
    return path


def _feature_frame(rows: list[dict[str, Any]], feature_set: dict[str, list[str]]) -> pd.DataFrame:
    frame = pd.DataFrame.from_records(rows)
    recorded_at = pd.to_datetime(frame["recorded_at"], errors="coerce")
    frame["hour"] = recorded_at.dt.hour
    frame["day_of_week"] = recorded_at.dt.dayofweek
    frame["segment_id"] = frame["segment_id"].astype(str)
    frame["congestion_level"] = frame["congestion_level"].fillna("unknown").astype(str)
    for name in feature_set["numeric"]:
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    return frame[feature_set["numeric"] + feature_set["categorical"]]


def _training_frame(db: Session) -> pd.DataFrame:
    readings = get_table("traffic_readings")
    roads = get_table("road_segments")
    required = {"segment_id", "recorded_at", "speed_kmh", "vehicle_count", "travel_time_minutes", "congestion_level"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise ValueError(f"traffic_readings is missing model columns: {', '.join(sorted(missing))}.")
    if "segment_id" not in roads.c:
        raise ValueError("road_segments is missing segment_id.")

    selected = [
        readings.c.segment_id,
        readings.c.recorded_at,
        readings.c.speed_kmh,
        readings.c.vehicle_count,
        readings.c.congestion_level,
        readings.c.travel_time_minutes,
    ]
    if "length_km" in roads.c:
        selected.append(roads.c.length_km.label("road_length_km"))
    statement = select(*selected).select_from(
        readings.join(roads, readings.c.segment_id == roads.c.segment_id)
    ).order_by(readings.c.recorded_at.asc())
    frame = pd.DataFrame.from_records(db.execute(statement).mappings().all())
    if "road_length_km" not in frame:
        frame["road_length_km"] = np.nan
    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], errors="coerce")
    frame["travel_time_minutes"] = pd.to_numeric(frame["travel_time_minutes"], errors="coerce")
    return frame.dropna(subset=["recorded_at", "travel_time_minutes"])


def _pipeline(feature_set: dict[str, list[str]], classification: bool = False) -> Any:
    try:
        from sklearn.compose import ColumnTransformer
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        from sklearn.impute import SimpleImputer
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import OneHotEncoder
    except ImportError as exc:
        raise RuntimeError("scikit-learn is installed but its compiled dependencies cannot load in this environment.") from exc

    preprocessing = ColumnTransformer(
        transformers=[
            ("numeric", SimpleImputer(strategy="median"), feature_set["numeric"]),
            (
                "categorical",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="most_frequent")),
                    ("onehot", OneHotEncoder(handle_unknown="ignore")),
                ]),
                feature_set["categorical"],
            ),
        ],
        remainder="drop",
    )
    if classification:
        estimator = RandomForestClassifier(
            n_estimators=250,
            min_samples_leaf=2,
            class_weight="balanced_subsample",
            random_state=42,
            n_jobs=-1,
        )
    else:
        estimator = RandomForestRegressor(n_estimators=250, min_samples_leaf=2, random_state=42, n_jobs=-1)
    return Pipeline([
        ("preprocessing", preprocessing),
        ("estimator", estimator),
    ])


def train_model(db: Session) -> dict[str, Any]:
    frame = _training_frame(db)
    if len(frame) < MINIMUM_TRAINING_ROWS:
        raise InsufficientTrainingData(
            f"Training requires at least {MINIMUM_TRAINING_ROWS} valid historical readings; found {len(frame)}. Add more readings and try again."
        )
    split_at = int(len(frame) * 0.8)
    if split_at < 2 or len(frame) - split_at < 2:
        raise InsufficientTrainingData("Not enough chronological training and validation rows. Add more historical readings.")
    try:
        from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
    except ImportError as exc:
        raise RuntimeError("scikit-learn is installed but its compiled dependencies cannot load in this environment.") from exc

    rows = frame.to_dict(orient="records")
    models: dict[str, Any] = {}
    model_info: dict[str, Any] = {}

    for name, target_column, unit in (
        ("travel_time", "travel_time_minutes", "minutes"),
        ("traffic_volume", "vehicle_count", "vehicles per reading"),
    ):
        eligible = frame[target_column].notna()
        task_frame = frame.loc[eligible].reset_index(drop=True)
        if len(task_frame) < MINIMUM_TRAINING_ROWS:
            model_info[name] = {
                "available": False,
                "target": target_column,
                "eligible_rows": int(len(task_frame)),
                "detail": f"At least {MINIMUM_TRAINING_ROWS} valid rows are required; found {len(task_frame)}.",
            }
            continue
        task_split = int(len(task_frame) * 0.8)
        task_features = _feature_frame(task_frame.to_dict(orient="records"), FEATURES[name])
        target = pd.to_numeric(task_frame[target_column], errors="coerce")
        valid_target = target.notna()
        task_frame = task_frame.loc[valid_target].reset_index(drop=True)
        task_features = task_features.loc[valid_target].reset_index(drop=True)
        target = target.loc[valid_target].reset_index(drop=True).astype(float)
        task_split = int(len(task_frame) * 0.8)
        if len(task_frame) < MINIMUM_TRAINING_ROWS or task_split < 2 or len(task_frame) - task_split < 2:
            model_info[name] = {"available": False, "target": target_column, "eligible_rows": int(len(task_frame)), "detail": "Not enough chronological training and validation rows."}
            continue
        pipeline = _pipeline(FEATURES[name])
        pipeline.fit(task_features.iloc[:task_split], target.iloc[:task_split])
        predicted = pipeline.predict(task_features.iloc[task_split:])
        actual = target.iloc[task_split:].to_numpy()
        metrics: dict[str, float] = {
            "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        }
        if len(actual) >= 2 and np.unique(actual).size > 1:
            metrics["r2"] = float(r2_score(actual, predicted))
        pipeline.fit(task_features, target)
        models[name] = pipeline
        model_info[name] = {
            "available": True,
            "target": target_column,
            "unit": unit,
            "feature_names": FEATURES[name]["numeric"] + FEATURES[name]["categorical"],
            "training_rows": int(task_split),
            "validation_rows": int(len(task_frame) - task_split),
            "metrics": metrics,
        }

    class_counts = frame["congestion_level"].dropna().astype(str).value_counts()
    congestion_detail = ""
    classifier_frame = frame.loc[frame["congestion_level"].notna()].reset_index(drop=True)
    if len(classifier_frame) < MINIMUM_TRAINING_ROWS:
        congestion_detail = f"At least {MINIMUM_TRAINING_ROWS} classified readings are required; found {len(classifier_frame)}."
    elif len(class_counts) < 2 or class_counts.min() < 2:
        congestion_detail = "At least two congestion levels with multiple historical examples are required."
    else:
        class_split = int(len(classifier_frame) * 0.8)
        class_features = _feature_frame(classifier_frame.to_dict(orient="records"), FEATURES["congestion"])
        class_target = classifier_frame["congestion_level"].astype(str)
        train_classes = set(class_target.iloc[:class_split])
        validation_classes = set(class_target.iloc[class_split:])
        if len(train_classes) < 2 or len(validation_classes) < 2:
            congestion_detail = "The chronological training and validation windows must each contain at least two congestion levels."
        elif not validation_classes.issubset(train_classes):
            congestion_detail = "The validation window contains a congestion level absent from training; add more examples for each level."
        else:
            try:
                classifier = _pipeline(FEATURES["congestion"], classification=True)
                classifier.fit(class_features.iloc[:class_split], class_target.iloc[:class_split])
                predicted_classes = classifier.predict(class_features.iloc[class_split:])
                actual_classes = class_target.iloc[class_split:]
                class_metrics = {
                    "accuracy": float(accuracy_score(actual_classes, predicted_classes)),
                    "f1_weighted": float(f1_score(actual_classes, predicted_classes, average="weighted", zero_division=0)),
                }
                classifier.fit(class_features, class_target)
                models["congestion"] = classifier
                model_info["congestion"] = {
                    "available": True,
                    "target": "congestion_level",
                    "unit": "classification",
                    "classes": sorted(train_classes),
                    "feature_names": FEATURES["congestion"]["numeric"] + FEATURES["congestion"]["categorical"],
                    "training_rows": int(class_split),
                    "validation_rows": int(len(classifier_frame) - class_split),
                    "metrics": class_metrics,
                }
            except ImportError as exc:
                raise RuntimeError("scikit-learn is installed but its compiled dependencies cannot load in this environment.") from exc
    if "congestion" not in model_info:
        model_info["congestion"] = {
            "available": False,
            "target": "congestion_level",
            "eligible_rows": int(len(classifier_frame)),
            "detail": congestion_detail or "Congestion classification could not be evaluated reliably.",
        }

    if not models:
        raise InsufficientTrainingData("There is not enough valid history to train any requested output model.")
    training_rows = int(split_at)
    metadata = {
        "model_name": "RandomForest multi-output service",
        "models": model_info,
        "training_rows": training_rows,
        "validation_rows": int(len(frame) - split_at),
        "total_rows": int(len(frame)),
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "weather_used": False,
    }
    travel_info = model_info.get("travel_time", {})
    metadata["metrics"] = travel_info.get("metrics", {})
    artifact_path = model_path()
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=artifact_path.parent, suffix=".tmp", delete=False) as temp_file:
            temp_path = temp_file.name
        joblib.dump({"models": models, "metadata": metadata}, temp_path)
        os.replace(temp_path, artifact_path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    return metadata


def model_status(db: Session) -> dict[str, Any]:
    path = model_path()
    readings = get_table("traffic_readings")
    required = {"travel_time_minutes", "vehicle_count", "congestion_level"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise ValueError(f"traffic_readings is missing model columns: {', '.join(sorted(missing))}.")
    total_rows = int(db.scalar(select(func.count()).select_from(readings)) or 0)
    rows_by_target = {
        "travel_time": int(db.scalar(select(func.count(readings.c.travel_time_minutes))) or 0),
        "traffic_volume": int(db.scalar(select(func.count(readings.c.vehicle_count))) or 0),
        "congestion": int(db.scalar(select(func.count(readings.c.congestion_level))) or 0),
    }
    readiness: dict[str, Any] = {}
    for name, rows in rows_by_target.items():
        readiness[name] = {
            "available": False,
            "eligible_rows": rows,
            "detail": f"At least {MINIMUM_TRAINING_ROWS} valid historical rows are required; found {rows}.",
        }
    levels = db.execute(
        select(readings.c.congestion_level, func.count().label("class_count"))
        .where(readings.c.congestion_level.is_not(None))
        .group_by(readings.c.congestion_level)
    ).all()
    if rows_by_target["congestion"] >= MINIMUM_TRAINING_ROWS:
        if len(levels) < 2 or min(int(row.class_count) for row in levels) < 2:
            readiness["congestion"]["detail"] = "At least two congestion levels with multiple examples are required."
        else:
            readiness["congestion"]["detail"] = "Ready for chronological classification validation."
    if not path.is_file():
        return {
            "available": False,
            "detail": "No trained model artifact is available.",
            "total_rows": total_rows,
            "minimum_training_rows": MINIMUM_TRAINING_ROWS,
            "eligible_rows": rows_by_target,
            "models": readiness,
        }
    try:
        artifact = joblib.load(path)
    except (OSError, ValueError, EOFError, ImportError):
        return {
            "available": False,
            "detail": "The saved model could not be loaded. Retrain the model.",
            "total_rows": total_rows,
            "minimum_training_rows": MINIMUM_TRAINING_ROWS,
            "eligible_rows": rows_by_target,
            "models": readiness,
        }
    metadata = artifact.get("metadata", {})
    fitted_models = artifact.get("models", {})
    for name, model_info in metadata.get("models", {}).items():
        if name in fitted_models:
            readiness[name] = model_info
    return {
        "available": bool(fitted_models),
        "detail": "One or more trained models are available." if fitted_models else "No trained prediction models are available.",
        "total_rows": total_rows,
        "minimum_training_rows": MINIMUM_TRAINING_ROWS,
        "eligible_rows": rows_by_target,
        **metadata,
        "models": readiness,
    }


def predict_travel_time(db: Session, request: PredictionRequest) -> dict[str, Any]:
    artifact_path = model_path()
    if not artifact_path.is_file():
        raise InsufficientTrainingData("No trained model is available. Train a model from historical readings first.")
    try:
        artifact = joblib.load(artifact_path)
    except (OSError, ValueError, EOFError, ImportError) as exc:
        raise RuntimeError("The saved model could not be loaded. Retrain it after the model runtime is available.") from exc
    models = artifact.get("models", {})
    roads = get_table("road_segments")
    if "segment_id" not in roads.c:
        raise ValueError("road_segments is missing segment_id.")
    road = db.execute(select(roads).where(roads.c.segment_id == request.segment_id)).mappings().first()
    if road is None:
        raise LookupError("Road segment not found.")
    timestamp = to_database_datetime(request.predicted_for)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if timestamp <= now:
        raise ValueError("predicted_for must be a future date and time.")
    readings = get_table("traffic_readings")
    reading_columns = [name for name in ("recorded_at", "speed_kmh", "vehicle_count", "congestion_level") if name in readings.c]
    if "segment_id" not in readings.c or "recorded_at" not in reading_columns:
        raise ValueError("traffic_readings is missing required prediction-input columns.")
    recent = db.execute(
        select(*(readings.c[name] for name in reading_columns))
        .where(readings.c.segment_id == request.segment_id)
        .where(readings.c.recorded_at <= now)
        .order_by(readings.c.recorded_at.desc())
        .limit(10)
    ).mappings().all()
    if not recent:
        raise InsufficientTrainingData("No historical readings exist for this road segment. Add readings before predicting.")
    recent_frame = pd.DataFrame.from_records([dict(row) for row in recent])
    average_speed = pd.to_numeric(recent_frame.get("speed_kmh"), errors="coerce").mean() if "speed_kmh" in recent_frame else np.nan
    average_vehicles = pd.to_numeric(recent_frame.get("vehicle_count"), errors="coerce").mean() if "vehicle_count" in recent_frame else np.nan
    congestion_values = recent_frame.get("congestion_level", pd.Series(dtype=object)).dropna().astype(str)
    historical_congestion = congestion_values.mode().iloc[0] if not congestion_values.empty else None
    speed_value = request.speed_kmh if request.speed_kmh is not None else average_speed
    vehicles_value = request.vehicle_count if request.vehicle_count is not None else average_vehicles
    congestion_value = request.current_congestion_level or historical_congestion
    if pd.isna(speed_value):
        speed_value = np.nan
    if pd.isna(vehicles_value):
        vehicles_value = np.nan

    row = {
        "segment_id": request.segment_id,
        "road_length_km": road.get("length_km") if "length_km" in road else np.nan,
        "speed_kmh": speed_value,
        "vehicle_count": vehicles_value,
        "hour": timestamp.hour,
        "day_of_week": timestamp.weekday(),
        "congestion_level": congestion_value or "unknown",
        "recorded_at": timestamp,
    }
    outputs: dict[str, Any] = {
        "predicted_travel_time_minutes": None,
        "predicted_vehicle_count": None,
        "predicted_congestion_level": None,
        "average_speed_kmh": None,
    }
    unavailable: dict[str, str] = {}
    for name, output_key, target_feature in (
        ("travel_time", "predicted_travel_time_minutes", FEATURES["travel_time"]),
        ("traffic_volume", "predicted_vehicle_count", FEATURES["traffic_volume"]),
        ("congestion", "predicted_congestion_level", FEATURES["congestion"]),
    ):
        pipeline = models.get(name)
        if pipeline is None:
            unavailable[name] = artifact.get("metadata", {}).get("models", {}).get(name, {}).get("detail", "This model is not trained.")
            continue
        model_features = _feature_frame([row], target_feature)
        predicted = pipeline.predict(model_features)[0]
        if name == "congestion":
            if str(predicted) not in CONGESTION_LEVELS:
                unavailable[name] = "The classifier returned an unsupported congestion class."
                continue
            outputs[output_key] = str(predicted)
        else:
            value = float(predicted)
            if not np.isfinite(value) or value < 0:
                unavailable[name] = "The model output was not a valid nonnegative estimate."
                continue
            outputs[output_key] = value
    travel_minutes = outputs["predicted_travel_time_minutes"]
    length = road.get("length_km") if "length_km" in road else None
    if travel_minutes and length and float(length) > 0:
        outputs["average_speed_kmh"] = float(length) * 60 / travel_minutes
    if all(value is None for value in outputs.values()):
        raise InsufficientTrainingData("No trained model can produce a prediction. Train with sufficient historical readings first.")

    incidents = get_table("incidents")
    active_incidents: list[dict[str, Any]] = []
    if {"segment_id", "start_time", "end_time"}.issubset(incidents.c.keys()):
        active_statement = select(incidents).where(incidents.c.segment_id == request.segment_id)
        active_statement = active_statement.where(incidents.c.start_time <= now).where(
            or_(incidents.c.end_time.is_(None), incidents.c.end_time >= now)
        )
        active_incidents = [dict(item) for item in db.execute(active_statement).mappings().all()]

    weather_table = get_table("weather_data")
    weather: dict[str, Any] | None = None
    if "recorded_at" in weather_table.c:
        weather_row = db.execute(select(weather_table).order_by(weather_table.c.recorded_at.desc()).limit(1)).mappings().first()
        weather = dict(weather_row) if weather_row else None
    return {
        "segment_id": request.segment_id,
        "segment_name": road.get("name"),
        "predicted_for": timestamp,
        **outputs,
        "model_inputs": {
            "speed_kmh": None if pd.isna(speed_value) else float(speed_value),
            "speed_source": "request override" if request.speed_kmh is not None else "mean of up to 10 latest stored readings",
            "vehicle_count": None if pd.isna(vehicles_value) else float(vehicles_value),
            "vehicle_count_source": "request override" if request.vehicle_count is not None else "mean of up to 10 latest stored readings",
            "congestion_level": congestion_value,
            "congestion_source": "request override" if request.current_congestion_level else "most common of up to 10 latest stored readings",
            "road_length_km": None if length is None else float(length),
            "prediction_hour": timestamp.hour,
            "prediction_day_of_week": timestamp.strftime("%A"),
            "historical_readings_used": len(recent),
            "feature_names": artifact.get("metadata", {}).get("models", {}),
        },
        "unavailable_outputs": unavailable,
        "context": {
            "active_incidents": active_incidents,
            "weather": weather,
            "weather_is_road_specific": False,
        },
        "model": artifact["metadata"],
    }


def save_prediction(db: Session, request: PredictionRequest, prediction: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    table = get_table("traffic_predictions")
    values: dict[str, Any] = {
        "segment_id": request.segment_id,
        "predicted_for": to_database_datetime(request.predicted_for),
        "predicted_travel_time_minutes": prediction.get("predicted_travel_time_minutes"),
    }
    if prediction.get("average_speed_kmh") is not None:
        values["predicted_speed_kmh"] = prediction["average_speed_kmh"]
    if prediction.get("predicted_congestion_level") is not None:
        values["predicted_congestion_level"] = prediction["predicted_congestion_level"]
    unsupported = ["predicted_vehicle_count"] if prediction.get("predicted_vehicle_count") is not None and "predicted_vehicle_count" not in table.c else []
    values = {name: value for name, value in values.items() if name in table.c and value is not None}
    if not any(name in values for name in ("predicted_travel_time_minutes", "predicted_speed_kmh", "predicted_congestion_level")):
        return None, [], unsupported
    result = db.execute(insert(table).values(**values))
    db.commit()
    if "prediction_id" in table.c and result.inserted_primary_key:
        row = db.execute(select(table).where(table.c.prediction_id == result.inserted_primary_key[0])).mappings().first()
        if row:
                return dict(row), list(values), unsupported
        return values, list(values), unsupported