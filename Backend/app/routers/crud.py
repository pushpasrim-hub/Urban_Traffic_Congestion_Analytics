from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, ValidationError
from sqlalchemy import DateTime, Table, func, insert, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import get_table
from app.schemas import to_database_datetime
from app.security import get_current_user


def _time_column(table: Table, preferred: tuple[str, ...]) -> str | None:
    for name in preferred:
        if name in table.c:
            return name
    return next((column.name for column in table.c if isinstance(column.type, DateTime)), None)


def _database_values(payload: BaseModel) -> dict[str, Any]:
    values = payload.model_dump(exclude_unset=True)
    return {
        name: to_database_datetime(value) if isinstance(value, datetime) else value
        for name, value in values.items()
    }


def _parse_payload(schema: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from None


def _check_columns(table: Table, values: dict[str, Any]) -> None:
    missing = set(values).difference(table.c.keys())
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"The existing {table.name} table is missing API-supported columns: {', '.join(sorted(missing))}.",
        )
    null_fields = [name for name, value in values.items() if value is None and not table.c[name].nullable]
    if null_fields:
        raise HTTPException(
            status_code=422,
            detail=f"These columns cannot be null in the existing database: {', '.join(sorted(null_fields))}.",
        )


def _validate_segment(db: Session, segment_id: int | None) -> None:
    if segment_id is None:
        return
    try:
        roads = get_table("road_segments")
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="The road-segment table is unavailable.") from None
    if "segment_id" not in roads.c:
        raise HTTPException(status_code=503, detail="The road_segments table is missing segment_id.")
    if db.execute(select(roads.c.segment_id).where(roads.c.segment_id == segment_id)).first() is None:
        raise HTTPException(status_code=422, detail="segment_id does not reference an existing road segment.")


def _fetch_item(db: Session, table: Table, primary_key: str, item_id: int) -> dict[str, Any]:
    row = db.execute(
        select(table).where(table.c[primary_key] == item_id)
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Record not found.")
    return dict(row)


def _check_road_references(db: Session, segment_id: int) -> None:
    for related_name in ("traffic_readings", "incidents", "traffic_predictions"):
        related = get_table(related_name)
        if "segment_id" not in related.c:
            continue
        count = db.scalar(
            select(func.count()).select_from(related).where(related.c.segment_id == segment_id)
        )
        if count:
            raise HTTPException(
                status_code=409,
                detail=f"Road segment is referenced by {related_name}; delete or reassign those records first.",
            )


def register_crud_routes(
    router: APIRouter,
    path: str,
    table_name: str,
    primary_key: str,
    create_schema: type[BaseModel],
    patch_schema: type[BaseModel],
) -> None:
    def list_records(
        segment_id: int | None = None,
        location: str | None = None,
        congestion_level: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        from_time: datetime | None = None,
        to_time: datetime | None = None,
        active_only: bool = False,
        search: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        db: Session = Depends(get_db),
        _user: dict[str, Any] = Depends(get_current_user),
    ) -> list[dict[str, Any]]:
        table = get_table(table_name)
        statement = select(table)
        for name, value in (("segment_id", segment_id), ("location", location), ("congestion_level", congestion_level)):
            if value is not None:
                if name not in table.c:
                    raise HTTPException(status_code=422, detail=f"The {table_name} table does not support the {name} filter.")
                statement = statement.where(table.c[name] == value)
        lower_time = from_time or start_time
        upper_time = to_time or end_time
        if lower_time is not None or upper_time is not None or active_only:
            time_name = _time_column(table, ("recorded_at", "predicted_for", "start_time", "created_at"))
            if time_name is None:
                raise HTTPException(status_code=422, detail=f"The {table_name} table has no time column to filter.")
            if lower_time is not None:
                statement = statement.where(table.c[time_name] >= to_database_datetime(lower_time))
            if upper_time is not None:
                statement = statement.where(table.c[time_name] <= to_database_datetime(upper_time))
        if active_only:
            if "start_time" not in table.c or "end_time" not in table.c:
                raise HTTPException(status_code=422, detail="Active filtering requires start_time and end_time columns.")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            statement = statement.where(table.c.start_time <= now).where(
                or_(table.c.end_time.is_(None), table.c.end_time >= now)
            )
        if search:
            string_columns = [column for column in table.c if str(column.type).upper().startswith(("VARCHAR", "CHAR", "TEXT"))]
            if string_columns:
                statement = statement.where(or_(*(column.ilike(f"%{search}%") for column in string_columns)))
        order_column = _time_column(table, ("recorded_at", "predicted_for", "start_time", "created_at"))
        if order_column:
            statement = statement.order_by(table.c[order_column].desc())
        elif primary_key in table.c:
            statement = statement.order_by(table.c[primary_key].desc())
        rows = db.execute(statement.limit(limit).offset(offset)).mappings().all()
        return [dict(row) for row in rows]

    def get_record(
        item_id: int = Path(..., alias=primary_key),
        db: Session = Depends(get_db),
        _user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        return _fetch_item(db, get_table(table_name), primary_key, item_id)

    def create_record(
        payload: dict[str, Any] = Body(...),
        db: Session = Depends(get_db),
        _user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        table = get_table(table_name)
        values = _database_values(_parse_payload(create_schema, payload))
        _check_columns(table, values)
        if "segment_id" in values and table_name != "road_segments":
            _validate_segment(db, values["segment_id"])
        if table_name == "incidents" and values.get("end_time") and values["end_time"] < values["start_time"]:
            raise HTTPException(status_code=422, detail="end_time must not be earlier than start_time.")
        try:
            result = db.execute(insert(table).values(**values))
            db.commit()
            if result.inserted_primary_key and primary_key in table.c:
                return _fetch_item(db, table, primary_key, result.inserted_primary_key[0])
            return values
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="The record conflicts with an existing database constraint.") from None
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=503, detail="The database could not save this record.") from None

    def replace_record(
        item_id: int = Path(..., alias=primary_key),
        payload: dict[str, Any] = Body(...),
        db: Session = Depends(get_db),
        _user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        return update_record(item_id, _parse_payload(create_schema, payload), db, _user)

    def patch_record(
        item_id: int = Path(..., alias=primary_key),
        payload: dict[str, Any] = Body(...),
        db: Session = Depends(get_db),
        _user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        values = _database_values(_parse_payload(patch_schema, payload))
        if not values:
            raise HTTPException(status_code=422, detail="Provide at least one field to update.")
        return update_values(item_id, values, db)

    def update_record(
        item_id: int,
        payload: BaseModel,
        db: Session,
        _user: dict[str, Any],
    ) -> dict[str, Any]:
        return update_values(item_id, _database_values(payload), db)

    def update_values(item_id: int, values: dict[str, Any], db: Session) -> dict[str, Any]:
        table = get_table(table_name)
        _check_columns(table, values)
        _fetch_item(db, table, primary_key, item_id)
        if "segment_id" in values and table_name != "road_segments":
            _validate_segment(db, values["segment_id"])
        if table_name == "incidents":
            current = _fetch_item(db, table, primary_key, item_id)
            start_time = values.get("start_time", current.get("start_time"))
            end_time = values.get("end_time", current.get("end_time"))
            if start_time and end_time and end_time < start_time:
                raise HTTPException(status_code=422, detail="end_time must not be earlier than start_time.")
        try:
            db.execute(update(table).where(table.c[primary_key] == item_id).values(**values))
            db.commit()
            return _fetch_item(db, table, primary_key, item_id)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="The update conflicts with an existing database constraint.") from None
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=503, detail="The database could not update this record.") from None

    def delete_record(
        item_id: int = Path(..., alias=primary_key),
        db: Session = Depends(get_db),
        _user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, str]:
        table = get_table(table_name)
        _fetch_item(db, table, primary_key, item_id)
        if table_name == "road_segments":
            _check_road_references(db, item_id)
        try:
            db.execute(table.delete().where(table.c[primary_key] == item_id))
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="This record is referenced by other records and cannot be deleted.") from None
        except SQLAlchemyError:
            db.rollback()
            raise HTTPException(status_code=503, detail="The database could not delete this record.") from None
        return {"detail": "Record deleted."}

    router.add_api_route(path, list_records, methods=["GET"], response_model=list[dict], name=f"list_{table_name}")
    router.add_api_route(path, create_record, methods=["POST"], response_model=dict, status_code=status.HTTP_201_CREATED, name=f"create_{table_name}")
    router.add_api_route(f"{path}/{{{primary_key}}}", get_record, methods=["GET"], response_model=dict, name=f"get_{table_name}")
    router.add_api_route(f"{path}/{{{primary_key}}}", replace_record, methods=["PUT"], response_model=dict, name=f"replace_{table_name}")
    router.add_api_route(f"{path}/{{{primary_key}}}", patch_record, methods=["PATCH"], response_model=dict, name=f"patch_{table_name}")
    router.add_api_route(f"{path}/{{{primary_key}}}", delete_record, methods=["DELETE"], response_model=dict, name=f"delete_{table_name}")