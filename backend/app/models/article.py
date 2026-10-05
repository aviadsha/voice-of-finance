import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONList, JSONType, TimestampMixin, UUIDPkMixin, str_enum


class ArticleFormat(enum.StrEnum):
    SUMMARY = "summary"
    DEEP_DIVE = "deep_dive"
    ANALYSIS = "analysis"


class ArticleStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


# Formats that are only fully readable by premium subscribers.
PREMIUM_FORMATS = frozenset({ArticleFormat.DEEP_DIVE, ArticleFormat.ANALYSIS})


class Article(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (
        # GIN indexes power the JSONB containment (`@>`) filters on tickers/tags.
        Index("ix_articles_tickers_gin", "tickers", postgresql_using="gin"),
        Index("ix_articles_tags_gin", "tags", postgresql_using="gin"),
    )

    interview_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interviews.id", ondelete="CASCADE"), index=True)
    # Set for human-authored "premium author insights" (verified analysts).
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)

    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    format: Mapped[ArticleFormat] = mapped_column(str_enum(ArticleFormat), index=True)
    status: Mapped[ArticleStatus] = mapped_column(str_enum(ArticleStatus), default=ArticleStatus.PUBLISHED, index=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    headline: Mapped[str] = mapped_column(String(300))
    meta_description: Mapped[str] = mapped_column(String(320))
    # Teaser/summary always visible to everyone (free tier).
    summary: Mapped[str] = mapped_column(Text)
    # Full Markdown body; gated for premium articles.
    content: Mapped[str] = mapped_column(Text)
    # [{"quote": str, "timestamp": float | None, "url": str, "verified": bool, "speaker": str | None}]
    citations: Mapped[JSONList] = mapped_column(JSONType, default=list)
    tags: Mapped[JSONList] = mapped_column(JSONType, default=list)
    tickers: Mapped[JSONList] = mapped_column(JSONType, default=list)
    # Ratio (0-1) of citations that were verified verbatim against the transcript.
    citation_accuracy: Mapped[float | None] = mapped_column()
    ai_model: Mapped[str | None] = mapped_column(String(100))
    reading_time_minutes: Mapped[int] = mapped_column(Integer, default=1)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    interview: Mapped["Interview | None"] = relationship(back_populates="articles")  # noqa: F821
    author: Mapped["User | None"] = relationship(lazy="joined")  # noqa: F821
