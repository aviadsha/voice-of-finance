import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

# Configure settings before the application is imported.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
os.environ["BILLING_MOCK_ENABLED"] = "true"
os.environ["ANALYST_VERIFICATION_THRESHOLD"] = "10"

import httpx  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.agents import pipeline  # noqa: E402
from app.core import database  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User, UserRole  # noqa: E402
from app.services.youtube import DownloadedAudio, VideoMetadata  # noqa: E402

SEGMENTS = [
    {"start": 0.0, "end": 10.0, "text": "Welcome to the program, today we discuss the economy."},
    {"start": 10.0, "end": 20.0, "text": "Inflation is sticky and the Federal Reserve will stay patient."},
    {"start": 20.0, "end": 30.0, "text": "We remain overweight Nvidia because AI demand is enormous."},
]


class FakeLLM:
    model = "fake-claude"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system: str, prompt: str, max_tokens: int | None = None) -> dict[str, Any]:
        self.calls.append((system, prompt))
        if "research analyst" in system:
            return {
                "summary": "A discussion about inflation and AI.",
                "speakers": [{"name": "Jane Doe", "role": "CIO"}],
                "topics": ["Inflation", "AI Semiconductors"],
                "companies": [{"name": "Nvidia", "ticker": "nvda"}, {"name": "Nvidia", "ticker": "NVDA"}],
                "key_quotes": [
                    {"quote": "the Federal Reserve will stay patient", "speaker": "Jane Doe", "timestamp": "00:10"},
                    {"quote": "This was never said in the interview at all", "speaker": "Jane Doe"},
                ],
                "insights": [{"insight": "Fed on hold", "category": "macro", "confidence": "high"}],
                "sentiment": "Bullish",
            }
        fmt = "summary" if "SUMMARY -" in prompt else "deep" if "DEEP-DIVE -" in prompt else "analysis"
        return {
            "headline": f"Inflation Is Sticky, Says CIO ({fmt})",
            "meta_description": "A CIO explains why the Fed will stay patient and why AI demand matters.",
            "summary": "The Fed will stay patient while AI demand stays enormous.",
            "content": "## Overview\n\n" + "Body text. " * 300,
            "citations": [
                {"quote": "We remain overweight Nvidia because AI demand is enormous.", "timestamp": "00:20"},
                {"quote": "A fabricated quote that does not exist", "timestamp": "01:00"},
            ],
            "tags": ["Inflation", "Federal Reserve"],
            "tickers": ["NVDA", "$SPY"],
        }


class FakeTranscriber:
    async def transcribe(self, audio_path: Path, prompt: str | None = None) -> dict[str, Any]:
        return {"text": " ".join(s["text"] for s in SEGMENTS), "language": "en", "segments": SEGMENTS}


class FakeDownloader:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def fetch_metadata(self, video_id: str) -> VideoMetadata:
        return VideoMetadata(
            video_id=video_id, title="Macro Outlook with Jane Doe", channel="Finance TV", duration_seconds=30
        )

    async def download_audio(self, video_id: str, workdir: Path) -> DownloadedAudio:
        if self.fail:
            raise RuntimeError("download blocked")
        workdir.mkdir(parents=True, exist_ok=True)
        path = workdir / "audio.mp3"
        path.write_bytes(b"fake")
        return DownloadedAudio(metadata=await self.fetch_metadata(video_id), chunks=[(path, 0.0)], workdir=workdir)


class FakeFactory:
    def __init__(self) -> None:
        self.llm_instance = FakeLLM()
        self.download_fails = False

    def llm(self) -> FakeLLM:
        return self.llm_instance

    def transcriber(self) -> FakeTranscriber:
        return FakeTranscriber()

    def downloader(self) -> FakeDownloader:
        return FakeDownloader(fail=self.download_fails)


@pytest.fixture
async def db_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AsyncIterator[Any]:
    # Set TEST_DATABASE_URL (postgresql+asyncpg://...) to run the suite against PostgreSQL.
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = create_async_engine(url)

    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def _fk_pragma(dbapi_connection: Any, _: Any) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", session_factory)

    async def _get_db() -> AsyncIterator[Any]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    yield engine
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.fixture
def fake_factory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FakeFactory:
    factory = FakeFactory()
    monkeypatch.setattr(pipeline, "agent_factory", factory)
    monkeypatch.setattr(pipeline.settings, "audio_workdir", str(tmp_path / "audio"))
    return factory


@pytest.fixture
async def client(db_engine: Any) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


async def signup(client: httpx.AsyncClient, email: str, password: str = "password123") -> dict[str, str]:
    response = await client.post("/api/v1/auth/signup", json={"email": email, "password": password, "full_name": email})
    assert response.status_code == 201, response.text
    return auth_header(response.json()["access_token"])


async def make_admin(client: httpx.AsyncClient, email: str = "admin@example.com") -> dict[str, str]:
    async with database.SessionLocal() as session:
        session.add(
            User(email=email, hashed_password=hash_password("password123"), role=UserRole.ADMIN, full_name="Admin")
        )
        await session.commit()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "password123"})
    assert response.status_code == 200, response.text
    return auth_header(response.json()["access_token"])
