import sys
from pathlib import Path

from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine


ADDITIVE_COLUMNS = {
    "problem_type": "VARCHAR(40) NULL",
    "congestion_severity": "VARCHAR(20) NULL",
    "problem_description": "VARCHAR(500) NULL",
}


def ensure_context_columns(connection: Connection) -> list[str]:
    if "decision_recommendations" not in inspect(connection).get_table_names():
        raise ValueError(
            "decision_recommendations is missing. Apply migration "
            "002_decision_recommendations.sql first."
        )

    existing = {
        column["name"]
        for column in inspect(connection).get_columns("decision_recommendations")
    }
    added: list[str] = []
    for name, definition in ADDITIVE_COLUMNS.items():
        if name not in existing:
            connection.execute(
                text(
                    f"ALTER TABLE decision_recommendations "
                    f"ADD COLUMN {name} {definition}"
                )
            )
            added.append(name)
    return added


def main() -> None:
    try:
        with engine.begin() as connection:
            added = ensure_context_columns(connection)
            if added:
                for name in added:
                    print(f"Added nullable column: {name}")
            else:
                print("Recommendation context columns already exist; no changes were made.")
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    except SQLAlchemyError:
        raise SystemExit(
            "Could not update recommendation storage. Check that MySQL is running "
            "and Backend/.env points to the correct database."
        ) from None


if __name__ == "__main__":
    main()
