import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.routers import decision_support


app = FastAPI(
    title="Urban Traffic Congestion Analytics API",
    description="Traffic congestion analytics and rule-based decision support over stored traffic records.",
    version="2.0.0",
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
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(decision_support.router)


@app.get("/", tags=["Status"])
def welcome() -> dict[str, str]:
    return {
        "name": "Urban Traffic Congestion Analytics & Decision Support System",
        "status": "running",
        "documentation": "/docs",
    }


@app.get("/health", tags=["Status"], response_model=None)
def health() -> dict[str, object] | JSONResponse:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            existing = set(inspect(connection).get_table_names())
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "database": "unavailable",
                "detail": "Check Backend/.env and make sure MySQL is running.",
            },
        )

    missing_core_tables = sorted(
        set(decision_support.CORE_TABLES).difference(existing)
    )
    if missing_core_tables:
        return JSONResponse(
            status_code=503,
            content={
                "status": "degraded",
                "database": "connected",
                "missing_tables": missing_core_tables,
            },
        )
    recommendation_storage = "connected" if "decision_recommendations" in existing else "missing"
    return {
        "status": "ok" if recommendation_storage == "connected" else "degraded",
        "database": "connected",
        "recommendations_storage": recommendation_storage,
        "missing_tables": (
            [] if recommendation_storage == "connected" else ["decision_recommendations"]
        ),
    }


@app.get("/api/health", tags=["Status"], include_in_schema=False, response_model=None)
def api_health() -> dict[str, object] | JSONResponse:
    return health()


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The database is unavailable or does not contain the required urban traffic tables."},
    )