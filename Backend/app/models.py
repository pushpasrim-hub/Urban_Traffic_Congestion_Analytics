from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, func

from app.database import engine

TRAFFIC_TABLES = {
    "road_segments",
    "traffic_readings",
    "weather_data",
    "incidents",
    "traffic_predictions",
}

metadata = MetaData()
auth_metadata = MetaData()
traffic_app_users = Table(
    "traffic_app_users",
    auth_metadata,
    Column("user_id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(120), nullable=False, unique=True),
    Column("password_hash", String(255), nullable=False),
    Column("is_active", Boolean, nullable=False, server_default="1"),
    Column("token_version", Integer, nullable=False, server_default="0"),
    Column("created_at", DateTime, nullable=False, server_default=func.current_timestamp()),
)


def get_table(table_name: str) -> Table:
    if table_name not in TRAFFIC_TABLES:
        raise ValueError("Unknown traffic table")
    if table_name not in metadata.tables:
        Table(table_name, metadata, autoload_with=engine)
    return metadata.tables[table_name]


def clear_reflected_tables() -> None:
    metadata.clear()