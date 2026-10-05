"""Agent 1 - YouTube interview extraction.

Pipeline: YouTube URL -> metadata + audio (yt-dlp/ffmpeg) -> transcript (Whisper)
-> topics, quotes, insights, companies (Claude) -> database.
"""

import logging
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.text_utils import (
    TranscriptIndex,
    normalize_ticker,
    normalize_topic,
    parse_timestamp,
    transcript_for_prompt,
)
from app.core.config import settings
from app.models import Interview, InterviewStatus
from app.services.ai import JSONLLM, Transcriber
from app.services.youtube import AudioDownloader

logger = logging.getLogger(__name__)

INSIGHTS_SYSTEM_PROMPT = """You are a senior financial research analyst. You read transcripts of \
finance-related interviews (podcasts, TV interviews, earnings discussions) and extract structured, \
factual intelligence. Never invent facts that are not in the transcript. Quotes MUST be copied \
verbatim from the transcript. Respond with a single JSON object and nothing else."""

INSIGHTS_PROMPT_TEMPLATE = """Analyse the following interview transcript.

Video title: {title}
Channel: {channel}
Published: {published}

Return a JSON object with exactly these keys:
{{
  "summary": "3-5 sentence neutral summary of the interview",
  "speakers": [{{"name": "string", "role": "e.g. CEO of X / host / economist"}}],
  "topics": ["short topic names, e.g. 'Interest Rates', 'AI Semiconductors'"],
  "companies": [{{"name": "Company name", "ticker": "TICKER or null"}}],
  "key_quotes": [{{"quote": "verbatim quote from transcript", "speaker": "name or null", \
"timestamp": "mm:ss from the transcript marker or null", "context": "why it matters"}}],
  "insights": [{{"insight": "actionable or notable insight", "category": "macro|company|sector|market|policy|other", \
"confidence": "high|medium|low"}}],
  "sentiment": "bullish|bearish|neutral|mixed"
}}

Guidelines:
- Up to 10 topics, 10 key quotes and 10 insights, ordered by importance.
- Only include companies that are explicitly discussed.
- Quotes must be exact substrings of the transcript (ignore the [mm:ss] markers).

TRANSCRIPT:
{transcript}
"""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


class YouTubeExtractionAgent:
    def __init__(
        self,
        session: AsyncSession,
        downloader: AudioDownloader,
        transcriber: Transcriber,
        llm: JSONLLM,
        workdir: Path | None = None,
    ) -> None:
        self.session = session
        self.downloader = downloader
        self.transcriber = transcriber
        self.llm = llm
        self.workdir = workdir or Path(settings.audio_workdir)

    async def _set_status(self, interview: Interview, status: InterviewStatus) -> None:
        interview.status = status
        await self.session.commit()

    async def run(self, interview_id: uuid.UUID) -> Interview:
        interview = await self.session.get(Interview, interview_id)
        if interview is None:
            raise LookupError(f"Interview {interview_id} not found")

        job_dir = self.workdir / str(interview.id)
        try:
            interview.error_message = None
            await self._set_status(interview, InterviewStatus.DOWNLOADING)

            metadata = await self.downloader.fetch_metadata(interview.youtube_video_id)
            if metadata.duration_seconds and metadata.duration_seconds > settings.max_video_duration_seconds:
                raise ValueError(
                    f"Video is too long ({metadata.duration_seconds}s > {settings.max_video_duration_seconds}s)"
                )
            self._apply_metadata(interview, metadata)
            await self.session.commit()

            audio = await self.downloader.download_audio(interview.youtube_video_id, job_dir)
            await self._set_status(interview, InterviewStatus.TRANSCRIBING)
            await self._transcribe(interview, audio.chunks)

            await self._set_status(interview, InterviewStatus.ANALYZING)
            await self._extract_insights(interview)

            interview.status = InterviewStatus.COMPLETED
            interview.processed_at = datetime.now(UTC)
            await self.session.commit()
            logger.info("Interview %s extracted (%s)", interview.id, interview.title)
            return interview
        except Exception as exc:
            logger.exception("Extraction failed for interview %s", interview_id)
            await self.session.rollback()
            interview = await self.session.get(Interview, interview_id)
            if interview is not None:
                interview.status = InterviewStatus.FAILED
                interview.error_message = f"{type(exc).__name__}: {exc}"[:2000]
                await self.session.commit()
            raise
        finally:
            shutil.rmtree(job_dir, ignore_errors=True)

    @staticmethod
    def _apply_metadata(interview: Interview, metadata: Any) -> None:
        interview.title = metadata.title or interview.title
        interview.channel = metadata.channel
        interview.description = metadata.description
        interview.thumbnail_url = metadata.thumbnail_url
        interview.duration_seconds = metadata.duration_seconds
        interview.published_at = metadata.published_at
        interview.extra_metadata = {**(interview.extra_metadata or {}), "youtube_tags": metadata.tags}

    async def _transcribe(self, interview: Interview, chunks: list[tuple[Path, float]]) -> None:
        texts: list[str] = []
        segments: list[dict[str, Any]] = []
        language: str | None = None
        # Prime Whisper with the title for better spelling of names/tickers.
        prompt = interview.title
        for path, offset in chunks:
            result = await self.transcriber.transcribe(path, prompt=prompt)
            language = language or result.get("language")
            texts.append(result.get("text", "").strip())
            for segment in result.get("segments", []):
                segments.append(
                    {
                        "start": round(float(segment["start"]) + offset, 2),
                        "end": round(float(segment["end"]) + offset, 2),
                        "text": segment["text"],
                    }
                )
        interview.transcript = "\n".join(t for t in texts if t)
        interview.transcript_segments = segments
        interview.language = language
        await self.session.commit()

    async def _extract_insights(self, interview: Interview) -> None:
        if not interview.transcript:
            raise ValueError("Transcript is empty - nothing to analyse")
        prompt = INSIGHTS_PROMPT_TEMPLATE.format(
            title=interview.title or "Unknown",
            channel=interview.channel or "Unknown",
            published=interview.published_at.date().isoformat() if interview.published_at else "Unknown",
            transcript=transcript_for_prompt(
                interview.transcript_segments, interview.transcript, settings.transcript_max_chars_for_llm
            ),
        )
        data = await self.llm.complete_json(INSIGHTS_SYSTEM_PROMPT, prompt)
        self.apply_insights(interview, data)

    @staticmethod
    def apply_insights(interview: Interview, data: dict[str, Any]) -> None:
        """Normalise the model output and verify quotes against the transcript."""
        index = TranscriptIndex(interview.transcript_segments or [], interview.transcript)

        quotes: list[dict[str, Any]] = []
        for item in _as_list(data.get("key_quotes")):
            if not isinstance(item, dict) or not str(item.get("quote", "")).strip():
                continue
            quote = str(item["quote"]).strip()
            verified, located_at = index.locate(quote)
            quotes.append(
                {
                    "quote": quote,
                    "speaker": item.get("speaker"),
                    "timestamp": located_at if located_at is not None else parse_timestamp(item.get("timestamp")),
                    "context": item.get("context"),
                    "verified": verified,
                }
            )
        # Verified quotes first.
        quotes.sort(key=lambda q: not q["verified"])

        companies: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in _as_list(data.get("companies")):
            if isinstance(item, str):
                item = {"name": item, "ticker": None}
            if not isinstance(item, dict) or not item.get("name"):
                continue
            ticker = normalize_ticker(str(item["ticker"])) if item.get("ticker") else None
            key = ticker or str(item["name"]).lower()
            if key in seen:
                continue
            seen.add(key)
            companies.append({"name": str(item["name"]), "ticker": ticker})

        topics = []
        for topic in _as_list(data.get("topics")):
            if isinstance(topic, str) and topic.strip() and normalize_topic(topic):
                topics.append({"name": topic.strip(), "slug": normalize_topic(topic)})

        interview.summary = str(data.get("summary") or "").strip() or None
        interview.speakers = [s for s in _as_list(data.get("speakers")) if isinstance(s, dict)]
        interview.topics = topics[:10]
        interview.companies = companies[:20]
        interview.key_quotes = quotes[:10]
        interview.insights = [i for i in _as_list(data.get("insights")) if isinstance(i, dict)][:10]
        sentiment = str(data.get("sentiment") or "").lower()
        interview.sentiment = sentiment if sentiment in {"bullish", "bearish", "neutral", "mixed"} else None
