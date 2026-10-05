"""Text helpers shared by the agents (quote verification, timestamps, slugs)."""

import bisect
import re
import string
from typing import Any

from slugify import slugify

_PUNCT_TABLE = str.maketrans({c: " " for c in string.punctuation + "“”‘’—–…"})
_WS = re.compile(r"\s+")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


def normalize_text(text: str) -> str:
    return _WS.sub(" ", text.lower().translate(_PUNCT_TABLE)).strip()


def normalize_topic(value: str) -> str:
    return slugify(value, max_length=60)


def normalize_ticker(value: str) -> str | None:
    value = value.strip().upper().lstrip("$")
    return value if _TICKER_RE.match(value) else None


def format_timestamp(seconds: float | None) -> str:
    if seconds is None:
        return "--:--"
    seconds = int(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"


def transcript_for_prompt(segments: list[dict[str, Any]], fallback: str | None, max_chars: int) -> str:
    """Render the transcript with `[mm:ss]` markers so the model can cite timestamps."""
    if segments:
        text = "\n".join(f"[{format_timestamp(s.get('start'))}] {s.get('text', '').strip()}" for s in segments)
    else:
        text = fallback or ""
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[... transcript truncated ...]"
    return text


def parse_timestamp(value: Any) -> float | None:
    """Parse `mm:ss` / `h:mm:ss` / numeric seconds into seconds."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        parts = [int(p) for p in str(value).strip().split(":")]
    except ValueError:
        return None
    seconds = 0
    for part in parts:
        seconds = seconds * 60 + part
    return float(seconds)


def reading_time_minutes(markdown: str, wpm: int = 220) -> int:
    return max(1, round(len(markdown.split()) / wpm))


class TranscriptIndex:
    """Normalised transcript with a char-offset -> timestamp index for quote lookup."""

    def __init__(self, segments: list[dict[str, Any]], transcript: str | None = None) -> None:
        self._offsets: list[int] = []
        self._starts: list[float] = []
        parts: list[str] = []
        cursor = 0
        if segments:
            for segment in segments:
                normalized = normalize_text(str(segment.get("text", "")))
                if not normalized:
                    continue
                self._offsets.append(cursor)
                self._starts.append(float(segment.get("start") or 0.0))
                parts.append(normalized)
                cursor += len(normalized) + 1
        elif transcript:
            parts.append(normalize_text(transcript))
        self.text = " ".join(parts)

    def _timestamp_at(self, position: int) -> float | None:
        if not self._offsets:
            return None
        index = bisect.bisect_right(self._offsets, position) - 1
        return self._starts[max(index, 0)]

    def locate(self, quote: str) -> tuple[bool, float | None]:
        """Return (verified_verbatim, timestamp) for a quote.

        A quote is *verified* when its normalised form appears verbatim in the
        transcript. If only its opening words match, the timestamp is still
        returned but the quote is not considered verified.
        """
        normalized = normalize_text(quote)
        if not normalized or not self.text:
            return False, None
        position = self.text.find(normalized)
        if position != -1:
            return True, self._timestamp_at(position)
        words = normalized.split()
        if len(words) >= 6:
            position = self.text.find(" ".join(words[:6]))
            if position != -1:
                return False, self._timestamp_at(position)
        return False, None
