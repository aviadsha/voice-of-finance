import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.agents.community import CommunityError
from app.api.routes import articles, auth, community, interviews, users
from app.core import database
from app.core.config import settings

logging.basicConfig(level=logging.DEBUG if settings.debug else logging.INFO)
logger = logging.getLogger("voice_of_finance")

API_DESCRIPTION = """
**Voice of Finance** turns finance interviews on YouTube into high-quality articles.

* **Interviews** - submit a YouTube URL; the extraction agent downloads the audio (yt-dlp),
  transcribes it (OpenAI Whisper) and extracts topics, quotes and insights (Claude).
* **Articles** - the generation agent writes *summary*, *deep-dive* and *analysis* articles with
  headlines, meta descriptions and transcript-verified citations.
* **Community** - comments, votes, reputation and verified analysts.
* **Freemium** - free summaries; premium deep-dives, analysis, transcripts and portfolio tracking.

Authenticate with `POST /api/v1/auth/login` (or the **Authorize** button) and send
the returned `access_token` as a bearer credential in the `Authorization` header.
"""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s (%s)", settings.app_name, settings.environment)
    yield
    await database.engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=API_DESCRIPTION,
    lifespan=lifespan,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(CommunityError)
async def community_error_handler(_: Request, exc: CommunityError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


for router in (auth.router, users.router, interviews.router, articles.router, community.router):
    app.include_router(router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Liveness + database connectivity check."""
    db_status = "ok"
    try:
        async with database.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - depends on infrastructure
        logger.exception("Database health check failed")
        db_status = "unavailable"
    return {"status": "ok" if db_status == "ok" else "degraded", "database": db_status}


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs"}
