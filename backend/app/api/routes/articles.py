import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from slugify import slugify
from sqlalchemy import func, select, update

from app.agents.community import json_array_contains
from app.agents.text_utils import normalize_ticker, normalize_topic, reading_time_minutes
from app.api.deps import AdminUser, AnalystUser, DBSession, OptionalUser
from app.models import Article, ArticleFormat, ArticleStatus, Interview, User
from app.schemas import ArticleCreate, ArticleListItem, ArticleOut, ArticleStatusUpdate, Page

router = APIRouter(prefix="/articles", tags=["articles"])


def can_read_full(article: Article, user: User | None) -> bool:
    """Freemium rule: free articles for everyone, premium articles for premium members (and their author)."""
    if not article.is_premium:
        return True
    if user is None:
        return False
    return user.is_premium or article.author_id == user.id


async def get_published_article(db: DBSession, slug: str, user: User | None = None) -> Article:
    article = (await db.execute(select(Article).where(Article.slug == slug))).unique().scalar_one_or_none()
    visible = article is not None and (
        article.status == ArticleStatus.PUBLISHED
        or (user is not None and (user.is_admin or article.author_id == user.id))
    )
    if not visible:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return article


def serialize_article(article: Article, user: User | None, interview: Interview | None = None) -> ArticleOut:
    entitled = can_read_full(article, user)
    data = ArticleOut.model_validate(article, from_attributes=True).model_dump()
    data.update(
        content=article.content if entitled else None,
        # Citations are always shown for transparency; premium readers get the full list.
        citations=article.citations if entitled else article.citations[:2],
        is_locked=not entitled,
        source_url=interview.watch_url if interview else None,
        source_title=interview.title if interview else None,
    )
    return ArticleOut.model_validate(data)


@router.get("", response_model=Page[ArticleListItem])
async def list_articles(
    db: DBSession,
    format: ArticleFormat | None = None,
    ticker: str | None = Query(None, max_length=20),
    tag: str | None = Query(None, max_length=60),
    premium: bool | None = None,
    interview_id: uuid.UUID | None = None,
    q: str | None = Query(None, max_length=200, description="Search in headlines"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[ArticleListItem]:
    query = select(Article).where(Article.status == ArticleStatus.PUBLISHED)
    dialect = db.bind.dialect.name
    if format is not None:
        query = query.where(Article.format == format)
    if premium is not None:
        query = query.where(Article.is_premium.is_(premium))
    if interview_id is not None:
        query = query.where(Article.interview_id == interview_id)
    if ticker:
        normalized = normalize_ticker(ticker)
        if normalized is None:
            raise HTTPException(status_code=422, detail="Invalid ticker symbol")
        query = query.where(json_array_contains(Article.tickers, normalized, dialect))
    if tag:
        query = query.where(json_array_contains(Article.tags, normalize_topic(tag), dialect))
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.where(Article.headline.ilike(f"%{escaped}%", escape="\\"))

    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (
        (
            await db.execute(
                query.order_by(Article.published_at.desc().nullslast(), Article.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .unique()
        .scalars()
    )
    return Page[ArticleListItem](
        items=[ArticleListItem.model_validate(a) for a in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{slug}", response_model=ArticleOut)
async def read_article(slug: str, db: DBSession, user: OptionalUser) -> ArticleOut:
    """Full article. Premium content is replaced by a paywall (`is_locked=true`) for free readers."""
    article = await get_published_article(db, slug, user)
    await db.execute(update(Article).where(Article.id == article.id).values(view_count=Article.view_count + 1))
    await db.commit()
    await db.refresh(article)
    interview = await db.get(Interview, article.interview_id) if article.interview_id else None
    return serialize_article(article, user, interview)


@router.post("", response_model=ArticleOut, status_code=status.HTTP_201_CREATED)
async def create_author_article(payload: ArticleCreate, author: AnalystUser, db: DBSession) -> ArticleOut:
    """Publish a premium author insight (verified analysts and admins)."""
    base = slugify(payload.headline, max_length=80, word_boundary=True) or "insight"
    slug = base
    while (await db.execute(select(Article.id).where(Article.slug == slug))).first():
        slug = f"{base}-{uuid.uuid4().hex[:6]}"
    article = Article(
        slug=slug,
        author_id=author.id,
        format=ArticleFormat.ANALYSIS,
        status=ArticleStatus.PUBLISHED,
        is_premium=payload.is_premium,
        headline=payload.headline.strip(),
        meta_description=payload.meta_description.strip(),
        summary=payload.summary.strip(),
        content=payload.content.strip(),
        citations=[],
        tags=sorted({t for t in (normalize_topic(x) for x in payload.tags) if t}),
        tickers=sorted({t for t in (normalize_ticker(x) for x in payload.tickers) if t}),
        reading_time_minutes=reading_time_minutes(payload.content),
        published_at=datetime.now(UTC),
    )
    db.add(article)
    await db.commit()
    article = await get_published_article(db, slug, author)
    return serialize_article(article, author)


@router.post("/{slug}/status", response_model=ArticleOut, tags=["admin"])
async def set_article_status(slug: str, payload: ArticleStatusUpdate, admin: AdminUser, db: DBSession) -> ArticleOut:
    new_status = payload.status
    article = await get_published_article(db, slug, admin)
    article.status = new_status
    if new_status == ArticleStatus.PUBLISHED and article.published_at is None:
        article.published_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(article)
    return serialize_article(article, admin)
