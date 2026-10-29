"""The user endpoints of the API, with the users kept in Neo4j"""

import httpx2 as httpx
import pytest
import pytest_asyncio
from pangloss_api.app import create_app
from pangloss_users import service

pytestmark = pytest.mark.asyncio(loop_scope="session")

PASSWORD = "correct horse"


@pytest_asyncio.fixture(loop_scope="session")
async def client():
    # (the settings and the database are those of the test session; the server's
    # startup is not run, as the connection is already open)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


async def login(client, username, password=PASSWORD):
    return await client.post(
        "/api/users/token", data={"username": username, "password": password}
    )


async def bearer(client, username) -> dict:
    token = (await login(client, username)).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def test_users_through_the_api(client, db_driver, clear_database):
    await service.create_user("root", "root@example.com", PASSWORD, admin=True)
    admin = await bearer(client, "root")

    # An admin creates a user
    response = await client.post(
        "/api/users",
        json={
            "username": "john",
            "email": "john@example.com",
            "password": PASSWORD,
            "fullName": "John Smith",
        },
        headers=admin,
    )
    assert response.status_code == 201
    assert response.json()["email"] == "john@example.com"

    # ... who can log in, and sees themselves
    john = await bearer(client, "john")
    me = (await client.get("/api/users/me", headers=john)).json()
    assert me["username"] == "john"
    assert me["fullName"] == "John Smith"
    assert me["admin"] is False
    assert "hashed_password" not in me

    # A username or email in use is a conflict
    taken = await client.post(
        "/api/users",
        json={"username": "john", "email": "x@example.com", "password": PASSWORD},
        headers=admin,
    )
    assert taken.status_code == 409
    taken = await client.post(
        "/api/users",
        json={"username": "jane", "email": "john@example.com", "password": PASSWORD},
        headers=admin,
    )
    assert taken.status_code == 409

    # Changing their own details and password
    response = await client.patch(
        "/api/users/me", json={"fullName": "J. Smith"}, headers=john
    )
    assert response.json()["fullName"] == "J. Smith"
    response = await client.put(
        "/api/users/me/password",
        json={"oldPassword": PASSWORD, "newPassword": "a new password"},
        headers=john,
    )
    assert response.status_code == 200
    assert (await login(client, "john")).status_code == 401
    assert (await login(client, "john", "a new password")).status_code == 200

    # An admin disables them: the token they already hold stops working
    response = await client.put(
        "/api/users/john/disabled", json={"disabled": True}, headers=admin
    )
    assert response.json()["disabled"] is True
    assert (await client.get("/api/users/me", headers=john)).status_code == 401
    assert (await login(client, "john", "a new password")).status_code == 401

    users = (await client.get("/api/users", headers=admin)).json()
    assert {u["username"] for u in users} >= {"root", "john"}
