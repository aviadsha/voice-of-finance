"""Agent 2 - Article generation with Claude.

Turns an extracted interview into publishable articles in several formats, with
SEO headline/meta description and source citations that are verified against
the original transcript (with deep links to the exact YouTube timestamp).
"""

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from slugify import slugify
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.text_utils import (
    TranscriptIndex,
    normalize_ticker,
    normalize_topic,
    parse_timestamp,
    reading_time_minutes,
    transcript_for_prompt,
)
from app.core.config import settings
from app.models import PREMIUM_FORMATS, Article, ArticleFormat, ArticleStatus, Interview
from app.services.ai import JSONLLM
from app.services.youtube import timestamp_url

logger = logging.getLogger(__name__)

ARTICLE_SYSTEM_PROMPT = """You are an award-winning financial journalist writing for "Voice of Finance". \
You write clear, engaging, rigorously factual articles based ONLY on the supplied interview \
transcript and extracted insights.

Hard rules:
1. Do not invent numbers, facts, forecasts or quotes. If something is not in the transcript, do not state it.
2. Attribute every opinion or forecast to the person who said it.
3. Every direct quote in the article must be copied verbatim from the transcript and listed in "citations".
4. This is journalism, not investment advice. Never tell readers to buy or sell.
5. Write in Markdown. Use "##" section headings. Do not include the headline in the body.
6. Respond with a single JSON object and nothing else."""

FORMAT_GUIDES: dict[ArticleFormat, str] = {
    ArticleFormat.SUMMARY: (
        "SUMMARY - a 300-500 word news brief. Open with the single most newsworthy point, "
        "follow with a '## Key Takeaways' bullet list (4-6 bullets) and a short closing paragraph."
    ),
    ArticleFormat.DEEP_DIVE: (
        "DEEP-DIVE - a 1200-1800 word feature. Provide background, walk through each major theme of "
        "the interview in its own section, weave in direct quotes, and end with '## What to Watch'."
    ),
    ArticleFormat.ANALYSIS: (
        "ANALYSIS - a 900-1400 word market analysis. Cover '## The Thesis', '## Bull Case', '## Bear Case', "
        "'## Market Implications' (sectors / tickers affected) and '## Risks'. Clearly separate what the "
        "speaker said from your own analytical framing."
    ),
}

ARTICLE_PROMPT_TEMPLATE = """Write an article in the following format:
{format_guide}

SOURCE
Title: {title}
Channel: {channel}
Published: {published}
Speakers: {speakers}

EXTRACTED INSIGHTS (JSON)
{insights}

Return a JSON object with exactly these keys:
{{
  "headline": "compelling, accurate headline, max 90 characters, no clickbait",
  "meta_description": "SEO meta description, 120-155 characters",
  "summary": "2-3 sentence teaser shown to all readers",
  "content": "full article body in Markdown",
  "citations": [{{"quote": "verbatim transcript quote used in the article", "speaker": "name or null", \
"timestamp": "mm:ss marker from the transcript or null"}}],
  "tags": ["3-8 topic tags"],
  "tickers": ["stock tickers discussed, e.g. NVDA"]
}}

TRANSCRIPT (with [mm:ss] markers):
{transcript}
"""


def _truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


class ArticleGenerationAgent:
    def __init__(self, session: AsyncSession, llm: JSONLLM) -> None:
        self.session = session
        self.llm = llm

    async def generate(
        self,
        interview: Interview,
        formats: list[ArticleFormat] | None = None,
        publish: bool = True,
    ) -> list[Article]:
        if not interview.transcript:
            raise ValueError("Interview has no transcript; run the extraction agent first")
        formats = list(dict.fromkeys(formats or list(ArticleFormat)))
        articles: list[Article] = []
        for article_format in formats:
            data = await self.llm.complete_json(ARTICLE_SYSTEM_PROMPT, self._build_prompt(interview, article_format))
            article = await self._build_article(interview, article_format, data, publish)
            # Regenerating replaces the previous article of the same format.
            await self.session.execute(
                delete(Article).where(Article.interview_id == interview.id, Article.format == article_format)
            )
            self.session.add(article)
            await self.session.flush()
            articles.append(article)
            logger.info("Generated %s article '%s' for interview %s", article_format, article.headline, interview.id)
        await self.session.commit()
        return articles

    def _build_prompt(self, interview: Interview, article_format: ArticleFormat) -> str:
        insights = {
            "summary": interview.summary,
            "topics": [t.get("name") for t in interview.topics or [] if isinstance(t, dict)],
            "companies": interview.companies,
            "key_quotes": [
                {k: q.get(k) for k in ("quote", "speaker", "context")}
                for q in interview.key_quotes or []
                if q.get("verified")
            ],
            "insights": interview.insights,
            "sentiment": interview.sentiment,
        }
        speakers = ", ".join(
            f"{s.get('name')} ({s.get('role')})" if s.get("role") else str(s.get("name"))
            for s in interview.speakers or []
        )
        return ARTICLE_PROMPT_TEMPLATE.format(
            format_guide=FORMAT_GUIDES[article_format],
            title=interview.title or "Unknown",
            channel=interview.channel or "Unknown",
            published=interview.published_at.date().isoformat() if interview.published_at else "Unknown",
            speakers=speakers or "Unknown",
            insights=json.dumps(insights, ensure_ascii=False, indent=2),
            transcript=transcript_for_prompt(
                interview.transcript_segments, interview.transcript, settings.transcript_max_chars_for_llm
            ),
        )

    async def _build_article(
        self, interview: Interview, article_format: ArticleFormat, data: dict[str, Any], publish: bool
    ) -> Article:
        headline = _truncate(str(data.get("headline") or interview.title or "Untitled interview"), 300)
        content = str(data.get("content") or "").strip()
        if not content:
            raise ValueError(f"Model returned an empty {article_format} article")
        summary = str(data.get("summary") or interview.summary or "").strip() or _truncate(content, 400)
        meta = _truncate(str(data.get("meta_description") or summary), 160)

        citations = self.verify_citations(interview, data.get("citations"))
        verified = sum(1 for c in citations if c["verified"])

        tickers = {normalize_ticker(str(t)) for t in data.get("tickers") or [] if t}
        tickers |= {c["ticker"] for c in interview.companies or [] if isinstance(c, dict) and c.get("ticker")}
        tags = {normalize_topic(str(t)) for t in data.get("tags") or [] if t}
        tags |= {t["slug"] for t in interview.topics or [] if isinstance(t, dict) and t.get("slug")}

        now = datetime.now(UTC)
        return Article(
            id=uuid.uuid4(),
            interview_id=interview.id,
            slug=await self._unique_slug(headline),
            format=article_format,
            status=ArticleStatus.PUBLISHED if publish else ArticleStatus.DRAFT,
            is_premium=article_format in PREMIUM_FORMATS,
            headline=headline,
            meta_description=meta,
            summary=summary,
            content=content,
            citations=citations,
            citation_accuracy=round(verified / len(citations), 3) if citations else None,
            tags=sorted(t for t in tags if t)[:12],
            tickers=sorted(t for t in tickers if t)[:12],
            ai_model=getattr(self.llm, "model", None),
            reading_time_minutes=reading_time_minutes(content),
            published_at=now if publish else None,
        )

    @staticmethod
    def verify_citations(interview: Interview, raw: Any) -> list[dict[str, Any]]:
        """Check each citation against the transcript and attach a timestamped source link."""
        index = TranscriptIndex(interview.transcript_segments or [], interview.transcript)
        citations: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, str):
                item = {"quote": item}
            if not isinstance(item, dict):
                continue
            quote = str(item.get("quote") or "").strip()
            if not quote or quote in seen:
                continue
            seen.add(quote)
            verified, located_at = index.locate(quote)
            timestamp = located_at if located_at is not None else parse_timestamp(item.get("timestamp"))
            citations.append(
                {
                    "quote": quote,
                    "speaker": item.get("speaker"),
                    "timestamp": timestamp,
                    "url": timestamp_url(interview.youtube_video_id, timestamp),
                    "verified": verified,
                }
            )
        return citations

    async def _unique_slug(self, headline: str) -> str:
        base = slugify(headline, max_length=80, word_boundary=True) or "article"
        slug = base
        while (await self.session.execute(select(Article.id).where(Article.slug == slug))).first():
            slug = f"{base}-{uuid.uuid4().hex[:6]}"
        return slug
