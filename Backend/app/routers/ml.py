import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic, time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.schemas import PredictionRequest, WhatIfRequest
from app.security import get_current_user
from app.services.prediction_service import (
    InsufficientTrainingData,
    model_status,
    predict_travel_time,
    save_prediction,
    train_model,
    what_if_scenarios,
)

router = APIRouter(prefix="/ml", tags=["Machine learning"])
logger = logging.getLogger(__name__)
_training_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="traffic-model-training")
_training_jobs: dict[str, dict[str, Any]] = {}
_training_jobs_lock = Lock()
_TRAINING_JOB_RETENTION_SECONDS = 3600
_prediction_requests_lock = Lock()
_prediction_request_cache: dict[
    tuple[int, str], tuple[float, str, dict[str, Any]]
] = {}
_PREDICTION_REQUEST_RETENTION_SECONDS = 300
_PREDICTION_REQUEST_CACHE_LIMIT = 256


def _training_job_snapshot(job_id: str) -> dict[str, Any]:
    with _training_jobs_lock:
        _prune_training_jobs(time())
        job = _training_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Training job was not found or has expired.")
        return dict(job)


def _run_training_job(job_id: str) -> None:
    with _training_jobs_lock:
        job = _training_jobs.get(job_id)
        if job is None:
            return
        job.update(
            status="running",
            progress="Loading eligible readings and fitting chronological validation models.",
        )
    try:
        with SessionLocal() as db:
            result = train_model(db)
    except InsufficientTrainingData as exc:
        detail = str(exc)
    except SQLAlchemyError:
        logger.exception("Background traffic-model training could not load historical data.")
        detail = "Historical traffic data could not be loaded from MySQL. Check the backend log for details."
    except (ValueError, RuntimeError) as exc:
        logger.exception("Background traffic-model training failed.")
        detail = str(exc)
    except Exception as exc:
        logger.exception("Unexpected error during background traffic-model training.")
        detail = f"Training failed unexpectedly ({type(exc).__name__}). Check the backend log for details."
    else:
        with _training_jobs_lock:
            job = _training_jobs.get(job_id)
            if job is not None:
                job.update(
                    status="completed",
                    progress="Training and chronological evaluation completed.",
                    result=result,
                    finished_at=time(),
                )
        return

    with _training_jobs_lock:
        job = _training_jobs.get(job_id)
        if job is not None:
            job.update(
                status="failed",
                progress="Training did not complete.",
                error=detail,
                finished_at=time(),
            )


def _prune_training_jobs(now: float) -> None:
    expired = [
        job_id
        for job_id, job in _training_jobs.items()
        if job.get("finished_at") is not None
        and now - job["finished_at"] > _TRAINING_JOB_RETENTION_SECONDS
    ]
    for job_id in expired:
        _training_jobs.pop(job_id, None)


@router.get("/status")
def get_model_status(
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return model_status(db)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Historical traffic data is unavailable.") from None


@router.post("/train", status_code=202)
def train(_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    now = time()
    with _training_jobs_lock:
        _prune_training_jobs(now)
        active_job = next(
            (
                job
                for job in _training_jobs.values()
                if job["status"] in {"queued", "running"}
            ),
            None,
        )
        if active_job is not None:
            return {
                "job_id": active_job["job_id"],
                "status": active_job["status"],
                "progress": active_job["progress"],
            }

        job_id = uuid4().hex
        _training_jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "progress": "Waiting for the model-training worker.",
            "created_at": now,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        _training_executor.submit(_run_training_job, job_id)
        return {
            "job_id": job_id,
            "status": "queued",
            "progress": "Waiting for the model-training worker.",
        }


@router.get("/train/{job_id}")
def training_status(
    job_id: str,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    return _training_job_snapshot(job_id)


@router.post("/predict")
def predict(
    request: PredictionRequest,
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
    idempotency_key: UUID | None = Header(default=None, alias="Idempotency-Key"),
) -> dict:
    cache_key = (
        (int(_user["user_id"]), str(idempotency_key))
        if idempotency_key is not None and request.save
        else None
    )
    request_fingerprint = hashlib.sha256(
        json.dumps(
            request.model_dump(mode="json", exclude={"save"}),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    if cache_key is not None:
        with _prediction_requests_lock:
            now = monotonic()
            expired = [
                key
                for key, (created_at, _, _) in _prediction_request_cache.items()
                if now - created_at > _PREDICTION_REQUEST_RETENTION_SECONDS
            ]
            for key in expired:
                _prediction_request_cache.pop(key, None)
            cached = _prediction_request_cache.get(cache_key)
            if cached is not None:
                _, cached_fingerprint, cached_response = cached
                if cached_fingerprint != request_fingerprint:
                    raise HTTPException(
                        status_code=409,
                        detail="This prediction request key was already used with different inputs.",
                    )
                return {**cached_response, "idempotent_replay": True}

            response = _make_prediction_response(db, request)
            _prediction_request_cache[cache_key] = (
                monotonic(),
                request_fingerprint,
                response,
            )
            if len(_prediction_request_cache) > _PREDICTION_REQUEST_CACHE_LIMIT:
                oldest = sorted(
                    _prediction_request_cache,
                    key=lambda key: _prediction_request_cache[key][0],
                )[: len(_prediction_request_cache) - _PREDICTION_REQUEST_CACHE_LIMIT]
                for key in oldest:
                    _prediction_request_cache.pop(key, None)
            return response

    return _make_prediction_response(db, request)


def _make_prediction_response(
    db: Session,
    request: PredictionRequest,
) -> dict[str, Any]:
    try:
        prediction = predict_travel_time(db, request)
        saved_record = None
        saved_fields: list[str] = []
        unsupported_fields: list[str] = []
        if request.save:
            saved_record, saved_fields, unsupported_fields = save_prediction(db, request, prediction)
    except InsufficientTrainingData as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Prediction data could not be loaded or saved.") from None
    return {
        **prediction,
        "saved": saved_record is not None,
        "saved_fields": saved_fields,
        "unsupported_persistence_fields": unsupported_fields,
        "prediction": saved_record,
        "idempotent_replay": False,
    }


@router.post("/what-if")
def what_if(
    request: WhatIfRequest,
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        return what_if_scenarios(db, request)
    except InsufficientTrainingData as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Scenario inputs could not be loaded from the existing database.") from None