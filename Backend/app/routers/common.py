from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import DateTime, Table


def require_column(table: Table, *names: str) -> str:
    for name in names:
        if name in table.c:
            return name
    for column in table.c:
        if isinstance(column.type, DateTime):
            return column.name
    raise HTTPException(
        status_code=422,
        detail=f"The database table '{table.name}' does not contain the required time column.",
    )


def optional_time_column(table: Table, *names: str) -> str | None:
    for name in names:
        if name in table.c:
            return name
    return next(
        (column.name for column in table.c if isinstance(column.type, DateTime)),
        None,
    )


def optional_column(table: Table, *names: str) -> str | None:
    return next((name for name in names if name in table.c), None)


def normalize_time(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    from app.schemas import to_database_datetime

    return to_database_datetime(value)