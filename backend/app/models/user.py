import enum
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin, str_enum


class UserRole(enum.StrEnum):
    USER = "user"
    ANALYST = "analyst"
    ADMIN = "admin"


class SubscriptionTier(enum.StrEnum):
    FREE = "free"
    PREMIUM = "premium"


class FollowType(enum.StrEnum):
    COMPANY = "company"
    TOPIC = "topic"


class User(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(200))
    bio: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(str_enum(UserRole), default=UserRole.USER)
    tier: Mapped[SubscriptionTier] = mapped_column(str_enum(SubscriptionTier), default=SubscriptionTier.FREE)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified_analyst: Mapped[bool] = mapped_column(Boolean, default=False)
    reputation: Mapped[int] = mapped_column(Integer, default=0)

    follows: Mapped[list["Follow"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin", passive_deletes=True
    )

    @property
    def is_premium(self) -> bool:
        return self.tier == SubscriptionTier.PREMIUM or self.role == UserRole.ADMIN

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN


class Follow(UUIDPkMixin, TimestampMixin, Base):
    """A company (ticker) or topic followed by a user."""

    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("user_id", "follow_type", "value", name="uq_follows_user_target"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    follow_type: Mapped[FollowType] = mapped_column(str_enum(FollowType))
    # Normalised value: upper-case ticker for companies, lower-case slug for topics.
    value: Mapped[str] = mapped_column(String(100), index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="follows")


class PortfolioHolding(UUIDPkMixin, TimestampMixin, Base):
    """Premium feature: simple portfolio tracking."""

    __tablename__ = "portfolio_holdings"
    __table_args__ = (UniqueConstraint("user_id", "ticker", name="uq_portfolio_holdings_user_ticker"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    ticker: Mapped[str] = mapped_column(String(20))
    shares: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    notes: Mapped[str | None] = mapped_column(Text)
