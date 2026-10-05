import enum
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPkMixin, str_enum


class Comment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "comments"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    moderation_reason: Mapped[str | None] = mapped_column(String(300))

    user: Mapped["User"] = relationship(lazy="joined")  # noqa: F821


class CommentVote(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "comment_votes"
    __table_args__ = (
        UniqueConstraint("comment_id", "user_id", name="uq_comment_votes_comment_user"),
        CheckConstraint("value IN (-1, 1)", name="value_is_plus_minus_one"),
    )

    comment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("comments.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    value: Mapped[int] = mapped_column(Integer)


class ApplicationStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class AnalystApplication(UUIDPkMixin, TimestampMixin, Base):
    """A request from a community member to become a verified analyst."""

    __tablename__ = "analyst_applications"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    credentials: Mapped[str] = mapped_column(Text)
    links: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ApplicationStatus] = mapped_column(
        str_enum(ApplicationStatus), default=ApplicationStatus.PENDING, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    review_notes: Mapped[str | None] = mapped_column(Text)
