import os
import secrets
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import BrowserSessionTicketRequest, LoginRequest
from app.models import traffic_app_users
from app.security import authenticate_user, bearer_scheme, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])
SESSION_COOKIE_NAME = "urban_traffic_session"
_BROWSER_SESSION_TICKETS: dict[str, tuple[str, float]] = {}
_BROWSER_SESSION_TICKETS_LOCK = Lock()
_BROWSER_SESSION_TICKET_TTL_SECONDS = 30


def _allowed_frontend_origins() -> set[str]:
    configured = os.getenv("FRONTEND_ORIGIN", "http://localhost:8501")
    return {origin.strip() for origin in configured.split(",") if origin.strip()}


def _require_frontend_origin(request: Request) -> None:
    if request.headers.get("origin") not in _allowed_frontend_origins():
        raise HTTPException(status_code=403, detail="The browser session request origin is not allowed.")


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


@router.post("/browser-cookie-ticket")
def create_browser_cookie_ticket(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    _user: dict[str, object] = Depends(get_current_user),
) -> dict[str, str]:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    ticket = secrets.token_urlsafe(32)
    expires_at = monotonic() + _BROWSER_SESSION_TICKET_TTL_SECONDS
    with _BROWSER_SESSION_TICKETS_LOCK:
        expired = [
            value
            for value, (_, expiry) in _BROWSER_SESSION_TICKETS.items()
            if expiry <= monotonic()
        ]
        for value in expired:
            _BROWSER_SESSION_TICKETS.pop(value, None)
        _BROWSER_SESSION_TICKETS[ticket] = (credentials.credentials, expires_at)
    return {"ticket": ticket}


@router.post("/browser-session")
def create_browser_session(
    payload: BrowserSessionTicketRequest,
    request: Request,
) -> Response:
    _require_frontend_origin(request)
    with _BROWSER_SESSION_TICKETS_LOCK:
        entry = _BROWSER_SESSION_TICKETS.pop(payload.ticket, None)
    if entry is None or entry[1] <= monotonic():
        raise HTTPException(status_code=401, detail="The browser session ticket is invalid or expired. Sign in again.")

    max_age = max(0, int(os.getenv("ACCESS_TOKEN_MINUTES", "60")) * 60)
    response = Response(content='{"status":"authenticated"}', media_type="application/json")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=entry[0],
        max_age=max_age,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/browser-logout", status_code=status.HTTP_204_NO_CONTENT)
def clear_browser_session(request: Request) -> Response:
    _require_frontend_origin(request)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


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