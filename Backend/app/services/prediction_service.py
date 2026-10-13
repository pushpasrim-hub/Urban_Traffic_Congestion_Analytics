import os
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import insert, select, or_
from sqlalchemy.orm import Session

from app.database import BACKEND_DIR
from app.models import get_table
from app.schemas import PredictionRequest, to_database_datetime

MINIMUM_TRAINING_ROWS = 30
FEATURES = {
    "travel_time": {
        "numeric": ["road_length_km", "lag_speed_kmh", "lag_vehicle_count", "hour", "day_of_week"],
        "categorical": ["segment_id", "lag_congestion_level"],
    },
    "traffic_volume": {
        "numeric": ["road_length_km", "lag_speed_kmh", "lag_vehicle_count", "hour", "day_of_week"],
        "categorical": ["segment_id", "lag_congestion_level"],
    },
    "congestion": {
        "numeric": ["road_length_km", "lag_speed_kmh", "lag_vehicle_count", "hour", "day_of_week"],
        "categorical": ["segment_id", "lag_congestion_level"],
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
    if "recorded_at" in frame:
        recorded_at = pd.to_datetime(frame["recorded_at"], errors="coerce")
        frame["hour"] = recorded_at.dt.hour
        frame["day_of_week"] = recorded_at.dt.dayofweek
    frame["segment_id"] = frame["segment_id"].astype(str)
    if "lag_congestion_level" in frame:
        frame["lag_congestion_level"] = frame["lag_congestion_level"].astype(object).where(
            frame["lag_congestion_level"].notna(), np.nan
        )
        frame["lag_congestion_level"] = frame["lag_congestion_level"].map(
            lambda value: str(value).strip().lower()
            if pd.notna(value) and str(value).strip()
            else np.nan
        )
    for name in feature_set["numeric"]:
        if name not in frame:
            frame[name] = np.nan
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
        frame.loc[(frame[name] < 0) | ~np.isfinite(frame[name]), name] = np.nan
    return frame[feature_set["numeric"] + feature_set["categorical"]]


def _training_frame(db: Session) -> pd.DataFrame:
    readings = get_table("traffic_readings")
    roads = get_table("road_segments")
    required = {"segment_id", "recorded_at"}
    missing = required.difference(readings.c.keys())
    if missing:
        raise ValueError(f"traffic_readings is missing required model columns: {', '.join(sorted(missing))}.")
    if "segment_id" not in roads.c:
        raise ValueError("road_segments is missing segment_id.")

    selected = [readings.c.segment_id, readings.c.recorded_at]
    for name in ("reading_id", "speed_kmh", "vehicle_count", "congestion_level", "travel_time_minutes"):
        if name in readings.c:
            selected.append(readings.c[name])
    if "length_km" in roads.c:
        selected.append(roads.c.length_km.label("road_length_km"))
    statement = select(*selected).select_from(
        readings.join(roads, readings.c.segment_id == roads.c.segment_id)
    ).order_by(readings.c.recorded_at.asc(), readings.c.segment_id.asc())
    selected_rows = db.execute(statement).mappings().all()
    frame = pd.DataFrame.from_records(selected_rows, columns=[column.key for column in selected])
    schema = {
        table.name: {column.name: str(column.type) for column in table.columns}
        for table in (readings, roads)
    }
    diagnostics: dict[str, Any] = {
        "loaded_rows": int(len(frame)),
        "duplicate_rows_removed": 0,
        "invalid_timestamps_removed": 0,
        "missing_segment_ids_removed": 0,
        "negative_measurements_replaced_with_missing": 0,
        "invalid_numeric_values_by_column": {},
        "schema": schema,
    }
    if "road_length_km" not in frame:
        frame["road_length_km"] = np.nan
    for name in ("speed_kmh", "vehicle_count", "travel_time_minutes", "road_length_km"):
        if name not in frame:
            frame[name] = np.nan
        source_values = frame[name]
        values = pd.to_numeric(frame[name], errors="coerce")
        diagnostics["invalid_numeric_values_by_column"][name] = int(
            (source_values.notna() & (values.isna() | ~np.isfinite(values))).sum()
        )
        diagnostics["negative_measurements_replaced_with_missing"] += int((values < 0).sum())
        frame[name] = values.mask((values < 0) | ~np.isfinite(values))
    if "congestion_level" not in frame:
        frame["congestion_level"] = None
    frame["congestion_level"] = frame["congestion_level"].map(
        lambda value: str(value).strip().lower() if pd.notna(value) and str(value).strip() else None
    )
    frame["recorded_at"] = pd.to_datetime(frame["recorded_at"], errors="coerce")
    diagnostics["invalid_timestamps_removed"] = int(frame["recorded_at"].isna().sum())
    diagnostics["missing_segment_ids_removed"] = int(frame["segment_id"].isna().sum())
    frame = frame.dropna(subset=["recorded_at", "segment_id"])
    duplicate_subset = [name for name in frame.columns if name != "reading_id"]
    frame = frame.drop_duplicates(subset=duplicate_subset, keep="first").copy()
    diagnostics["duplicate_rows_removed"] = (
        diagnostics["loaded_rows"]
        - diagnostics["invalid_timestamps_removed"]
        - diagnostics["missing_segment_ids_removed"]
        - int(len(frame))
    )
    frame = frame.sort_values(["recorded_at", "segment_id"], kind="stable").reset_index(drop=True)
    frame["segment_id"] = frame["segment_id"].astype(str)
    frame["hour"] = frame["recorded_at"].dt.hour
    frame["day_of_week"] = frame["recorded_at"].dt.dayofweek

    frame["lag_speed_kmh"] = np.nan
    frame["lag_vehicle_count"] = np.nan
    frame["lag_congestion_level"] = None
    for _, group in frame.groupby("segment_id", sort=False):
        speed_history: deque[float] = deque(maxlen=10)
        volume_history: deque[float] = deque(maxlen=10)
        label_history: deque[str] = deque(maxlen=10)
        for _, same_time in group.groupby("recorded_at", sort=True):
            indices = same_time.index
            frame.loc[indices, "lag_speed_kmh"] = (
                float(np.mean(speed_history)) if speed_history else np.nan
            )
            frame.loc[indices, "lag_vehicle_count"] = (
                float(np.mean(volume_history)) if volume_history else np.nan
            )
            frame.loc[indices, "lag_congestion_level"] = (
                pd.Series(list(label_history), dtype="object").mode().iloc[0]
                if label_history
                else None
            )
            for row in same_time.itertuples(index=False):
                speed = getattr(row, "speed_kmh")
                volume = getattr(row, "vehicle_count")
                label = getattr(row, "congestion_level")
                if pd.notna(speed):
                    speed_history.append(float(speed))
                if pd.notna(volume):
                    volume_history.append(float(volume))
                if label:
                    label_history.append(str(label))
    diagnostics["missing_values_by_column"] = {
        name: int(frame[name].isna().sum())
        for name in (
            "recorded_at",
            "segment_id",
            "road_length_km",
            "speed_kmh",
            "vehicle_count",
            "travel_time_minutes",
            "congestion_level",
            "lag_speed_kmh",
            "lag_vehicle_count",
            "lag_congestion_level",
        )
    }
    diagnostics["eligible_rows_by_target"] = {
        "travel_time": int(
            (
                pd.to_numeric(frame["travel_time_minutes"], errors="coerce").ge(0)
                & np.isfinite(pd.to_numeric(frame["travel_time_minutes"], errors="coerce"))
            ).sum()
        ),
        "traffic_volume": int(
            (
                pd.to_numeric(frame["vehicle_count"], errors="coerce").ge(0)
                & np.isfinite(pd.to_numeric(frame["vehicle_count"], errors="coerce"))
            ).sum()
        ),
        "congestion": int(frame["congestion_level"].notna().sum()),
    }
    diagnostics["congestion_label_counts"] = {
        str(label): int(count)
        for label, count in frame["congestion_level"].value_counts().items()
    }
    frame.attrs["preprocessing"] = diagnostics
    return frame


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
            ("numeric", SimpleImputer(strategy="median", keep_empty_features=True), feature_set["numeric"]),
            (
                "categorical",
                Pipeline([
                    ("imputer", SimpleImputer(strategy="constant", fill_value="missing")),
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
        from sklearn.dummy import DummyClassifier, DummyRegressor
        from sklearn.metrics import (
            accuracy_score,
            confusion_matrix,
            f1_score,
            mean_absolute_error,
            mean_squared_error,
            precision_score,
            r2_score,
            recall_score,
        )
    except ImportError as exc:
        raise RuntimeError("scikit-learn is installed but its compiled dependencies cannot load in this environment.") from exc

    models: dict[str, Any] = {}
    model_info: dict[str, Any] = {}

    for name, target_column, unit, available_column in (
        ("travel_time", "travel_time_minutes", "minutes", "travel_time_minutes"),
        ("traffic_volume", "vehicle_count", "vehicles per reading", "vehicle_count"),
    ):
        target_values = pd.to_numeric(frame[target_column], errors="coerce")
        eligible = target_values.ge(0) & np.isfinite(target_values)
        task_frame = frame.loc[eligible].reset_index(drop=True)
        if len(task_frame) < MINIMUM_TRAINING_ROWS:
            model_info[name] = {
                "available": False,
                "target": target_column,
                "eligible_rows": int(len(task_frame)),
                "detail": (
                    f"The traffic_readings table has no {available_column} column."
                    if available_column not in frame.attrs.get("preprocessing", {}).get("schema", {}).get("traffic_readings", {})
                    else f"At least {MINIMUM_TRAINING_ROWS} valid rows are required; found {len(task_frame)}."
                ),
            }
            continue
        task_features = _feature_frame(task_frame.to_dict(orient="records"), FEATURES[name])
        target = pd.to_numeric(task_frame[target_column], errors="coerce").reset_index(drop=True).astype(float)
        task_split = int(len(task_frame) * 0.8)
        if len(task_frame) < MINIMUM_TRAINING_ROWS or task_split < 2 or len(task_frame) - task_split < 2:
            model_info[name] = {"available": False, "target": target_column, "eligible_rows": int(len(task_frame)), "detail": "Not enough chronological training and validation rows."}
            continue
        pipeline = _pipeline(FEATURES[name])
        pipeline.fit(task_features.iloc[:task_split], target.iloc[:task_split])
        predicted = pipeline.predict(task_features.iloc[task_split:])
        actual = target.iloc[task_split:].to_numpy()
        baseline = DummyRegressor(strategy="mean")
        baseline.fit(task_features.iloc[:task_split], target.iloc[:task_split])
        baseline_predicted = baseline.predict(task_features.iloc[task_split:])
        metrics: dict[str, float] = {
            "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
        }
        metrics["baseline_mae"] = float(mean_absolute_error(actual, baseline_predicted))
        metrics["baseline_rmse"] = float(np.sqrt(mean_squared_error(actual, baseline_predicted)))
        if len(actual) >= 2 and np.unique(actual).size > 1:
            metrics["r2"] = float(r2_score(actual, predicted))
            metrics["baseline_r2"] = float(r2_score(actual, baseline_predicted))
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
            "baseline": {"name": "DummyRegressor(mean)", "metrics": {
                "mae": metrics["baseline_mae"],
                "rmse": metrics["baseline_rmse"],
                **({"r2": metrics["baseline_r2"]} if "baseline_r2" in metrics else {}),
            }},
        }

    classifier_frame = frame.loc[frame["congestion_level"].notna()].reset_index(drop=True)
    class_target = classifier_frame["congestion_level"].astype(str).reset_index(drop=True)
    class_counts = class_target.value_counts()
    congestion_detail = ""
    if len(classifier_frame) < MINIMUM_TRAINING_ROWS:
        congestion_detail = f"At least {MINIMUM_TRAINING_ROWS} classified readings are required; found {len(classifier_frame)}."
    elif len(class_counts) < 2:
        congestion_detail = "At least two distinct congestion labels are required in the historical readings."
    else:
        class_split = int(len(classifier_frame) * 0.8)
        class_features = _feature_frame(classifier_frame.to_dict(orient="records"), FEATURES["congestion"])
        train_classes = sorted(set(class_target.iloc[:class_split]))
        validation_classes = sorted(set(class_target.iloc[class_split:]))
        classifier = _pipeline(FEATURES["congestion"], classification=True)
        classifier.fit(class_features.iloc[:class_split], class_target.iloc[:class_split])
        predicted_classes = classifier.predict(class_features.iloc[class_split:])
        actual_classes = class_target.iloc[class_split:]
        evaluation_labels = sorted(set(actual_classes) | set(predicted_classes) | set(train_classes))
        class_metrics = {
            "accuracy": float(accuracy_score(actual_classes, predicted_classes)),
            "precision_weighted": float(precision_score(actual_classes, predicted_classes, labels=evaluation_labels, average="weighted", zero_division=0)),
            "recall_weighted": float(recall_score(actual_classes, predicted_classes, labels=evaluation_labels, average="weighted", zero_division=0)),
            "f1_weighted": float(f1_score(actual_classes, predicted_classes, labels=evaluation_labels, average="weighted", zero_division=0)),
            "confusion_matrix": confusion_matrix(actual_classes, predicted_classes, labels=evaluation_labels).tolist(),
            "confusion_matrix_labels": evaluation_labels,
        }
        baseline = DummyClassifier(strategy="most_frequent")
        baseline.fit(class_features.iloc[:class_split], class_target.iloc[:class_split])
        baseline_predicted = baseline.predict(class_features.iloc[class_split:])
        class_metrics["baseline_accuracy"] = float(accuracy_score(actual_classes, baseline_predicted))
        class_metrics["baseline_precision_weighted"] = float(precision_score(actual_classes, baseline_predicted, labels=evaluation_labels, average="weighted", zero_division=0))
        class_metrics["baseline_recall_weighted"] = float(recall_score(actual_classes, baseline_predicted, labels=evaluation_labels, average="weighted", zero_division=0))
        class_metrics["baseline_f1_weighted"] = float(f1_score(actual_classes, baseline_predicted, labels=evaluation_labels, average="weighted", zero_division=0))
        classifier.fit(class_features, class_target)
        models["congestion"] = classifier
        model_info["congestion"] = {
            "available": True,
            "target": "congestion_level",
            "unit": "classification",
            "classes": sorted(set(class_target)),
            "feature_names": FEATURES["congestion"]["numeric"] + FEATURES["congestion"]["categorical"],
            "training_rows": int(class_split),
            "validation_rows": int(len(classifier_frame) - class_split),
            "metrics": class_metrics,
            "baseline": {
                "name": "DummyClassifier(most_frequent)",
                "metrics": {
                    "accuracy": class_metrics["baseline_accuracy"],
                    "precision_weighted": class_metrics["baseline_precision_weighted"],
                    "recall_weighted": class_metrics["baseline_recall_weighted"],
                    "f1_weighted": class_metrics["baseline_f1_weighted"],
                },
            },
            "validation_labels_not_seen_in_training": sorted(set(validation_classes) - set(train_classes)),
        }
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
        "preprocessing": frame.attrs.get("preprocessing", {}),
        "limitations": [
            "Validation uses a chronological holdout; results depend on the historical period and data quality.",
            "Lagged traffic inputs use up to ten earlier readings for the same road segment; no current-row target is used as a feature.",
            "Weather is not a model feature because the existing schema has no defensible road-to-weather mapping.",
            "Predictions are estimates from stored historical observations, not real-time sensor feeds.",
        ],
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
    frame = _training_frame(db)
    schema = frame.attrs.get("preprocessing", {}).get("schema", {})
    rows_by_target = {
        "travel_time": int(
            (
                pd.to_numeric(frame["travel_time_minutes"], errors="coerce").ge(0)
                & np.isfinite(pd.to_numeric(frame["travel_time_minutes"], errors="coerce"))
            ).sum()
        ),
        "traffic_volume": int(
            (
                pd.to_numeric(frame["vehicle_count"], errors="coerce").ge(0)
                & np.isfinite(pd.to_numeric(frame["vehicle_count"], errors="coerce"))
            ).sum()
        ),
        "congestion": int(frame["congestion_level"].notna().sum()),
    }
    readiness: dict[str, Any] = {}
    for name, rows in rows_by_target.items():
        target_column = {
            "travel_time": "travel_time_minutes",
            "traffic_volume": "vehicle_count",
            "congestion": "congestion_level",
        }[name]
        target_exists = target_column in schema.get("traffic_readings", {})
        readiness[name] = {
            "available": False,
            "eligible_rows": rows,
            "detail": (
                "The existing traffic_readings table does not contain this target column."
                if not target_exists
                else f"At least {MINIMUM_TRAINING_ROWS} valid historical rows are required; found {rows}."
            ),
        }
    class_counts = frame["congestion_level"].dropna().value_counts()
    if rows_by_target["congestion"] >= MINIMUM_TRAINING_ROWS and len(class_counts) < 2:
        readiness["congestion"]["detail"] = "At least two distinct congestion labels are required in the historical readings."
    elif rows_by_target["congestion"] >= MINIMUM_TRAINING_ROWS:
        readiness["congestion"]["detail"] = "Ready for chronological classification validation."
    if not path.is_file():
        return {
            "available": False,
            "detail": "No trained model artifact is available.",
            "total_rows": int(len(frame)),
            "minimum_training_rows": MINIMUM_TRAINING_ROWS,
            "eligible_rows": rows_by_target,
            "models": readiness,
        }
    try:
        artifact = joblib.load(path)
    except (OSError, ValueError, EOFError, ImportError, AttributeError, KeyError, TypeError):
        return {
            "available": False,
            "detail": "The saved model could not be loaded. Retrain the model.",
            "total_rows": int(len(frame)),
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
        "total_rows": int(len(frame)),
        "minimum_training_rows": MINIMUM_TRAINING_ROWS,
        "eligible_rows": rows_by_target,
        **metadata,
        "models": readiness,
    }


def _load_artifact() -> dict[str, Any]:
    artifact_path = model_path()
    if not artifact_path.is_file():
        raise InsufficientTrainingData("No trained model is available. Train a model from historical readings first.")
    try:
        artifact = joblib.load(artifact_path)
    except (OSError, ValueError, EOFError, ImportError, AttributeError, KeyError, TypeError) as exc:
        raise RuntimeError("The saved model could not be loaded. Retrain it after the model runtime is available.") from exc
    if not isinstance(artifact, dict) or not isinstance(artifact.get("models"), dict):
        raise RuntimeError("The saved model artifact has an unsupported format. Retrain the model.")
    return artifact


def predict_travel_time(
    db: Session,
    request: PredictionRequest,
    *,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact = artifact or _load_artifact()
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
        "lag_speed_kmh": speed_value,
        "lag_vehicle_count": vehicles_value,
        "lag_congestion_level": congestion_value,
        "hour": timestamp.hour,
        "day_of_week": timestamp.weekday(),
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
            trained_classes = {str(label) for label in getattr(pipeline, "classes_", [])}
            if str(predicted) not in trained_classes:
                unavailable[name] = "The classifier returned a label outside the trained class set."
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
            "weather_condition": request.weather_condition,
            "rainfall_mm": request.rainfall_mm,
            "weather_used": False,
            "weather_limitation": "Weather is not a trained feature and weather records have no road-segment mapping.",
            "road_length_km": None if length is None else float(length),
            "prediction_hour": timestamp.hour,
            "prediction_day_of_week": timestamp.strftime("%A"),
            "historical_readings_used": len(recent),
            "feature_names": {
                name: item.get("feature_names", [])
                for name, item in artifact.get("metadata", {}).get("models", {}).items()
            },
        },
        "unavailable_outputs": unavailable,
        "context": {
            "active_incidents": active_incidents,
            "weather": weather,
            "weather_is_road_specific": False,
        },
        "model": artifact["metadata"],
    }


def what_if_scenarios(db: Session, request: PredictionRequest) -> dict[str, Any]:
    artifact = _load_artifact()
    baseline = predict_travel_time(db, request, artifact=artifact)
    model_info = artifact.get("metadata", {}).get("models", {})
    volume_features_used = any(
        "lag_vehicle_count" in item.get("feature_names", [])
        for item in model_info.values()
        if item.get("available")
    )
    volume_value = baseline.get("model_inputs", {}).get("vehicle_count")
    scenarios: list[dict[str, Any]] = []
    if volume_features_used and volume_value is not None and np.isfinite(float(volume_value)):
        increased_request = request.model_copy(
            update={"vehicle_count": float(volume_value) * 1.2, "save": False}
        )
        increased = predict_travel_time(db, increased_request, artifact=artifact)
        comparisons: dict[str, Any] = {}
        for key in (
            "predicted_travel_time_minutes",
            "predicted_vehicle_count",
            "predicted_congestion_level",
        ):
            base_value = baseline.get(key)
            scenario_value = increased.get(key)
            comparisons[key] = {
                "baseline": base_value,
                "scenario": scenario_value,
                "difference": (
                    float(scenario_value) - float(base_value)
                    if isinstance(base_value, (int, float))
                    and isinstance(scenario_value, (int, float))
                    else None
                ),
            }
        scenarios.append({
            "name": "traffic_volume_increased_20_percent",
            "supported": True,
            "hypothetical": True,
            "input_vehicle_count": float(volume_value) * 1.2,
            "predictions": comparisons,
        })
    else:
        scenarios.append({
            "name": "traffic_volume_increased_20_percent",
            "supported": False,
            "hypothetical": True,
            "detail": "The trained model does not use traffic volume as an input, or a valid baseline volume is unavailable.",
        })

    rainy_features_used = any(
        any(token in feature.lower() for token in ("rain", "weather", "precipitation"))
        for item in model_info.values()
        for feature in item.get("feature_names", [])
    )
    scenarios.append({
        "name": "rainy_weather",
        "supported": False,
        "hypothetical": True,
        "detail": (
            "The artifact lists a weather feature, but no road-specific rainy-weather value can be supplied safely."
            if rainy_features_used
            else "Weather is not used by the trained model; weather_data has no road-segment mapping in the existing schema."
        ),
    })
    return {
        "hypothetical": True,
        "interpretation": "These are model-based hypothetical comparisons, not proven causal effects.",
        "baseline": baseline,
        "scenarios": scenarios,
        "model": artifact.get("metadata", {}),
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