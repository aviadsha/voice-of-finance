import httpx

from tests.conftest import auth_header, signup


async def test_signup_login_and_me(client: httpx.AsyncClient) -> None:
    headers = await signup(client, "Alice@Example.com")

    me = await client.get("/api/v1/users/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == "alice@example.com"
    assert body["tier"] == "free"
    assert body["is_premium"] is False
    assert "hashed_password" not in body

    login = await client.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "password123"})
    assert login.status_code == 200
    assert login.json()["access_token"]

    # OAuth2 form flow used by Swagger UI.
    token = await client.post("/api/v1/auth/token", data={"username": "alice@example.com", "password": "password123"})
    assert token.status_code == 200


async def test_duplicate_signup_and_bad_credentials(client: httpx.AsyncClient) -> None:
    await signup(client, "bob@example.com")
    duplicate = await client.post("/api/v1/auth/signup", json={"email": "BOB@example.com", "password": "password123"})
    assert duplicate.status_code == 409

    bad = await client.post("/api/v1/auth/login", json={"email": "bob@example.com", "password": "wrong-password"})
    assert bad.status_code == 401

    short = await client.post("/api/v1/auth/signup", json={"email": "c@example.com", "password": "short"})
    assert short.status_code == 422


async def test_protected_routes_require_valid_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/users/me")).status_code == 401
    assert (await client.get("/api/v1/users/me", headers=auth_header("not-a-jwt"))).status_code == 401


async def test_update_profile(client: httpx.AsyncClient) -> None:
    headers = await signup(client, "dana@example.com")
    response = await client.patch("/api/v1/users/me", json={"bio": "Macro nerd"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["bio"] == "Macro nerd"


async def test_health_and_docs(client: httpx.AsyncClient) -> None:
    health = await client.get("/health")
    assert health.json() == {"status": "ok", "database": "ok"}
    openapi = await client.get("/api/v1/openapi.json")
    assert openapi.status_code == 200
    assert "/api/v1/interviews" in openapi.json()["paths"]
