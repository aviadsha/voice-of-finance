from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/token", auto_error=False)

DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_optional_user(db: DBSession, token: Annotated[str | None, Depends(oauth2_scheme)]) -> User | None:
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def require_premium(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_premium:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Premium subscription required")
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin privileges required")
    return user


async def require_analyst(user: Annotated[User, Depends(get_current_user)]) -> User:
    if not (user.is_admin or (user.role == UserRole.ANALYST and user.is_verified_analyst)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verified analyst privileges required")
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]
PremiumUser = Annotated[User, Depends(require_premium)]
AdminUser = Annotated[User, Depends(require_admin)]
AnalystUser = Annotated[User, Depends(require_analyst)]
