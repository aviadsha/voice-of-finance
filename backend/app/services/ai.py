"""Thin, mockable wrappers around the external AI providers."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)


class AIConfigurationError(RuntimeError):
    """Raised when an AI provider is used without being configured."""


class LLMResponseError(RuntimeError):
    """Raised when the LLM response cannot be parsed."""


class JSONLLM(Protocol):
    model: str

    async def complete_json(self, system: str, prompt: str, max_tokens: int | None = None) -> dict[str, Any]: ...


class Transcriber(Protocol):
    async def transcribe(self, audio_path: Path, prompt: str | None = None) -> dict[str, Any]: ...


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from an LLM response (handles code fences / prose)."""
    candidates: list[str] = [text.strip()]
    candidates += [m.strip() for m in _JSON_FENCE.findall(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise LLMResponseError("Model response did not contain a valid JSON object")


class ClaudeClient:
    """Claude (Anthropic) client that returns JSON objects."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        api_key = api_key or settings.anthropic_api_key
        if not api_key:
            raise AIConfigurationError("ANTHROPIC_API_KEY is not configured")
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self.model = model or settings.anthropic_model

    async def complete_json(self, system: str, prompt: str, max_tokens: int | None = None) -> dict[str, Any]:
        response = await self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens or settings.anthropic_max_tokens,
            system=system,
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")
        if response.stop_reason == "max_tokens":
            logger.warning("Claude response truncated at max_tokens (%s)", self.model)
        return parse_json_object(text)


class WhisperTranscriber:
    """OpenAI Whisper transcription client."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        api_key = api_key or settings.openai_api_key
        if not api_key:
            raise AIConfigurationError("OPENAI_API_KEY is not configured")
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key)
        self.model = model or settings.whisper_model

    async def transcribe(self, audio_path: Path, prompt: str | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "response_format": "verbose_json",
            "timestamp_granularities": ["segment"],
        }
        if prompt:
            kwargs["prompt"] = prompt
        with audio_path.open("rb") as audio_file:
            result = await self._client.audio.transcriptions.create(file=audio_file, **kwargs)
        data = result.model_dump() if hasattr(result, "model_dump") else dict(result)
        return {
            "text": data.get("text", ""),
            "language": data.get("language"),
            "segments": [
                {"start": float(s["start"]), "end": float(s["end"]), "text": s["text"].strip()}
                for s in (data.get("segments") or [])
            ],
        }
