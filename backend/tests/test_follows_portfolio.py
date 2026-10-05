import httpx

from app import cli
from tests.conftest import signup


async def test_follows_and_personalised_feed(client: httpx.AsyncClient) -> None:
    await cli.seed()
    headers = await signup(client, "follower@example.com")

    assert (await client.get("/api/v1/me/feed", headers=headers)).json() == []

    company = await client.post(
        "/api/v1/me/follows",
        json={"follow_type": "company", "value": "$nvda", "display_name": "Nvidia"},
        headers=headers,
    )
    assert company.status_code == 201
    assert company.json()["value"] == "NVDA"

    duplicate = await client.post(
        "/api/v1/me/follows", json={"follow_type": "company", "value": "NVDA"}, headers=headers
    )
    assert duplicate.status_code == 409

    invalid = await client.post(
        "/api/v1/me/follows", json={"follow_type": "company", "value": "not a ticker"}, headers=headers
    )
    assert invalid.status_code == 422

    topic = await client.post(
        "/api/v1/me/follows", json={"follow_type": "topic", "value": "Interest Rates"}, headers=headers
    )
    assert topic.json()["value"] == "interest-rates"

    follows = (await client.get("/api/v1/me/follows", headers=headers)).json()
    assert {f["value"] for f in follows} == {"NVDA", "interest-rates"}

    feed = (await client.get("/api/v1/me/feed", headers=headers)).json()
    assert len(feed) == 2

    for follow in follows:
        assert (await client.delete(f"/api/v1/me/follows/{follow['id']}", headers=headers)).status_code == 204
    await client.post("/api/v1/me/follows", json={"follow_type": "company", "value": "AAPL"}, headers=headers)
    assert (await client.get("/api/v1/me/feed", headers=headers)).json() == []


async def test_portfolio_is_premium_only(client: httpx.AsyncClient) -> None:
    await cli.seed()
    headers = await signup(client, "investor@example.com")
    assert (await client.get("/api/v1/me/portfolio", headers=headers)).status_code == 402

    await client.post("/api/v1/subscription/upgrade", headers=headers)
    holding = await client.post(
        "/api/v1/me/portfolio", json={"ticker": "nvda", "shares": "10", "average_cost": "100.5"}, headers=headers
    )
    assert holding.status_code == 201, holding.text
    assert holding.json()["ticker"] == "NVDA"

    # Upsert by ticker.
    await client.post(
        "/api/v1/me/portfolio", json={"ticker": "NVDA", "shares": "20", "average_cost": "100"}, headers=headers
    )
    portfolio = (await client.get("/api/v1/me/portfolio", headers=headers)).json()
    assert len(portfolio["holdings"]) == 1
    assert float(portfolio["total_cost_basis"]) == 2000
    assert len(portfolio["related_articles"]) == 2

    holding_id = portfolio["holdings"][0]["id"]
    assert (await client.delete(f"/api/v1/me/portfolio/{holding_id}", headers=headers)).status_code == 204
