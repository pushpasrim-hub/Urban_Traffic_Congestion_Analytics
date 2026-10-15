from sqlalchemy import (
    Boolean,
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    func,
    inspect,
)

from app.database import engine

TRAFFIC_TABLES = {
    "road_segments",
    "traffic_readings",
    "weather_data",
    "incidents",
    "decision_recommendations",
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

decision_recommendations = Table(
    "decision_recommendations",
    metadata,
    Column("recommendation_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "segment_id",
        Integer,
        ForeignKey("road_segments.segment_id"),
        nullable=False,
    ),
    Column("priority", String(20), nullable=False),
    Column("recommendation_text", String(500), nullable=False),
    Column("evidence_summary", Text, nullable=False),
    Column(
        "created_at",
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
    ),
    Column("status", String(30), nullable=False, server_default="pending"),
    Column("deduplication_key", CHAR(64), nullable=False, unique=True),
)


def get_table(table_name: str) -> Table:
    if table_name not in TRAFFIC_TABLES:
        raise ValueError("Unknown traffic table")
    if table_name not in metadata.tables:
        Table(table_name, metadata, autoload_with=engine)
    return metadata.tables[table_name]


def ensure_decision_recommendations_table() -> bool:
    if "decision_recommendations" in inspect(engine).get_table_names():
        return False
    if "road_segments" not in metadata.tables:
        Table("road_segments", metadata, autoload_with=engine)
    metadata.create_all(engine, tables=[decision_recommendations], checkfirst=True)
    return True


def clear_reflected_tables() -> None:
    metadata.clear()