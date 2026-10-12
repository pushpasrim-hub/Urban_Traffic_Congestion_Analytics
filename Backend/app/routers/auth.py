from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import LoginRequest
from app.models import traffic_app_users
from app.security import authenticate_user, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        user = authenticate_user(db, payload.username, payload.password)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Authentication storage is unavailable.") from None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "username": user["username"],
    }


@router.get("/me")
def me(user: dict[str, object] = Depends(get_current_user)) -> dict[str, object]:
    return {"user_id": user["user_id"], "username": user["username"]}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: dict[str, object] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        db.execute(
            update(traffic_app_users)
            .where(traffic_app_users.c.user_id == user["user_id"])
            .values(token_version=traffic_app_users.c.token_version + 1)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="The session could not be ended. Try again.") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)