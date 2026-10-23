"""A fake server for the client's unit tests"""

import datetime
import json
from collections.abc import Callable
from uuid import uuid7

import httpx2 as httpx
from pangloss_models import initialise
from pangloss_models.model_bases.entity import Entity
from pangloss_sdk import client as sdk_client
from pangloss_sdk.settings import SdkSettings


def make_models():
    class Person(Entity):
        pass

    initialise()
    return Person


def head_json(id=None, label="Ada", version=1) -> dict:
    return {
        "type": "Person",
        "id": str(id or uuid7()),
        "label": label,
        "urls": [],
        "meta": {
            "createdBy": "john",
            "createdWhen": datetime.datetime(2026, 1, 1).isoformat(),
            "updatedBy": None,
            "updatedWhen": None,
            "version": version,
        },
    }


def reference_json(id=None, label="Ada") -> dict:
    return {"type": "Person", "id": str(id or uuid7()), "label": label}


class FakeServer:
    """Records requests; answers with what `answer` returns (a status and a body)"""

    def __init__(self, answer: Callable | None = None, password="secret"):
        self.requests: list[httpx.Request] = []
        self.answer = answer or (lambda request: (200, {}))
        self.password = password
        self.revoked: list[str] = []
        self.logins = 0
        self.refreshes = 0
        self.valid_tokens: set[str] = set()
        self.valid_refresh: set[str] = set()

    def issue(self) -> dict:
        n = len(self.valid_tokens) + 1
        access, refresh = f"access-{n}", f"refresh-{n}"
        self.valid_tokens.add(access)
        self.valid_refresh.add(refresh)
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": 1800}

    def expire_access_tokens(self) -> None:
        self.valid_tokens.clear()

    def _respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/api/users/token":
            self.logins += 1
            form = dict(item.split("=") for item in request.content.decode().split("&"))
            if form.get("password") != self.password:
                return httpx.Response(401, json={"detail": "Incorrect username or password"})
            return httpx.Response(200, json=self.issue())
        if path == "/api/users/token/refresh":
            self.refreshes += 1
            token = json.loads(request.content)["refresh_token"]
            if token not in self.valid_refresh:
                return httpx.Response(401, json={"detail": "Invalid or expired token"})
            access = f"access-r{self.refreshes}"
            self.valid_tokens.add(access)
            return httpx.Response(200, json={"access_token": access, "token_type": "bearer", "expires_in": 1800})
        if path == "/api/users/token/revoke":
            self.revoked.append(json.loads(request.content)["refresh_token"])
            self.valid_refresh.discard(json.loads(request.content)["refresh_token"])
            return httpx.Response(204)
        if path == "/api/users/me":
            header = request.headers.get("authorization", "")
            token = header.removeprefix("Bearer ")
            if token not in self.valid_tokens:
                return httpx.Response(401, json={"detail": "Not logged in"})
            return httpx.Response(200, json={"username": "ada"})
        header = request.headers.get("authorization")
        if header is not None and header.removeprefix("Bearer ") not in self.valid_tokens:
            return httpx.Response(401, json={"detail": "Invalid or expired token"})
        status, body = self.answer(request)
        return httpx.Response(status, json=body)

    def async_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._respond)

    sync_transport = async_transport


def settings(**values) -> SdkSettings:
    return SdkSettings(
        URL="http://pangloss.test",  # type: ignore[arg-type]
        INSTALLED_APPS=[],
        **values,
    )


def async_client(server: FakeServer, prompt=None, **values) -> sdk_client.AsyncClient:
    client = sdk_client.AsyncClient(settings(**values), server.async_transport(), prompt)
    sdk_client.install(client)
    return client


def sync_client(server: FakeServer, prompt=None, **values) -> sdk_client.Client:
    client = sdk_client.Client(settings(**values), server.sync_transport(), prompt)
    sdk_client.install(client)
    return client
