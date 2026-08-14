"""Request-scoped identity: token → user, or 401.

`authenticate` is the pure decoder (no session lifecycle, no HTTP responses);
`get_current_user` is the FastAPI dependency every protected route relies on.
"""
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from database import get_session
from models import User
from services.emailer import Mailer, resend_mailer
from utils.auth import decode_token


def authenticate(request: Request, db: Session) -> User | None:
    """Extract Bearer token, decode it, load the user. None on any failure."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        return None

    try:
        payload = decode_token(token)
    except Exception:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    return db.get(User, user_id)


def get_current_user(
    request: Request, db: Session = Depends(get_session)
) -> User:
    user = authenticate(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_mailer() -> Mailer:
    """Dependency seam — tests override this to capture raw verification tokens."""
    return resend_mailer