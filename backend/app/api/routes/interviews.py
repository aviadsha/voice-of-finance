import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from sqlalchemy import func, select

from app.agents import pipeline
from app.api.deps import AdminUser, AnalystUser, DBSession, PremiumUser
from app.models import Interview, InterviewStatus
from app.schemas import (
    GenerateArticlesRequest,
    InterviewCreate,
    InterviewListItem,
    InterviewOut,
    InterviewWithTranscript,
    Page,
)
from app.services.youtube import InvalidYouTubeURL, canonical_url, extract_video_id

router = APIRouter(prefix="/interviews", tags=["interviews"])

_IN_PROGRESS = {
    InterviewStatus.DOWNLOADING,
    InterviewStatus.TRANSCRIBING,
    InterviewStatus.ANALYZING,
    InterviewStatus.GENERATING,
}


async def _get_interview(db: DBSession, interview_id: uuid.UUID) -> Interview:
    interview = await db.get(Interview, interview_id)
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview


@router.post("", response_model=InterviewOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_interview(
    payload: InterviewCreate, background: BackgroundTasks, user: AnalystUser, db: DBSession
) -> Interview:
    """Queue a YouTube interview for extraction (and, optionally, article generation).

    Restricted to admins and verified analysts because each run consumes paid AI credits.
    """
    try:
        video_id = extract_video_id(payload.youtube_url)
    except InvalidYouTubeURL as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None

    existing = (await db.execute(select(Interview).where(Interview.youtube_video_id == video_id))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "This video has already been submitted", "interview_id": str(existing.id)},
        )
    interview = Interview(youtube_url=canonical_url(video_id), youtube_video_id=video_id, submitted_by_id=user.id)
    db.add(interview)
    await db.commit()
    await db.refresh(interview)
    background.add_task(pipeline.process_interview, interview.id, payload.generate_articles, payload.formats)
    return interview


@router.get("", response_model=Page[InterviewListItem])
async def list_interviews(
    db: DBSession,
    status_filter: InterviewStatus | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> Page[InterviewListItem]:
    query = select(Interview)
    if status_filter is not None:
        query = query.where(Interview.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Interview.created_at.desc()).limit(limit).offset(offset))).scalars()
    return Page[InterviewListItem](
        items=[InterviewListItem.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{interview_id}", response_model=InterviewOut)
async def get_interview(interview_id: uuid.UUID, db: DBSession) -> Interview:
    return await _get_interview(db, interview_id)


@router.get("/{interview_id}/transcript", response_model=InterviewWithTranscript)
async def get_transcript(interview_id: uuid.UUID, _: PremiumUser, db: DBSession) -> Interview:
    """Full timestamped transcript (premium)."""
    return await _get_interview(db, interview_id)


@router.post("/{interview_id}/reprocess", response_model=InterviewOut, status_code=status.HTTP_202_ACCEPTED)
async def reprocess_interview(
    interview_id: uuid.UUID, payload: GenerateArticlesRequest, background: BackgroundTasks, _: AdminUser, db: DBSession
) -> Interview:
    """Re-run the full pipeline (download, transcription, insights, articles)."""
    interview = await _get_interview(db, interview_id)
    if interview.status in _IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interview is currently being processed")
    interview.status = InterviewStatus.PENDING
    await db.commit()
    background.add_task(pipeline.process_interview, interview.id, True, payload.formats)
    return interview


@router.post("/{interview_id}/articles", response_model=InterviewOut, status_code=status.HTTP_202_ACCEPTED)
async def regenerate_articles(
    interview_id: uuid.UUID, payload: GenerateArticlesRequest, background: BackgroundTasks, _: AdminUser, db: DBSession
) -> Interview:
    """(Re)generate articles from an already-transcribed interview."""
    interview = await _get_interview(db, interview_id)
    if not interview.transcript:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interview has not been transcribed yet")
    if interview.status in _IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Interview is currently being processed")
    background.add_task(pipeline.regenerate_articles, interview.id, payload.formats)
    return interview


@router.delete("/{interview_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interview(interview_id: uuid.UUID, _: AdminUser, db: DBSession) -> None:
    interview = await _get_interview(db, interview_id)
    await db.delete(interview)
    await db.commit()
