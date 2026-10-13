from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
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


@router.post("/train")
def train(_user: dict = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return train_model(db)
    except InsufficientTrainingData as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Historical traffic data could not be loaded from MySQL.") from None


@router.post("/predict")
def predict(
    request: PredictionRequest,
    _user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
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