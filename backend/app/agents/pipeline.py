"""Orchestrates the agents: extraction -> article generation."""

import logging
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.article_generator import ArticleGenerationAgent
from app.agents.youtube_extractor import YouTubeExtractionAgent
from app.core import database
from app.core.config import settings
from app.models import ArticleFormat, Interview, InterviewStatus
from app.services.ai import JSONLLM, ClaudeClient, Transcriber, WhisperTranscriber
from app.services.youtube import AudioDownloader, YtDlpDownloader

logger = logging.getLogger(__name__)


class AgentFactory:
    """Builds the external clients used by the agents. Swap it out in tests."""

    def llm(self) -> JSONLLM:
        return ClaudeClient()

    def transcriber(self) -> Transcriber:
        return WhisperTranscriber()

    def downloader(self) -> AudioDownloader:
        return YtDlpDownloader(
            max_chunk_mb=settings.whisper_max_chunk_mb,
            chunk_seconds=settings.whisper_chunk_seconds,
        )


agent_factory = AgentFactory()


async def process_interview(
    interview_id: uuid.UUID,
    generate_articles: bool = True,
    formats: list[ArticleFormat] | None = None,
) -> None:
    """Background job: run the full pipeline for a single interview."""
    async with database.SessionLocal() as session:
        try:
            llm = agent_factory.llm()
            extractor = YouTubeExtractionAgent(
                session,
                downloader=agent_factory.downloader(),
                transcriber=agent_factory.transcriber(),
                llm=llm,
                workdir=Path(settings.audio_workdir),
            )
        except Exception as exc:  # e.g. missing API keys
            logger.exception("Could not initialise agents for interview %s", interview_id)
            await _mark_failed(session, interview_id, exc)
            return

        try:
            interview = await extractor.run(interview_id)
        except Exception:
            return  # already logged and marked as failed by the agent

        if generate_articles:
            await generate_articles_for(session, interview, formats, llm)


async def generate_articles_for(
    session: AsyncSession,
    interview: Interview,
    formats: list[ArticleFormat] | None,
    llm: JSONLLM | None = None,
) -> None:
    interview.status = InterviewStatus.GENERATING
    await session.commit()
    try:
        await ArticleGenerationAgent(session, llm or agent_factory.llm()).generate(interview, formats)
    except Exception as exc:
        logger.exception("Article generation failed for interview %s", interview.id)
        await session.rollback()
        await _mark_failed(session, interview.id, exc, prefix="Article generation failed")
        return
    interview.status = InterviewStatus.COMPLETED
    await session.commit()


async def regenerate_articles(interview_id: uuid.UUID, formats: list[ArticleFormat] | None = None) -> None:
    async with database.SessionLocal() as session:
        interview = await session.get(Interview, interview_id)
        if interview is None:
            return
        await generate_articles_for(session, interview, formats)


async def _mark_failed(
    session: AsyncSession, interview_id: uuid.UUID, exc: Exception, prefix: str | None = None
) -> None:
    interview = await session.get(Interview, interview_id)
    if interview is None:
        return
    message = f"{type(exc).__name__}: {exc}"
    interview.status = InterviewStatus.FAILED
    interview.error_message = (f"{prefix}: {message}" if prefix else message)[:2000]
    await session.commit()
