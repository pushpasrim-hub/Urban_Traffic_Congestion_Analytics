from fastapi import APIRouter

router = APIRouter()
from app.routers.crud import register_crud_routes
from app.schemas import WeatherCreate, WeatherPatch

register_crud_routes(router, "/weather", "weather_data", "weather_id", WeatherCreate, WeatherPatch)