import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.agents.community import CommunityAgent, json_array_contains
from app.agents.text_utils import normalize_ticker, normalize_topic
from app.api.deps import AdminUser, CurrentUser, DBSession, PremiumUser
from app.core.config import settings
from app.models import Article, ArticleStatus, Follow, FollowType, PortfolioHolding, SubscriptionTier, User
from app.schemas import (
    AdminUserUpdate,
    ArticleListItem,
    FollowCreate,
    FollowOut,
    HoldingCreate,
    HoldingOut,
    PortfolioOut,
    UserMe,
    UserPublic,
    UserUpdate,
)

router = APIRouter(tags=["users"])


# --------------------------------------------------------------------------- profile
@router.get("/users/me", response_model=UserMe)
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/users/me", response_model=UserMe)
async def update_me(payload: UserUpdate, user: CurrentUser, db: DBSession) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


@router.get("/users/{user_id}", response_model=UserPublic)
async def read_user(user_id: uuid.UUID, db: DBSession) -> User:
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/admin/users/{user_id}", response_model=UserMe, tags=["admin"])
async def admin_update_user(user_id: uuid.UUID, payload: AdminUserUpdate, _: AdminUser, db: DBSession) -> User:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return user


# --------------------------------------------------------------------------- follows
@router.get("/me/follows", response_model=list[FollowOut], tags=["follows"])
async def list_follows(user: CurrentUser) -> list[Follow]:
    return sorted(user.follows, key=lambda f: f.created_at)


@router.post("/me/follows", response_model=FollowOut, status_code=status.HTTP_201_CREATED, tags=["follows"])
async def create_follow(payload: FollowCreate, user: CurrentUser, db: DBSession) -> Follow:
    if payload.follow_type == FollowType.COMPANY:
        value = normalize_ticker(payload.value)
        if value is None:
            raise HTTPException(status_code=422, detail="Invalid ticker symbol")
    else:
        value = normalize_topic(payload.value)
        if not value:
            raise HTTPException(status_code=422, detail="Invalid topic")
    follow = Follow(
        user_id=user.id,
        follow_type=payload.follow_type,
        value=value,
        display_name=payload.display_name or payload.value.strip(),
    )
    db.add(follow)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Already following") from None
    await db.refresh(follow)
    return follow


@router.delete("/me/follows/{follow_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["follows"])
async def delete_follow(follow_id: uuid.UUID, user: CurrentUser, db: DBSession) -> None:
    follow = await db.get(Follow, follow_id)
    if follow is None or follow.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Follow not found")
    await db.delete(follow)
    await db.commit()


@router.get("/me/feed", response_model=list[ArticleListItem], tags=["follows"])
async def personalised_feed(
    user: CurrentUser,
    db: DBSession,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[Article]:
    """Articles matching the companies and topics the user follows."""
    await db.refresh(user, attribute_names=["follows"])
    return await CommunityAgent(db).personalised_feed(user, limit=limit, offset=offset)


# --------------------------------------------------------------------------- portfolio (premium)
async def _portfolio(user: User, db: DBSession) -> PortfolioOut:
    holdings = list(
        (
            await db.execute(
                select(PortfolioHolding).where(PortfolioHolding.user_id == user.id).order_by(PortfolioHolding.ticker)
            )
        ).scalars()
    )
    total = sum(((h.average_cost or Decimal(0)) * h.shares for h in holdings), Decimal(0))
    related: list[Article] = []
    if holdings:
        dialect = db.bind.dialect.name
        related = list(
            (
                await db.execute(
                    select(Article)
                    .where(
                        Article.status == ArticleStatus.PUBLISHED,
                        or_(*[json_array_contains(Article.tickers, h.ticker, dialect) for h in holdings]),
                    )
                    .order_by(Article.published_at.desc().nullslast())
                    .limit(20)
                )
            )
            .unique()
            .scalars()
        )
    return PortfolioOut(
        holdings=[HoldingOut.model_validate(h) for h in holdings],
        total_cost_basis=total,
        related_articles=[ArticleListItem.model_validate(a) for a in related],
    )


@router.get("/me/portfolio", response_model=PortfolioOut, tags=["portfolio"])
async def get_portfolio(user: PremiumUser, db: DBSession) -> PortfolioOut:
    return await _portfolio(user, db)


@router.post("/me/portfolio", response_model=HoldingOut, status_code=status.HTTP_201_CREATED, tags=["portfolio"])
async def upsert_holding(payload: HoldingCreate, user: PremiumUser, db: DBSession) -> PortfolioHolding:
    if normalize_ticker(payload.ticker) is None:
        raise HTTPException(status_code=422, detail="Invalid ticker symbol")
    holding = (
        await db.execute(
            select(PortfolioHolding).where(
                PortfolioHolding.user_id == user.id, PortfolioHolding.ticker == payload.ticker
            )
        )
    ).scalar_one_or_none()
    if holding is None:
        holding = PortfolioHolding(user_id=user.id, ticker=payload.ticker)
        db.add(holding)
    holding.shares = payload.shares
    holding.average_cost = payload.average_cost
    holding.notes = payload.notes
    await db.commit()
    await db.refresh(holding)
    return holding


@router.delete("/me/portfolio/{holding_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["portfolio"])
async def delete_holding(holding_id: uuid.UUID, user: PremiumUser, db: DBSession) -> None:
    holding = await db.get(PortfolioHolding, holding_id)
    if holding is None or holding.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    await db.delete(holding)
    await db.commit()


# --------------------------------------------------------------------------- subscription
PLANS = [
    {
        "tier": SubscriptionTier.FREE,
        "name": "Free",
        "price_monthly_usd": 0,
        "features": [
            "Article summaries & news briefs",
            "Follow companies and topics",
            "Join community discussions",
        ],
    },
    {
        "tier": SubscriptionTier.PREMIUM,
        "name": "Premium",
        "price_monthly_usd": 12,
        "features": [
            "Full deep-dive and analysis articles",
            "Full interview transcripts with timestamps",
            "Portfolio tracking with related coverage",
            "Premium insights from verified analysts",
        ],
    },
]


@router.get("/subscription/plans", tags=["subscription"])
async def list_plans() -> list[dict]:
    return PLANS


@router.post("/subscription/upgrade", response_model=UserMe, tags=["subscription"])
async def upgrade(user: CurrentUser, db: DBSession) -> User:
    """Upgrade to premium. In the MVP this is a mock checkout (see `BILLING_MOCK_ENABLED`)."""
    if not settings.billing_mock_enabled:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Online checkout is not configured yet. Please contact support.",
        )
    user.tier = SubscriptionTier.PREMIUM
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/subscription/cancel", response_model=UserMe, tags=["subscription"])
async def cancel(user: CurrentUser, db: DBSession) -> User:
    user.tier = SubscriptionTier.FREE
    await db.commit()
    await db.refresh(user)
    return user
