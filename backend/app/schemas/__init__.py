import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import (
    ApplicationStatus,
    ArticleFormat,
    ArticleStatus,
    FollowType,
    InterviewStatus,
    SubscriptionTier,
    UserRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- auth / users
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(ORMModel):
    id: uuid.UUID
    full_name: str | None
    bio: str | None
    role: UserRole
    is_verified_analyst: bool
    reputation: int


class UserMe(UserPublic):
    email: EmailStr
    tier: SubscriptionTier
    is_premium: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    bio: str | None = Field(default=None, max_length=2000)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserMe


class AdminUserUpdate(BaseModel):
    role: UserRole | None = None
    tier: SubscriptionTier | None = None
    is_active: bool | None = None
    is_verified_analyst: bool | None = None


# --------------------------------------------------------------------------- follows
class FollowCreate(BaseModel):
    follow_type: FollowType
    value: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=200)


class FollowOut(ORMModel):
    id: uuid.UUID
    follow_type: FollowType
    value: str
    display_name: str | None
    created_at: datetime


# --------------------------------------------------------------------------- portfolio
class HoldingCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=20)
    shares: Decimal = Field(gt=0)
    average_cost: Decimal | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("ticker")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.strip().upper()


class HoldingOut(ORMModel):
    id: uuid.UUID
    ticker: str
    shares: Decimal
    average_cost: Decimal | None
    notes: str | None
    created_at: datetime


class PortfolioOut(BaseModel):
    holdings: list[HoldingOut]
    total_cost_basis: Decimal
    related_articles: list["ArticleListItem"]


# --------------------------------------------------------------------------- interviews
class InterviewCreate(BaseModel):
    youtube_url: str = Field(min_length=10, max_length=500)
    generate_articles: bool = True
    formats: list[ArticleFormat] = Field(default_factory=lambda: list(ArticleFormat))


class InterviewListItem(ORMModel):
    id: uuid.UUID
    youtube_url: str
    youtube_video_id: str
    status: InterviewStatus
    title: str | None
    channel: str | None
    thumbnail_url: str | None
    duration_seconds: int | None
    published_at: datetime | None
    topics: list
    companies: list
    created_at: datetime


class InterviewOut(InterviewListItem):
    error_message: str | None
    description: str | None
    summary: str | None
    speakers: list
    key_quotes: list
    insights: list
    sentiment: str | None
    processed_at: datetime | None


class InterviewWithTranscript(InterviewOut):
    transcript: str | None
    transcript_segments: list


# --------------------------------------------------------------------------- articles
class ArticleListItem(ORMModel):
    id: uuid.UUID
    slug: str
    format: ArticleFormat
    is_premium: bool
    headline: str
    meta_description: str
    summary: str
    tags: list
    tickers: list
    reading_time_minutes: int
    published_at: datetime | None
    interview_id: uuid.UUID | None
    author: UserPublic | None = None


class ArticleOut(ArticleListItem):
    status: ArticleStatus
    # `None` when the reader is not entitled to the full article (paywall).
    content: str | None
    citations: list
    citation_accuracy: float | None
    view_count: int
    is_locked: bool = False
    source_url: str | None = None
    source_title: str | None = None


class ArticleCreate(BaseModel):
    """Premium author insight written by a verified analyst."""

    headline: str = Field(min_length=5, max_length=300)
    meta_description: str = Field(min_length=10, max_length=320)
    summary: str = Field(min_length=10)
    content: str = Field(min_length=50)
    tags: list[str] = Field(default_factory=list, max_length=20)
    tickers: list[str] = Field(default_factory=list, max_length=20)
    is_premium: bool = True


class ArticleStatusUpdate(BaseModel):
    status: ArticleStatus


class GenerateArticlesRequest(BaseModel):
    formats: list[ArticleFormat] = Field(default_factory=lambda: list(ArticleFormat), min_length=1)


# --------------------------------------------------------------------------- community
class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    parent_id: uuid.UUID | None = None


class CommentOut(ORMModel):
    id: uuid.UUID
    article_id: uuid.UUID
    parent_id: uuid.UUID | None
    body: str
    score: int
    is_deleted: bool
    created_at: datetime
    user: UserPublic
    # The requesting user's vote on this comment (1, -1 or 0); 0 for anonymous readers.
    my_vote: int = 0


class VoteRequest(BaseModel):
    # 1 = upvote, -1 = downvote, 0 = remove vote
    value: int = Field(ge=-1, le=1)


class AnalystApplicationCreate(BaseModel):
    credentials: str = Field(min_length=20, max_length=5000)
    links: str | None = Field(default=None, max_length=2000)


class AnalystApplicationOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID
    credentials: str
    links: str | None
    status: ApplicationStatus
    review_notes: str | None
    created_at: datetime


class AnalystApplicationReview(BaseModel):
    approve: bool
    review_notes: str | None = Field(default=None, max_length=2000)


class LeaderboardEntry(UserPublic):
    pass


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


PortfolioOut.model_rebuild()
