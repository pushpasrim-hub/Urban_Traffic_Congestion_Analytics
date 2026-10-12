from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import get_table
from app.routers.crud import register_crud_routes
from app.schemas import TrafficReadingCreate, TrafficReadingPatch
from app.security import get_current_user

router = APIRouter()


@router.get("/traffic-readings/latest", response_model=list[dict])
def latest_traffic_readings(
    segment_id: int | None = None,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> list[dict]:
    table = get_table("traffic_readings")
    for name in ("segment_id", "recorded_at"):
        if name not in table.c:
            raise HTTPException(status_code=503, detail=f"The traffic_readings table is missing {name}.")
    ranked = select(
        *table.c,
        func.row_number().over(
            partition_by=table.c.segment_id,
            order_by=table.c.recorded_at.desc(),
        ).label("_row_number"),
    ).subquery()
    statement = select(*(ranked.c[name] for name in table.c.keys())).where(ranked.c._row_number == 1)
    if segment_id is not None:
        statement = statement.where(ranked.c.segment_id == segment_id)
    return [dict(row) for row in db.execute(statement).mappings().all()]


register_crud_routes(router, "/traffic-readings", "traffic_readings", "reading_id", TrafficReadingCreate, TrafficReadingPatch)