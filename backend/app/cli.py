"""Command line utilities.

python -m app.cli create-admin admin@example.com 'S3cure-passw0rd'
python -m app.cli ingest https://www.youtube.com/watch?v=VIDEO_ID --formats summary analysis
python -m app.cli seed            # demo content, no API keys required
"""

import argparse
import asyncio
import getpass
import sys
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.agents import pipeline
from app.core import database
from app.core.security import hash_password
from app.models import Article, ArticleFormat, ArticleStatus, Interview, InterviewStatus, User, UserRole
from app.services.youtube import canonical_url, extract_video_id, timestamp_url


async def create_admin(email: str, password: str) -> None:
    async with database.SessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if user is None:
            user = User(email=email.lower(), hashed_password=hash_password(password), full_name="Admin")
            session.add(user)
        else:
            user.hashed_password = hash_password(password)
        user.role = UserRole.ADMIN
        user.is_verified_analyst = True
        await session.commit()
        print(f"Admin user ready: {email}")


async def ingest(url: str, formats: list[ArticleFormat] | None, generate: bool) -> int:
    video_id = extract_video_id(url)
    async with database.SessionLocal() as session:
        interview = (
            await session.execute(select(Interview).where(Interview.youtube_video_id == video_id))
        ).scalar_one_or_none()
        if interview is None:
            interview = Interview(youtube_url=canonical_url(video_id), youtube_video_id=video_id)
            session.add(interview)
            await session.commit()
        interview_id = interview.id
    print(f"Processing interview {interview_id} ({video_id}) ...")
    await pipeline.process_interview(interview_id, generate, formats)
    async with database.SessionLocal() as session:
        interview = await session.get(Interview, interview_id)
        print(f"Status: {interview.status}")
        if interview.error_message:
            print(f"Error: {interview.error_message}", file=sys.stderr)
            return 1
        articles = (await session.execute(select(Article).where(Article.interview_id == interview_id))).unique()
        for article in articles.scalars():
            print(f"  [{article.format}] {article.headline} -> /articles/{article.slug}")
    return 0


SEED_SEGMENTS = [
    (0, "Welcome back to the show. Today we are talking about interest rates, inflation and AI chips."),
    (12, "Inflation has come down a lot, but the last mile is always the hardest part."),
    (25, "I think the Fed will cut rates slowly, maybe two times next year, not more."),
    (41, "On semiconductors, demand for AI accelerators is still far ahead of supply."),
    (58, "Nvidia remains the leader, but margins will normalise as competition catches up."),
    (75, "For investors the biggest risk is concentration in a handful of mega cap stocks."),
]


async def seed() -> None:
    """Insert a demo interview with articles so the UI works without AI credentials."""
    async with database.SessionLocal() as session:
        video_id = "dQw4w9WgXcQ"
        if (await session.execute(select(Interview.id).where(Interview.youtube_video_id == video_id))).first():
            print("Seed data already present")
            return
        segments = [{"start": float(s), "end": float(s + 12), "text": t} for s, t in SEED_SEGMENTS]
        now = datetime.now(UTC)
        interview = Interview(
            youtube_url=canonical_url(video_id),
            youtube_video_id=video_id,
            status=InterviewStatus.COMPLETED,
            title="Demo: The Fed, Inflation and the AI Chip Boom",
            channel="Voice of Finance Demo",
            thumbnail_url=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            duration_seconds=90,
            published_at=now - timedelta(days=1),
            language="en",
            transcript=" ".join(t for _, t in SEED_SEGMENTS),
            transcript_segments=segments,
            summary="A strategist discusses inflation, expected Fed rate cuts and the AI semiconductor cycle.",
            speakers=[{"name": "Demo Strategist", "role": "Chief Market Strategist"}],
            topics=[
                {"name": "Interest Rates", "slug": "interest-rates"},
                {"name": "Inflation", "slug": "inflation"},
                {"name": "Semiconductors", "slug": "semiconductors"},
            ],
            companies=[{"name": "Nvidia", "ticker": "NVDA"}],
            key_quotes=[
                {"quote": SEED_SEGMENTS[2][1], "speaker": "Demo Strategist", "timestamp": 25.0, "verified": True},
                {"quote": SEED_SEGMENTS[4][1], "speaker": "Demo Strategist", "timestamp": 58.0, "verified": True},
            ],
            insights=[
                {"insight": "Expect a slow, shallow rate-cut cycle.", "category": "macro", "confidence": "medium"},
                {"insight": "AI accelerator demand still exceeds supply.", "category": "sector", "confidence": "high"},
            ],
            sentiment="mixed",
            processed_at=now,
        )
        session.add(interview)
        await session.flush()

        def citation(index: int) -> dict:
            start, quote = SEED_SEGMENTS[index]
            return {
                "quote": quote,
                "speaker": "Demo Strategist",
                "timestamp": float(start),
                "url": timestamp_url(video_id, start),
                "verified": True,
            }

        common = {
            "interview_id": interview.id,
            "status": ArticleStatus.PUBLISHED,
            "tags": ["inflation", "interest-rates", "semiconductors"],
            "tickers": ["NVDA"],
            "citation_accuracy": 1.0,
            "ai_model": "seed",
            "published_at": now,
        }
        session.add_all(
            [
                Article(
                    slug="fed-to-cut-slowly-as-ai-chip-demand-outruns-supply",
                    format=ArticleFormat.SUMMARY,
                    is_premium=False,
                    headline="Fed to Cut Slowly as AI Chip Demand Outruns Supply, Strategist Says",
                    meta_description="A market strategist expects only two Fed cuts next year and says AI accelerator "
                    "demand is still far ahead of supply.",
                    summary="Inflation's 'last mile' will keep the Fed cautious, while AI chip demand stays hot.",
                    content=(
                        "Inflation has cooled, but the final stretch is the hardest, according to our guest.\n\n"
                        f'> "{SEED_SEGMENTS[2][1]}"\n\n## Key Takeaways\n\n'
                        "- Rate cuts likely to be slow and limited\n- AI accelerator demand exceeds supply\n"
                        "- Nvidia leads, but margins may normalise\n- Concentration risk in mega caps\n"
                    ),
                    citations=[citation(1), citation(2)],
                    reading_time_minutes=1,
                    **common,
                ),
                Article(
                    slug="ai-semiconductors-bull-case-bear-case-analysis",
                    format=ArticleFormat.ANALYSIS,
                    is_premium=True,
                    headline="AI Semiconductors: The Bull Case, the Bear Case and the Concentration Risk",
                    meta_description="Premium analysis of the AI chip cycle: supply constraints, Nvidia's margins and "
                    "why mega-cap concentration is the key risk.",
                    summary="We break down the strategist's view on the AI chip cycle and what it means for investors.",
                    content=(
                        "## The Thesis\n\nDemand for AI accelerators remains ahead of supply.\n\n"
                        f'> "{SEED_SEGMENTS[3][1]}"\n\n## Bull Case\n\nSupply constraints support pricing.\n\n'
                        f'## Bear Case\n\n> "{SEED_SEGMENTS[4][1]}"\n\n## Risks\n\n'
                        f'> "{SEED_SEGMENTS[5][1]}"\n'
                    ),
                    citations=[citation(3), citation(4), citation(5)],
                    reading_time_minutes=2,
                    **common,
                ),
            ]
        )
        await session.commit()
        print("Seeded demo interview and articles")


async def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    try:
        return await coro
    finally:
        await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Voice of Finance utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    admin = sub.add_parser("create-admin", help="Create or promote an admin user")
    admin.add_argument("email")
    admin.add_argument("password", nargs="?", help="Prompted for if omitted")

    ingest_cmd = sub.add_parser("ingest", help="Run the extraction + article pipeline for a YouTube URL")
    ingest_cmd.add_argument("url")
    ingest_cmd.add_argument("--formats", nargs="+", choices=[f.value for f in ArticleFormat], default=None)
    ingest_cmd.add_argument("--no-articles", action="store_true", help="Only extract, do not generate articles")

    sub.add_parser("seed", help="Insert demo content (no API keys required)")

    args = parser.parse_args()
    if args.command == "create-admin":
        password = args.password or getpass.getpass("Password: ")
        if len(password) < 8:
            parser.error("password must be at least 8 characters")
        asyncio.run(_run(create_admin(args.email, password)))
        return 0
    if args.command == "ingest":
        formats = [ArticleFormat(f) for f in args.formats] if args.formats else None
        return asyncio.run(_run(ingest(args.url, formats, not args.no_articles)))
    if args.command == "seed":
        asyncio.run(_run(seed()))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
