import httpx
import pytest

from app.agents.text_utils import TranscriptIndex, parse_timestamp
from app.services.ai import LLMResponseError, parse_json_object
from app.services.youtube import InvalidYouTubeURL, extract_video_id, timestamp_url
from tests.conftest import SEGMENTS, FakeFactory, make_admin, signup


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
        "https://youtu.be/dQw4w9WgXcQ?si=abc",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://m.youtube.com/live/dQw4w9WgXcQ",
        "youtube.com/watch?v=dQw4w9WgXcQ",
        "dQw4w9WgXcQ",
    ],
)
def test_extract_video_id(url: str) -> None:
    assert extract_video_id(url) == "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url", ["https://vimeo.com/123", "https://www.youtube.com/watch?v=short", "https://evil.com/watch?v=dQw4w9WgXcQ"]
)
def test_extract_video_id_rejects_invalid(url: str) -> None:
    with pytest.raises(InvalidYouTubeURL):
        extract_video_id(url)


def test_transcript_index_locates_quotes() -> None:
    index = TranscriptIndex(SEGMENTS)
    assert index.locate("the federal reserve will stay PATIENT") == (True, 10.0)
    assert index.locate("We remain overweight Nvidia, because AI demand is enormous!") == (True, 20.0)
    # Opening words match but the rest is paraphrased -> timestamp only, not verified.
    assert index.locate("We remain overweight Nvidia because AI is a bubble") == (False, 20.0)
    assert index.locate("Completely invented") == (False, None)


def test_parse_helpers() -> None:
    assert parse_timestamp("01:05") == 65
    assert parse_timestamp("1:00:00") == 3600
    assert parse_timestamp(12) == 12
    assert parse_timestamp("n/a") is None
    assert timestamp_url("dQw4w9WgXcQ", 65.7) == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=65s"
    assert parse_json_object('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('prefix {"b": [1, 2]} suffix') == {"b": [1, 2]}
    with pytest.raises(LLMResponseError):
        parse_json_object("no json here")


async def test_submit_interview_runs_full_pipeline(client: httpx.AsyncClient, fake_factory: FakeFactory) -> None:
    admin = await make_admin(client)
    response = await client.post(
        "/api/v1/interviews", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"}, headers=admin
    )
    assert response.status_code == 202, response.text
    interview_id = response.json()["id"]

    # Background task has completed by the time the ASGI call returns.
    interview = (await client.get(f"/api/v1/interviews/{interview_id}")).json()
    assert interview["status"] == "completed", interview["error_message"]
    assert interview["title"] == "Macro Outlook with Jane Doe"
    assert interview["sentiment"] == "bullish"
    assert interview["companies"] == [{"name": "Nvidia", "ticker": "NVDA"}]
    assert [t["slug"] for t in interview["topics"]] == ["inflation", "ai-semiconductors"]
    verified, invented = interview["key_quotes"]
    assert verified["verified"] is True and verified["timestamp"] == 10.0
    assert invented["verified"] is False

    articles = (await client.get("/api/v1/articles", params={"interview_id": interview_id})).json()
    assert articles["total"] == 3
    formats = {a["format"]: a for a in articles["items"]}
    assert set(formats) == {"summary", "deep_dive", "analysis"}
    assert formats["summary"]["is_premium"] is False
    assert formats["analysis"]["is_premium"] is True
    assert "NVDA" in formats["summary"]["tickers"] and "SPY" in formats["summary"]["tickers"]
    assert "federal-reserve" in formats["summary"]["tags"]

    article = (await client.get(f"/api/v1/articles/{formats['summary']['slug']}")).json()
    assert article["citation_accuracy"] == 0.5
    good, bad = article["citations"]
    assert good["verified"] is True
    assert good["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=20s"
    assert bad["verified"] is False
    assert len(article["meta_description"]) <= 160
    assert article["reading_time_minutes"] >= 2

    # Only verified quotes are fed into the article prompt.
    article_prompts = [p for s, p in fake_factory.llm_instance.calls if "journalist" in s]
    assert len(article_prompts) == 3
    assert "never said" not in article_prompts[0].split("TRANSCRIPT")[0]

    # Duplicate submissions are rejected.
    duplicate = await client.post(
        "/api/v1/interviews", json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, headers=admin
    )
    assert duplicate.status_code == 409

    # Regenerating a single format replaces the existing article of that format.
    regen = await client.post(f"/api/v1/interviews/{interview_id}/articles", json={"formats": ["summary"]}, headers=admin)
    assert regen.status_code == 202
    assert len([s for s, _ in fake_factory.llm_instance.calls if "journalist" in s]) == 4
    articles = (await client.get("/api/v1/articles", params={"interview_id": interview_id})).json()
    assert articles["total"] == 3

    # Deleting the interview cascades to its articles.
    assert (await client.delete(f"/api/v1/interviews/{interview_id}", headers=admin)).status_code == 204
    assert (await client.get("/api/v1/articles")).json()["total"] == 0


async def test_pipeline_failure_is_recorded(client: httpx.AsyncClient, fake_factory: FakeFactory) -> None:
    fake_factory.download_fails = True
    admin = await make_admin(client)
    response = await client.post(
        "/api/v1/interviews", json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ", "generate_articles": False}, headers=admin
    )
    interview = (await client.get(f"/api/v1/interviews/{response.json()['id']}")).json()
    assert interview["status"] == "failed"
    assert "download blocked" in interview["error_message"]

    failed = (await client.get("/api/v1/interviews", params={"status": "failed"})).json()
    assert failed["total"] == 1


async def test_submit_interview_permissions_and_validation(client: httpx.AsyncClient, fake_factory: FakeFactory) -> None:
    payload = {"youtube_url": "https://youtu.be/dQw4w9WgXcQ"}
    assert (await client.post("/api/v1/interviews", json=payload)).status_code == 401
    user = await signup(client, "user@example.com")
    assert (await client.post("/api/v1/interviews", json=payload, headers=user)).status_code == 403

    admin = await make_admin(client)
    invalid = await client.post("/api/v1/interviews", json={"youtube_url": "https://vimeo.com/12345"}, headers=admin)
    assert invalid.status_code == 422
