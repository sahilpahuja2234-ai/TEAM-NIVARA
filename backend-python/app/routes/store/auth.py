"""POST /api/store/auth/register, /login, GET /api/store/auth/me."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from passlib.context import CryptContext
from sqlmodel import Session, select

from app.auth.jwt import create_access_token, get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserMeResponse,
    UserRegisterResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# bcrypt context — cost factor 12 is a reasonable default
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _hash(password: str) -> str:
    return _pwd_ctx.hash(password)


def _verify(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# --------------------------------------------------------------------------- #
# Register
# --------------------------------------------------------------------------- #
@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserRegisterResponse,
    summary="Register a new customer account",
)
def register(
    body: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserRegisterResponse:
    existing = db.exec(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )
    user = User(
        email=body.email,
        hashed_password=_hash(body.password),
        full_name=body.full_name,
        role="customer",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserRegisterResponse(user_id=user.id, email=user.email)


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Obtain a Bearer token (24 h expiry)",
)
def login(
    body: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    user = db.exec(select(User).where(User.email == body.email)).first()
    if not user or not _verify(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    token = create_access_token(
        subject=user.id,
        extra_claims={"role": user.role, "email": user.email},
    )
    return TokenResponse(access_token=token, token_type="bearer", role=user.role)


# --------------------------------------------------------------------------- #
# Me
# --------------------------------------------------------------------------- #
@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Return the authenticated user's profile",
)
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserMeResponse:
    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
    )
