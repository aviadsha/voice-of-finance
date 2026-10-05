import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import JSONDict, JSONList, JSONType, TimestampMixin, UUIDPkMixin, str_enum


class InterviewStatus(enum.StrEnum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class Interview(UUIDPkMixin, TimestampMixin, Base):
    """A YouTube interview processed by the extraction agent."""

    __tablename__ = "interviews"

    youtube_url: Mapped[str] = mapped_column(String(500))
    youtube_video_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    status: Mapped[InterviewStatus] = mapped_column(
        str_enum(InterviewStatus), default=InterviewStatus.PENDING, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    # --- YouTube metadata ---
    title: Mapped[str | None] = mapped_column(String(500))
    channel: Mapped[str | None] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    language: Mapped[str | None] = mapped_column(String(16))

    # --- Transcription (Whisper) ---
    transcript: Mapped[str | None] = mapped_column(Text)
    # [{"start": float, "end": float, "text": str}]
    transcript_segments: Mapped[JSONList] = mapped_column(JSONType, default=list)

    # --- Insights (Claude) ---
    summary: Mapped[str | None] = mapped_column(Text)
    speakers: Mapped[JSONList] = mapped_column(JSONType, default=list)
    topics: Mapped[JSONList] = mapped_column(JSONType, default=list)
    # Upper-case tickers / company names mentioned.
    companies: Mapped[JSONList] = mapped_column(JSONType, default=list)
    # [{"quote": str, "speaker": str | None, "timestamp": float | None, "context": str | None}]
    key_quotes: Mapped[JSONList] = mapped_column(JSONType, default=list)
    # [{"insight": str, "category": str, "confidence": str}]
    insights: Mapped[JSONList] = mapped_column(JSONType, default=list)
    sentiment: Mapped[str | None] = mapped_column(String(32))
    extra_metadata: Mapped[JSONDict] = mapped_column(JSONType, default=dict)

    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    articles: Mapped[list["Article"]] = relationship(  # noqa: F821
        back_populates="interview", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.youtube_video_id}"
