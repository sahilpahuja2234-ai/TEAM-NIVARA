"""JWT creation, verification, and OAuth2 bearer dependency.

Uses python-jose (HS256) with a 24-hour token lifetime.
SECRET_KEY is loaded from .env via app.config.settings.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlmodel import Session, select

from app.config import settings
from app.db.models import User
from app.db.session import get_db

# Token URL for OAuth2 compatibility (used by Swagger UI "Authorize" button)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/store/auth/login")

ALGORITHM = settings.jwt_algorithm
SECRET_KEY = settings.jwt_secret
EXPIRE_MINUTES = settings.access_token_expire_minutes


# --------------------------------------------------------------------------- #
# Token helpers
# --------------------------------------------------------------------------- #

def create_access_token(subject: str, extra_claims: dict | None = None) -> str:
    """Create a signed JWT.

    Args:
        subject: The user's UUID (stored in the ``sub`` claim).
        extra_claims: Optional additional claims (e.g. ``{"role": "admin"}``).

    Returns:
        A compact, URL-safe JWT string.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=EXPIRE_MINUTES)
    payload: dict = {
        "sub": subject,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises HTTPException 401 on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# --------------------------------------------------------------------------- #
# FastAPI dependencies
# --------------------------------------------------------------------------- #

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """Resolve the Bearer token to a User row.

    Raises 401 if the token is invalid or the user does not exist.
    Raises 403 if the user account is inactive.
    """
    payload = decode_token(token)
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    return user


def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Dependency that enforces role=admin. Raises 403 otherwise."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user
