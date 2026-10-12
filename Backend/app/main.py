import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.models import TRAFFIC_TABLES, auth_metadata
from app.routers import analytics, auth, incidents, ml, predictions, roads, traffic, weather


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        auth_metadata.create_all(engine, tables=[auth_metadata.tables["traffic_app_users"]], checkfirst=True)
        _create_initial_admin()
    except SQLAlchemyError:
        pass
    yield


def _create_initial_admin() -> None:
    from app.security import hash_password
    from app.models import traffic_app_users
    from sqlalchemy import insert, select
    from app.database import SessionLocal

    username = os.getenv("INITIAL_ADMIN_USERNAME", "").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if not username or len(password) < 12:
        return
    with SessionLocal() as session:
        exists = session.execute(
            select(traffic_app_users.c.user_id).where(traffic_app_users.c.username == username)
        ).first()
        if exists is None:
            session.execute(insert(traffic_app_users).values(username=username, password_hash=hash_password(password)))
            session.commit()


app = FastAPI(
    title="Urban Traffic Congestion Analytics API",
    description="Authenticated analytics and travel-time prediction over the existing urban_traffic_db records.",
    version="1.0.0",
    lifespan=lifespan,
)

origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGIN", "http://localhost:8501"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(roads.router, prefix="/api", tags=["Road segments"])
app.include_router(traffic.router, prefix="/api", tags=["Traffic readings"])
app.include_router(weather.router, prefix="/api", tags=["Weather"])
app.include_router(incidents.router, prefix="/api", tags=["Incidents"])
app.include_router(predictions.router, prefix="/api", tags=["Predictions"])
app.include_router(ml.router, prefix="/api")


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _exc: SQLAlchemyError) -> JSONResponse:
    del _request, _exc
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable or does not contain the required urban traffic tables."},
    )


@app.get("/api/health", tags=["Health"], response_model=None)
def health() -> dict[str, object] | JSONResponse:
    if not os.getenv("DB_USER"):
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable", "detail": "Set DB_USER in Backend/.env."},
        )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            existing = set(inspect(connection).get_table_names())
            missing = sorted(TRAFFIC_TABLES.difference(existing))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable", "detail": "Check Backend/.env and MySQL availability."},
        )
    if missing:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "connected", "missing_tables": missing},
        )
    return {"status": "ok", "database": "connected", "tables": sorted(TRAFFIC_TABLES)}