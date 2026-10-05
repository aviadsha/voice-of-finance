import httpx
import pytest

from app import cli
from app.core.config import Settings
from tests.conftest import make_admin, signup

FREE_SLUG = "fed-to-cut-slowly-as-ai-chip-demand-outruns-supply"
PREMIUM_SLUG = "ai-semiconductors-bull-case-bear-case-analysis"


async def test_list_and_filter_articles(client: httpx.AsyncClient) -> None:
    await cli.seed()
    response = await client.get("/api/v1/articles")
    assert response.status_code == 200
    assert response.json()["total"] == 2

    premium = await client.get("/api/v1/articles", params={"premium": True})
    assert [a["slug"] for a in premium.json()["items"]] == [PREMIUM_SLUG]

    by_ticker = await client.get("/api/v1/articles", params={"ticker": "nvda"})
    assert by_ticker.json()["total"] == 2
    assert (await client.get("/api/v1/articles", params={"ticker": "AAPL"})).json()["total"] == 0
    assert (await client.get("/api/v1/articles", params={"tag": "Interest Rates"})).json()["total"] == 2
    assert (await client.get("/api/v1/articles", params={"q": "bull case"})).json()["total"] == 1
    assert (await client.get("/api/v1/articles", params={"format": "summary"})).json()["total"] == 1


async def test_freemium_paywall(client: httpx.AsyncClient) -> None:
    await cli.seed()

    free_article = (await client.get(f"/api/v1/articles/{FREE_SLUG}")).json()
    assert free_article["is_locked"] is False
    assert free_article["content"]
    assert free_article["source_url"].startswith("https://www.youtube.com/watch?v=")

    anonymous = (await client.get(f"/api/v1/articles/{PREMIUM_SLUG}")).json()
    assert anonymous["is_locked"] is True
    assert anonymous["content"] is None
    assert anonymous["summary"]
    assert len(anonymous["citations"]) == 2

    headers = await signup(client, "reader@example.com")
    free_user = (await client.get(f"/api/v1/articles/{PREMIUM_SLUG}", headers=headers)).json()
    assert free_user["is_locked"] is True

    upgraded = await client.post("/api/v1/subscription/upgrade", headers=headers)
    assert upgraded.json()["tier"] == "premium"
    premium_user = (await client.get(f"/api/v1/articles/{PREMIUM_SLUG}", headers=headers)).json()
    assert premium_user["is_locked"] is False
    assert "## The Thesis" in premium_user["content"]
    assert len(premium_user["citations"]) == 3
    assert premium_user["view_count"] == 3

    await client.post("/api/v1/subscription/cancel", headers=headers)
    assert (await client.get(f"/api/v1/articles/{PREMIUM_SLUG}", headers=headers)).json()["is_locked"] is True


async def test_transcript_is_premium(client: httpx.AsyncClient) -> None:
    await cli.seed()
    interview_id = (await client.get("/api/v1/interviews")).json()["items"][0]["id"]
    headers = await signup(client, "t@example.com")
    assert (await client.get(f"/api/v1/interviews/{interview_id}/transcript", headers=headers)).status_code == 402
    await client.post("/api/v1/subscription/upgrade", headers=headers)
    transcript = await client.get(f"/api/v1/interviews/{interview_id}/transcript", headers=headers)
    assert transcript.status_code == 200
    assert transcript.json()["transcript_segments"]


async def test_unknown_article_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/articles/does-not-exist")).status_code == 404


async def test_plans(client: httpx.AsyncClient) -> None:
    plans = (await client.get("/api/v1/subscription/plans")).json()
    assert [p["tier"] for p in plans] == ["free", "premium"]


async def test_admin_sets_article_status(client: httpx.AsyncClient) -> None:
    await cli.seed()
    reader = await signup(client, "reader2@example.com")
    body = {"status": "archived"}
    assert (await client.post(f"/api/v1/articles/{FREE_SLUG}/status", json=body, headers=reader)).status_code == 403

    admin = await make_admin(client)
    archived = await client.post(f"/api/v1/articles/{FREE_SLUG}/status", json=body, headers=admin)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    assert (await client.get(f"/api/v1/articles/{FREE_SLUG}")).status_code == 404


def test_mock_billing_disabled_by_default_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BILLING_MOCK_ENABLED", raising=False)
    secret = "s" * 48
    assert Settings(environment="production", jwt_secret_key=secret).billing_mock_enabled is False
    assert Settings(environment="development").billing_mock_enabled is True
    explicit = Settings(environment="production", jwt_secret_key=secret, billing_mock_enabled=True)
    assert explicit.billing_mock_enabled is True
