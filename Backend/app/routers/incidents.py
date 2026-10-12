from fastapi import APIRouter

from app.routers.crud import register_crud_routes
from app.schemas import IncidentCreate, IncidentPatch

router = APIRouter()

register_crud_routes(router, "/incidents", "incidents", "incident_id", IncidentCreate, IncidentPatch)