from fastapi import APIRouter

router = APIRouter()
from app.routers.crud import register_crud_routes
from app.schemas import PredictionCreate, PredictionPatch

register_crud_routes(router, "/predictions", "traffic_predictions", "prediction_id", PredictionCreate, PredictionPatch)