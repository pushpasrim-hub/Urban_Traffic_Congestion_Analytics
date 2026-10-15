import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import ensure_decision_recommendations_table


def main() -> None:
    created = ensure_decision_recommendations_table()
    if created:
        print("Created only the missing decision_recommendations table.")
    else:
        print("decision_recommendations already exists; no schema changes were made.")


if __name__ == "__main__":
    main()
