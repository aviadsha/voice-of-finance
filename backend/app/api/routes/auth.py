from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DBSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserMe

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(access_token=create_access_token(user.id), user=UserMe.model_validate(user))


async def _authenticate(db: DBSession, email: str, password: str) -> User:
    user = (await db.execute(select(User).where(func.lower(User.email) == email.lower()))).scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")
    return user


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: UserCreate, db: DBSession) -> TokenResponse:
    email = payload.email.lower()
    exists = (await db.execute(select(User.id).where(func.lower(User.email) == email))).first()
    if exists:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
    user = User(email=email, hashed_password=hash_password(payload.password), full_name=payload.full_name)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists"
        ) from None
    await db.refresh(user)
    return _token_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DBSession) -> TokenResponse:
    return _token_response(await _authenticate(db, payload.email, payload.password))


@router.post("/token", response_model=TokenResponse, include_in_schema=True)
async def login_for_access_token(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DBSession) -> TokenResponse:
    """OAuth2 password flow (used by the "Authorize" button in the Swagger UI)."""
    return _token_response(await _authenticate(db, form.username, form.password))
