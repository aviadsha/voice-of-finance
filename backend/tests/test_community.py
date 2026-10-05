import httpx

from app import cli
from app.agents.community import moderate_text
from tests.conftest import make_admin, signup

SLUG = "fed-to-cut-slowly-as-ai-chip-demand-outruns-supply"
PREMIUM_SLUG = "ai-semiconductors-bull-case-bear-case-analysis"


async def test_comments_votes_and_reputation(client: httpx.AsyncClient) -> None:
    await cli.seed()
    author = await signup(client, "author@example.com")
    voter = await signup(client, "voter@example.com")

    created = await client.post(
        f"/api/v1/articles/{SLUG}/comments", json={"body": "Great point on rates."}, headers=author
    )
    assert created.status_code == 201, created.text
    comment = created.json()
    assert comment["user"]["reputation"] == 1  # +1 for commenting

    reply = await client.post(
        f"/api/v1/articles/{SLUG}/comments", json={"body": "Agreed.", "parent_id": comment["id"]}, headers=voter
    )
    assert reply.status_code == 201
    assert reply.json()["parent_id"] == comment["id"]

    # Cannot vote on own comment.
    own = await client.post(f"/api/v1/comments/{comment['id']}/vote", json={"value": 1}, headers=author)
    assert own.status_code == 403

    up = await client.post(f"/api/v1/comments/{comment['id']}/vote", json={"value": 1}, headers=voter)
    assert up.json()["score"] == 1
    assert up.json()["my_vote"] == 1
    assert up.json()["user"]["reputation"] == 6  # 1 + 5

    # Voting again with the same value is idempotent.
    again = await client.post(f"/api/v1/comments/{comment['id']}/vote", json={"value": 1}, headers=voter)
    assert again.json()["score"] == 1

    # The comment list reports each reader's own vote (anonymous readers get 0).
    listed = (await client.get(f"/api/v1/articles/{SLUG}/comments", headers=voter)).json()
    assert {c["id"]: c["my_vote"] for c in listed}[comment["id"]] == 1
    anonymous = (await client.get(f"/api/v1/articles/{SLUG}/comments")).json()
    assert all(c["my_vote"] == 0 for c in anonymous)

    down = await client.post(f"/api/v1/comments/{comment['id']}/vote", json={"value": -1}, headers=voter)
    assert down.json()["score"] == -1
    assert down.json()["user"]["reputation"] == 0  # 1 + (-2) floored at 0

    cleared = await client.post(f"/api/v1/comments/{comment['id']}/vote", json={"value": 0}, headers=voter)
    assert cleared.json()["score"] == 0

    comments = (await client.get(f"/api/v1/articles/{SLUG}/comments")).json()
    assert len(comments) == 2

    # Only the owner can delete.
    assert (await client.delete(f"/api/v1/comments/{comment['id']}", headers=voter)).status_code == 403
    assert (await client.delete(f"/api/v1/comments/{comment['id']}", headers=author)).status_code == 204
    comments = (await client.get(f"/api/v1/articles/{SLUG}/comments")).json()
    assert any(c["is_deleted"] and c["body"] == "[deleted]" for c in comments)


async def test_spam_comment_rejected(client: httpx.AsyncClient) -> None:
    await cli.seed()
    headers = await signup(client, "spammer@example.com")
    response = await client.post(
        f"/api/v1/articles/{SLUG}/comments",
        json={"body": "Guaranteed returns of 50% daily, DM me on telegram"},
        headers=headers,
    )
    assert response.status_code == 422
    assert "spam" in response.json()["detail"]
    assert (await client.post(f"/api/v1/articles/{SLUG}/comments", json={"body": "hi"})).status_code == 401


def test_moderation_rules() -> None:
    assert moderate_text("Thoughtful comment about bond yields.").allowed
    assert not moderate_text("   ").allowed
    assert not moderate_text("send BTC to this address to double your money").allowed
    shouting = moderate_text("THIS STOCK IS GOING TO EXPLODE NEXT WEEK BELIEVE ME")
    assert shouting.allowed and shouting.flagged


async def test_verified_analyst_workflow(client: httpx.AsyncClient) -> None:
    await cli.seed()
    admin = await make_admin(client)
    analyst = await signup(client, "analyst@example.com")
    fans = [await signup(client, f"fan{i}@example.com") for i in range(2)]

    application = {"credentials": "CFA charterholder, 10 years on the sell side covering semis."}
    # Not enough reputation yet (threshold is 10 in tests).
    assert (
        await client.post("/api/v1/community/analyst-applications", json=application, headers=analyst)
    ).status_code == 403

    comment = (
        await client.post(f"/api/v1/articles/{SLUG}/comments", json={"body": "Margins will compress."}, headers=analyst)
    ).json()
    for fan in fans:
        await client.post(f"/api/v1/comments/{comment['id']}/vote", json={"value": 1}, headers=fan)

    leaderboard = (await client.get("/api/v1/community/leaderboard")).json()
    assert leaderboard[0]["reputation"] == 11

    # Analysts cannot publish before being verified.
    insight = {
        "headline": "Why AI chip margins will compress",
        "meta_description": "A verified analyst on semiconductor margins.",
        "summary": "Competition is coming for AI accelerator margins.",
        "content": "## Thesis\n\n" + "Competition increases as supply catches up. " * 10,
        "tickers": ["nvda", "amd"],
        "tags": ["Semiconductors"],
    }
    assert (await client.post("/api/v1/articles", json=insight, headers=analyst)).status_code == 403

    applied = await client.post("/api/v1/community/analyst-applications", json=application, headers=analyst)
    assert applied.status_code == 201
    duplicate = await client.post("/api/v1/community/analyst-applications", json=application, headers=analyst)
    assert duplicate.status_code == 409

    # Non-admins cannot review.
    review_url = f"/api/v1/community/analyst-applications/{applied.json()['id']}/review"
    assert (await client.post(review_url, json={"approve": True}, headers=analyst)).status_code == 403
    pending = (await client.get("/api/v1/community/analyst-applications?status=pending", headers=admin)).json()
    assert len(pending) == 1
    reviewed = await client.post(review_url, json={"approve": True, "review_notes": "Welcome"}, headers=admin)
    assert reviewed.json()["status"] == "approved"

    me = (await client.get("/api/v1/users/me", headers=analyst)).json()
    assert me["role"] == "analyst" and me["is_verified_analyst"] is True

    published = await client.post("/api/v1/articles", json=insight, headers=analyst)
    assert published.status_code == 201, published.text
    article = published.json()
    assert article["is_premium"] is True
    assert article["is_locked"] is False  # the author can read their own premium insight
    assert article["author"]["is_verified_analyst"] is True
    assert article["tickers"] == ["AMD", "NVDA"]

    # Free readers only see the teaser.
    reader = await signup(client, "reader@example.com")
    locked = (await client.get(f"/api/v1/articles/{article['slug']}", headers=reader)).json()
    assert locked["is_locked"] is True


async def test_comments_on_premium_article_allowed_for_free_users(client: httpx.AsyncClient) -> None:
    await cli.seed()
    headers = await signup(client, "free@example.com")
    response = await client.post(
        f"/api/v1/articles/{PREMIUM_SLUG}/comments", json={"body": "Interested in the bear case."}, headers=headers
    )
    assert response.status_code == 201
