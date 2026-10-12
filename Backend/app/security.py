import os
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import traffic_app_users

password_hash = PasswordHash.recommended()
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hash.verify(password, encoded)
    except (ValueError, TypeError):
        return False


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured. Set JWT_SECRET_KEY in Backend/.env.",
        )
    return secret


def create_access_token(user: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user["user_id"]),
            "username": user["username"],
            "ver": int(user.get("token_version", 0)),
            "exp": now + timedelta(minutes=int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))),
            "iat": now,
        },
        _jwt_secret(),
        algorithm="HS256",
    )


def authenticate_user(db: Session, username: str, password: str) -> dict[str, Any] | None:
    user = db.execute(
        select(traffic_app_users).where(traffic_app_users.c.username == username)
    ).mappings().first()
    if user is None or not user["is_active"] or not verify_password(password, user["password_hash"]):
        return None
    return dict(user)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication is required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=["HS256"])
        user_id = int(payload["sub"])
        token_version = int(payload["ver"])
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.", headers={"WWW-Authenticate": "Bearer"}) from None
    try:
        user = db.execute(
            select(traffic_app_users).where(traffic_app_users.c.user_id == user_id)
        ).mappings().first()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Authentication storage is unavailable.") from None
    if user is None or not user["is_active"] or int(user["token_version"]) != token_version:
        raise HTTPException(status_code=401, detail="Your session is invalid or expired.", headers={"WWW-Authenticate": "Bearer"})
    return {"user_id": user["user_id"], "username": user["username"], "token_version": user["token_version"]}