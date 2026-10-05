"""Agent 3 - Community management.

Handles comment moderation, voting, reputation, verified-analyst workflow and
personalised feeds based on followed companies/topics.
"""

import logging
import re
import uuid
from dataclasses import dataclass

from sqlalchemy import String, cast, or_, select, type_coerce
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    AnalystApplication,
    ApplicationStatus,
    Article,
    ArticleStatus,
    Comment,
    CommentVote,
    FollowType,
    User,
    UserRole,
)

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_REPEATED_CHARS_RE = re.compile(r"(.)\1{9,}")
# Classic financial-spam / pump-and-dump patterns.
_SPAM_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"guaranteed\s+(returns?|profits?|gains?)",
        r"\b\d{2,}\s*%\s*(daily|per\s+day|a\s+day)\b",
        r"(dm|message|whats\s*app|telegram)\s+me",
        r"\bpump\b.*\bto the moon\b",
        r"send\s+(btc|eth|crypto|usdt)",
        r"(double|triple)\s+your\s+(money|investment)",
    )
]


class CommunityError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class ModerationResult:
    allowed: bool
    flagged: bool = False
    reason: str | None = None


def moderate_text(body: str) -> ModerationResult:
    """Fast, deterministic moderation. Rejects obvious spam, flags borderline content."""
    text = body.strip()
    if not text:
        return ModerationResult(False, reason="Comment is empty")
    for pattern in _SPAM_PATTERNS:
        if pattern.search(text):
            return ModerationResult(False, reason="Comment looks like financial spam or a scam")
    if len(_URL_RE.findall(text)) > 3:
        return ModerationResult(False, reason="Too many links")
    letters = [c for c in text if c.isalpha()]
    if len(letters) >= 30 and sum(c.isupper() for c in letters) / len(letters) > 0.8:
        return ModerationResult(True, flagged=True, reason="Excessive capitalisation")
    if _REPEATED_CHARS_RE.search(text):
        return ModerationResult(True, flagged=True, reason="Repeated characters")
    return ModerationResult(True)


def json_array_contains(column, value: str, dialect_name: str):  # type: ignore[no-untyped-def]
    """Portable "JSON array contains string" filter (JSONB @> on Postgres)."""
    if dialect_name == "postgresql":
        return type_coerce(column, JSONB).contains([value])
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace('"', "")
    return cast(column, String).like(f'%"{escaped}"%', escape="\\")


class CommunityAgent:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ reputation
    async def _adjust_reputation(self, user_id: uuid.UUID, delta: int) -> None:
        if delta == 0:
            return
        user = await self.session.get(User, user_id)
        if user is not None:
            user.reputation = max(0, user.reputation + delta)

    @staticmethod
    def can_apply_for_verification(user: User) -> bool:
        return not user.is_verified_analyst and user.reputation >= settings.analyst_verification_threshold

    # ------------------------------------------------------------------ comments
    async def add_comment(self, user: User, article: Article, body: str, parent_id: uuid.UUID | None = None) -> Comment:
        result = moderate_text(body)
        if not result.allowed:
            raise CommunityError(result.reason or "Comment rejected by moderation", 422)
        if parent_id is not None:
            parent = await self.session.get(Comment, parent_id)
            if parent is None or parent.article_id != article.id or parent.is_deleted:
                raise CommunityError("Parent comment not found", 404)
        comment = Comment(
            article_id=article.id,
            user_id=user.id,
            parent_id=parent_id,
            body=body.strip(),
            is_flagged=result.flagged,
            moderation_reason=result.reason,
        )
        self.session.add(comment)
        await self._adjust_reputation(user.id, settings.reputation_per_comment)
        await self.session.commit()
        await self.session.refresh(comment, attribute_names=["user"])
        return comment

    async def delete_comment(self, actor: User, comment: Comment) -> None:
        if comment.user_id != actor.id and not actor.is_admin:
            raise CommunityError("You can only delete your own comments", 403)
        comment.is_deleted = True
        comment.body = "[deleted]"
        await self.session.commit()

    async def vote(self, voter: User, comment: Comment, value: int) -> Comment:
        if value not in (-1, 0, 1):
            raise CommunityError("Vote must be -1, 0 or 1")
        if comment.user_id == voter.id:
            raise CommunityError("You cannot vote on your own comment", 403)
        if comment.is_deleted:
            raise CommunityError("Cannot vote on a deleted comment")

        existing = (
            await self.session.execute(
                select(CommentVote).where(CommentVote.comment_id == comment.id, CommentVote.user_id == voter.id)
            )
        ).scalar_one_or_none()
        previous = existing.value if existing else 0
        if previous == value:
            return comment

        if existing is not None and value == 0:
            await self.session.delete(existing)
        elif existing is not None:
            existing.value = value
        else:
            self.session.add(CommentVote(comment_id=comment.id, user_id=voter.id, value=value))

        comment.score += value - previous
        await self._adjust_reputation(comment.user_id, self._reputation_for(value) - self._reputation_for(previous))
        await self.session.commit()
        await self.session.refresh(comment)
        return comment

    @staticmethod
    def _reputation_for(vote: int) -> int:
        if vote > 0:
            return settings.reputation_per_upvote
        if vote < 0:
            return settings.reputation_per_downvote
        return 0

    # ------------------------------------------------------------------ verified analysts
    async def apply_for_verification(self, user: User, credentials: str, links: str | None) -> AnalystApplication:
        if user.is_verified_analyst:
            raise CommunityError("You are already a verified analyst", 409)
        if not self.can_apply_for_verification(user):
            raise CommunityError(
                f"At least {settings.analyst_verification_threshold} reputation is required to apply", 403
            )
        pending = (
            await self.session.execute(
                select(AnalystApplication.id).where(
                    AnalystApplication.user_id == user.id,
                    AnalystApplication.status == ApplicationStatus.PENDING,
                )
            )
        ).first()
        if pending:
            raise CommunityError("You already have a pending application", 409)
        application = AnalystApplication(user_id=user.id, credentials=credentials, links=links)
        self.session.add(application)
        await self.session.commit()
        return application

    async def review_application(
        self, reviewer: User, application: AnalystApplication, approve: bool, notes: str | None
    ) -> AnalystApplication:
        if not reviewer.is_admin:
            raise CommunityError("Only admins can review applications", 403)
        if application.status != ApplicationStatus.PENDING:
            raise CommunityError("Application has already been reviewed", 409)
        application.status = ApplicationStatus.APPROVED if approve else ApplicationStatus.REJECTED
        application.reviewer_id = reviewer.id
        application.review_notes = notes
        if approve:
            user = await self.session.get(User, application.user_id)
            if user is not None:
                user.is_verified_analyst = True
                if user.role == UserRole.USER:
                    user.role = UserRole.ANALYST
        await self.session.commit()
        return application

    async def leaderboard(self, limit: int = 20) -> list[User]:
        result = await self.session.execute(
            select(User)
            .where(User.is_active.is_(True))
            .order_by(User.reputation.desc(), User.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------ personalised feed
    async def personalised_feed(self, user: User, limit: int = 20, offset: int = 0) -> list[Article]:
        conditions = []
        dialect = self.session.bind.dialect.name
        for follow in user.follows:
            column = Article.tickers if follow.follow_type == FollowType.COMPANY else Article.tags
            conditions.append(json_array_contains(column, follow.value, dialect))
        if not conditions:
            return []
        result = await self.session.execute(
            select(Article)
            .where(Article.status == ArticleStatus.PUBLISHED, or_(*conditions))
            .order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.unique().scalars().all())
