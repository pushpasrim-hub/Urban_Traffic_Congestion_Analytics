from fastapi import APIRouter

router = APIRouter()
from app.routers.crud import register_crud_routes
from app.schemas import RoadSegmentCreate, RoadSegmentPatch

register_crud_routes(router, "/road-segments", "road_segments", "segment_id", RoadSegmentCreate, RoadSegmentPatch)