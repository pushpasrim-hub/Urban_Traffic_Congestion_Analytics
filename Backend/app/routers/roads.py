from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import get_table
from app.routers.crud import (
    _road_reference_counts,
    _road_reference_tables,
    register_crud_routes,
)
from app.schemas import RoadSegmentCreate, RoadSegmentPatch
from app.security import get_current_user

router = APIRouter()

register_crud_routes(
    router,
    "/road-segments",
    "road_segments",
    "segment_id",
    RoadSegmentCreate,
    RoadSegmentPatch,
    include_list=False,
)


class RoadReassignmentRequest(BaseModel):
    destination_segment_id: int = Field(gt=0)


@router.get("/road-segments/{segment_id}/dependencies")
def road_dependencies(
    segment_id: int,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    roads = get_table("road_segments")
    if db.execute(
        select(roads.c.segment_id).where(roads.c.segment_id == segment_id)
    ).first() is None:
        raise HTTPException(status_code=404, detail="Road segment not found.")
    counts = _road_reference_counts(db, segment_id)
    return {
        "segment_id": segment_id,
        "total": sum(counts.values()),
        "by_table": counts,
    }


@router.post("/road-segments/{segment_id}/reassign-and-delete")
def reassign_and_delete_road(
    segment_id: int,
    payload: RoadReassignmentRequest,
    db: Session = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    roads = get_table("road_segments")
    destination_id = payload.destination_segment_id
    if destination_id == segment_id:
        raise HTTPException(
            status_code=422,
            detail="Choose a different road segment as the reassignment destination.",
        )

    try:
        with db.begin():
            road_ids = db.execute(
                select(roads.c.segment_id)
                .where(roads.c.segment_id.in_([segment_id, destination_id]))
                .order_by(roads.c.segment_id)
                .with_for_update()
            ).scalars().all()
            if segment_id not in road_ids:
                raise HTTPException(status_code=404, detail="Road segment not found.")
            if destination_id not in road_ids:
                raise HTTPException(status_code=404, detail="Destination road segment not found.")

            references = _road_reference_tables(db)
            counts = _road_reference_counts(db, segment_id)
            for table_name in counts:
                related, column_names = references[table_name]
                for column_name in column_names:
                    db.execute(
                        update(related)
                        .where(related.c[column_name] == segment_id)
                        .values({column_name: destination_id})
                    )

            deleted = db.execute(
                delete(roads).where(roads.c.segment_id == segment_id)
            )
            if deleted.rowcount != 1:
                raise HTTPException(
                    status_code=409,
                    detail="The road segment changed during reassignment. No changes were saved.",
                )
    except HTTPException:
        raise
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail=(
                "Road reassignment could not be completed because a related database "
                "constraint was not satisfied. No changes were saved."
            ),
        ) from None
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Road reassignment failed because of a database error. No changes were saved.",
        ) from None

    return {
        "detail": "Linked records reassigned and road segment deleted.",
        "segment_id": segment_id,
        "destination_segment_id": destination_id,
        "reassigned": counts,
        "total_reassigned": sum(counts.values()),
    }