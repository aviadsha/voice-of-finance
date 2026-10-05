import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.agents.community import CommunityAgent
from app.api.deps import AdminUser, CurrentUser, DBSession, OptionalUser
from app.api.routes.articles import get_published_article
from app.models import AnalystApplication, ApplicationStatus, Comment, CommentVote, User
from app.schemas import (
    AnalystApplicationCreate,
    AnalystApplicationOut,
    AnalystApplicationReview,
    CommentCreate,
    CommentOut,
    LeaderboardEntry,
    VoteRequest,
)

router = APIRouter(tags=["community"])


@router.get("/articles/{slug}/comments", response_model=list[CommentOut])
async def list_comments(
    slug: str,
    db: DBSession,
    user: OptionalUser,
    sort: str = Query("top", pattern="^(top|new)$"),
    limit: int = Query(100, ge=1, le=500),
) -> list[CommentOut]:
    article = await get_published_article(db, slug, user)
    order = (Comment.score.desc(), Comment.created_at.asc()) if sort == "top" else (Comment.created_at.desc(),)
    result = await db.execute(select(Comment).where(Comment.article_id == article.id).order_by(*order).limit(limit))
    comments = list(result.unique().scalars().all())
    my_votes: dict[uuid.UUID, int] = {}
    if user is not None and comments:
        votes = await db.execute(
            select(CommentVote.comment_id, CommentVote.value).where(
                CommentVote.user_id == user.id, CommentVote.comment_id.in_([c.id for c in comments])
            )
        )
        my_votes = {comment_id: value for comment_id, value in votes.all()}
    return [_comment_out(c, my_votes.get(c.id, 0)) for c in comments]


def _comment_out(comment: Comment, my_vote: int = 0) -> CommentOut:
    return CommentOut.model_validate(comment).model_copy(update={"my_vote": my_vote})


@router.post("/articles/{slug}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def create_comment(slug: str, payload: CommentCreate, user: CurrentUser, db: DBSession) -> CommentOut:
    article = await get_published_article(db, slug, user)
    return _comment_out(await CommunityAgent(db).add_comment(user, article, payload.body, payload.parent_id))


async def _get_comment(db: DBSession, comment_id: uuid.UUID) -> Comment:
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    return comment


@router.post("/comments/{comment_id}/vote", response_model=CommentOut)
async def vote_comment(comment_id: uuid.UUID, payload: VoteRequest, user: CurrentUser, db: DBSession) -> CommentOut:
    comment = await _get_comment(db, comment_id)
    return _comment_out(await CommunityAgent(db).vote(user, comment, payload.value), payload.value)


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(comment_id: uuid.UUID, user: CurrentUser, db: DBSession) -> None:
    comment = await _get_comment(db, comment_id)
    await CommunityAgent(db).delete_comment(user, comment)


@router.get("/community/leaderboard", response_model=list[LeaderboardEntry])
async def leaderboard(db: DBSession, limit: int = Query(20, ge=1, le=100)) -> list[User]:
    return await CommunityAgent(db).leaderboard(limit)


@router.post(
    "/community/analyst-applications",
    response_model=AnalystApplicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def apply_for_verification(
    payload: AnalystApplicationCreate, user: CurrentUser, db: DBSession
) -> AnalystApplication:
    """Apply to become a verified analyst (requires a minimum community reputation)."""
    return await CommunityAgent(db).apply_for_verification(user, payload.credentials, payload.links)


@router.get("/community/analyst-applications", response_model=list[AnalystApplicationOut])
async def list_applications(
    user: CurrentUser, db: DBSession, status_filter: ApplicationStatus | None = Query(None, alias="status")
) -> list[AnalystApplication]:
    """Admins see all applications; other users see their own."""
    query = select(AnalystApplication).order_by(AnalystApplication.created_at.desc())
    if not user.is_admin:
        query = query.where(AnalystApplication.user_id == user.id)
    if status_filter is not None:
        query = query.where(AnalystApplication.status == status_filter)
    return list((await db.execute(query)).scalars().all())


@router.post("/community/analyst-applications/{application_id}/review", response_model=AnalystApplicationOut)
async def review_application(
    application_id: uuid.UUID, payload: AnalystApplicationReview, admin: AdminUser, db: DBSession
) -> AnalystApplication:
    application = await db.get(AnalystApplication, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return await CommunityAgent(db).review_application(admin, application, payload.approve, payload.review_notes)
