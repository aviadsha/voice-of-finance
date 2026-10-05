"""YouTube helpers built on top of yt-dlp and ffmpeg."""

import asyncio
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}


class InvalidYouTubeURL(ValueError):
    pass


def extract_video_id(url: str) -> str:
    """Return the 11-character YouTube video id for the supported URL formats."""
    url = url.strip()
    if _VIDEO_ID_RE.match(url):
        return url
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    if host not in _YOUTUBE_HOSTS:
        raise InvalidYouTubeURL("URL must be a youtube.com or youtu.be link")
    candidate: str | None = None
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = (parse_qs(parsed.query).get("v") or [None])[0]
    else:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
            candidate = parts[1]
    if not candidate or not _VIDEO_ID_RE.match(candidate):
        raise InvalidYouTubeURL("Could not find a valid YouTube video id in the URL")
    return candidate


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def timestamp_url(video_id: str, seconds: float | None) -> str:
    if seconds is None:
        return canonical_url(video_id)
    return f"https://www.youtube.com/watch?v={video_id}&t={max(int(seconds), 0)}s"


@dataclass
class VideoMetadata:
    video_id: str
    title: str | None = None
    channel: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    published_at: datetime | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class DownloadedAudio:
    metadata: VideoMetadata
    # Ordered chunks, each paired with its start offset (seconds) in the full audio.
    chunks: list[tuple[Path, float]]
    workdir: Path


class AudioDownloader(Protocol):
    async def fetch_metadata(self, video_id: str) -> VideoMetadata: ...

    async def download_audio(self, video_id: str, workdir: Path) -> DownloadedAudio: ...


def _parse_upload_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def _metadata_from_info(video_id: str, info: dict[str, Any]) -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        title=info.get("title"),
        channel=info.get("channel") or info.get("uploader"),
        description=info.get("description"),
        thumbnail_url=info.get("thumbnail"),
        duration_seconds=int(info["duration"]) if info.get("duration") else None,
        published_at=_parse_upload_date(info.get("upload_date")),
        tags=list(info.get("tags") or [])[:30],
    )


class YtDlpDownloader:
    """Downloads the audio track with yt-dlp and splits it for the Whisper API."""

    def __init__(self, max_chunk_mb: int, chunk_seconds: int, audio_bitrate_kbps: int = 64) -> None:
        self.max_chunk_bytes = max_chunk_mb * 1024 * 1024
        self.chunk_seconds = chunk_seconds
        self.audio_bitrate_kbps = audio_bitrate_kbps

    async def fetch_metadata(self, video_id: str) -> VideoMetadata:
        return await asyncio.to_thread(self._fetch_metadata_sync, video_id)

    async def download_audio(self, video_id: str, workdir: Path) -> DownloadedAudio:
        return await asyncio.to_thread(self._download_sync, video_id, workdir)

    def _fetch_metadata_sync(self, video_id: str) -> VideoMetadata:
        from yt_dlp import YoutubeDL

        with YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=False)
        return _metadata_from_info(video_id, info or {})

    def _download_sync(self, video_id: str, workdir: Path) -> DownloadedAudio:
        from yt_dlp import YoutubeDL

        if shutil.which("ffmpeg") is None:
            raise RuntimeError("ffmpeg is required for audio extraction but was not found on PATH")
        workdir.mkdir(parents=True, exist_ok=True)
        options = {
            "format": "bestaudio/best",
            "outtmpl": str(workdir / "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": str(self.audio_bitrate_kbps),
                }
            ],
            # Mono, 16 kHz is all Whisper needs and keeps files small.
            "postprocessor_args": {"extractaudio": ["-ac", "1", "-ar", "16000"]},
        }
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(canonical_url(video_id), download=True)
        audio_path = workdir / f"{video_id}.mp3"
        if not audio_path.exists():
            raise RuntimeError("Audio extraction failed: output file not found")
        return DownloadedAudio(
            metadata=_metadata_from_info(video_id, info or {}),
            chunks=self._split(audio_path),
            workdir=workdir,
        )

    def _split(self, audio_path: Path) -> list[tuple[Path, float]]:
        if audio_path.stat().st_size <= self.max_chunk_bytes:
            return [(audio_path, 0.0)]
        pattern = audio_path.with_name(f"{audio_path.stem}_chunk_%03d.mp3")
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(audio_path),
                "-f", "segment", "-segment_time", str(self.chunk_seconds),
                "-c", "copy", "-reset_timestamps", "1",
                str(pattern),
            ],
            check=True,
        )  # fmt: skip
        chunks = sorted(audio_path.parent.glob(f"{audio_path.stem}_chunk_*.mp3"))
        return [(chunk, float(index * self.chunk_seconds)) for index, chunk in enumerate(chunks)]
