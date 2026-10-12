from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.security import get_current_user

AuthenticatedUser = dict[str, object]


def get_authenticated_db(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Session:
    return db