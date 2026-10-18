import getpass
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import auth_metadata, engine, traffic_app_users
from app.security import hash_password


def main() -> None:
    auth_metadata.create_all(engine, tables=[traffic_app_users], checkfirst=True)
    username = input("Administrator username: ").strip()
    if not username:
        raise SystemExit("Username cannot be empty.")
    password = getpass.getpass("Administrator password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12:
        raise SystemExit("Choose a password with at least 12 characters.")
    if password != confirmation:
        raise SystemExit("The passwords did not match.")

    with SessionLocal() as db:
        try:
            if db.execute(
                select(traffic_app_users.c.user_id).where(
                    traffic_app_users.c.username == username
                )
            ).first():
                raise SystemExit("That username already exists.")
            db.execute(
                traffic_app_users.insert().values(
                    username=username,
                    password_hash=hash_password(password),
                    is_active=True,
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()
            raise SystemExit("That username already exists.") from None
        except SQLAlchemyError:
            db.rollback()
            raise SystemExit("The administrator account could not be saved.") from None
    print(f"Administrator '{username}' created.")


if __name__ == "__main__":
    main()
